# Sentinel Test Data Generator — Expanded Use Cases

> Deep-dive into what this system tests, what's missing, and where it should go.

---

## 1. What Sentinel Is Actually Being Trained to Detect

The current 4 scenarios each test a **different class of detection** — not the same anomaly from different angles, but genuinely different reasoning capabilities:

| Scenario | Detection Class | What Sentinel Must Do |
|---|---|---|
| `application_drop` | **Metric anomaly + theme clustering** | See `form_error` spikes in BQ `web_events`, correlate with Zendesk ticket surge on same theme, cross-source RCA |
| `payment_failures` | **Spike detection + revenue correlation** | Detect payment failure rate jump from ~5% baseline to 70–80%, correlate with support volume |
| `kyc_delays` | **Funnel stall detection** | Detect that `kyc_started → kyc_completed` conversion dropped, pinpoint specific vendor (Hyperverge/IDfy/etc) |
| `regional_outage` | **Dimensional segmentation** | Detect city-level drop, zero funnel progression from one city, dead clicks in PostHog, geographic RCA |

Each scenario is designed to exercise a specific Sentinel tool or reasoning path, not just trigger a generic alert.

---

## 2. Gaps in Current Coverage

The codebase has **no scenarios for these real incident classes**:

### 🔴 Slow Degradation (vs. sudden spike)
Everything currently is binary: works → broken instantly. Real incidents degrade gradually:
- KYC processing time creeps from 3h → 8h → 24h over days
- Payment failure rate goes 5% → 12% → 35% over a week
- Sentinel needs to detect drift, not just cliffs. `traffic_gen.py` cannot produce this pattern today.

### 🔴 Silent Failures
Events that look successful in PostHog/BQ but generate support tickets days later:
- Policy issued but wrong nominee name
- Premium debited but policy not activated
- Application marked `completed` in DB but stuck in underwriting queue

### 🔴 Correlated Multi-Source Without Single Root Cause
All current scenarios have one clean cause. Real incidents are messier:
- Payment failures + KYC delays simultaneously during a high-traffic campaign
- Two different cities affected by different issues at the same time

### 🔴 Recovery Detection
After an anomaly fires, the system normalises. Sentinel needs to detect *resolution* too — a `incident_resolved` signal across all 3 sources that confirms the incident window has closed.

### 🔴 Scheduled / Campaign Traffic Spikes
Current normal traffic is flat (10–40 customers, uniform random timestamps). Real products have:
- Morning spike (9–11am IST)
- Post-salary weekend surges
- Post-marketing-email traffic bursts

Sentinel needs to learn these patterns are **not** anomalies, or it will fire false positives.

---

## 3. New Scenarios Worth Building

### `underwriting_delay`
Simulates the underwriting team being overwhelmed or a rule engine failing:
- **BigQuery:** Applications pile up in `status=under_review`, `current_stage=underwriting`, no state transitions for 48–96h
- **PostHog:** Users return to `/apply/status` page repeatedly (polling behaviour, high `page_view` count per session)
- **Zendesk:** "Where is my policy?" tickets, 4–7 days after application completion
- **Sentinel tests:** Funnel time-to-completion anomaly, repeated-visit pattern detection

### `channel_attribution_collapse`
One acquisition channel (e.g. `paid_search`) suddenly stops sending traffic:
- **BigQuery:** `web_events` show zero `channel=paid_search` for a 6h window
- **PostHog:** No sessions with UTM parameters from Google Ads
- **Zendesk:** No correlated tickets (purely a data/tracking issue — no user impact)
- **Sentinel tests:** Dimension-level anomaly detection, silent marketing failure, absence-of-signal detection

### `high_value_customer_churn`
Customers with `income_band=50L+` start abandoning at the payment step:
- **BigQuery:** `payment_page_view` rows exist but zero `payment_completed` for high-income segment
- **PostHog:** Long session times on payment page (users are trying but failing)
- **Zendesk:** Tickets mentioning specific premium amounts (Rs 50,000+)
- **Sentinel tests:** Segment-specific anomaly, revenue impact estimation, cross-metric correlation

### `device_specific_bug`
Application drop only on `mobile_web`, desktop works fine:
- **BigQuery:** `web_events` show `mobile_web` sessions dropping at `application_health` step, desktop conversion unchanged
- **PostHog:** `$dead_click` events on mobile user agents, zero on desktop
- **Zendesk:** Tickets mentioning "mobile app", "phone", "Android", "iPhone"
- **Sentinel tests:** Dimensional RCA (device dimension), partial funnel failure, cross-source device correlation

### `product_specific_outage`
One product code (`ULIP_FW`) is broken, others are fine:
- **BigQuery:** Applications with `product_code=ULIP_FW` all have `status=error`, other products normal
- **PostHog:** Sessions with `product=ULIP_FW` exit at quote step
- **Zendesk:** Tickets explicitly mentioning ULIP plan
- **Sentinel tests:** Attribute-level filtering, product-scoped anomaly, impact radius estimation

