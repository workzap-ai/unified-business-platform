"""Standalone Pi SaaS against the real test database.

Kapso, Stripe and AI providers are HTTP/mock doubles. These tests prove the trust
boundaries (audiences, tenant isolation, record-level access, grants, entitlement,
signed webhooks, idempotency) and the onboarding/billing state machines. They do not
prove live provider behaviour.
"""

import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pi_saas_support import (
    ONBOARDING,
    PASSWORD,
    FakeProvider,
    configure,
    kapso_signature,
    pi_client,
    pi_register,
    stripe_signature,
    worker_ctx,
)
from sqlalchemy import func, select
from test_service_lifecycle import register

from app.modules.audit.models import AuditEvent
from app.modules.environments.models import Environment
from app.modules.pi.models import PiMessage, PiSettings, WhatsAppConnection
from app.modules.pi.runtime import process_pi_event, send_pi_message
from app.modules.pi_saas import billing
from app.modules.pi_saas.entitlement import entitlement
from app.modules.pi_saas.jobs import process_pi_billing_event, process_pi_provider_event
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiOperatorAssignment,
    PiOperatorMember,
    PiPlan,
    PiProviderConnection,
    PiProviderEvent,
    PiStaffRequest,
    PiSubscription,
)
from app.modules.products.service import enabled_products
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


async def _account(db, session_view) -> PiBusinessAccount:
    row = await db.scalar(
        select(PiBusinessAccount).where(
            PiBusinessAccount.tenant_id == UUID(session_view["business"]["id"])
        )
    )
    assert row is not None
    return row


async def _onboard(client, steps=(1, 2, 4)) -> None:
    for step in steps:
        response = await client.put(
            f"/api/v1/pi-app/account/onboarding/{step}", json=ONBOARDING[step]
        )
        assert response.status_code == 200, response.text


async def _publish_all_drafts(client) -> None:
    drafts = (await client.get("/api/v1/pi-app/knowledge/drafts")).json()
    for draft in drafts:
        response = await client.post(f"/api/v1/pi-app/knowledge/drafts/{draft['id']}/publish")
        assert response.status_code == 200, response.text


async def _connect(client, provider, db, number: str) -> None:
    response = await client.post("/api/v1/pi-app/whatsapp/setup", json={})
    assert response.status_code == 200, response.text
    row = await db.scalar(
        select(PiProviderConnection)
        .where(PiProviderConnection.status == "setup_pending")
        .order_by(PiProviderConnection.created_at.desc())
    )
    provider.add_number(row.external_customer_id, number, "+1 555 010 0000")
    response = await client.post("/api/v1/pi-app/whatsapp/confirm", json={})
    assert response.status_code == 200 and response.json()["status"] == "connected", response.text


async def _ready_business(app, provider, db, name: str, number: str, launch: bool = True):
    client = pi_client(app)
    view = await pi_register(client, name)
    await _onboard(client)
    await _publish_all_drafts(client)
    await _connect(client, provider, db, number)
    if launch:
        response = await client.post("/api/v1/pi-app/account/launch")
        assert response.status_code == 200, response.text
    return client, view


def _message_event(number: str, sender: str, text: str, mid: str) -> dict:
    return {
        "message": {
            "id": mid,
            "timestamp": "1730092800",
            "type": "text",
            "from": sender,
            "text": {"body": text},
        },
        "conversation": {"id": "conv_1", "phone_number": sender, "phone_number_id": number},
        "phone_number_id": number,
    }


async def _kapso(client, event_type: str, event: dict, key: str | None = None):
    body = json.dumps(event).encode()
    return await client.post(
        "/api/v1/webhooks/kapso",
        content=body,
        headers={
            "content-type": "application/json",
            "x-webhook-event": event_type,
            "x-webhook-signature": kapso_signature(body),
            "x-idempotency-key": key or str(uuid4()),
        },
    )


async def _run_jobs(app, provider, db) -> None:
    """Drain captured jobs through the real job functions (depth-first)."""
    ctx = {**worker_ctx(app, db), "queue": provider.queue}
    while provider.queue.jobs:
        name, args = provider.queue.jobs.pop(0)
        if name == "process_pi_provider_event":
            await process_pi_provider_event(ctx, *args)
        elif name == "process_pi_event":
            await process_pi_event(ctx, *args)
        elif name == "send_pi_message":
            await send_pi_message(ctx, *args)
        elif name == "process_pi_billing_event":
            await process_pi_billing_event(ctx, *args)


