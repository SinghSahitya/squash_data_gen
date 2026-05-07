3# Continuous LLM-Powered Test Data Generation — Plan

## Goal

Run a cron job that continuously pushes **correlated synthetic data** across BigQuery, PostHog, and Zendesk, mimicking a real insurance product (Axis Max Life). Use an LLM to generate varied, realistic content so the data doesn't look templated.

---

## 1. Current State vs Target

| Aspect | Current | Target |
|--------|---------|--------|
| Trigger | Manual CLI (`python run.py --scenario X`) | Cron job (randomized intervals, 3-8 times/day) |
| Content variety | Fixed templates, same 8-10 tickets | LLM generates unique ticket text, event narratives each run |
| Scenario selection | Explicit or random from 4 | Weighted random — mix of normal traffic + occasional anomalies |
| Correlation | Same customer IDs across sources | Same + temporal correlation (ticket appears 20-40 min after funnel drop) |
| Baseline traffic | None — only anomaly data | Background "healthy" traffic so anomalies stand out |

---

## 2. NVIDIA Free API Integration

NVIDIA provides free inference APIs for models like Llama 3.1 70B, Mistral, etc. via `build.nvidia.com`.

### Setup

```bash
# Get free API key from https://build.nvidia.com
NVIDIA_API_KEY=nvapi-xxxxx
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
```

### Usage (OpenAI-compatible endpoint)

```python
import httpx

def llm_generate(prompt: str, system: str = "") -> str:
    resp = httpx.post(
        f"{NVIDIA_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
        json={
            "model": NVIDIA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 500,
        },
        timeout=30.0,
    )
    return resp.json()["choices"][0]["message"]["content"]
```

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│  cron_runner.py  (entry point, runs on schedule)    │
├─────────────────────────────────────────────────────┤
│  1. Decide: normal traffic OR anomaly scenario      │
│     (weighted: 70% normal, 30% anomaly)             │
│  2. Generate correlated "story" for this run        │
│  3. Push to all three sources with realistic delays │
└───────┬─────────────┬────────────────┬──────────────┘
        │             │                │
   BigQuery       PostHog          Zendesk
   (batch load)   (/batch API)     (REST API)
```

### 3.1 Two Modes

**Normal traffic (70% of runs):**
- 5-30 customers complete various funnel stages
- Healthy conversion rates (~3-5% landing → payment)
- 0-2 support tickets (routine questions, not complaints)
- Builds the "baseline" that Sentinel learns from

**Anomaly injection (30% of runs):**
- One of the 4 scenarios (or LLM invents a new one)
- Clear statistical deviation from baseline
- 3-8 correlated support tickets within 20-60 min
- PostHog shows funnel collapse or frustration spike

### 3.2 LLM Responsibilities

| What LLM generates | Why |
|--------------------|----|
| Zendesk ticket subject + body | Varied language, realistic Indian English, different complaint styles |
| Customer names + cities | Culturally accurate, no repetition |
| Scenario narrative (for anomaly runs) | "Payment gateway partner X had a 2-hour outage affecting UPI users in {city}" — coherent story across all sources |
| Event property variations | Realistic device/browser/OS combos, referrer URLs, UTM params |

### 3.3 What Stays Hardcoded (no LLM needed)

- Event names (must match PostHog fingerprint exactly)
- Funnel step ordering
- BigQuery schema/column names
- Numerical distributions (amounts, processing times)
- Conversion rates (controlled to create clear anomaly signals)

---

## 4. Cron Schedule Design

```
# Run baseline traffic 5x/day at varied times (IST)
# Randomized within each window to avoid clockwork patterns
0 9 * * *    python cron_runner.py --mode=traffic   # Morning burst
0 11 * * *   python cron_runner.py --mode=traffic   # Mid-morning
30 14 * * *  python cron_runner.py --mode=traffic   # Afternoon
0 17 * * *   python cron_runner.py --mode=traffic   # Evening
30 20 * * *  python cron_runner.py --mode=traffic   # Night

