# Sentinel Test Data Generator

Generates correlated anomaly data across BigQuery and Zendesk to test Sentinel's anomaly detection, theme clustering, and RCA pipeline end-to-end.

## Setup

```bash
cd sentinel_test_data
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

### Zendesk Trial Setup

1. Sign up at [zendesk.com/register](https://www.zendesk.com/register/) for a 14-day free trial
2. Go to **Admin Center > Apps & Integrations > APIs > Zendesk API**
3. Enable Token Access and create an API token
4. Add your subdomain, email, and token to `.env`

## Usage

```bash
# List available scenarios
python run.py --list

# Run a specific scenario
python run.py --scenario application_drop
python run.py --scenario payment_failures
python run.py --scenario kyc_delays
python run.py --scenario regional_outage

# Run random scenario(s)
python run.py --random
python run.py --random --count 2

# Run all scenarios at once
python run.py --all

# Clean up all injected test data
python run.py --cleanup
```

## Scenarios

| Scenario | What It Simulates | Sentinel Tests |
|---|---|---|
| `application_drop` | Application form breaking (40% drop in completions) | Metric anomaly, support-theme, RCA cross-source |
| `payment_failures` | Payment gateway outage (35% failure spike) | Spike detection, Zendesk theme clustering, cross-metric |
| `kyc_delays` | KYC vendor degradation (48h+ processing) | Funnel anomaly, multi-metric correlation, support-theme |
| `regional_outage` | City going dark (zero conversions from region) | Segment anomaly, dimension RCA, geographic correlation |

## How It Works

Each scenario injects correlated data into **both** BigQuery and Zendesk:

- **BigQuery**: Inserts anomalous rows into relevant tables (applications, payments, KYC, web_events, support_tickets) with timestamps in the recent time window
- **Zendesk**: Creates realistic support tickets with varied phrasing (to test LLM theme clustering), linked to the same customers from BigQuery
- **Correlation**: Same customer IDs, same time window, same issue themes across both systems

## Cleanup

All injected data is tracked in `.test_state.json`. Run `python run.py --cleanup` to:
- Delete all test customer rows from BigQuery (cascades across all tables by customer_id)
- Delete all Zendesk tickets tagged with `sentinel_test`