# --------------------------------------------------------------------------- tests


async def test_registration_provisions_a_separate_business_and_pi_only_session(
    api, app, provider, business_db
):
    client = pi_client(app)
    view = await pi_register(client)
    assert view["business"]["setup_state"] == "draft" and view["roles"] == ["owner"]
    account = await _account(business_db, view)
    environments = list(
        await business_db.scalars(
            select(Environment.key).where(Environment.tenant_id == account.tenant_id)
        )
    )
    assert sorted(environments) == ["production", "test"]
    for env in (account.production_environment_id, account.test_environment_id):
        scope = WorkspaceScope.system(account.tenant_id, env, frozenset(), "test")
        assert "pi" in await enabled_products(business_db, scope)
        policy = await business_db.scalar(
            select(PiSettings).where(
                PiSettings.tenant_id == account.tenant_id, PiSettings.environment_id == env
            )
        )
        assert policy.auto_reply_enabled is False  # Nothing replies before launch.
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
    )
    assert subscription.status == "trialing" and subscription.trial_ends_at > datetime.now(UTC)
    # The Pi session never reaches Owner OS routes, and vice versa.
    assert (await client.get("/api/v1/customers")).status_code == 401
    assert (await client.get("/api/v1/auth/session")).status_code == 401
    await register(api)  # Owner OS session in the other client
    assert (await api.get("/api/v1/pi-app/account")).status_code == 401
    # Origins are bound to their audience for mutations.
    assert (await client.post("/api/v1/auth/logout")).status_code == 403
    assert (await api.post("/api/v1/pi-app/auth/logout")).status_code == 403
    # The customer journey exposes no internal identifiers.
    body = (await client.get("/api/v1/pi-app/account")).text
    assert str(account.production_environment_id) not in body
    await client.aclose()


async def test_onboarding_is_resumable_and_launch_requires_real_readiness(
    app, provider, business_db
):
    client = pi_client(app)
    view = await pi_register(client)
    await _onboard(client, steps=(1,))
    account = (await client.get("/api/v1/pi-app/account")).json()
    assert account["completed_steps"] == [1] and account["onboarding_step"] == 2
    await _onboard(client, steps=(2, 4))
    account = (await client.get("/api/v1/pi-app/account")).json()
    assert account["setup_state"] == "awaiting_connection"
    ready = {i["key"]: i["done"] for i in account["readiness"]}
    assert ready["knowledge"] is False  # Offerings are a draft until published.
    response = await client.post("/api/v1/pi-app/account/launch")
    assert response.status_code == 409 and "WhatsApp" in response.json()["error"]["message"]
    await _publish_all_drafts(client)
    setup = await client.post("/api/v1/pi-app/whatsapp/setup", json={})
    assert setup.json()["setup_url"].startswith("https://")
    assert (await client.get("/api/v1/pi-app/account")).json()["setup_state"] == "pending_approval"
    # A forged callback number is never linked: the provider does not list it.
    forged = await client.post(
        "/api/v1/pi-app/whatsapp/confirm", json={"phone_number_id": "99999999"}
    )
    assert forged.json()["status"] == "setup_pending"
    row = await business_db.scalar(
        select(PiProviderConnection).where(
            PiProviderConnection.tenant_id == UUID(view["business"]["id"])
        )
    )
    provider.add_number(row.external_customer_id, "1098765432", "+1 555 010 0000")
    confirmed = await client.post("/api/v1/pi-app/whatsapp/confirm", json={})
    assert confirmed.json()["status"] == "connected" and confirmed.json()["setup_url"] is None
    assert "1098765432" not in confirmed.text  # Provider ids stay server-side.
    launched = await client.post("/api/v1/pi-app/account/launch")
    assert launched.status_code == 200 and launched.json()["setup_state"] == "active"
    account_row = await _account(business_db, view)
    prod = await business_db.scalar(
        select(PiSettings.auto_reply_enabled).where(
            PiSettings.tenant_id == account_row.tenant_id,
            PiSettings.environment_id == account_row.production_environment_id,
        )
    )
    test = await business_db.scalar(
        select(PiSettings.auto_reply_enabled).where(
            PiSettings.tenant_id == account_row.tenant_id,
            PiSettings.environment_id == account_row.test_environment_id,
        )
    )
    assert prod is True and test is False
    kapso_calls = [r for r in provider.requests if "api.kapso.ai" in str(r.url)]
    assert all(r.headers["x-api-key"] for r in kapso_calls)
    await client.aclose()


