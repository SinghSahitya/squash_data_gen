"""
Normal traffic generator — pushes healthy baseline data across BigQuery,
PostHog, and Zendesk that mimics a real product's daily activity.

This is the "boring" data that lets Sentinel learn what normal looks like,
so that anomaly scenarios actually stand out.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from generators.bigquery_gen import BigQueryGenerator, _gen_customer, _uid, _rand_ts, EVENT_NAMES, PRODUCTS, DEVICES, CHANNELS, PAYMENT_MODES, KYC_VENDORS, KYC_TYPES, IST
from generators.posthog_gen import PostHogGenerator
from generators.zendesk_gen import ZendeskGenerator
from content_gen import generate_customers, generate_routine_ticket

# Healthy funnel conversion rates (approximate)
# landing_view → calculator_started → quote_generated → application_started →
# application_personal → application_health → application_nominee →
# kyc_started → kyc_completed → income_uploaded → payment_page_view → payment_completed
_STEP_PASS_RATES = [1.0, 0.65, 0.55, 0.40, 0.85, 0.80, 0.90, 0.75, 0.85, 0.80, 0.70, 0.85]


def _simulate_funnel_depth(rates: list[float] = _STEP_PASS_RATES) -> int:
    """Return how many funnel steps a user completes (1-based index)."""
    for i, rate in enumerate(rates):
        if random.random() > rate:
            return i
    return len(rates)


class TrafficGenerator:
    """Generates a batch of normal product traffic across all three data sources."""

    def __init__(self):
        self.bq = BigQueryGenerator()
        self.ph = PostHogGenerator()
        self.zd = ZendeskGenerator()

    def run(self, customer_count: int = 20, window_hours: int = 4) -> dict:
        """
        Generate one batch of healthy traffic.

        Args:
            customer_count: Number of users in this batch (10-50 typical)
            window_hours: How far back to spread events (2-6 typical)

        Returns summary dict.
        """
        sentinel_run_id = str(uuid.uuid4())
        now = datetime.now(IST)
        window_start = now - timedelta(hours=window_hours)

        # Generate customers (LLM-varied if available)
        llm_customers = generate_customers(count=customer_count)
        customers = []
        for i, lc in enumerate(llm_customers):
            base = _gen_customer(city=lc.get("city"))
            base["full_name"] = lc.get("full_name", base["full_name"])
            base["email"] = lc.get("email", base["email"])
            base["age"] = lc.get("age", base["age"])
            base["gender"] = lc.get("gender", base["gender"])
            base["acquired_at"] = _rand_ts(now - timedelta(days=60), window_start).isoformat()
            customers.append(base)

        # ── BigQuery: customers + funnel data ──
        self.bq._insert_rows("customers", customers)

        applications = []
        web_events = []
        payments = []
        kyc_rows = []

        for c in customers:
            depth = _simulate_funnel_depth()
            session_id = _uid()

            for step_idx in range(depth):
                event_name = EVENT_NAMES[step_idx]
                ts = _rand_ts(window_start, now)
                web_events.append({
                    "event_id": _uid(),
                    "session_id": session_id,
                    "customer_id": c["customer_id"],
                    "event_name": event_name,
                    "page_path": f"/{event_name.replace('_', '-')}",
                    "device": random.choice(DEVICES),
                    "city": c["city"],
                    "channel": random.choice(CHANNELS),
                    "product_code": random.choice(PRODUCTS),
                    "event_time": ts.isoformat(),
                })

            # If they got past application_started (step 4+), create an application
            if depth >= 4:
                completed = depth >= len(EVENT_NAMES)
                stage_map = ["started", "personal_done", "health_done", "nominee_done", "kyc_started", "kyc_done", "income_done", "payment_done"]
                current_stage = stage_map[min(depth - 4, len(stage_map) - 1)]
                app_ts = _rand_ts(window_start, now)
                applications.append({
                    "application_id": _uid(),
                    "quote_id": _uid(),
                    "customer_id": c["customer_id"],
                    "product_code": random.choice(PRODUCTS),
                    "status": "completed" if completed else random.choice(["in_progress", "in_progress", "abandoned"]),
                    "current_stage": current_stage,
                    "started_at": app_ts.isoformat(),
                    "completed_at": (app_ts + timedelta(minutes=random.randint(5, 40))).isoformat() if completed else None,
                    "device": random.choice(DEVICES),
                    "variant_calc_v2": random.choice(["control", "variant_a"]),
                    "variant_kyc_video": random.choice(["control", "variant_b"]),
                    "dropped_off_stage": None if completed else current_stage,
                })

            # If they reached kyc_started (step 8+)
            if depth >= 8:
                kyc_ts = _rand_ts(window_start, now)
                kyc_rows.append({
                    "kyc_id": _uid(),
                    "customer_id": c["customer_id"],
                    "application_id": _uid(),
                    "vendor": random.choice(KYC_VENDORS),
                    "kyc_type": random.choice(KYC_TYPES),
                    "attempt_no": 1,
                    "started_at": kyc_ts.isoformat(),
                    "completed_at": (kyc_ts + timedelta(seconds=random.randint(30, 300))).isoformat() if depth >= 9 else None,
                    "status": "passed" if depth >= 9 else "pending",
                    "reject_reason": None,
                    "processing_seconds": random.randint(30, 300),
                })

            # If they reached payment_completed (step 12)
            if depth >= 12:
                pay_ts = _rand_ts(window_start, now)
                payments.append({
                    "payment_id": _uid(),
                    "policy_id": _uid(),
                    "customer_id": c["customer_id"],
                    "amount_inr": random.choice([8000, 12000, 15000, 25000, 35000, 50000]),
                    "payment_mode": random.choice(PAYMENT_MODES),
                    "frequency": random.choice(["monthly", "annual", "semi_annual", "quarterly"]),
                    "is_first_premium": True,
                    "status": "success",
                    "failure_reason": None,
                    "attempted_at": pay_ts.isoformat(),
                    "settled_at": (pay_ts + timedelta(seconds=random.randint(5, 60))).isoformat(),
                })

        if web_events:
            self.bq._insert_rows("web_events", web_events)
        if applications:
            self.bq._insert_rows("applications", applications)
        if kyc_rows:
            self.bq._insert_rows("kyc_verifications", kyc_rows)
        if payments:
            self.bq._insert_rows("premium_payments", payments)

        # ── PostHog: same events mirrored ──
        ph_count = 0
        if self.ph.enabled:
            for c in customers:
                depth = _simulate_funnel_depth()
                session_id = str(uuid.uuid4())
                for step_idx in range(depth):
                    event_name = EVENT_NAMES[step_idx]
                    ts = _rand_ts(window_start, now)
                    self.ph._queue(self.ph._make_event(
                        event=event_name,
                        distinct_id=c["customer_id"],
                        timestamp=ts,
                        session_id=session_id,
                        sentinel_run_id=sentinel_run_id,
                        scenario="normal_traffic",
                        properties={"city": c["city"]},
                    ))
                    ph_count += 1
            self.ph._flush()

        # ── Zendesk: 0-3 routine tickets ──
        ticket_ids = []
        if self.zd.enabled:
            routine_count = random.randint(0, 3)
            for c in random.sample(customers, min(routine_count, len(customers))):
                ticket_data = generate_routine_ticket(c["full_name"], c["city"])
                if ticket_data:
                    tid = self.zd._create_ticket(
                        subject=ticket_data["subject"],
                        body=ticket_data["body"],
                        requester_name=c["full_name"],
                        requester_email=c["email"],
                        tags=["sentinel_test", "normal_traffic"],
                    )
                    if tid:
                        ticket_ids.append(tid)

        summary = {
            "mode": "traffic",
            "sentinel_run_id": sentinel_run_id,
            "customers": len(customers),
            "web_events": len(web_events),
            "applications": len(applications),
            "kyc_verifications": len(kyc_rows),
            "payments": len(payments),
            "posthog_events": ph_count,
            "zendesk_tickets": len(ticket_ids),
            "window": f"{window_start.isoformat()} → {now.isoformat()}",
        }

        print(f"\n  [traffic] Run complete: {summary['customers']} customers, "
              f"{summary['web_events']} BQ events, {summary['posthog_events']} PH events, "
              f"{summary['zendesk_tickets']} tickets, {summary['applications']} apps, "
              f"{summary['payments']} payments")

        return summary
