"""
BigQuery anomaly data generator.
Appends anomalous rows via batch load jobs (NDJSON), avoiding the streaming API.
Cleanup uses DELETE by customer_id (see cleanup()).
"""

import io
import json
import uuid
import random
from datetime import datetime, timedelta, timezone
from google.cloud.bigquery import Client, LoadJobConfig, SourceFormat, WriteDisposition
from config import BQ_PROJECT, BQ_KEY_FILE, BQ_DATASET

IST = timezone(timedelta(hours=5, minutes=30))

CITIES = [
    "Mumbai", "Delhi NCR", "Bangalore", "Chennai", "Kolkata",
    "Pune", "Ahmedabad", "Hyderabad", "Lucknow", "Surat",
    "Noida", "Gurugram", "Indore", "Nagpur", "Bhopal", "Chandigarh",
]
STATES = {
    "Mumbai": "Maharashtra", "Delhi NCR": "Delhi", "Bangalore": "Karnataka",
    "Chennai": "Tamil Nadu", "Kolkata": "West Bengal", "Pune": "Maharashtra",
    "Ahmedabad": "Gujarat", "Hyderabad": "Telangana", "Lucknow": "Uttar Pradesh",
    "Surat": "Gujarat", "Noida": "Uttar Pradesh", "Gurugram": "Haryana",
    "Indore": "Madhya Pradesh", "Nagpur": "Maharashtra", "Bhopal": "Madhya Pradesh",
    "Chandigarh": "Chandigarh",
}
PRODUCTS = ["TERM_SAVE", "ULIP_FW", "TERM_SMART", "CHILD_SF", "RETIRE_ETERNAL", "SAVINGS_GUAR", "SAVINGS_SE", "ULIP_PLAT"]
DEVICES = ["mobile_web", "desktop"]
CHANNELS = ["organic_search", "paid_search", "direct", "paid_social", "affiliate", "referral", "email", "aggregator"]
PAYMENT_MODES = ["upi", "netbanking", "debit_card", "credit_card", "nach_auto_debit"]
KYC_VENDORS = ["Karza", "Hyperverge", "IDfy", "Signzy"]
KYC_TYPES = ["aadhaar_offline", "aadhaar_otp"]
KYC_REJECT_REASONS = ["face_mismatch", "low_quality_image", "address_mismatch", "otp_failed", "document_expired", "vendor_timeout", "name_mismatch"]
SUPPORT_CHANNELS = ["chat", "phone", "email", "whatsapp"]
PAGE_PATHS = ["/term-life-insurance", "/calculator", "/quote", "/apply", "/apply/personal", "/apply/health", "/apply/nominee", "/apply/kyc", "/apply/kyc/done", "/apply/income", "/apply/pay", "/apply/pay/done"]
EVENT_NAMES = ["landing_view", "calculator_started", "quote_generated", "application_started", "application_personal", "application_health", "application_nominee", "kyc_started", "kyc_completed", "income_uploaded", "payment_page_view", "payment_completed"]

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Sai", "Reyansh", "Arjun", "Vihaan", "Krishna", "Ishaan", "Karthik",
               "Priya", "Ananya", "Diya", "Meera", "Tanvi", "Neha", "Pooja", "Riya", "Kavitha", "Shreya"]
LAST_NAMES = ["Sharma", "Gupta", "Patel", "Reddy", "Kumar", "Singh", "Pillai", "Iyer", "Bansal", "Pandey",
              "Mehta", "Verma", "Joshi", "Kapoor", "Nair", "Das", "Rao", "Chatterjee", "Malhotra", "Bhat"]
EMAIL_DOMAINS = ["gmail.com", "outlook.com", "rediffmail.com", "yahoo.co.in"]


def _get_client() -> Client:
    return Client(project=BQ_PROJECT, credentials=_load_credentials())


def _load_credentials():
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(BQ_KEY_FILE)


def _table(name: str) -> str:
    return f"{BQ_PROJECT}.{BQ_DATASET}.{name}"


def _uid() -> str:
    return str(uuid.uuid4())


def _rand_ts(start: datetime, end: datetime) -> datetime:
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=random.uniform(0, delta))


