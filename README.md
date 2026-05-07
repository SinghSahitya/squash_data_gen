# Sentinel Test Data Generator

Autonomous, LLM-powered synthetic data pipeline that pushes correlated events across **BigQuery**, **PostHog**, and **Zendesk** — mimicking a real insurance product (Axis Max Life) so Sentinel can detect anomalies, cluster support themes, and run RCA across sources.

Runs on a cron via GitHub Actions. Fire and forget.

## Setup

```bash
cd sentinel_test_data
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # Linux/Mac
cp .env.example .env
# Edit .env with your credentials
```

### Required Credentials

| Service | What to set | Where to get it |
|---------|------------|-----------------|
| BigQuery | `BIGQUERY_PROJECT`, `BIGQUERY_KEY_FILE`, `BIGQUERY_DATASET` | GCP Console → Service Account key JSON |
| Zendesk | `ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, `ZENDESK_API_TOKEN` | Admin Center → APIs → Zendesk API → Token Access |
| PostHog | `POSTHOG_HOST`, `POSTHOG_PROJECT_API_KEY` | Project Settings → Project API Key (`phc_...`) |
| NVIDIA LLM | `NVIDIA_API_KEY` | https://build.nvidia.com → Get API Key (`nvapi-...`) |

NVIDIA key is optional — without it, the generator falls back to hardcoded templates (still works, just less varied).

## Usage

### Autonomous (cron — recommended)

```bash
# Auto mode: 70% normal traffic, 30% random anomaly
python cron_runner.py

# Force a specific mode
python cron_runner.py --mode=traffic
python cron_runner.py --mode=anomaly

# Dry run (shows what would happen, no data pushed)
python cron_runner.py --dry-run --no-jitter
```

### Manual (specific scenarios)

```bash
# List available scenarios
python run.py --list

# Run a specific scenario
python run.py --scenario application_drop
python run.py --scenario payment_failures
python run.py --scenario kyc_delays
python run.py --scenario regional_outage

# Source filters
python run.py --scenario payment_failures --posthog-only
python run.py --all --skip-zendesk

# Random
python run.py --random --count 2

# Clean up all injected test data
python run.py --cleanup
```

## How It Works

### Two Modes

**Normal traffic (70%)** — builds Sentinel's baseline:
- 10-40 customers flow through the funnel at healthy conversion rates
- BigQuery: customers, web_events, applications, KYC, payments
- PostHog: same events mirrored with session IDs
- Zendesk: 0-3 routine (non-complaint) tickets

**Anomaly injection (30%)** — creates detectable incidents:
- LLM picks a random scenario + generates a narrative
- Data shows clear statistical deviation (funnel collapse, payment spikes, regional drop)
- 5-10 correlated support tickets appear with varied complaint language
- All three sources tell the same story from different angles

### Correlation

Every run generates a `sentinel_run_id` (UUID) attached to:
- PostHog event properties
- BigQuery rows (same customer IDs + time window)
- Zendesk tickets (same customers, tagged `sentinel_test`)

### LLM (NVIDIA)

When `NVIDIA_API_KEY` is set, the LLM generates:
- Unique Zendesk ticket subjects + bodies (varied tone, natural Indian English)
- Customer profiles (names, cities, demographics)
- Anomaly narratives (what broke, where, severity)

Falls back to hardcoded templates if the API is down or key is missing.

## Scenarios

| Scenario | What It Simulates | Sentinel Should Detect |
|---|---|---|
| `application_drop` | Form/API breaking → abandonment spike | Metric anomaly, support-theme, RCA cross-source |
| `payment_failures` | Payment gateway outage → failed transactions | Spike detection, theme clustering, cross-metric correlation |
| `kyc_delays` | KYC vendor degradation → 48h+ processing | Funnel anomaly, multi-metric correlation |
| `regional_outage` | CDN/infra failure → city goes dark | Segment anomaly, dimension RCA, geographic correlation |

## GitHub Actions (Automated)

The workflow at `.github/workflows/sentinel-data-gen.yml` runs automatically:

- **5x/day**: Normal traffic (09:00, 11:00, 14:30, 17:00, 20:30 IST)
- **3x/week**: Random anomaly (Mon, Wed, Fri)
- **Manual**: Actions tab → "Run workflow" → pick mode

Secrets to configure in GitHub repo settings:
`POSTHOG_PROJECT_API_KEY`, `NVIDIA_API_KEY`, `BIGQUERY_PROJECT`, `BIGQUERY_DATASET`, `BIGQUERY_CREDENTIALS_JSON`, `ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, `ZENDESK_API_TOKEN`

## Cleanup

All injected data is tracked in `.test_state.json`. Run `python run.py --cleanup` to:
- Delete test customer rows from BigQuery (by customer_id across all tables)
- Delete Zendesk tickets tagged with `sentinel_test`
- PostHog: events persist (use a dedicated test project to isolate)
