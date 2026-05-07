"""
Scenario definitions that orchestrate correlated data injection
across BigQuery, Zendesk, and PostHog.
"""

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from generators.bigquery_gen import BigQueryGenerator
from generators.zendesk_gen import ZendeskGenerator
from generators.posthog_gen import PostHogGenerator

STATE_FILE = Path(__file__).parent / ".test_state.json"
IST = timezone(timedelta(hours=5, minutes=30))

SCENARIO_INFO = {
    "application_drop": {
        "name": "Application Form Broken",
        "description": "Simulates application form failures causing a drop in completed applications, with correlated form error web events and support tickets.",
        "sentinel_tests": ["metric anomaly (application count drop)", "support-theme (form errors)", "RCA cross-source (web_events + tickets)"],
    },
    "payment_failures": {
        "name": "Payment Gateway Down",
        "description": "Simulates a payment gateway outage causing premium payment failures, with correlated support tickets about payment issues.",
        "sentinel_tests": ["metric anomaly (payment failure spike)", "support-theme (payment complaints)", "cross-metric correlation (revenue dip)"],
    },
    "kyc_delays": {
        "name": "KYC Verification Bottleneck",
        "description": "Simulates KYC vendor degradation causing verifications to stall, blocking applications and generating support complaints.",
        "sentinel_tests": ["metric anomaly (KYC completion rate drop)", "funnel anomaly (approval rate drop)", "support-theme (KYC delays)"],
    },
    "regional_outage": {
        "name": "Regional Outage",
        "description": "Simulates a specific city going dark — no new quotes or applications, only landing page views, with regional support complaints.",
        "sentinel_tests": ["segment anomaly (city-level drop)", "RCA segment_metric_by_dimension tool", "geographic correlation"],
    },
}


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"runs": []}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def list_scenarios():
    print("\nAvailable scenarios:\n")
    for key, info in SCENARIO_INFO.items():
        print(f"  {key}")
        print(f"    {info['name']}: {info['description']}")
        print(f"    Tests: {', '.join(info['sentinel_tests'])}")
        print()


