"""
LLM-powered content generation for realistic, varied test data.

Each function tries the LLM first and falls back to hardcoded templates
if the API is unavailable or returns garbage.
"""

import random
from llm_client import llm_generate_json, llm_generate

# ---------------------------------------------------------------------------
# Fallback data (used when LLM is unavailable)
# ---------------------------------------------------------------------------

_FALLBACK_NAMES = [
    "Aarav Sharma", "Priya Patel", "Vivaan Gupta", "Ananya Reddy", "Sai Kumar",
    "Meera Iyer", "Arjun Singh", "Diya Nair", "Karthik Rao", "Neha Bansal",
    "Ishaan Mehta", "Tanvi Joshi", "Reyansh Pandey", "Kavitha Pillai", "Vihaan Das",
    "Shreya Kapoor", "Krishna Verma", "Pooja Chatterjee", "Aditya Malhotra", "Riya Bhat",
]

_FALLBACK_CITIES = [
    "Mumbai", "Delhi NCR", "Bangalore", "Chennai", "Kolkata",
    "Pune", "Ahmedabad", "Hyderabad", "Lucknow", "Surat",
]

_FALLBACK_TICKET_SUBJECTS = {
    "application_drop": [
        "Cannot submit my insurance application",
        "Application form throwing error on health section",
        "Getting error when trying to apply for insurance",
    ],
    "payment_failures": [
        "Premium payment failed multiple times",
        "Payment not going through for policy renewal",
        "Cannot pay premium - gateway error",
    ],
    "kyc_delays": [
        "KYC verification stuck for 3 days",
        "KYC verification not completing",
        "Application blocked due to KYC pending",
    ],
    "regional_outage": [
        "Website not loading from my city",
        "Cannot access application form",
        "Service seems unavailable in our area",
    ],
}

_SYSTEM_PROMPT = """\
You are a test data generator for an Indian insurance company (Axis Max Life).
You generate realistic content that mimics real customer interactions and product data.
Always use natural Indian English. Respond ONLY with valid JSON, no markdown fences or explanation."""

# ---------------------------------------------------------------------------
# Customer generation
# ---------------------------------------------------------------------------

def generate_customers(count: int = 15, city_bias: str | None = None) -> list[dict]:
    """Generate a batch of realistic customer profiles."""
    prompt = f"""Generate {count} realistic Indian customer profiles for a life insurance company.
Each customer should have: full_name, email, phone, gender (M/F), age (22-58), city, income_band.

Cities should be Indian metros/tier-1 cities.{f' Bias {count // 2}+ customers toward {city_bias}.' if city_bias else ''}
Emails should look real (gmail.com, outlook.com, yahoo.co.in).
Income bands: 3L-5L, 5L-10L, 10L-20L, 20L-50L, 50L+

Return a JSON array of {count} objects."""

    result = llm_generate_json(prompt, system=_SYSTEM_PROMPT)
    if result and isinstance(result, list) and len(result) >= count // 2:
        return result[:count]

    # Fallback
    customers = []
    for i in range(count):
        name = random.choice(_FALLBACK_NAMES)
        city = city_bias if (city_bias and random.random() < 0.6) else random.choice(_FALLBACK_CITIES)
        parts = name.split()
        email = f"{parts[0].lower()}.{parts[-1].lower()}{random.randint(10, 9999)}@{random.choice(['gmail.com', 'outlook.com', 'yahoo.co.in'])}"
        customers.append({
            "full_name": name,
            "email": email,
            "phone": f"+91{random.randint(7000000000, 9999999999)}",
            "gender": random.choice(["M", "F"]),
            "age": random.randint(22, 58),
            "city": city,
            "income_band": random.choice(["3L-5L", "5L-10L", "10L-20L", "20L-50L", "50L+"]),
        })
    return customers


# ---------------------------------------------------------------------------
# Zendesk ticket generation
# ---------------------------------------------------------------------------

def generate_ticket(scenario: str, customer_name: str, city: str, product: str = "term life insurance") -> dict:
    """Generate a realistic support ticket subject + body."""
    scenario_descriptions = {
        "application_drop": "they cannot complete the online insurance application form — it shows errors or goes blank",
        "payment_failures": "their premium payment keeps failing with gateway errors, they are worried about policy lapse",
        "kyc_delays": "their KYC/Aadhaar verification has been stuck for days, blocking their application",
        "regional_outage": f"the website is not loading or working properly from {city}, they can see landing page but nothing beyond",
    }

    desc = scenario_descriptions.get(scenario, "they are having trouble with the insurance platform")

    prompt = f"""Generate a realistic support ticket for an Indian insurance company (Axis Max Life).

Customer: {customer_name}, City: {city}, Product: {product}
Issue: {desc}

Write a unique support ticket. The customer is frustrated but polite, writing in natural Indian English.
Vary the tone — sometimes worried, sometimes angry, sometimes confused.
2-4 sentences for the body. Subject should be 5-10 words.

Return JSON: {{"subject": "...", "body": "..."}}"""

    result = llm_generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.9)
    if result and isinstance(result, dict) and result.get("subject") and result.get("body"):
        return result

    # Fallback
    subjects = _FALLBACK_TICKET_SUBJECTS.get(scenario, ["Need help with my application"])
    return {
        "subject": random.choice(subjects),
        "body": f"Hi, I am {customer_name} from {city}. I am facing issues with my {product} application. Please help resolve this urgently.",
    }