async def test_kapso_webhooks_are_verified_deduplicated_and_routed_to_one_business(
    api, app, provider, business_db
):
    client_a, view_a = await _ready_business(
        app, provider, business_db, "Alpha", "1111111111", launch=False
    )
    client_b, view_b = await _ready_business(
        app, provider, business_db, "Beta", "2222222222", launch=False
    )
    event = _message_event("1111111111", "15550001111", "Hello Alpha", "wamid.alpha1")
    body = json.dumps(event).encode()
    bad = await client_a.post(
        "/api/v1/webhooks/kapso",
        content=body,
        headers={"x-webhook-event": "whatsapp.message.received", "x-webhook-signature": "0" * 64},
    )
    assert bad.status_code == 401
    assert await business_db.scalar(select(func.count()).select_from(PiProviderEvent)) == 0
    for _ in range(2):  # Provider retry with the same idempotency key.
        response = await _kapso(client_a, "whatsapp.message.received", event, key="idem-1")
        assert response.status_code == 200
    await _run_jobs(app, provider, business_db)
    messages = list(
        await business_db.scalars(
            select(PiMessage).where(PiMessage.provider_message_id == "wamid.alpha1")
        )
    )
    assert len(messages) == 1
    assert messages[0].tenant_id == UUID(view_a["business"]["id"])
    assert messages[0].status == "skipped"  # Not launched: stored, never answered.
    row = await business_db.scalar(
        select(PiProviderEvent).where(PiProviderEvent.idempotency_key == "idem-1")
    )
    assert row.duplicate_count == 1 and row.status == "processed"
    a_list = (await client_a.get("/api/v1/pi-app/pi/conversations")).json()
    b_list = (await client_b.get("/api/v1/pi-app/pi/conversations")).json()
    assert a_list["total"] == 1 and b_list["total"] == 0
    other = a_list["items"][0]["id"]
    assert (
        await client_b.get(f"/api/v1/pi-app/pi/conversations/{other}/messages")
    ).status_code == 404
    # A number disconnected at the provider stops the connection.
    await _kapso(
        client_a,
        "whatsapp.phone_number.disconnected",
        {
            "phone_number_id": "1111111111",
            "customer": {"id": ""},
            "event": "whatsapp.phone_number.disconnected",
        },
    )
    await _run_jobs(app, provider, business_db)
    connection = await business_db.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.phone_number_id == "1111111111")
    )
    assert connection.status == "disabled"
    whatsapp = (await client_a.get("/api/v1/pi-app/whatsapp")).json()
    assert whatsapp["production"]["status"] == "disconnected"
    await client_a.aclose()
    await client_b.aclose()


async def test_lapsed_plan_blocks_automation_and_queued_sends(app, provider, business_db):
    client, view = await _ready_business(app, provider, business_db, "Gamma", "3333333333")
    account = await _account(business_db, view)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
    )
    subscription.trial_ends_at = datetime.now(UTC) - timedelta(minutes=1)
    await business_db.flush()
    plan = await entitlement(business_db, account.tenant_id)
    assert plan.automation is False and plan.reason == "TRIAL_ENDED"
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("3333333333", "15550003333", "Hi", "wamid.g1"),
    )
    await _run_jobs(app, provider, business_db)
    message = await business_db.scalar(
        select(PiMessage).where(PiMessage.provider_message_id == "wamid.g1")
    )
    assert message.status == "skipped" and message.error_code == "TRIAL_ENDED"
    # A reply queued before the plan lapsed is not delivered afterwards.
    queued = PiMessage(
        tenant_id=message.tenant_id,
        environment_id=message.environment_id,
        conversation_id=message.conversation_id,
        direction="outbound",
        sender_type="ai",
        body="Queued earlier",
        status="queued",
    )
    business_db.add(queued)
    await business_db.flush()
    before = len([r for r in provider.requests if r.url.path.endswith("/messages")])
    await send_pi_message(worker_ctx(app, business_db), str(queued.id))
    await business_db.refresh(queued)
    assert queued.status == "skipped" and queued.error_code == "TRIAL_ENDED"
    assert len([r for r in provider.requests if r.url.path.endswith("/messages")]) == before
    await client.aclose()


