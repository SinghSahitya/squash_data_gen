"""
Zendesk ticket generator.
Creates realistic support tickets via the Zendesk REST API that correlate
with BigQuery anomaly data (same customers, same time window, same issues).
"""

import random
import requests
from requests.auth import HTTPBasicAuth
from config import ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN, SENTINEL_TEST_TAG

TICKET_TEMPLATES = {
    "application_drop": [
        {
            "subject": "Cannot submit my insurance application",
            "body": "I have been trying to submit my term life insurance application for the last hour but the form keeps showing an error. I filled in all my personal and health details but when I click submit, nothing happens. Please help urgently.",
        },
        {
            "subject": "Application form throwing error on health section",
            "body": "I started filling out the application form for TERM_SAVE plan. After filling personal details, the health declaration page is not loading properly. I keep getting a blank screen. My application is stuck.",
        },
        {
            "subject": "Getting error when trying to apply for insurance",
            "body": "I want to buy term life insurance but your application form is broken. When I enter my health details and click next, it shows 'Something went wrong'. I have tried on both mobile and desktop. Very frustrating experience.",
        },
        {
            "subject": "Application stuck on personal details page",
            "body": "I am trying to apply for ULIP plan but the form is not saving my personal information. It keeps going back to the first step. I have filled the form 3 times now. Is there a technical issue with your website?",
        },
        {
            "subject": "Form error while applying - please fix",
            "body": "Your online application form has some technical issue. I was filling the application for savings plan and after the personal details section, I got an error message. I've been waiting for 30 minutes and it's still not working.",
        },
        {
            "subject": "Unable to complete insurance application online",
            "body": "I've been trying to complete my insurance application since morning. The form shows an error every time I try to proceed past the health questionnaire. Can someone please look into this? I need the policy urgently.",
        },
        {
            "subject": "Website keeps crashing during application",
            "body": "Your website crashes every time I try to fill the application form. I have tried clearing cache and using a different browser but the problem persists. Is there a server issue on your end?",
        },
        {
            "subject": "Application form not working since yesterday",
            "body": "Since yesterday evening, I cannot proceed with my application form. The page goes blank after I fill the health details. My quote was for Rs 15000 annual premium for TERM_SMART. Please resolve this.",
        },
    ],
    "payment_failures": [
        {
            "subject": "Premium payment failed multiple times",
            "body": "I am trying to pay my insurance premium of Rs 12000 but the payment is failing every time. I tried UPI, net banking and debit card - all showing 'bank unavailable'. My payment is due tomorrow. Please help.",
        },
        {
            "subject": "Payment not going through for policy renewal",
            "body": "My annual premium payment is due and I have been trying to pay since morning. The payment page shows 'transaction failed - bank unavailable'. I have sufficient balance in my account. What is happening?",
        },
        {
            "subject": "Charged but payment shows failed in account",
            "body": "I tried paying my premium and the amount was debited from my bank account (Rs 25000) but your system shows payment failed. This happened twice. Now Rs 50000 is stuck. Please resolve immediately.",
        },
        {
            "subject": "Cannot pay premium - gateway error",
            "body": "Every time I try to pay my premium, I get 'Payment gateway temporarily unavailable'. I have tried all payment modes - UPI, cards, net banking. Nothing works. Is the payment system down?",
        },
        {
            "subject": "Payment declined for insurance premium",
            "body": "My NACH auto-debit for insurance premium was declined. The bank says there is no issue from their side. I need to pay within 3 days or my policy will lapse. Please look into this urgently.",
        },
        {
            "subject": "First premium payment keeps failing",
            "body": "I just got my policy approved but cannot make the first premium payment. The payment fails every time with 'bank unavailable' error. I have tried using different payment methods but nothing works.",
        },
        {
            "subject": "Duplicate debit for premium payment",
            "body": "I was paying my quarterly premium of Rs 8000 and the payment failed but the amount got deducted from my account. When I tried again, it got deducted again. Now Rs 16000 has been deducted but no successful payment recorded.",
        },
        {
            "subject": "Premium payment page showing error",
            "body": "When I click on 'Pay Premium' in my account, the page either doesn't load or shows a gateway timeout error. I have been trying for the last 4 hours. My premium is overdue by 2 days already.",
        },
        {
            "subject": "Unable to pay - transaction timeout",
            "body": "I initiated a premium payment via net banking and after entering my bank credentials, the page timed out. The payment shows as failed but I am not sure if money was debited. Very worried about policy lapse.",
        },
        {
            "subject": "Payment system seems down",
            "body": "Is your payment system currently down? I and my husband are both trying to pay our premiums and both of us are getting the same 'bank unavailable' error. We are in Mumbai and using HDFC bank.",
        },
    ],
    "kyc_delays": [
        {
            "subject": "KYC verification stuck for 3 days",
            "body": "I submitted my KYC documents 3 days ago but the verification is still showing 'in progress'. The Aadhaar offline verification has been pending for over 72 hours. How long does it normally take? My application is completely stuck.",
        },
        {
            "subject": "KYC verification not completing",
            "body": "My KYC has been pending for more than 2 days now. I completed the Aadhaar OTP verification but the status still shows pending. Because of this, my insurance application cannot proceed further.",
        },
        {
            "subject": "How long does KYC take? Mine is stuck",
            "body": "I applied for term insurance 4 days ago and did the KYC immediately. But it is still in 'processing' state. My agent told me it usually takes a few minutes but it has been days. Is there some issue with your KYC system?",
        },
        {
            "subject": "KYC rejected for no reason - need help",
            "body": "My KYC was rejected saying 'face mismatch' but the photo on my Aadhaar is clearly me. I tried again and now it's been stuck in processing for 2 days. I need this policy for my home loan. Please expedite.",
        },
        {
            "subject": "Application blocked due to KYC pending",
            "body": "My application has been stuck at the KYC stage for 5 days. I uploaded all required documents and did the Aadhaar verification. The system keeps showing 'verification in progress'. Can someone manually verify my documents?",
        },
        {
            "subject": "Aadhaar verification taking too long",
            "body": "The Aadhaar verification step in my application has been processing for 48+ hours. I have completed all other steps. Is there an issue with your KYC vendor? I need the policy issued before the end of this month.",
        },
    ],
    "regional_outage": [
        {
            "subject": "Website not loading from Mumbai",
            "body": "I am in Mumbai and your website is not loading properly. The pages are either blank or showing timeout errors. I have tried from both my phone and laptop using different internet connections. Is there a regional issue?",
        },
        {
            "subject": "Cannot access application form - Mumbai",
            "body": "I am unable to access the insurance application form from Mumbai. The landing page loads but when I click on 'Get Quote' or 'Apply Now', nothing happens. My friend in Delhi says it works fine for him.",
        },
        {
            "subject": "Website down in our area?",
            "body": "Is the website down for Mumbai region? Multiple people in my office are unable to access the application form. We can see the homepage but cannot proceed to get a quote. We all use different internet providers.",
        },
        {
            "subject": "Cannot get a quote - page not loading",
            "body": "I have been trying to get an insurance quote for the last few hours but the calculator page refuses to load. I can see the landing page but anything beyond that just shows a loading spinner. I am based in Mumbai.",
        },
        {
            "subject": "Service unavailable from Mumbai location",
            "body": "Your service seems to be unavailable from Mumbai. I can open the home page but all other pages give a timeout. I checked with my colleagues in Pune and they are facing the same issue. Please look into this regional outage.",
        },
    ],
}


