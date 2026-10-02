"""Pay-by-link/QR: a payment reachable by anyone holding the raw token, no session.

Covers both row types the token pattern is generic over (``PiManualPayment`` — the Pi
subscription itself — and ``PiPaymentRequest`` — a business collecting from its own
customer): issue, anonymous view, anonymous proof submission, the token going dead once
the row leaves its "live" states, wrong-token 404 and a rate-limit trip.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pi_saas_support import PI_ORIGIN, FakeProvider, configure, pi_client, pi_register
from sqlalchemy import select
from test_pi_customer_payments import _enable, _invoice
from test_pi_pipeline import pi_workspace
from test_service_lifecycle import create, register

from app.core import rate_limit
from app.modules.pi.models import PiConversation, WhatsAppConnection
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.models import PiOperatorMember, PiPlan
from app.modules.pi_saas.payment_models import PiManualPayment

pytestmark = pytest.mark.integration
CLIENT = "/api/v1/pi-app/billing"
ADMIN = "/api/v1/operator/pi/billing"
CONFIG = {
    "seller_name": "Test Pi",
    "bank_enabled": True,
    "bank_name": "Test bank",
    "account_title": "Test Pi",
    "iban": "PK36SCBL0000001123456702",
    "cash_enabled": True,
    "cash_instructions": "Pay the test cashier at the test office",
}


class FakeRedis:
    """A deterministic counter standing in for Redis, so rate limiting can actually be
    exercised in a test (the default test settings point at an unreachable Redis, which
    makes the limiter fail open on purpose)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True


async def _manual_payment_business(api: httpx.AsyncClient, business_db: Any) -> dict[str, Any]:
    """A Pi business with a pending cash/bank manual payment, set up the same way
    test_pi_manual_billing's ``collection`` fixture does."""
    app = api._transport.app  # type: ignore[attr-defined]
    provider = FakeProvider()
    configure(app, provider)
    identity = await register(api)
    operator = PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner")
    business_db.add(operator)
    await business_db.flush()
    response = await api.put(ADMIN + "/settings", json=CONFIG)
    assert response.status_code == 200, response.text
    plan = await business_db.scalar(select(PiPlan).where(PiPlan.key == "starter"))
    plan.manual_monthly_price_pkr = Decimal("2500.00")
    await business_db.flush()
    client = pi_client(app)
    view = await pi_register(client)
    body = {
        "request_key": str(uuid4()),
        "plan": "starter",
        "method": "bank_transfer",
        "months": 1,
    }
    created = await client.post(CLIENT + "/payments", json=body)
    assert created.status_code == 201, created.text
    return {
        "app": app,
        "client": client,
        "tenant": view["business"]["id"],
        "payment": created.json(),
    }


def _anon_client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"origin": PI_ORIGIN},
    )


