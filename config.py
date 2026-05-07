import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BQ_PROJECT = os.getenv("BIGQUERY_PROJECT", "axis-max-life")
BQ_KEY_FILE = os.getenv("BIGQUERY_KEY_FILE", str(Path(__file__).resolve().parent.parent / "dummy_data" / "axis-max-life-dbc75b2c6913.json"))
BQ_DATASET = os.getenv("BIGQUERY_DATASET", "insurance_analytics")

ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN", "")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL", "")
ZENDESK_API_TOKEN = os.getenv("ZENDESK_API_TOKEN", "")

POSTHOG_HOST = os.getenv("POSTHOG_HOST", "https://us.posthog.com")
POSTHOG_PROJECT_API_KEY = os.getenv("POSTHOG_PROJECT_API_KEY", "")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

SENTINEL_TEST_TAG = "sentinel_test"
