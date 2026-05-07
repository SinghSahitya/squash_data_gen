"""
PostHog synthetic event generator.
Pushes correlated events via the PostHog Capture /batch API so that
Sentinel's PostHog fetcher (event_count, funnel_conversion, HogQL)
can detect anomalies in sync with BigQuery + Zendesk test data.

Uses the *Project API Key* (phc_...) for ingestion — this is a write-only
key, separate from the Personal API Key used for reading/querying.
"""

import random
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from config import (
    POSTHOG_HOST,
    POSTHOG_PROJECT_API_KEY,
    SENTINEL_TEST_TAG,
)

IST = timezone(timedelta(hours=5, minutes=30))

_BATCH_SIZE = 50
_TIMEOUT = 15.0
_RETRY_ATTEMPTS = 3

EVENT_NAMES = [
    "landing_view",
    "calculator_started",
    "quote_generated",
    "application_started",
    "application_personal",
    "application_health",
    "application_nominee",
    "kyc_started",
    "kyc_completed",
    "income_uploaded",
    "payment_page_view",
    "payment_completed",
]

PAGE_PATHS = {
    "landing_view": "/term-life-insurance",
    "calculator_started": "/calculator",
    "quote_generated": "/quote",
    "application_started": "/apply",
    "application_personal": "/apply/personal",
    "application_health": "/apply/health",
    "application_nominee": "/apply/nominee",
    "kyc_started": "/apply/kyc",
    "kyc_completed": "/apply/kyc/done",
    "income_uploaded": "/apply/income",
    "payment_page_view": "/apply/pay",
    "payment_completed": "/apply/pay/done",
}


def _new_session_id() -> str:
    return str(uuid.uuid4())


def _rand_ts(start: datetime, end: datetime) -> datetime:
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=random.uniform(0, delta))


