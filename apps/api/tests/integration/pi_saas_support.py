"""Helpers for Pi SaaS integration tests: a Pi app client, a scripted Kapso/Stripe
provider (HTTP mock transport) and captured background jobs run against the test DB."""

import hashlib
import hmac
import itertools
import json
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from pydantic import SecretStr

PI_ORIGIN = "http://localhost:3200"
KAPSO_KEY = "kapso-test-project-key"
KAPSO_SECRET = "kapso-webhook-test-secret"
STRIPE_SECRET = "whsec_test_signing_secret"
PASSWORD = "PiBusiness!Secure234"


class CaptureQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[str, ...]]] = []

    async def enqueue(self, name: str, *args: str, job_id: str | None = None) -> bool:
        self.jobs.append((name, args))
        return True

    async def close(self) -> None:
        return None


class FakeProvider:
    """Scripted Kapso platform + Stripe API. Records every request it receives."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.customers: dict[str, str] = {}
        self.numbers: dict[str, list[dict[str, Any]]] = {}
        self.ids = itertools.count(1)
        self.fail_kapso = False
        # WhatsApp message templates visible through Kapso's Meta proxy (campaigns/reminders).
        self.templates: list[dict[str, Any]] = []
        self.webhooks: dict[str, list[dict[str, Any]]] = {}
        self.flows: list[dict[str, Any]] = []
        self.connected_tokens: list[str] = []
        self.setup_links: list[dict[str, Any]] = []

    def add_number(
        self, customer_id: str, phone_number_id: str, display: str, **extra: Any
    ) -> None:
        self.numbers.setdefault(customer_id, []).append(
            {
                "phone_number_id": phone_number_id,
                "display_phone_number": display,
                "business_account_id": "1234567890",
                "status": "active",
                "display_name": "Test business",
                "customer_id": customer_id,
                "name_status": "APPROVED",
                **extra,
            }
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if "api.kapso.ai" in url:
            if request.headers.get("x-api-key") != KAPSO_KEY:
                return httpx.Response(401)
            if self.fail_kapso:
                return httpx.Response(503)
            path = request.url.path
            if path == "/platform/v1/customers" and request.method == "POST":
                body = json.loads(request.content)
                customer_id = str(uuid4())
                self.customers[customer_id] = body["customer"]["external_customer_id"]
                return httpx.Response(201, json={"data": {"id": customer_id}})
            if path == "/platform/v1/customers" and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": cid, "external_customer_id": ext}
                            for cid, ext in self.customers.items()
                        ]
                    },
                )
            if path.endswith("/setup_links") and request.method == "POST":
                # Like real Kapso: the fields must be wrapped in "setup_link".
                link = json.loads(request.content or b"{}").get("setup_link")
                if not isinstance(link, dict) or not link.get("success_redirect_url"):
                    return httpx.Response(
                        400,
                        json={"error": "param is missing or the value is empty: setup_link"},
                    )
                self.setup_links.append(link)
                return httpx.Response(
                    201,
                    json={
                        "data": {
                            "id": f"link_{next(self.ids)}",
                            "url": "https://app.kapso.ai/setup/abc",
                            "expires_at": "2030-01-01T00:00:00Z",
                            "whatsapp_setup_status": "pending",
                        }
                    },
                )
            if path == "/platform/v1/whatsapp/phone_numbers":
                customer = request.url.params.get("customer_id", "")
                if customer:
                    return httpx.Response(200, json={"data": self.numbers.get(customer, [])})
                everything = [n for numbers in self.numbers.values() for n in numbers]
                return httpx.Response(200, json={"data": everything})
            if path.endswith("/whatsapp/phone_numbers") and request.method == "POST":
                customer = path.split("/customers/")[1].split("/")[0]
                body = json.loads(request.content)["whatsapp_phone_number"]
                self.connected_tokens.append(body["access_token"])
                self.add_number(
                    customer,
                    body["phone_number_id"],
                    "+1 415 555 0199",
                    business_account_id=body["business_account_id"],
                )
                return httpx.Response(201, json={"data": self.numbers[customer][-1]})
            if path.endswith("/webhooks") and "/whatsapp/phone_numbers/" in path:
                number = path.split("/phone_numbers/")[1].split("/")[0]
                if request.method == "POST":
                    hook = json.loads(request.content)["whatsapp_webhook"]
                    self.webhooks.setdefault(number, []).append(hook)
                    return httpx.Response(201, json={"data": hook})
                return httpx.Response(200, json={"data": self.webhooks.get(number, [])})
            if path == "/platform/v1/whatsapp/flows" and request.method == "POST":
                flow = json.loads(request.content)["whatsapp_flow"]
                self.flows.append(flow)
                return httpx.Response(
                    201, json={"data": {"id": "flow_1", "meta_flow_id": "998877665544"}}
                )
            if path.endswith("/health"):
                return httpx.Response(
                    200,
                    json={"status": "healthy", "checks": {"messaging_health": {"status": "ok"}}},
                )
            if "/meta/whatsapp/" in path and path.endswith("/message_templates"):
                if request.method == "POST":
                    body = json.loads(request.content)
                    self.templates.append({**body, "status": "PENDING"})
                    return httpx.Response(200, json={"id": "tmpl_1", "status": "PENDING"})
                name = request.url.params.get("name", "")
                found = [t for t in self.templates if not name or t["name"] == name]
                return httpx.Response(200, json={"data": found})
            if "/meta/whatsapp/" in path and path.endswith("/messages"):
                return httpx.Response(200, json={"messages": [{"id": f"wamid.k{next(self.ids)}"}]})
            return httpx.Response(404)
        if "api.stripe.com" in url:
            if request.url.path == "/v1/checkout/sessions":
                return httpx.Response(
                    200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/1"}
                )
            if request.url.path == "/v1/billing_portal/sessions":
                return httpx.Response(200, json={"url": "https://billing.stripe.com/p/1"})
            if request.url.path.startswith("/v1/subscriptions/"):
                return httpx.Response(200, json={"id": "sub_1", "cancel_at_period_end": True})
            return httpx.Response(404)
        return httpx.Response(503)


def configure(app: Any, provider: FakeProvider) -> CaptureQueue:
    settings = app.state.settings
    settings.kapso_api_key = SecretStr(KAPSO_KEY)
    settings.kapso_webhook_secret = SecretStr(KAPSO_SECRET)
    settings.pi_billing_stripe_secret_key = SecretStr("sk_test_platform")
    settings.pi_billing_stripe_webhook_secret = SecretStr(STRIPE_SECRET)
    # Older feature tests connect WhatsApp directly; the approval + payment gate is
    # covered by test_pi_business_journey (which turns it back on).
    settings.pi_whatsapp_requires_approval = False
    if settings.secrets_encryption_key is None:
        settings.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    queue = CaptureQueue()
    app.state.queue = queue
    return queue


def pi_client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"origin": PI_ORIGIN},
    )


async def pi_register(
    client: httpx.AsyncClient, business: str = "Bright Studio", offer_type: str = "services"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/pi-app/auth/register",
        json={
            "email": f"pi-{uuid4().hex}@example.com",
            "password": PASSWORD,
            "display_name": "Amina",
            "business_name": business,
            "offer_type": offer_type,
        },
    )
    assert response.status_code == 201, response.text
    client.headers["x-csrf-token"] = client.cookies["pi_csrf"]
    return response.json()


def worker_ctx(app: Any, db: Any) -> dict[str, Any]:
    @asynccontextmanager
    async def sessions() -> Any:
        yield db

    return {"sessions": sessions, "settings": app.state.settings, "http": app.state.http}


def kapso_signature(body: bytes) -> str:
    return hmac.new(KAPSO_SECRET.encode(), body, hashlib.sha256).hexdigest()


def stripe_signature(body: bytes, at: int | None = None) -> str:
    at = at or int(time.time())
    digest = hmac.new(STRIPE_SECRET.encode(), f"{at}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={at},v1={digest}"


ONBOARDING = {
    1: {"name": "Bright Studio", "language": "en", "timezone": "UTC", "description": "Web design"},
    2: {"offer_type": "services", "offerings": [{"name": "Website design"}]},
    3: {"choice": "existing"},
    4: {
        "goals": ["answer_questions", "capture_leads"],
        "automation_mode": "ai_led",
        "price_disclosure": "quote",
        "tools": ["knowledge", "customers"],
    },
}