---

## 4. Realism Improvements the Codebase Needs

### Traffic shape is too uniform
`traffic_gen.py` spreads events uniformly across a 2–6h window using `_rand_ts()`. Real traffic has intraday shape. Without this, Sentinel can't distinguish "Tuesday 3am low traffic" from an anomaly.

```python
# Suggested: hour-weighted timestamp generation
HOUR_WEIGHTS = {
    8: 0.3,  9: 0.8,  10: 1.0, 11: 0.9,  # Morning peak
    12: 0.6, 13: 0.5, 14: 0.6,            # Afternoon dip
    15: 0.7, 16: 0.8, 17: 1.0,            # Evening peak
    18: 0.9, 19: 0.8, 20: 0.7,            # Post-work
    21: 0.4, 22: 0.2,                     # Late night
}
```

### City distribution is flat
All cities are equally likely in `CITIES`. Real distribution skews heavily toward Mumbai/Delhi NCR/Bangalore. Chandigarh and Mumbai should not have equal probability — this inflates the signal-to-noise ratio for `regional_outage` scenarios.

### Anomaly severity isn't graduated
All anomalies are maximal — 70–80% failure rates, complete city blackouts. Real incidents start at 20% and escalate. `cron_runner.py` already generates a `severity` field from the LLM narrative (`high`/`medium`/`low`) but `bigquery_gen.py` ignores it. The severity should modulate the failure rates:

```python
FAILURE_RATE_BY_SEVERITY = {
    "low":    0.25,
    "medium": 0.50,
    "high":   0.80,
}
```

---

## 5. What This Enables Sentinel to Demo

Once gaps above are filled, this system lets Sentinel demonstrate:

| Demo Statement | Data Required |
|---|---|
| "We detected a payment gateway outage 4 min after it started" | `payment_failures` with gradual severity ramp |
| "We clustered 47 support tickets to a single KYC vendor failure" | `kyc_delays` with vendor-specific ticket language |
| "We identified Bangalore as the only affected city" | `regional_outage` with `city_override` plumbed through |
| "We saw the anomaly resolve at 3:47pm" | Recovery injection run after anomaly scenario |
| "We correlated a 32% revenue drop to a UI bug on mobile" | `device_specific_bug` scenario |
| "We detected this 6 hours before any human noticed" | Slow degradation scenario with gradual ramp |
| "We suppressed a false positive during a campaign spike" | Weighted traffic simulation matching campaign timing |

---

## 6. Operational Expansions

### Regression Suite for Sentinel
`run.py --scenario <name>` is already a clean CLI. Wrapping it in pytest fixtures gives a full regression suite:
1. Inject anomaly
2. Wait N minutes
3. Assert Sentinel fired the right alert with correct metadata
4. Cleanup

Fully automated Sentinel QA that runs on every Sentinel code change.

### Historical Backfill
`_rand_ts()` accepts any time window. Setting it to `now - 90 days` lets you generate 90 days of synthetic history in one run — bootstrapping a fresh Sentinel instance's baseline learning without waiting months for real data to accumulate.

### Multi-Tenant Testing
The `sentinel_run_id` pattern already works for this. Adding a `tenant_id` field to every BQ row and Zendesk ticket lets you run multiple simulated companies in the same dataset, testing Sentinel's ability to keep anomaly scopes isolated per tenant.

### Load Testing Sentinel
Scale `customer_count` in `cron_runner.py` to 500–1000 to generate high-volume data and measure whether Sentinel's detection latency degrades under load. The generator is already architected to handle this (NDJSON batch loads to BQ, PostHog `/batch` API).

### Severity Ladder Testing
Run the same scenario 4 times back-to-back with `severity=low → medium → high → critical` and verify Sentinel's alert thresholds fire at the right level — not too early (false positive) and not too late (missed incident).

---

## 7. Scenario × Detection Capability Matrix

Sentinel detection tools mapped against which scenarios exercise them:

| Sentinel Capability | `app_drop` | `payment_failures` | `kyc_delays` | `regional_outage` | Missing Scenarios |
|---|:---:|:---:|:---:|:---:|---|
| Metric spike detection | ✅ | ✅ | — | — | slow degradation |
| Funnel conversion anomaly | ✅ | — | ✅ | ✅ | underwriting_delay |
| Support theme clustering | ✅ | ✅ | ✅ | ✅ | — |
| Cross-source RCA | ✅ | ✅ | ✅ | ✅ | — |
| Dimensional segmentation | — | — | ✅ (vendor) | ✅ (city) | device_specific_bug, product_specific |
| Absence-of-signal detection | — | — | — | ✅ | channel_attribution_collapse |
| Revenue impact estimation | — | ✅ | — | — | high_value_churn |
| Incident recovery detection | — | — | — | — | **not built yet** |
| Slow drift / trend detection | — | — | — | — | **not built yet** |