def generate_tickets_batch(scenario: str, customers: list[dict], count: int = 5) -> list[dict]:
    """Generate multiple unique tickets for a scenario."""
    prompt = f"""Generate {count} unique support tickets for an Indian insurance company (Axis Max Life).

Scenario: {scenario.replace('_', ' ')}
Customers filing tickets:
{chr(10).join(f"- {c.get('full_name', 'Customer')} from {c.get('city', 'Mumbai')}" for c in customers[:count])}

Each ticket should be different in tone and wording. Some customers are angry, some confused, some worried.
Use natural Indian English. Each body should be 2-4 sentences.

Return a JSON array of {count} objects, each with "subject" and "body" keys."""

    result = llm_generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.9)
    if result and isinstance(result, list) and len(result) >= count // 2:
        return result[:count]

    # Fallback: generate individually
    tickets = []
    for c in customers[:count]:
        tickets.append(generate_ticket(scenario, c.get("full_name", "Customer"), c.get("city", "Mumbai")))
    return tickets


# ---------------------------------------------------------------------------
# Scenario narrative generation (for anomaly runs)
# ---------------------------------------------------------------------------

def generate_anomaly_narrative() -> dict:
    """Generate a random anomaly scenario narrative.

    Returns:
        {
            "scenario_type": one of application_drop|payment_failures|kyc_delays|regional_outage,
            "description": "What happened (1-2 sentences, ops language)",
            "affected_city": city or None,
            "affected_product": product or None,
            "severity": "medium" or "high",
        }
    """
    prompt = """Generate a random incident scenario for an Indian life insurance company's digital platform.

Pick ONE of these incident types:
- application_drop: form/API breaks causing application abandonment
- payment_failures: payment gateway or banking partner outage
- kyc_delays: KYC/Aadhaar verification vendor degradation
- regional_outage: CDN or regional infra failure affecting one city

Generate a realistic 1-2 sentence description of what went wrong (internal ops language).
Pick a random affected Indian city (Mumbai, Delhi NCR, Bangalore, Chennai, Pune, Hyderabad, Kolkata, Ahmedabad).
Pick severity: "medium" (partial degradation) or "high" (full outage).

Return JSON:
{
    "scenario_type": "...",
    "description": "...",
    "affected_city": "..." or null,
    "affected_product": "..." or null,
    "severity": "medium" or "high"
}"""

    result = llm_generate_json(prompt, system=_SYSTEM_PROMPT)
    if result and isinstance(result, dict) and result.get("scenario_type"):
        valid_types = {"application_drop", "payment_failures", "kyc_delays", "regional_outage"}
        if result["scenario_type"] in valid_types:
            return result

    # Fallback
    scenario = random.choice(["application_drop", "payment_failures", "kyc_delays", "regional_outage"])
    city = random.choice(_FALLBACK_CITIES[:6])
    descriptions = {
        "application_drop": f"Health declaration API returning 500s intermittently, causing form abandonment on /apply/health for users in {city}",
        "payment_failures": f"HDFC Bank gateway partner reporting elevated timeouts since 2pm IST, affecting UPI and netbanking payments",
        "kyc_delays": f"Karza Aadhaar offline verification queue backed up — processing times exceeding 48 hours",
        "regional_outage": f"CDN edge node in {city} serving stale/empty responses for all pages beyond landing",
    }
    return {
        "scenario_type": scenario,
        "description": descriptions[scenario],
        "affected_city": city if scenario == "regional_outage" else None,
        "affected_product": None,
        "severity": random.choice(["medium", "high"]),
    }


# ---------------------------------------------------------------------------
# Normal traffic content (routine questions, not complaints)
# ---------------------------------------------------------------------------

def generate_routine_ticket(customer_name: str, city: str) -> dict | None:
    """Generate a routine (non-complaint) support ticket. Returns None sometimes (no ticket)."""
    if random.random() < 0.6:
        return None

    prompt = f"""Generate a routine (non-complaint) support ticket for an Indian insurance company.
Customer: {customer_name} from {city}.

This is NOT a complaint. It's a normal question like:
- Asking about policy details, coverage, premium amounts
- Requesting a document (policy copy, premium receipt)
- Asking about claim process
- Updating contact details
- Asking about tax benefits (80C, 80D)

Keep it short (1-2 sentences). Natural Indian English.

Return JSON: {{"subject": "...", "body": "..."}}"""

    result = llm_generate_json(prompt, system=_SYSTEM_PROMPT, temperature=0.9)
    if result and isinstance(result, dict) and result.get("subject"):
        return result

    # Fallback
    routine_subjects = [
        "Need copy of my policy document",
        "Question about tax benefits under 80C",
        "How to update my nominee details?",
        "Premium receipt for FY 2025-26",
        "What is the claim settlement process?",
    ]
    return {
        "subject": random.choice(routine_subjects),
        "body": f"Hi, I am {customer_name} from {city}. {random.choice(['Could you please help me with this?', 'Kindly assist.', 'Please advise on the same.', 'Would appreciate your help on this.'])}",
    }
