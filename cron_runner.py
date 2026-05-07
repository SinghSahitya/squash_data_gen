#!/usr/bin/env python3
"""
Autonomous cron runner for Sentinel test data generation.

Fire this on a schedule and forget. It will:
  - 70% of the time: generate normal baseline traffic
  - 30% of the time: inject a random anomaly scenario
  - Use LLM (NVIDIA) for varied content when available
  - Fall back to templates if LLM is down
  - Add time jitter so events don't look clockwork
  - Log each run to .cron_history.json

Usage:
  python cron_runner.py                  # Auto mode (weighted random)
  python cron_runner.py --mode=traffic   # Force normal traffic
  python cron_runner.py --mode=anomaly   # Force anomaly injection
  python cron_runner.py --dry-run        # Print what would happen, don't push
"""

import argparse
import json
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import POSTHOG_PROJECT_API_KEY, NVIDIA_API_KEY
from content_gen import generate_anomaly_narrative, generate_customers, generate_tickets_batch
from scenarios import run_scenario, SCENARIO_INFO

IST = timezone(timedelta(hours=5, minutes=30))
HISTORY_FILE = Path(__file__).parent / ".cron_history.json"

# Weights: 70% traffic, 30% anomaly
ANOMALY_PROBABILITY = 0.30

# Volume ranges
TRAFFIC_CUSTOMER_RANGE = (10, 40)
ANOMALY_CUSTOMER_RANGE = (12, 25)
JITTER_MINUTES_RANGE = (0, 25)


def _add_jitter():
    """Sleep for a random 0-25 minutes to avoid clockwork patterns."""
    jitter = random.randint(*JITTER_MINUTES_RANGE)
    if jitter > 0:
        print(f"[cron] Adding {jitter}min jitter before run...")
        time.sleep(jitter * 60)


def _log_run(record: dict):
    """Append a run record to .cron_history.json."""
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, ValueError):
            history = []

    # Keep last 200 runs
    history.append(record)
    history = history[-200:]
    HISTORY_FILE.write_text(json.dumps(history, indent=2, default=str))


def run_traffic(dry_run: bool = False) -> dict:
    """Generate a batch of normal baseline traffic."""
    customer_count = random.randint(*TRAFFIC_CUSTOMER_RANGE)
    window_hours = random.choice([2, 3, 4, 5, 6])

    print(f"[cron] Mode: TRAFFIC — {customer_count} customers, {window_hours}h window")

    if dry_run:
        return {"mode": "traffic", "dry_run": True, "customers": customer_count}

    from generators.traffic_gen import TrafficGenerator
    tg = TrafficGenerator()
    return tg.run(customer_count=customer_count, window_hours=window_hours)


def run_anomaly(dry_run: bool = False) -> dict:
    """Inject a random anomaly scenario with LLM-generated narrative."""
    narrative = generate_anomaly_narrative()
    scenario_type = narrative["scenario_type"]
    affected_city = narrative.get("affected_city")
    severity = narrative.get("severity", "medium")

    # Scale by severity
    if severity == "high":
        customer_mult = 1.5
    else:
        customer_mult = 1.0

    print(f"[cron] Mode: ANOMALY — {scenario_type} ({severity})")
    print(f"[cron] Narrative: {narrative.get('description', 'N/A')}")
    if affected_city:
        print(f"[cron] Affected city: {affected_city}")

    if dry_run:
        return {"mode": "anomaly", "dry_run": True, "scenario": scenario_type, "narrative": narrative}

    # Use the existing scenario runner (pushes to all 3 sources)
    result = run_scenario(scenario_type)
    result["narrative"] = narrative
    result["mode"] = "anomaly"
    return result


def main():
    parser = argparse.ArgumentParser(description="Autonomous Sentinel data generator")
    parser.add_argument("--mode", choices=["auto", "traffic", "anomaly"], default="auto",
                        help="Run mode: auto (weighted random), traffic, or anomaly")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without pushing data")
    parser.add_argument("--no-jitter", action="store_true", help="Skip random time jitter")
    args = parser.parse_args()

    now = datetime.now(IST)
    print(f"\n{'='*60}")
    print(f"[cron] Sentinel Data Generator — {now.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"[cron] LLM: {'NVIDIA (' + (NVIDIA_API_KEY[:12] + '...' if NVIDIA_API_KEY else 'not set') + ')' if NVIDIA_API_KEY else 'disabled (using templates)'}")
    print(f"[cron] PostHog: {'enabled' if POSTHOG_PROJECT_API_KEY else 'disabled'}")
    print(f"{'='*60}")

    # Add jitter unless disabled
    if not args.no_jitter and not args.dry_run:
        _add_jitter()

    # Decide mode
    if args.mode == "auto":
        mode = "anomaly" if random.random() < ANOMALY_PROBABILITY else "traffic"
    else:
        mode = args.mode

    # Run
    t0 = time.time()
    if mode == "traffic":
        result = run_traffic(dry_run=args.dry_run)
    else:
        result = run_anomaly(dry_run=args.dry_run)

    elapsed = time.time() - t0

    # Log
    run_record = {
        "timestamp": now.isoformat(),
        "mode": mode,
        "elapsed_seconds": round(elapsed, 1),
        "result": result,
    }
    if not args.dry_run:
        _log_run(run_record)

    print(f"\n[cron] Done in {elapsed:.1f}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