def _gen_customer(city: str | None = None) -> dict:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    c = city or random.choice(CITIES)
    return {
        "customer_id": _uid(),
        "full_name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}{random.randint(100,9999)}@{random.choice(EMAIL_DOMAINS)}",
        "phone": f"+91{random.randint(7000000000, 9999999999)}",
        "gender": random.choice(["M", "F"]),
        "age": random.randint(22, 58),
        "city": c,
        "state": STATES.get(c, "Maharashtra"),
        "city_tier": random.choice([1, 1, 2, 2, 3]),
        "income_band": random.choice(["3L-5L", "5L-10L", "10L-20L", "20L-50L", "50L+"]),
        "declared_annual_income_inr": random.choice([400000, 700000, 1200000, 2500000, 6000000]),
        "occupation": random.choice(["salaried", "self_employed", "professional", "business"]),
        "acquisition_channel": random.choice(CHANNELS),
        "acquired_at": None,  # set by caller
        "first_device": random.choice(DEVICES),
        "is_d2c": random.choice([True, False]),
    }


class BigQueryGenerator:
    def __init__(self):
        self.client = _get_client()
        self._inserted_tables: dict[str, list[str]] = {}

    def _insert_rows(self, table_name: str, rows: list[dict]):
        """Append rows via a batch load job (NDJSON file), not streaming or DML."""
        if not rows:
            return
        table_ref = _table(table_name)
        buf = io.BytesIO()
        for row in rows:
            buf.write(json.dumps(row, default=str, ensure_ascii=False).encode("utf-8"))
            buf.write(b"\n")
        buf.seek(0)
        job_config = LoadJobConfig(
            source_format=SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=WriteDisposition.WRITE_APPEND,
        )
        try:
            load_job = self.client.load_table_from_file(
                buf,
                table_ref,
                job_config=job_config,
            )
            load_job.result()
            out_rows = load_job.output_rows
            if out_rows is None:
                out_rows = len(rows)
            print(f"  [OK] Loaded {out_rows} rows into {table_name} (job {load_job.job_id})")
        except Exception as e:
            print(f"  [WARN] BigQuery load job failed for {table_name}: {e}")
            if hasattr(e, "errors") and e.errors:
                for err in e.errors[:3]:
                    print(f"    {err}")

    # ── Scenario A: Application Form Broken ─────────────────────────

    def inject_application_drop(self, window_hours: int = 6) -> dict:
        """
        Simulates an application form breaking:
        - Failed/abandoned applications spike
        - web_events show form_error events on /apply pages
        - support_tickets with application_error category
        Returns context dict with customer_ids for Zendesk correlation.
        """
        now = datetime.now(IST)
        window_start = now - timedelta(hours=window_hours)
        customer_ids = []

        customers = [_gen_customer() for _ in range(25)]
        for c in customers:
            c["acquired_at"] = _rand_ts(now - timedelta(days=30), window_start).isoformat()
        self._insert_rows("customers", customers)

        applications = []
        for c in customers:
            customer_ids.append(c["customer_id"])
            app = {
                "application_id": _uid(),
                "quote_id": _uid(),
                "customer_id": c["customer_id"],
                "product_code": random.choice(PRODUCTS),
                "status": "abandoned",
                "current_stage": random.choice(["started", "personal_done", "health_done"]),
                "started_at": _rand_ts(window_start, now).isoformat(),
                "completed_at": None,
                "device": random.choice(DEVICES),
                "variant_calc_v2": random.choice(["control", "variant_a"]),
                "variant_kyc_video": random.choice(["control", "variant_b"]),
                "dropped_off_stage": random.choice(["personal_done", "health_done", "started"]),
            }
            applications.append(app)
        self._insert_rows("applications", applications)

        web_events = []
        error_pages = ["/apply", "/apply/personal", "/apply/health"]
        for c in customers:
            for _ in range(random.randint(2, 5)):
                page = random.choice(error_pages)
                web_events.append({
                    "event_id": _uid(),
                    "session_id": _uid(),
                    "customer_id": c["customer_id"],
                    "event_name": "application_started",
                    "page_path": page,
                    "device": random.choice(DEVICES),
                    "city": c["city"],
                    "channel": random.choice(CHANNELS),
                    "product_code": random.choice(PRODUCTS),
                    "event_time": _rand_ts(window_start, now).isoformat(),
                })
        self._insert_rows("web_events", web_events)

        tickets = []
        ticket_customers = random.sample(customers, min(8, len(customers)))
        for c in ticket_customers:
            tickets.append({
                "ticket_id": _uid(),
                "customer_id": c["customer_id"],
                "policy_id": None,
                "category": "application_error",
                "funnel_stage": "application",
                "channel": random.choice(SUPPORT_CHANNELS),
                "status": "open",
                "csat_score": None,
                "opened_at": _rand_ts(window_start, now).isoformat(),
                "closed_at": None,
            })
        self._insert_rows("support_tickets", tickets)

        print(f"\n  Scenario A injected: {len(applications)} abandoned apps, {len(web_events)} error events, {len(tickets)} support tickets")
        return {
            "scenario": "application_drop",
            "customer_ids": customer_ids,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "ticket_customers": [c["customer_id"] for c in ticket_customers],
        }

    # ── Scenario B: Payment Gateway Down ────────────────────────────

    def inject_payment_failures(self, window_hours: int = 6) -> dict:
        """
        Simulates a payment gateway outage:
        - Spike in failed premium_payments with gateway_timeout reason
        - support_tickets about payment issues
        """
        now = datetime.now(IST)
        window_start = now - timedelta(hours=window_hours)
        customer_ids = []

        customers = [_gen_customer() for _ in range(20)]
        for c in customers:
            c["acquired_at"] = _rand_ts(now - timedelta(days=60), window_start).isoformat()
        self._insert_rows("customers", customers)

        payments = []
        for c in customers:
            customer_ids.append(c["customer_id"])
            for _ in range(random.randint(1, 3)):
                payments.append({
                    "payment_id": _uid(),
                    "policy_id": _uid(),
                    "customer_id": c["customer_id"],
                    "amount_inr": random.choice([8000, 12000, 15000, 25000, 50000]),
                    "payment_mode": random.choice(PAYMENT_MODES),
                    "frequency": random.choice(["monthly", "annual", "semi_annual", "quarterly"]),
                    "is_first_premium": random.choice([True, False]),
                    "status": "failed",
                    "failure_reason": random.choice(["bank_unavailable", "bank_unavailable", "bank_unavailable", "other"]),
                    "attempted_at": _rand_ts(window_start, now).isoformat(),
                    "settled_at": None,
                })
        self._insert_rows("premium_payments", payments)

        web_events = []
        for c in random.sample(customers, min(12, len(customers))):
            web_events.append({
                "event_id": _uid(),
                "session_id": _uid(),
                "customer_id": c["customer_id"],
                "event_name": "payment_page_view",
                "page_path": "/apply/pay",
                "device": random.choice(DEVICES),
                "city": c["city"],
                "channel": random.choice(CHANNELS),
                "product_code": random.choice(PRODUCTS),
                "event_time": _rand_ts(window_start, now).isoformat(),
            })
        self._insert_rows("web_events", web_events)

        tickets = []
        ticket_customers = random.sample(customers, min(10, len(customers)))
        for c in ticket_customers:
            tickets.append({
                "ticket_id": _uid(),
                "customer_id": c["customer_id"],
                "policy_id": None,
                "category": "general",
                "funnel_stage": "any",
                "channel": random.choice(SUPPORT_CHANNELS),
                "status": "open",
                "csat_score": None,
                "opened_at": _rand_ts(window_start, now).isoformat(),
                "closed_at": None,
            })
        self._insert_rows("support_tickets", tickets)

        print(f"\n  Scenario B injected: {len(payments)} failed payments, {len(web_events)} payment page events, {len(tickets)} support tickets")
        return {
            "scenario": "payment_failures",
            "customer_ids": customer_ids,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "ticket_customers": [c["customer_id"] for c in ticket_customers],
        }

    # ── Scenario C: KYC Verification Bottleneck ─────────────────────

    def inject_kyc_delays(self, window_hours: int = 8) -> dict:
        """
        Simulates KYC vendor degradation:
        - kyc_verifications stuck in pending with high processing_seconds
        - applications stalling at kyc_started stage
        - support_tickets about KYC delays
        """
        now = datetime.now(IST)
        window_start = now - timedelta(hours=window_hours)
        customer_ids = []
        target_vendor = random.choice(KYC_VENDORS)

        customers = [_gen_customer() for _ in range(18)]
        for c in customers:
            c["acquired_at"] = _rand_ts(now - timedelta(days=30), window_start).isoformat()
        self._insert_rows("customers", customers)

        kyc_rows = []
        for c in customers:
            customer_ids.append(c["customer_id"])
            started = _rand_ts(window_start, now - timedelta(hours=1))
            kyc_rows.append({
                "kyc_id": _uid(),
                "customer_id": c["customer_id"],
                "application_id": _uid(),
                "vendor": target_vendor,
                "kyc_type": random.choice(KYC_TYPES),
                "attempt_no": random.randint(1, 3),
                "started_at": started.isoformat(),
                "completed_at": None,
                "status": random.choice(["rejected", "rejected", "rejected", "passed"]),
                "reject_reason": random.choice(KYC_REJECT_REASONS) if random.random() < 0.75 else None,
                "processing_seconds": random.randint(120000, 300000),  # 33-83 hours
            })
        self._insert_rows("kyc_verifications", kyc_rows)

        applications = []
        for c in customers:
            applications.append({
                "application_id": _uid(),
                "quote_id": _uid(),
                "customer_id": c["customer_id"],
                "product_code": random.choice(PRODUCTS),
                "status": "abandoned",
                "current_stage": "kyc_started",
                "started_at": _rand_ts(window_start, now).isoformat(),
                "completed_at": None,
                "device": random.choice(DEVICES),
                "variant_calc_v2": random.choice(["control", "variant_a"]),
                "variant_kyc_video": random.choice(["control", "variant_b"]),
                "dropped_off_stage": "kyc_started",
            })
        self._insert_rows("applications", applications)

        tickets = []
        ticket_customers = random.sample(customers, min(6, len(customers)))
        for c in ticket_customers:
            tickets.append({
                "ticket_id": _uid(),
                "customer_id": c["customer_id"],
                "policy_id": None,
                "category": "kyc_failure",
                "funnel_stage": "kyc",
                "channel": random.choice(SUPPORT_CHANNELS),
                "status": "open",
                "csat_score": None,
                "opened_at": _rand_ts(window_start, now).isoformat(),
                "closed_at": None,
            })
        self._insert_rows("support_tickets", tickets)

        print(f"\n  Scenario C injected: {len(kyc_rows)} stalled KYCs (vendor={target_vendor}), {len(applications)} stuck apps, {len(tickets)} tickets")
        return {
            "scenario": "kyc_delays",
            "customer_ids": customer_ids,
            "target_vendor": target_vendor,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "ticket_customers": [c["customer_id"] for c in ticket_customers],
        }

    # ── Scenario D: Regional Outage ─────────────────────────────────

    def inject_regional_outage(self, window_hours: int = 12) -> dict:
        """
        Simulates a region going dark:
        - Zero new quote_requests and applications from a specific city
        - web_events only show landing_view (no deeper funnel) from that city
        - support_tickets from that region
        """
        now = datetime.now(IST)
        window_start = now - timedelta(hours=window_hours)
        target_city = random.choice(["Mumbai", "Delhi NCR", "Bangalore", "Chennai"])
        customer_ids = []

        customers = [_gen_customer(city=target_city) for _ in range(12)]
        for c in customers:
            c["acquired_at"] = _rand_ts(now - timedelta(days=30), window_start).isoformat()
        self._insert_rows("customers", customers)

        web_events = []
        for c in customers:
            customer_ids.append(c["customer_id"])
            for _ in range(random.randint(3, 7)):
                web_events.append({
                    "event_id": _uid(),
                    "session_id": _uid(),
                    "customer_id": c["customer_id"],
                    "event_name": "landing_view",
                    "page_path": "/term-life-insurance",
                    "device": random.choice(DEVICES),
                    "city": target_city,
                    "channel": random.choice(CHANNELS),
                    "product_code": random.choice(PRODUCTS),
                    "event_time": _rand_ts(window_start, now).isoformat(),
                })
        self._insert_rows("web_events", web_events)

        tickets = []
        ticket_customers = random.sample(customers, min(5, len(customers)))
        for c in ticket_customers:
            tickets.append({
                "ticket_id": _uid(),
                "customer_id": c["customer_id"],
                "policy_id": None,
                "category": "application_error",
                "funnel_stage": "application",
                "channel": random.choice(SUPPORT_CHANNELS),
                "status": "open",
                "csat_score": None,
                "opened_at": _rand_ts(window_start, now).isoformat(),
                "closed_at": None,
            })
        self._insert_rows("support_tickets", tickets)

        print(f"\n  Scenario D injected: regional outage in {target_city}, {len(web_events)} landing-only events, {len(tickets)} tickets")
        return {
            "scenario": "regional_outage",
            "customer_ids": customer_ids,
            "target_city": target_city,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "ticket_customers": [c["customer_id"] for c in ticket_customers],
        }

    # ── Cleanup ─────────────────────────────────────────────────────

    def cleanup(self, customer_ids: list[str]) -> None:
        """Delete all test rows by customer_id across all tables."""
        if not customer_ids:
            print("  No customer_ids to clean up.")
            return

        id_list = ", ".join(f"'{cid}'" for cid in customer_ids)
        tables_with_customer_id = [
            "customers", "applications", "web_events", "premium_payments",
            "kyc_verifications", "quote_requests", "support_tickets",
        ]
        for table in tables_with_customer_id:
            query = f"DELETE FROM `{BQ_PROJECT}.{BQ_DATASET}.{table}` WHERE customer_id IN ({id_list})"
            try:
                job = self.client.query(query)
                job.result()
                print(f"  [OK] Cleaned {table}: {job.num_dml_affected_rows} rows deleted")
            except Exception as e:
                print(f"  [WARN] Failed to clean {table}: {e}")