async def test_manual_payment_pay_link_full_circle(api: httpx.AsyncClient, business_db: Any):
    ctx = await _manual_payment_business(api, business_db)
    client, tenant, payment = ctx["client"], ctx["tenant"], ctx["payment"]
    link = await client.post(CLIENT + f"/payments/{payment['id']}/link")
    assert link.status_code == 200, link.text
    token = link.json()["token"]
    assert link.json()["url"].endswith(f"/pay/{token}")

    async with _anon_client(ctx["app"]) as anon:
        # Wrong token: a generic, indistinguishable 404.
        wrong = await anon.get(f"/api/v1/pi-app/pay/{token[:-4]}zzzz")
        assert wrong.status_code == 404

        view = await anon.get(f"/api/v1/pi-app/pay/{token}")
        assert view.status_code == 200, view.text
        body = view.json()
        assert body["status"] == "awaiting_payment" and body["amount"] == "2500.00"
        assert body["method"] == "bank_transfer" and body["business_name"]

        qr = await anon.get(f"/api/v1/pi-app/pay/{token}/qr.png")
        assert qr.status_code == 200
        assert qr.headers["content-type"] == "image/png"
        assert qr.content.startswith(b"\x89PNG\r\n\x1a\n")

        proof = await anon.post(
            f"/api/v1/pi-app/pay/{token}/proof",
            data={
                "payer_name": "Anon Payer",
                "reference": "TRX-LINK-1",
                "paid_on": datetime.now(UTC).date().isoformat(),
            },
            files={"file": ("receipt.pdf", b"%PDF-1.4 anon receipt", "application/pdf")},
        )
        assert proof.status_code == 200, proof.text
        assert proof.json()["status"] == "submitted"

        # Still "live" (submitted, not yet terminal): the view keeps working.
        still_live = await anon.get(f"/api/v1/pi-app/pay/{token}")
        assert still_live.status_code == 200
        assert still_live.json()["status"] == "submitted"

    # Staff review proceeds exactly as normal, through the authenticated operator route.
    review = await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{payment['id']}/review",
        json={
            "action": "approve",
            "note": "Confirmed in bank statement",
            "verified_received": True,
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "approved"

    row = await business_db.scalar(
        select(PiManualPayment).where(PiManualPayment.id == UUID(payment["id"]))
    )
    assert row.link_token_hash is not None  # link itself is not cleared...
    async with _anon_client(ctx["app"]) as anon:
        # ...but the token is dead: approved is no longer a "live" state.
        dead = await anon.get(f"/api/v1/pi-app/pay/{token}")
        assert dead.status_code == 404
        dead_proof = await anon.post(
            f"/api/v1/pi-app/pay/{token}/proof",
            data={"payer_name": "Dead Payer", "paid_on": datetime.now(UTC).date().isoformat()},
            files={"file": ("r.pdf", b"%PDF-1.4 x", "application/pdf")},
        )
        assert dead_proof.status_code == 404


async def test_manual_payment_link_rotation_and_expiry(api: httpx.AsyncClient, business_db: Any):
    ctx = await _manual_payment_business(api, business_db)
    client, payment = ctx["client"], ctx["payment"]
    first = (await client.post(CLIENT + f"/payments/{payment['id']}/link")).json()
    second = (await client.post(CLIENT + f"/payments/{payment['id']}/link")).json()
    assert first["token"] != second["token"]

    async with _anon_client(ctx["app"]) as anon:
        # Rotated: the old token is dead, the new one works.
        assert (await anon.get(f"/api/v1/pi-app/pay/{first['token']}")).status_code == 404
        assert (await anon.get(f"/api/v1/pi-app/pay/{second['token']}")).status_code == 200

    row = await business_db.scalar(
        select(PiManualPayment).where(PiManualPayment.id == UUID(payment["id"]))
    )
    row.link_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await business_db.flush()
    async with _anon_client(ctx["app"]) as anon:
        expired = await anon.get(f"/api/v1/pi-app/pay/{second['token']}")
        assert expired.status_code == 404


async def test_manual_payment_pay_link_rate_limit(api: httpx.AsyncClient, business_db: Any):
    ctx = await _manual_payment_business(api, business_db)
    client, payment = ctx["client"], ctx["payment"]
    token = (await client.post(CLIENT + f"/payments/{payment['id']}/link")).json()["token"]
    ctx["app"].state.redis = FakeRedis()
    # Setup above may already have tripped the real-redis-unavailable cooldown
    # (module-global, since the limiter fails open for 30s after a connection error).
    rate_limit._redis_down_until = 0.0
    async with _anon_client(ctx["app"]) as anon:
        statuses = [
            (await anon.get(f"/api/v1/pi-app/pay/{token}")).status_code for _ in range(31)
        ]
    assert statuses.count(429) == 1 and statuses[-1] == 429
    assert all(s == 200 for s in statuses[:30])


async def test_payment_request_pay_link_full_circle(api: httpx.AsyncClient, business_db: Any):
    await pi_workspace(api, business_db, business_type="service_business")
    await _enable(api)
    customer = await create(api, "customers", {"name": "Bilal", "tags": []})
    invoice = await _invoice(api, customer["id"])
    created = await create(
        api,
        "pi/payment-requests",
        {"invoice_id": invoice["id"], "method": "bank_transfer", "request_key": str(uuid4())},
    )
    link = await api.post(f"/api/v1/pi/payment-requests/{created['id']}/link")
    assert link.status_code == 200, link.text
    token = link.json()["token"]
    assert link.json()["url"].endswith(f"/pay/request/{token}")

    app = api._transport.app  # type: ignore[attr-defined]
    async with _anon_client(app) as anon:
        wrong = await anon.get(f"/api/v1/pi-app/pay/request/{token[:-4]}zzzz")
        assert wrong.status_code == 404

        view = await anon.get(f"/api/v1/pi-app/pay/request/{token}")
        assert view.status_code == 200, view.text
        assert view.json()["status"] == "open" and view.json()["amount"] == "15000.00"

        qr = await anon.get(f"/api/v1/pi-app/pay/request/{token}/qr.png")
        assert qr.status_code == 200 and qr.content.startswith(b"\x89PNG\r\n\x1a\n")

        proof = await anon.post(
            f"/api/v1/pi-app/pay/request/{token}/proof",
            data={"note": "Paid via bank transfer", "reference": created["reference"]},
        )
        assert proof.status_code == 200, proof.text
        assert proof.json()["status"] == "awaiting_verification"

    verified = await api.post(
        f"/api/v1/pi/payment-requests/{created['id']}/verify", json={"received": True}
    )
    assert verified.status_code == 200 and verified.json()["status"] == "paid"

    row = await business_db.scalar(
        select(PiPaymentRequest).where(PiPaymentRequest.id == UUID(created["id"]))
    )
    assert row.link_token_hash is not None
    async with _anon_client(app) as anon:
        dead = await anon.get(f"/api/v1/pi-app/pay/request/{token}")
        assert dead.status_code == 404


async def test_payment_request_send_includes_pay_link_and_rotates_it(
    api: httpx.AsyncClient, business_db: Any
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _enable(api)
    customer = await create(api, "customers", {"name": "Sana", "tags": []})
    invoice = await _invoice(api, customer["id"])
    connection = await business_db.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.tenant_id == UUID(pi.identity["tenant"]["id"])
        )
    )
    now = datetime.now(UTC)
    conversation = PiConversation(
        tenant_id=connection.tenant_id,
        environment_id=connection.environment_id,
        customer_id=UUID(customer["id"]),
        connection_id=connection.id,
        contact_wa_id="15550001111",
        mode="human",
        last_message_at=now,
        last_inbound_at=now,
    )
    business_db.add(conversation)
    await business_db.flush()
    created = await create(
        api,
        "pi/payment-requests",
        {
            "invoice_id": invoice["id"],
            "method": "bank_transfer",
            "request_key": str(uuid4()),
            "conversation_id": str(conversation.id),
        },
    )

    first_send = await api.post(f"/api/v1/pi/payment-requests/{created['id']}/send")
    assert first_send.status_code == 200, first_send.text
    row = await business_db.scalar(
        select(PiPaymentRequest).where(PiPaymentRequest.id == UUID(created["id"]))
    )
    first_hash = row.link_token_hash
    assert first_hash is not None

    second_send = await api.post(f"/api/v1/pi/payment-requests/{created['id']}/send")
    assert second_send.status_code == 200, second_send.text
    await business_db.refresh(row)
    assert row.link_token_hash is not None and row.link_token_hash != first_hash