class ZendeskGenerator:
    def __init__(self):
        if not all([ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN]):
            print("[WARN] Zendesk credentials not configured. Set ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN in .env")
            self.enabled = False
            return
        self.base_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2"
        self.auth = HTTPBasicAuth(f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN)
        self.enabled = True
        self.created_ticket_ids: list[int] = []

    def _create_ticket(self, subject: str, body: str, requester_name: str, requester_email: str, tags: list[str] | None = None) -> int | None:
        payload = {
            "ticket": {
                "subject": subject,
                "comment": {"body": body},
                "requester": {"name": requester_name, "email": requester_email},
                "tags": [SENTINEL_TEST_TAG] + (tags or []),
                "priority": random.choice(["normal", "high", "urgent"]),
            }
        }
        try:
            resp = requests.post(f"{self.base_url}/tickets.json", json=payload, auth=self.auth, timeout=15)
            resp.raise_for_status()
            ticket_id = resp.json()["ticket"]["id"]
            self.created_ticket_ids.append(ticket_id)
            return ticket_id
        except requests.RequestException as e:
            print(f"  [WARN] Failed to create Zendesk ticket: {e}")
            return None

    def create_scenario_tickets(self, scenario: str, customers: list[dict], city_override: str | None = None) -> list[int]:
        """
        Create Zendesk tickets for a scenario, using real customer data from
        BigQuery for requester correlation.
        """
        if not self.enabled:
            print("  [SKIP] Zendesk not configured, skipping ticket creation")
            return []

        templates = TICKET_TEMPLATES.get(scenario, [])
        if not templates:
            print(f"  [WARN] No templates for scenario: {scenario}")
            return []

        n_tickets = min(len(templates), max(3, len(customers)))
        selected_templates = random.sample(templates, n_tickets)
        selected_customers = random.sample(customers, min(n_tickets, len(customers)))

        ticket_ids = []
        for i, tmpl in enumerate(selected_templates):
            cust = selected_customers[i % len(selected_customers)]
            subject = tmpl["subject"]
            body = tmpl["body"]

            if city_override:
                subject = subject.replace("Mumbai", city_override)
                body = body.replace("Mumbai", city_override)

            tid = self._create_ticket(
                subject=subject,
                body=body,
                requester_name=cust.get("full_name", "Test User"),
                requester_email=cust.get("email", "test@example.com"),
                tags=[SENTINEL_TEST_TAG, scenario],
            )
            if tid:
                ticket_ids.append(tid)
                print(f"  [OK] Created Zendesk ticket #{tid}: {subject[:50]}...")

        return ticket_ids

    def cleanup(self) -> None:
        """Delete all tickets tagged with sentinel_test."""
        if not self.enabled:
            return

        try:
            resp = requests.get(
                f"{self.base_url}/search.json",
                params={"query": f"type:ticket tags:{SENTINEL_TEST_TAG}"},
                auth=self.auth,
                timeout=15,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                print("  No Zendesk tickets to clean up.")
                return

            ticket_ids = [str(r["id"]) for r in results]
            for batch_start in range(0, len(ticket_ids), 100):
                batch = ticket_ids[batch_start:batch_start + 100]
                resp = requests.delete(
                    f"{self.base_url}/tickets/destroy_many.json",
                    params={"ids": ",".join(batch)},
                    auth=self.auth,
                    timeout=30,
                )
                resp.raise_for_status()
                print(f"  [OK] Deleted {len(batch)} Zendesk tickets")
        except requests.RequestException as e:
            print(f"  [WARN] Zendesk cleanup failed: {e}")