async def test_signed_billing_webhooks_drive_the_subscription_lifecycle(app, provider, business_db):
    client = pi_client(app)
    view = await pi_register(client)
    tenant = view["business"]["id"]
    plan = await business_db.scalar(select(PiPlan).where(PiPlan.key == "growth"))
    plan.monthly_price, plan.stripe_price_id = Decimal("49.00"), "price_growthTEST1"
    await business_db.flush()
    checkout = await client.post("/api/v1/pi-app/billing/checkout", json={"plan": "growth"})
    assert checkout.status_code == 200 and checkout.json()["url"].startswith(
        "https://checkout.stripe.com"
    )
    sent = next(r for r in provider.requests if r.url.path == "/v1/checkout/sessions")
    assert f"client_reference_id={tenant}" in sent.content.decode()
    assert "idempotency-key" in sent.headers

    async def post(event: dict, *, sign: bool = True):
        body = json.dumps(event).encode()
        return await client.post(
            "/api/v1/webhooks/pi-billing/stripe",
            content=body,
            headers={
                "content-type": "application/json",
                "stripe-signature": stripe_signature(body) if sign else "t=1,v1=bad",
            },
        )

    now = int(time.time())
    subscription_obj = {
        "id": "sub_1",
        "object": "subscription",
        "status": "active",
        "customer": "cus_1",
        "metadata": {"tenant_id": tenant, "plan_key": "growth"},
        "current_period_start": now,
        "current_period_end": now + 30 * 86400,
    }
    assert (
        await post(
            {
                "id": "evt_0",
                "object": "event",
                "type": "customer.subscription.updated",
                "created": now,
                "data": {"object": subscription_obj},
            },
            sign=False,
        )
    ).status_code == 401
    active = {
        "id": "evt_1",
        "object": "event",
        "type": "customer.subscription.updated",
        "created": now,
        "data": {"object": subscription_obj},
    }
    assert (await post(active)).status_code == 200
    assert (await post(active)).status_code == 200  # duplicate delivery
    stale = {
        "id": "evt_old",
        "object": "event",
        "type": "customer.subscription.updated",
        "created": now - 600,
        "data": {"object": {**subscription_obj, "status": "past_due"}},
    }
    await post(stale)
    await _run_jobs(app, provider, business_db)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(tenant))
    )
    assert subscription.status == "active" and subscription.plan_key == "growth"
    jobs_for_duplicate = await business_db.scalar(
        select(func.count())
        .select_from(billing.PiBillingEvent)
        .where(billing.PiBillingEvent.event_id == "evt_1")
    )
    assert jobs_for_duplicate == 1
    failed = {
        "id": "evt_2",
        "object": "event",
        "type": "invoice.payment_failed",
        "created": now + 5,
        "data": {
            "object": {
                "id": "in_1",
                "object": "invoice",
                "status": "open",
                "customer": "cus_1",
                "subscription": "sub_1",
                "amount_due": 4900,
                "amount_paid": 0,
                "currency": "usd",
                "number": "PI-0001",
                "hosted_invoice_url": "https://invoice.stripe.com/i/1",
            }
        },
    }
    await post(failed)
    await _run_jobs(app, provider, business_db)
    await business_db.refresh(subscription)
    assert subscription.status == "past_due" and subscription.grace_ends_at > datetime.now(UTC)
    assert (await entitlement(business_db, UUID(tenant))).sending is True  # within grace
    bill = (await client.get("/api/v1/pi-app/billing")).json()
    assert (
        bill["invoices"][0]["amount_due"] == "49.00"
        and bill["subscription"]["status"] == "past_due"
    )
    subscription.grace_ends_at = datetime.now(UTC) - timedelta(seconds=1)
    await business_db.flush()
    assert await billing.sweep_lifecycle(business_db) == 1
    assert (await entitlement(business_db, UUID(tenant))).sending is False
    await client.aclose()