# Anomaly injection 1-2x/day (randomized, not every day)
0 13 * * 1,3,5  python cron_runner.py --mode=anomaly  # Mon/Wed/Fri afternoon
0 22 * * 2,4    python cron_runner.py --mode=anomaly  # Tue/Thu night
```

Each run internally adds ±30 min jitter so events don't land at exact cron times.

---

## 5. Implementation Tasks

### Phase 1: LLM client + content generation
- [ ] Add `sentinel_test_data/llm_client.py` — NVIDIA API wrapper (OpenAI-compatible)
- [ ] Add `sentinel_test_data/content_gen.py` — prompts for ticket text, customer profiles, scenario narratives
- [ ] Fallback: if LLM API fails, use existing templates (graceful degradation)

### Phase 2: Normal traffic generator
- [ ] Add `sentinel_test_data/generators/traffic_gen.py` — generates healthy baseline data
- [ ] Pushes realistic volumes: ~20-50 customers/run across full funnel
- [ ] Conversion rates: 100% landing → 60% calculator → 30% quote → 15% application → 8% payment
- [ ] Small random noise on all numbers

### Phase 3: Cron runner
- [ ] Add `sentinel_test_data/cron_runner.py` — picks mode, adds jitter, runs scenario
- [ ] Logs each run to `.cron_history.json` for debugging
- [ ] Respects rate limits (PostHog: 1M events/month free = ~33K/day headroom)

### Phase 4: Deployment
- [ ] GitHub Actions cron workflow (`.github/workflows/sentinel-data-gen.yml`)
- [ ] OR: Railway/Render cron job
- [ ] OR: local machine Task Scheduler (Windows) / crontab (Linux)
- [ ] Secrets via GitHub Secrets or `.env` on deploy target

---

## 6. Volume Budget (Free Tier Limits)

| Service | Free Limit | Our Usage (est.) | Headroom |
|---------|-----------|-----------------|----------|
| PostHog | 1M events/month | ~5K events/day = 150K/month | 85% free |
| BigQuery | 10 GB free storage, 1 TB query/month | Negligible (few KB/day) | 99% free |
| Zendesk | Limited by plan (agent seats) | 5-15 tickets/day | Fine for test |
| NVIDIA API | Generous free tier (varies by model) | ~20-30 calls/day | Well within |

---

## 7. Correlation Strategy

Each cron run:
1. Generate a `run_id` (UUID)
2. Generate a batch of customers (same IDs used across all 3 sources)
3. Define a time window (IST, realistic business hours with some night activity)
4. Push events in temporal order:
   - BigQuery web_events: funnel progression over 5-30 min
   - PostHog events: same events, same timestamps, same customer IDs
   - Zendesk tickets: appear 20-60 min AFTER the frustration point (realistic lag)
5. Tag everything with `run_id` for debugging/cleanup

---

## 8. Example LLM Prompts

### Ticket generation prompt:
```
You are generating a realistic support ticket for an Indian insurance company (Axis Max Life).
The customer is experiencing: {scenario_description}
Customer name: {name}, city: {city}, product: {product}

Write a short support ticket (subject + body, 2-4 sentences).
Use natural Indian English. The customer is frustrated but polite.
Do NOT use placeholder text. Make it sound like a real person wrote it.

Return JSON: {"subject": "...", "body": "..."}
```

### Scenario narrative prompt:
```
Generate a brief incident description for an insurance platform anomaly.
Type: {anomaly_type}
Affected: {city/segment/product}

Describe what went wrong in 1-2 sentences (internal ops language).
This will be used to guide correlated test data generation.
```

---

## 9. File Structure (final)

```
sentinel_test_data/
├── .env.example
├── .gitignore
├── config.py                  # env vars (BQ, Zendesk, PostHog, NVIDIA)
├── run.py                     # manual CLI (existing)
├── cron_runner.py             # NEW: scheduled entry point
├── llm_client.py              # NEW: NVIDIA API wrapper
├── content_gen.py             # NEW: LLM-powered content generation
├── scenarios.py               # scenario orchestration (existing, updated)
├── generators/
│   ├── bigquery_gen.py        # existing
│   ├── zendesk_gen.py         # existing
│   ├── posthog_gen.py         # existing (just created)
│   └── traffic_gen.py         # NEW: healthy baseline data
├── CONTINUOUS_DATA_GEN_PLAN.md
└── README.md
```

---

## 10. Deployment Recommendation

**GitHub Actions** is simplest for a repo-hosted cron:

```yaml
name: Sentinel Data Gen
on:
  schedule:
    - cron: '0 3,5,8,11,14 * * *'  # UTC times → IST business hours
  workflow_dispatch: {}  # manual trigger

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install httpx python-dotenv
      - run: python sentinel_test_data/cron_runner.py --mode=auto
        env:
          POSTHOG_PROJECT_API_KEY: ${{ secrets.POSTHOG_PROJECT_API_KEY }}
          POSTHOG_HOST: https://us.posthog.com
          BIGQUERY_PROJECT: ${{ secrets.BIGQUERY_PROJECT }}
          # ... other secrets
          NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}
```

---

*This plan keeps costs at $0 while generating realistic, LLM-varied, correlated data that makes Sentinel's anomaly detection actually useful for demos and testing.*