class PostHogGenerator:
    def __init__(self):
        if not POSTHOG_PROJECT_API_KEY:
            print("[WARN] POSTHOG_PROJECT_API_KEY not set. PostHog events will be skipped.")
            self.enabled = False
            return
        self.host = (POSTHOG_HOST or "https://us.posthog.com").rstrip("/")
        self.api_key = POSTHOG_PROJECT_API_KEY
        self.enabled = True
        self._events_buffer: list[dict] = []

    def _make_event(
        self,
        event: str,
        distinct_id: str,
        timestamp: datetime,
        session_id: str,
        sentinel_run_id: str,
        scenario: str,
        properties: dict | None = None,
    ) -> dict:
        props = {
            "$current_url": f"https://app.example.com{PAGE_PATHS.get(event, '/')}",
            "$pathname": PAGE_PATHS.get(event, "/"),
            "$session_id": session_id,
            "sentinel_run_id": sentinel_run_id,
            "sentinel_test": True,
            "scenario": scenario,
        }
        if properties:
            props.update(properties)
        return {
            "event": event,
            "properties": {
                **props,
                "distinct_id": distinct_id,
                "$lib": "sentinel_test_data",
            },
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "distinct_id": distinct_id,
        }

    def _flush(self):
        if not self._events_buffer:
            return
        batches = [
            self._events_buffer[i:i + _BATCH_SIZE]
            for i in range(0, len(self._events_buffer), _BATCH_SIZE)
        ]
        total_sent = 0
        for batch in batches:
            payload = {
                "api_key": self.api_key,
                "batch": batch,
            }
            for attempt in range(1, _RETRY_ATTEMPTS + 1):
                try:
                    resp = httpx.post(
                        f"{self.host}/batch/",
                        json=payload,
                        timeout=_TIMEOUT,
                    )
                    resp.raise_for_status()
                    total_sent += len(batch)
                    break
                except Exception as e:
                    if attempt == _RETRY_ATTEMPTS:
                        print(f"  [WARN] PostHog /batch failed after {_RETRY_ATTEMPTS} attempts: {e}")
                    else:
                        time.sleep(1 * attempt)
        self._events_buffer = []
        return total_sent

    def _queue(self, event: dict):
        self._events_buffer.append(event)
        if len(self._events_buffer) >= _BATCH_SIZE:
            self._flush()

    # ------------------------------------------------------------------
    # Scenario generators
    # ------------------------------------------------------------------

    def inject_application_drop(
        self,
        customers: list[dict],
        sentinel_run_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict:
        """
        Emit funnel events that show a drop: many early-step events,
        few later-step events. Add $rageclick on /apply pages.
        """
        if not self.enabled:
            return {"posthog_events": 0}

        count = 0
        for c in customers:
            distinct_id = c["customer_id"]
            session_id = _new_session_id()
            city = c.get("city", "Mumbai")

            cutoff_step = random.randint(1, 4)
            for i, event_name in enumerate(EVENT_NAMES[:cutoff_step + 1]):
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event=event_name,
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="application_drop",
                    properties={"city": city},
                ))
                count += 1

            if random.random() < 0.6:
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event="$rageclick",
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="application_drop",
                    properties={"city": city, "$current_url": "https://app.example.com/apply/health"},
                ))
                count += 1

        self._flush()
        print(f"  [OK] PostHog: {count} events for application_drop ({len(customers)} users, early funnel drop + rageclicks)")
        return {"posthog_events": count}

    def inject_payment_failures(
        self,
        customers: list[dict],
        sentinel_run_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict:
        """
        Emit high payment_page_view but very few payment_completed.
        """
        if not self.enabled:
            return {"posthog_events": 0}

        count = 0
        for c in customers:
            distinct_id = c["customer_id"]
            session_id = _new_session_id()
            city = c.get("city", "Mumbai")

            for event_name in EVENT_NAMES[:10]:
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event=event_name,
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="payment_failures",
                    properties={"city": city},
                ))
                count += 1

            ts = _rand_ts(window_start, window_end)
            self._queue(self._make_event(
                event="payment_page_view",
                distinct_id=distinct_id,
                timestamp=ts,
                session_id=session_id,
                sentinel_run_id=sentinel_run_id,
                scenario="payment_failures",
                properties={"city": city},
            ))
            count += 1

            if random.random() < 0.05:
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event="payment_completed",
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="payment_failures",
                    properties={"city": city},
                ))
                count += 1

        self._flush()
        print(f"  [OK] PostHog: {count} events for payment_failures ({len(customers)} users, high page_view / low completed)")
        return {"posthog_events": count}

    def inject_kyc_delays(
        self,
        customers: list[dict],
        sentinel_run_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict:
        """
        Emit many kyc_started but few kyc_completed.
        """
        if not self.enabled:
            return {"posthog_events": 0}

        count = 0
        for c in customers:
            distinct_id = c["customer_id"]
            session_id = _new_session_id()
            city = c.get("city", "Mumbai")

            for event_name in EVENT_NAMES[:8]:
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event=event_name,
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="kyc_delays",
                    properties={"city": city},
                ))
                count += 1

            if random.random() < 0.1:
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event="kyc_completed",
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="kyc_delays",
                    properties={"city": city},
                ))
                count += 1

        self._flush()
        print(f"  [OK] PostHog: {count} events for kyc_delays ({len(customers)} users, many kyc_started / few kyc_completed)")
        return {"posthog_events": count}

    def inject_regional_outage(
        self,
        customers: list[dict],
        sentinel_run_id: str,
        window_start: datetime,
        window_end: datetime,
        target_city: str,
    ) -> dict:
        """
        Emit only landing_view from the target city — no deeper funnel events.
        """
        if not self.enabled:
            return {"posthog_events": 0}

        count = 0
        for c in customers:
            distinct_id = c["customer_id"]
            session_id = _new_session_id()

            for _ in range(random.randint(2, 5)):
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event="landing_view",
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="regional_outage",
                    properties={"city": target_city},
                ))
                count += 1

            if random.random() < 0.4:
                ts = _rand_ts(window_start, window_end)
                self._queue(self._make_event(
                    event="$dead_click",
                    distinct_id=distinct_id,
                    timestamp=ts,
                    session_id=session_id,
                    sentinel_run_id=sentinel_run_id,
                    scenario="regional_outage",
                    properties={"city": target_city, "$current_url": "https://app.example.com/term-life-insurance"},
                ))
                count += 1

        self._flush()
        print(f"  [OK] PostHog: {count} events for regional_outage (city={target_city}, landing-only + dead_clicks)")
        return {"posthog_events": count}