async def _member_client(app, owner, role: str):
    email = f"{role}-{uuid4().hex}@example.com"
    response = await owner.post(
        "/api/v1/pi-app/team",
        json={
            "email": email,
            "display_name": role.title(),
            "role": role,
            "temporary_password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    client = pi_client(app)
    login = await client.post(
        "/api/v1/pi-app/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    client.headers["x-csrf-token"] = client.cookies["pi_csrf"]
    return client, login.json(), response.json()["membership_id"]


async def test_members_only_see_assigned_conversations_and_view_only_cannot_act(
    app, provider, business_db
):
    owner, view = await _ready_business(
        app, provider, business_db, "Delta", "4444444444", launch=False
    )
    for sender, mid in (("15550004441", "wamid.d1"), ("15550004442", "wamid.d2")):
        await _kapso(
            owner, "whatsapp.message.received", _message_event("4444444444", sender, "Hello", mid)
        )
    await _run_jobs(app, provider, business_db)
    subscription = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(view["business"]["id"]))
    )
    subscription.plan_key = "growth"  # Starter has two seats; this test needs three.
    await business_db.flush()
    member, member_view, member_membership = await _member_client(app, owner, "member")
    viewer, _, _ = await _member_client(app, owner, "viewer")
    items = (await owner.get("/api/v1/pi-app/pi/conversations")).json()["items"]
    mine, other = items[0]["id"], items[1]["id"]
    assert (await member.get("/api/v1/pi-app/pi/conversations")).json()["total"] == 0
    assigned = await owner.post(
        f"/api/v1/pi-app/pi/conversations/{mine}/assign",
        json={"user_id": member_view["user"]["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    visible = (await member.get("/api/v1/pi-app/pi/conversations")).json()
    assert [c["id"] for c in visible["items"]] == [mine]
    for path in (
        f"/api/v1/pi-app/pi/conversations/{other}/messages",
        f"/api/v1/pi-app/pi/conversations/{other}/history",
        f"/api/v1/pi-app/pi/conversations/{other}/context",
    ):
        assert (await member.get(path)).status_code == 404, path
    other_customer = items[1]["customer_id"]
    assert (
        await member.get(f"/api/v1/pi-app/pi/customers/{other_customer}/profile")
    ).status_code == 404
    customers = (await member.get("/api/v1/pi-app/pi/customers")).json()
    assert customers["total"] == 1  # counts never include hidden records
    assert (
        await member.post(f"/api/v1/pi-app/pi/conversations/{mine}/assign", json={"user_id": None})
    ).status_code == 403
    # View-only sees everything but cannot change anything.
    assert (await viewer.get("/api/v1/pi-app/pi/conversations")).json()["total"] == 2
    assert (
        await viewer.post(f"/api/v1/pi-app/pi/conversations/{mine}/actions/takeover")
    ).status_code == 403
    assert (
        await viewer.post(f"/api/v1/pi-app/pi/conversations/{mine}/messages", json={"body": "Hi"})
    ).status_code == 403
    assert (
        await viewer.post(f"/api/v1/pi-app/pi/conversations/{mine}/notes", json={"body": "x"})
    ).status_code == 403
    # Billing is its own permission.
    assert (await member.get("/api/v1/pi-app/billing")).status_code == 403
    # Revoked access is checked again on the next request.
    assert (await owner.delete(f"/api/v1/pi-app/team/{member_membership}")).status_code == 204
    revoked = await member.get("/api/v1/pi-app/pi/conversations")
    # Revocation clears the session's business selection: nothing is reachable.
    assert revoked.status_code in (401, 403, 409) and "items" not in revoked.json()
    assert (
        await member.put(
            "/api/v1/pi-app/auth/business", json={"business_id": view["business"]["id"]}
        )
    ).status_code == 404
    for c in (owner, member, viewer):
        await c.aclose()


async def test_operator_access_is_scoped_granted_and_audited(api, app, provider, business_db):
    client_a, view_a = await _ready_business(
        app, provider, business_db, "Epsilon", "5555555555", launch=False
    )
    client_b, view_b = await _ready_business(
        app, provider, business_db, "Zeta", "6666666666", launch=False
    )
    await _kapso(
        client_a,
        "whatsapp.message.received",
        _message_event("5555555555", "15550005555", "Secret", "wamid.e1"),
    )
    await _run_jobs(app, provider, business_db)
    identity = await register(api)  # Owner OS user
    assert (await api.get("/api/v1/operator/pi/accounts")).status_code == 403  # not an operator
    member = PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="support")
    business_db.add(member)
    await business_db.flush()
    business_db.add(
        PiOperatorAssignment(operator_id=member.id, tenant_id=UUID(view_a["business"]["id"]))
    )
    await business_db.flush()
    listed = (await api.get("/api/v1/operator/pi/accounts")).json()
    assert [i["tenant_id"] for i in listed["items"]] == [view_a["business"]["id"]]
    assert (
        await api.get(f"/api/v1/operator/pi/accounts/{view_b['business']['id']}")
    ).status_code == 404
    detail = (await api.get(f"/api/v1/operator/pi/accounts/{view_a['business']['id']}")).json()
    assert "Secret" not in json.dumps(detail) and "subscription" not in detail  # no billing cap
    tenant = view_a["business"]["id"]
    assert (
        await api.get(f"/api/v1/operator/pi/accounts/{tenant}/conversations")
    ).status_code == 403
    requested = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant}/support-requests",
        json={"scope": "conversations", "reason": "Customer reported a missing reply"},
    )
    assert requested.status_code == 201
    assert (
        await api.get(f"/api/v1/operator/pi/accounts/{tenant}/conversations")
    ).status_code == 403
    grant_id = requested.json()["id"]
    approved = await client_a.post(f"/api/v1/pi-app/account/support-access/{grant_id}/approve")
    assert approved.status_code == 200
    conversations = await api.get(f"/api/v1/operator/pi/accounts/{tenant}/conversations")
    assert conversations.status_code == 200 and len(conversations.json()) == 1
    audited = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "pi_operator.conversations_read",
            AuditEvent.tenant_id == UUID(tenant),
        )
    )
    assert audited == 1
    await client_a.post(f"/api/v1/pi-app/account/support-access/{grant_id}/revoke")
    assert (
        await api.get(f"/api/v1/operator/pi/accounts/{tenant}/conversations")
    ).status_code == 403
    # A Pi customer session can never reach operator routes.
    assert (await client_a.get("/api/v1/operator/pi/accounts")).status_code == 401
    summary = (await api.get("/api/v1/operator/pi/summary")).json()
    assert summary["businesses"] == 1
    for c in (client_a, client_b):
        await c.aclose()


