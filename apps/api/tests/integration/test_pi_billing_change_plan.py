"""Plan change with proration: saved-card upgrade/downgrade on an existing Stripe
subscription (no new checkout). Mirrors ``test_pi_saas.py``'s signed-webhook billing
test (same ``provider``/``business_db`` fixtures, same ``process_pi_billing_event``
drain), plus guard rails that are specific to this new path.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pi_saas_support import (
    FakeProvider,
    configure,
    pi_client,
    pi_register,
    stripe_signature,
    worker_ctx,
)
from sqlalchemy import select

from app.modules.pi_saas.jobs import process_pi_billing_event
from app.modules.pi_saas.models import PiPlan, PiSubscription

pytestmark = pytest.mark.integration
CLIENT = "/api/v1/pi-app/billing"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


async def _priced(business_db, key: str, price: str, stripe_price_id: str) -> PiPlan:
    plan = await business_db.scalar(select(PiPlan).where(PiPlan.key == key))
    plan.monthly_price, plan.stripe_price_id = Decimal(price), stripe_price_id
    await business_db.flush()
    return plan


async def _subscribed_business(app, provider, business_db) -> tuple[object, str]:
    """A business already on a real (faked) Stripe subscription for "starter", the
    same way checkout + a signed webhook would leave it — the precondition every
    plan-change call requires."""
    await _priced(business_db, "starter", "19.00", "price_starterTEST1")
    await _priced(business_db, "growth", "49.00", "price_growthTEST1")
    client = pi_client(app)
    view = await pi_register(client)
    tenant = view["business"]["id"]
    checkout = await client.post(CLIENT + "/checkout", json={"plan": "starter"})
    assert checkout.status_code == 200, checkout.text
    now = int(datetime.now(UTC).timestamp())
    event = {
        "id": "evt_subscribed",
        "object": "event",
        "type": "customer.subscription.updated",
        "created": now,
        "data": {
            "object": {
                "id": "sub_1",
                "object": "subscription",
                "status": "active",
                "customer": "cus_1",
                "metadata": {"tenant_id": tenant, "plan_key": "starter"},
                "current_period_start": now,
                "current_period_end": now + 30 * 86400,
            }
        },
    }
    body = json.dumps(event).encode()
    webhook = await client.post(
        "/api/v1/webhooks/pi-billing/stripe",
        content=body,
        headers={"content-type": "application/json", "stripe-signature": stripe_signature(body)},
    )
    assert webhook.status_code == 200, webhook.text
    await _drain(app, provider, business_db)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(tenant))
    )
    assert subscription.billing_provider == "stripe" and subscription.status == "active"
    assert subscription.plan_key == "starter"
    return client, tenant


async def _drain(app, provider, db) -> None:
    ctx = worker_ctx(app, db)
    while provider.queue.jobs:
        name, args = provider.queue.jobs.pop(0)
        if name == "process_pi_billing_event":
            await process_pi_billing_event(ctx, *args)


async def test_preview_change_plan_returns_stripes_prorated_amount(app, provider, business_db):
    client, _tenant = await _subscribed_business(app, provider, business_db)
    provider.subscription_items["sub_1"] = [{"id": "si_1", "price": {"id": "price_starterTEST1"}}]
    provider.upcoming_invoice = {"amount_due": 3217, "currency": "usd"}

    preview = await client.get(CLIENT + "/change-plan/preview", params={"plan": "growth"})
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "plan": "growth",
        "amount_due_now": "32.17",
        "currency": "USD",
        "new_recurring_amount": "49.00",
        "new_recurring_currency": "USD",
    }
    fetched_item = next(
        r
        for r in provider.requests
        if r.url.path == "/v1/subscriptions/sub_1" and r.method == "GET"
    )
    assert fetched_item is not None
    upcoming = next(r for r in provider.requests if r.url.path == "/v1/invoices/upcoming")
    assert upcoming.url.params["subscription"] == "sub_1"
    assert upcoming.url.params["subscription_items[0][id]"] == "si_1"
    assert upcoming.url.params["subscription_items[0][price]"] == "price_growthTEST1"
    await client.aclose()


async def test_change_plan_applies_through_existing_webhook_handling(app, provider, business_db):
    client, tenant = await _subscribed_business(app, provider, business_db)
    provider.subscription_items["sub_1"] = [{"id": "si_1", "price": {"id": "price_starterTEST1"}}]

    commit = await client.post(CLIENT + "/change-plan", json={"plan": "growth"})
    assert commit.status_code == 200, commit.text
    assert commit.json() == {"plan": "starter", "pending_plan": "growth", "status": "active"}
    sent = next(
        r
        for r in provider.requests
        if r.url.path == "/v1/subscriptions/sub_1" and r.method == "POST"
    )
    body = sent.content.decode()
    assert "items%5B0%5D%5Bid%5D=si_1" in body
    assert "items%5B0%5D%5Bprice%5D=price_growthTEST1" in body
    assert "proration_behavior=create_prorations" in body
    assert "idempotency-key" in sent.headers

    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(tenant))
    )
    assert subscription.plan_key == "starter" and subscription.pending_plan_key == "growth"

    # The existing customer.subscription.updated handling confirms it for real once
    # Stripe's webhook lands — no code of its own for proration confirmation.
    now = int(datetime.now(UTC).timestamp())
    confirm = {
        "id": "evt_confirm_change",
        "object": "event",
        "type": "customer.subscription.updated",
        "created": now,
        "data": {
            "object": {
                "id": "sub_1",
                "object": "subscription",
                "status": "active",
                "customer": "cus_1",
                "current_period_start": now,
                "current_period_end": now + 30 * 86400,
                "items": {"data": [{"price": {"id": "price_growthTEST1"}}]},
            }
        },
    }
    body = json.dumps(confirm).encode()
    webhook = await client.post(
        "/api/v1/webhooks/pi-billing/stripe",
        content=body,
        headers={"content-type": "application/json", "stripe-signature": stripe_signature(body)},
    )
    assert webhook.status_code == 200, webhook.text
    await _drain(app, provider, business_db)
    await business_db.refresh(subscription)
    assert subscription.plan_key == "growth" and subscription.pending_plan_key is None
    await client.aclose()


async def test_change_plan_rejects_a_manual_non_stripe_subscription(app, provider, business_db):
    await _priced(business_db, "growth", "49.00", "price_growthTEST1")
    client = pi_client(app)
    await pi_register(client)

    preview = await client.get(CLIENT + "/change-plan/preview", params={"plan": "growth"})
    assert preview.status_code == 409
    assert preview.json()["error"]["code"] == "PLAN_CHANGE_UNAVAILABLE"

    commit = await client.post(CLIENT + "/change-plan", json={"plan": "growth"})
    assert commit.status_code == 409
    assert commit.json()["error"]["code"] == "PLAN_CHANGE_UNAVAILABLE"
    await client.aclose()


async def test_change_plan_rejects_a_canceled_stripe_subscription(app, provider, business_db):
    await _priced(business_db, "growth", "49.00", "price_growthTEST1")
    client = pi_client(app)
    view = await pi_register(client)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(view["business"]["id"]))
    )
    subscription.billing_provider = "stripe"
    subscription.external_subscription_id = "sub_gone"
    subscription.status = "canceled"
    await business_db.flush()

    commit = await client.post(CLIENT + "/change-plan", json={"plan": "growth"})
    assert commit.status_code == 409
    assert commit.json()["error"]["code"] == "PLAN_CHANGE_UNAVAILABLE"
    await client.aclose()


async def test_change_plan_rejects_choosing_the_current_plan(app, provider, business_db):
    client, _tenant = await _subscribed_business(app, provider, business_db)
    provider.subscription_items["sub_1"] = [{"id": "si_1", "price": {"id": "price_starterTEST1"}}]

    commit = await client.post(CLIENT + "/change-plan", json={"plan": "starter"})
    assert commit.status_code == 409
    assert commit.json()["error"]["code"] == "SAME_PLAN"
    await client.aclose()
