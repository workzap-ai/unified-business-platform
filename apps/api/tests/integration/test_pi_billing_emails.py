"""Billing events fire email, not just an in-app notification.

Mirrors the password-reset tests' ``captured_emails`` pattern (monkeypatch
``send_platform_template`` where it is imported, read back what would have been sent),
but patched in ``app.modules.pi_saas.billing`` — the module all three new sends go
through (``billing.send_billing_email`` -> ``send_platform_template``).
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from sqlalchemy import select
from test_service_lifecycle import register

from app.modules.pi_saas import billing, manual_billing
from app.modules.pi_saas.models import (
    PiBillingEvent,
    PiBusinessAccount,
    PiOperatorMember,
    PiPlan,
    PiSubscription,
)

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


@pytest.fixture
def captured_emails(monkeypatch):
    sent: list[dict[str, Any]] = []

    async def fake(settings, http, template, to, variables, **kwargs):
        sent.append({"template": template, "to": list(to), "variables": dict(variables)})

    monkeypatch.setattr("app.modules.pi_saas.billing.send_platform_template", fake)
    return sent


async def _business(api: httpx.AsyncClient, business_db: Any) -> dict[str, Any]:
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
    return {
        "app": app,
        "client": client,
        "tenant": UUID(view["business"]["id"]),
        # The Pi-app registrant is the business owner and the billing email recipient —
        # distinct from the owner-os `identity` used only to grant PiOperatorMember.
        "owner_email": view["user"]["email"],
    }


async def test_manual_payment_approval_sends_receipt_email(
    api: httpx.AsyncClient, business_db: Any, captured_emails
):
    ctx = await _business(api, business_db)
    client, tenant = ctx["client"], ctx["tenant"]
    created = await client.post(
        CLIENT + "/payments",
        json={"request_key": str(uuid4()), "plan": "starter", "method": "cash", "months": 1},
    )
    assert created.status_code == 201, created.text
    row = created.json()
    submitted = await client.post(
        CLIENT + f"/payments/{row['id']}/submit",
        json={
            "payer_name": "Cash Payer",
            "paid_on": datetime.now(UTC).date().isoformat(),
        },
    )
    assert submitted.status_code == 200, submitted.text

    review = await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{row['id']}/review",
        json={"action": "approve", "note": "Cash counted", "verified_received": True},
    )
    assert review.status_code == 200, review.text

    receipts = [e for e in captured_emails if e["template"] == "pi_payment_receipt"]
    assert len(receipts) == 1
    sent = receipts[0]
    assert sent["to"] == [ctx["owner_email"]]
    assert sent["variables"]["plan"] == "Starter"
    assert sent["variables"]["amount"] == "PKR 2,500.00"
    assert sent["variables"]["receipt"]

    # Rejection must never send a receipt.
    captured_emails.clear()
    created2 = await client.post(
        CLIENT + "/payments",
        json={"request_key": str(uuid4()), "plan": "starter", "method": "cash", "months": 1},
    )
    row2 = created2.json()
    await client.post(
        CLIENT + f"/payments/{row2['id']}/submit",
        json={"payer_name": "Cash Payer", "paid_on": datetime.now(UTC).date().isoformat()},
    )
    await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{row2['id']}/review",
        json={"action": "reject", "note": "Not received", "verified_received": False},
    )
    assert not [e for e in captured_emails if e["template"] == "pi_payment_receipt"]


async def test_subscription_past_due_sends_email_alongside_notification(
    api: httpx.AsyncClient, business_db: Any, captured_emails
):
    ctx = await _business(api, business_db)
    app, tenant = ctx["app"], ctx["tenant"]
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant)
    )
    sub.billing_provider, sub.external_subscription_id, sub.external_customer_id, sub.status = (
        "stripe",
        "sub_pastdue",
        "cus_pastdue",
        "active",
    )
    await business_db.flush()
    event = PiBillingEvent(
        provider="stripe",
        event_id="evt_pastdue_1",
        event_type="customer.subscription.updated",
        payload={
            "created": int(datetime.now(UTC).timestamp()),
            "object": {
                "id": "sub_pastdue",
                "object": "subscription",
                "customer": "cus_pastdue",
                "status": "past_due",
            },
        },
    )
    business_db.add(event)
    await business_db.flush()
    await billing.apply_event(business_db, app.state.settings, event, app.state.http)
    assert sub.status == "past_due"

    past_due = [e for e in captured_emails if e["template"] == "pi_billing_past_due"]
    assert len(past_due) == 1
    assert past_due[0]["to"] == [ctx["owner_email"]]
    assert past_due[0]["variables"]["link"].endswith("/settings/billing")


async def test_invoice_paid_sends_confirmation_email(
    api: httpx.AsyncClient, business_db: Any, captured_emails
):
    ctx = await _business(api, business_db)
    app, tenant = ctx["app"], ctx["tenant"]
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant)
    )
    sub.billing_provider, sub.external_subscription_id, sub.external_customer_id, sub.status = (
        "stripe",
        "sub_inv1",
        "cus_inv1",
        "active",
    )
    await business_db.flush()
    event = PiBillingEvent(
        provider="stripe",
        event_id="evt_invoice_paid_1",
        event_type="invoice.paid",
        payload={
            "created": int(datetime.now(UTC).timestamp()),
            "object": {
                "id": "in_1",
                "object": "invoice",
                "subscription": "sub_inv1",
                "customer": "cus_inv1",
                "currency": "usd",
                "amount_due": 1000,
                "amount_paid": 1000,
                "status": "paid",
            },
        },
    )
    business_db.add(event)
    await business_db.flush()
    await billing.apply_event(business_db, app.state.settings, event, app.state.http)
    assert sub.status == "active"

    paid = [e for e in captured_emails if e["template"] == "pi_invoice_paid"]
    assert len(paid) == 1
    assert paid[0]["to"] == [ctx["owner_email"]]
    assert paid[0]["variables"]["amount"] == "10.00 USD"


async def test_apply_event_without_http_never_sends_email_and_does_not_crash(
    business_db: Any, api: httpx.AsyncClient, captured_emails
):
    """Existing direct callers of ``apply_event`` (e.g. test_pi_manual_billing) omit the
    optional ``http`` argument; the email path must stay a pure no-op in that case."""
    ctx = await _business(api, business_db)
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == ctx["tenant"])
    )
    sub.billing_provider, sub.external_subscription_id, sub.external_customer_id, sub.status = (
        "stripe",
        "sub_noemail",
        "cus_noemail",
        "active",
    )
    await business_db.flush()
    event = PiBillingEvent(
        provider="stripe",
        event_id="evt_noemail",
        event_type="invoice.paid",
        payload={
            "created": int(datetime.now(UTC).timestamp()),
            "object": {
                "id": "in_noemail",
                "object": "invoice",
                "subscription": "sub_noemail",
                "customer": "cus_noemail",
                "currency": "usd",
                "amount_due": 500,
                "amount_paid": 500,
                "status": "paid",
            },
        },
    )
    business_db.add(event)
    await business_db.flush()
    await billing.apply_event(business_db, api._transport.app.state.settings, event)  # no http
    assert captured_emails == []


async def test_decide_payment_without_settings_skips_email(
    api: httpx.AsyncClient, business_db: Any, captured_emails
):
    """Existing direct callers of ``decide_payment`` (e.g. test_pi_manual_billing) omit
    the optional ``settings``/``http`` arguments; must stay a no-op, not raise."""
    ctx = await _business(api, business_db)
    client, tenant = ctx["client"], ctx["tenant"]
    created = await client.post(
        CLIENT + "/payments",
        json={"request_key": str(uuid4()), "plan": "starter", "method": "cash", "months": 1},
    )
    row = created.json()
    await client.post(
        CLIENT + f"/payments/{row['id']}/submit",
        json={"payer_name": "Direct", "paid_on": datetime.now(UTC).date().isoformat()},
    )
    account = await business_db.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant)
    )
    payment = await manual_billing.decide_payment(
        business_db, tenant, UUID(row["id"]), account.created_by_user_id, "approve", "Direct call"
    )
    assert payment.status == "approved"
    assert captured_emails == []