async def test_human_approved_mode_holds_ai_replies_until_approved(
    app, provider, business_db, monkeypatch
):
    from test_pi_service_conversations import mock_turns, turn

    mock_turns(monkeypatch, turn(reply="Aapki website ka main maqsad kya hai?"))
    client, view = await _ready_business(
        app, provider, business_db, "Eta", "7777777777", launch=False
    )
    steps = dict(ONBOARDING[4], automation_mode="human_approved")
    assert (await client.put("/api/v1/pi-app/account/onboarding/4", json=steps)).status_code == 200
    assert (await client.post("/api/v1/pi-app/account/launch")).status_code == 200
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("7777777777", "15550007777", "Website chahiye", "wamid.h1"),
    )
    await _run_jobs(app, provider, business_db)
    drafted = await business_db.scalar(
        select(PiMessage).where(
            PiMessage.direction == "outbound", PiMessage.status == "pending_approval"
        )
    )
    assert drafted is not None
    assert not [r for r in provider.requests if r.url.path.endswith("/messages")]
    approvals = (await client.get("/api/v1/pi-app/pi/approvals")).json()
    assert [a["message_id"] for a in approvals] == [str(drafted.id)]
    approved = await client.post(
        f"/api/v1/pi-app/pi/conversations/{drafted.conversation_id}/messages/{drafted.id}/approve",
        json={},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "queued"
    await _run_jobs(app, provider, business_db)
    await business_db.refresh(drafted)
    assert drafted.status == "sent"
    sends = [r for r in provider.requests if r.url.path.endswith("/messages")]
    assert len(sends) == 1 and "/meta/whatsapp/v24.0/7777777777/messages" in str(sends[0].url)
    assert sends[0].headers["x-api-key"]
    await client.aclose()


async def test_teach_pi_drafts_are_not_used_until_published_and_team_only_never(
    app, provider, business_db
):
    client = pi_client(app)
    await pi_register(client)
    draft = await client.post(
        "/api/v1/pi-app/knowledge/drafts",
        json={"title": "Opening hours", "content": "Our studio welcomes visitors every weekday."},
    )
    internal = await client.post(
        "/api/v1/pi-app/knowledge/drafts",
        json={
            "title": "Supplier",
            "content": "Our studio supplier discount is internal.",
            "customer_visible": False,
        },
    )
    search = "/api/v1/pi-app/pi/knowledge/search?q=studio"
    assert (await client.get(search)).json() == []
    await client.post(f"/api/v1/pi-app/knowledge/drafts/{draft.json()['id']}/publish")
    await client.post(f"/api/v1/pi-app/knowledge/drafts/{internal.json()['id']}/publish")
    results = (await client.get(search)).json()
    assert len(results) == 1 and "weekday" in results[0]["snippet"]
    taught = await client.post(
        "/api/v1/pi-app/knowledge/teach", json={"text": "We now close at five on Fridays."}
    )
    assert taught.status_code == 201 and taught.json()["status"] == "draft"  # no AI: verbatim draft
    await client.aclose()


async def test_ask_owner_turns_unknown_questions_into_answers_and_knowledge(
    app, provider, business_db, monkeypatch
):
    from test_pi_pipeline import intent, scripted_gateway

    scripted_gateway(monkeypatch, lambda text: intent("support"))
    client = pi_client(app)
    await pi_register(client, "Theta", offer_type="products")
    steps = {**ONBOARDING, 2: {"offer_type": "products", "offerings": [{"name": "Router"}]}}
    for step in (1, 2, 4):
        body = dict(steps[step], automation_mode="ai_led") if step == 4 else steps[step]
        assert (
            await client.put(f"/api/v1/pi-app/account/onboarding/{step}", json=body)
        ).status_code == 200
    await _publish_all_drafts(client)
    await _connect(client, provider, business_db, "8888888888")
    assert (await client.post("/api/v1/pi-app/account/launch")).status_code == 200
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("8888888888", "15550008888", "Do you ship to Dubai?", "wamid.q1"),
    )
    await _run_jobs(app, provider, business_db)
    request = await business_db.scalar(select(PiStaffRequest))
    assert request is not None and "Dubai" in request.question
    listed = (await client.get("/api/v1/pi-app/staff-requests")).json()
    assert [r["id"] for r in listed] == [str(request.id)]
    answered = await client.post(
        f"/api/v1/pi-app/staff-requests/{request.id}/answer",
        json={"answer": "Yes, we ship to Dubai within the week.", "mode": "reusable"},
    )
    assert answered.status_code == 200 and answered.json()["status"] == "published"
    results = (await client.get("/api/v1/pi-app/pi/knowledge/search?q=Dubai")).json()
    assert results and "ship to Dubai" in results[0]["snippet"]
    reply = await business_db.scalar(
        select(PiMessage).where(PiMessage.sender_type == "human", PiMessage.direction == "outbound")
    )
    assert reply is not None and reply.body.startswith("Yes, we ship")
    await client.aclose()


async def test_two_businesses_of_one_owner_never_share_data(app, provider, business_db):
    client = pi_client(app)
    first = await pi_register(client, "Iota")
    second = (await client.post("/api/v1/pi-app/businesses", json={"name": "Kappa"})).json()
    assert second["business"]["name"] == "Kappa" and len(second["businesses"]) == 2
    assert first["business"]["id"] != second["business"]["id"]
    await client.post(
        "/api/v1/pi-app/knowledge/drafts",
        json={"title": "Kappa only", "content": "Kappa pricing notes."},
    )
    switched = await client.put(
        "/api/v1/pi-app/auth/business", json={"business_id": first["business"]["id"]}
    )
    assert switched.json()["business"]["name"] == "Iota"
    assert (await client.get("/api/v1/pi-app/knowledge/drafts")).json() == []
    await client.aclose()
