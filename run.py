#!/usr/bin/env python3
"""
Sentinel Test Data Generator CLI

Usage:
  python run.py --list                    List available scenarios
  python run.py --scenario application_drop  Run a specific scenario
  python run.py --random                  Run 1 random scenario
  python run.py --random --count 2        Run 2 random scenarios
  python run.py --all                     Run all 4 scenarios
  python run.py --cleanup                 Remove all injected test data

  # Source filters:
  python run.py --scenario payment_failures --skip-posthog
  python run.py --scenario kyc_delays --skip-zendesk
  python run.py --scenario application_drop --posthog-only
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scenarios import list_scenarios, run_scenario, run_random, cleanup_all, SCENARIO_INFO


def main():
    parser = argparse.ArgumentParser(
        description="Generate correlated anomaly data in BigQuery + Zendesk + PostHog for Sentinel testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List available scenarios")
    group.add_argument("--scenario", type=str, choices=list(SCENARIO_INFO.keys()), help="Run a specific scenario")
    group.add_argument("--random", action="store_true", help="Run random scenario(s)")
    group.add_argument("--all", action="store_true", help="Run all scenarios")
    group.add_argument("--cleanup", action="store_true", help="Clean up all injected test data")

    parser.add_argument("--count", type=int, default=1, help="Number of random scenarios to run (with --random)")
    parser.add_argument("--skip-posthog", action="store_true", help="Skip PostHog event injection")
    parser.add_argument("--skip-zendesk", action="store_true", help="Skip Zendesk ticket creation")
    parser.add_argument("--skip-bigquery", action="store_true", help="Skip BigQuery data injection")
    parser.add_argument("--posthog-only", action="store_true", help="Only inject PostHog events (skip BQ + Zendesk)")

    args = parser.parse_args()

    skip_posthog = args.skip_posthog
    skip_zendesk = args.skip_zendesk or args.posthog_only
    skip_bigquery = args.skip_bigquery or args.posthog_only

    run_kwargs = {
        "skip_posthog": skip_posthog,
        "skip_zendesk": skip_zendesk,
        "skip_bigquery": skip_bigquery,
    }

    if args.list:
        list_scenarios()
    elif args.scenario:
        run_scenario(args.scenario, **run_kwargs)
    elif args.random:
        run_random(count=args.count, **run_kwargs)
    elif args.all:
        for key in SCENARIO_INFO:
            run_scenario(key, **run_kwargs)
    elif args.cleanup:
        cleanup_all()


if __name__ == "__main__":
    main()