def run_scenario(scenario_key: str, skip_posthog: bool = False, skip_zendesk: bool = False, skip_bigquery: bool = False) -> dict:
    if scenario_key not in SCENARIO_INFO:
        print(f"Unknown scenario: {scenario_key}")
        print(f"Available: {', '.join(SCENARIO_INFO.keys())}")
        return {}

    info = SCENARIO_INFO[scenario_key]
    sentinel_run_id = str(uuid.uuid4())
    print(f"\n{'='*60}")
    print(f"Running scenario: {info['name']}")
    print(f"  sentinel_run_id: {sentinel_run_id}")
    print(f"{'='*60}")

    bq_result: dict = {}
    cust_ids: list[str] = []
    customers: list[dict] = []
    ticket_ids: list[int] = []
    posthog_result: dict = {}

    # Step 1: BigQuery
    if not skip_bigquery:
        bq = BigQueryGenerator()
        print(f"\n[1/3] Injecting BigQuery anomaly data...")
        inject_fn = {
            "application_drop": bq.inject_application_drop,
            "payment_failures": bq.inject_payment_failures,
            "kyc_delays": bq.inject_kyc_delays,
            "regional_outage": bq.inject_regional_outage,
        }[scenario_key]
        bq_result = inject_fn()
        cust_ids = bq_result.get("customer_ids", [])

        from generators.bigquery_gen import _get_client, BQ_PROJECT, BQ_DATASET
        client = _get_client()
        if cust_ids:
            id_list = ", ".join(f"'{c}'" for c in cust_ids[:10])
            query = f"SELECT customer_id, full_name, email, city FROM `{BQ_PROJECT}.{BQ_DATASET}.customers` WHERE customer_id IN ({id_list}) LIMIT 10"
            rows = list(client.query(query).result())
            customers = [dict(r) for r in rows]
        else:
            customers = [{"full_name": "Test User", "email": "test@example.com", "customer_id": str(uuid.uuid4()), "city": "Mumbai"}]
    else:
        print(f"\n[1/3] Skipping BigQuery (--skip-bigquery)")
        customers = [
            {"customer_id": str(uuid.uuid4()), "full_name": f"Test User {i}", "email": f"test{i}@example.com", "city": random.choice(["Mumbai", "Delhi NCR", "Bangalore"])}
            for i in range(15)
        ]
        cust_ids = [c["customer_id"] for c in customers]

    # Step 2: Zendesk
    if not skip_zendesk:
        zd = ZendeskGenerator()
        print(f"\n[2/3] Creating Zendesk tickets...")
        city_override = bq_result.get("target_city")
        ticket_ids = zd.create_scenario_tickets(scenario_key, customers, city_override=city_override)
    else:
        print(f"\n[2/3] Skipping Zendesk (--skip-zendesk)")

    # Step 3: PostHog
    if not skip_posthog:
        ph = PostHogGenerator()
        print(f"\n[3/3] Pushing PostHog events...")
        window_start = datetime.fromisoformat(bq_result["window_start"]) if bq_result.get("window_start") else datetime.now(IST) - timedelta(hours=6)
        window_end = datetime.fromisoformat(bq_result["window_end"]) if bq_result.get("window_end") else datetime.now(IST)

        ph_inject_fn = {
            "application_drop": ph.inject_application_drop,
            "payment_failures": ph.inject_payment_failures,
            "kyc_delays": ph.inject_kyc_delays,
            "regional_outage": lambda customers, sentinel_run_id, window_start, window_end: ph.inject_regional_outage(
                customers, sentinel_run_id, window_start, window_end, target_city=bq_result.get("target_city", "Mumbai")
            ),
        }[scenario_key]
        posthog_result = ph_inject_fn(
            customers=customers,
            sentinel_run_id=sentinel_run_id,
            window_start=window_start,
            window_end=window_end,
        )
    else:
        print(f"\n[3/3] Skipping PostHog (--skip-posthog)")

    state = _load_state()
    run_record = {
        "scenario": scenario_key,
        "sentinel_run_id": sentinel_run_id,
        "bq_customer_ids": cust_ids,
        "zendesk_ticket_ids": ticket_ids,
        "posthog_events": posthog_result.get("posthog_events", 0),
        "window_start": bq_result.get("window_start"),
        "window_end": bq_result.get("window_end"),
        "extra": {k: v for k, v in bq_result.items() if k not in ("customer_ids", "window_start", "window_end", "scenario")},
    }
    state["runs"].append(run_record)
    _save_state(state)

    print(f"\n{'='*60}")
    print(f"Scenario '{info['name']}' complete!")
    print(f"  Run ID:   {sentinel_run_id}")
    print(f"  BigQuery: {len(cust_ids)} affected customers")
    print(f"  Zendesk:  {len(ticket_ids)} tickets created")
    print(f"  PostHog:  {posthog_result.get('posthog_events', 0)} events pushed")
    print(f"  Window:   {bq_result.get('window_start')} to {bq_result.get('window_end')}")
    if bq_result.get("target_city"):
        print(f"  Region:   {bq_result['target_city']}")
    if bq_result.get("target_vendor"):
        print(f"  Vendor:   {bq_result['target_vendor']}")
    print(f"\nSentinel should detect:")
    for test in info["sentinel_tests"]:
        print(f"  - {test}")
    print(f"{'='*60}\n")

    return run_record


def run_random(count: int = 1, **kwargs) -> list[dict]:
    keys = list(SCENARIO_INFO.keys())
    selected = random.sample(keys, min(count, len(keys)))
    results = []
    for key in selected:
        results.append(run_scenario(key, **kwargs))
    return results


def cleanup_all():
    state = _load_state()
    runs = state.get("runs", [])
    if not runs:
        print("No test data to clean up.")
        return

    all_customer_ids = []
    all_ticket_ids = []
    for run in runs:
        all_customer_ids.extend(run.get("bq_customer_ids", []))
        all_ticket_ids.extend(run.get("zendesk_ticket_ids", []))

    unique_customer_ids = list(set(all_customer_ids))
    print(f"\nCleaning up {len(unique_customer_ids)} customers from BigQuery, {len(all_ticket_ids)} Zendesk tickets...")

    if unique_customer_ids:
        print("\n[1/2] Cleaning BigQuery...")
        bq = BigQueryGenerator()
        bq.cleanup(unique_customer_ids)

    if all_ticket_ids:
        print("\n[2/2] Cleaning Zendesk...")
        zd = ZendeskGenerator()
        zd.cleanup()

    state["runs"] = []
    _save_state(state)
    print("\nCleanup complete!")
