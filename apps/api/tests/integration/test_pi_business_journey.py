"""The paid Pi journey: business review → operator approval → paid or free plan →
WhatsApp connects (a number held earlier connects by itself) with a notification at
each step. Also: operator platform keys and plan management."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from sqlalchemy import select
from test_service_lifecycle import register

from app.modules.audit.models import AuditEvent
from app.modules.pi_saas import lifecycle_notify
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiOperatorMember,
    PiPlatformSetting,
    PiPoolNumber,
    PiSubscription,
)

pytestmark = pytest.mark.integration
PUBLIC = "https://api.example.test"
DETAILS = {
    "legal_name": "Noor Tailors (Pvt) Ltd",
    "address": "12 Main Boulevard, Gulberg",
    "city": "Lahore",
    "category": "Tailoring",
    "website": "https://noortailors.example",
    "contact_phone": "+92 300 1234567",
    "about": "Custom tailoring and alterations for men and women.",
}


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


def _provider(app) -> FakeProvider:
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    app.state.settings.integrations_public_base_url = PUBLIC
    app.state.settings.pi_whatsapp_requires_approval = True
    return fake


async def _operator(api, business_db, role: str = "owner") -> dict:
    identity = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(identity["user"]["id"]), role=role))
    await business_db.flush()
    return identity


async def _pool(api, provider, *numbers: tuple[str, str]) -> dict[str, dict]:
    customer = (await api.get("/api/v1/operator/pi/numbers")).json()["pool_customer_id"]
    for phone_id, display in numbers:
        provider.add_number(customer, phone_id, display)
    inventory = (await api.get("/api/v1/operator/pi/numbers")).json()
    return {n["display_phone_number"]: n for n in inventory["pool"]}


async def _tenant(business_db, view) -> UUID:
    account = await business_db.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.name == view["business"]["name"])
    )
    return account.tenant_id


async def _titles(client) -> list[str]:
    page = (await client.get("/api/v1/pi-app/notifications")).json()
    return [n["title"] for n in page["items"]]


async def test_review_approval_free_plan_connects_the_held_number(api, app, business_db):
    provider = _provider(app)
    await _operator(api, business_db)
    pool = await _pool(api, provider, ("6100000001", "+1 415 555 0201"))
    client = pi_client(app)
    view = await pi_register(client, "Noor Tailors")
    tenant_id = await _tenant(business_db, view)

    access = (await client.get("/api/v1/pi-app/whatsapp/access")).json()
    assert not access["ok"] and access["reason"] == "REVIEW_REQUIRED"
    assert [s["done"] for s in access["steps"]] == [False, False, False]
    own = await client.post("/api/v1/pi-app/whatsapp/setup", json={})
    assert own.status_code == 409 and own.json()["error"]["code"] == "REVIEW_REQUIRED"

    # Picking a number now only holds it; nobody else can take it meanwhile.
    number_id = pool["+1 415 555 0201"]["id"]
    held = await client.post(f"/api/v1/pi-app/whatsapp/numbers/{number_id}/choose", json={})
    assert held.status_code == 200 and held.json()["state"] == "held", held.text
    other = pi_client(app)
    await pi_register(other, "Zara Boutique")
    assert (await other.get("/api/v1/pi-app/whatsapp/numbers")).json() == []
    access = (await client.get("/api/v1/pi-app/whatsapp/access")).json()
    assert access["held"]["display_phone_number"] == "+1 415 555 0201"

    # Business review: details are required, then the operator decides.
    incomplete = await client.put("/api/v1/pi-app/business-review", json={"legal_name": "Noor"})
    assert incomplete.json()["missing"]
    refused = await client.post("/api/v1/pi-app/business-review/submit")
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "DETAILS_MISSING"
    await client.put("/api/v1/pi-app/business-review", json=DETAILS)
    submitted = await client.post("/api/v1/pi-app/business-review/submit")
    assert submitted.json()["status"] == "submitted" and not submitted.json()["editable"]
    locked = await client.put("/api/v1/pi-app/business-review", json=DETAILS)
    assert locked.status_code == 422

    queue = (await api.get("/api/v1/operator/pi/reviews")).json()
    assert queue["items"][0]["business"] == "Noor Tailors" and queue["counts"]["submitted"] >= 1
    needs = (await api.get("/api/v1/operator/pi/needs-you")).json()
    assert {"reviews", "held_numbers"} <= {i["kind"] for i in needs["items"]}
    no_note = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant_id}/review", json={"action": "request_changes"}
    )
    assert no_note.status_code == 422
    changes = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant_id}/review",
        json={"action": "request_changes", "note": "Please add your shop address in full."},
    )
    assert changes.json()["status"] == "changes_requested"
    mine = (await client.get("/api/v1/pi-app/business-review")).json()
    assert mine["editable"] and "shop address" in mine["note"]
    await client.put("/api/v1/pi-app/business-review", json={**DETAILS, "address": "12-B Main"})
    await client.post("/api/v1/pi-app/business-review/submit")
    approved = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant_id}/review", json={"action": "approve"}
    )
    assert approved.json()["status"] == "approved"
    access = (await client.get("/api/v1/pi-app/whatsapp/access")).json()
    assert access["reason"] == "PAYMENT_REQUIRED"  # a trial isn't enough
    row = await business_db.scalar(
        select(PiPoolNumber).where(PiPoolNumber.phone_number_id == "6100000001")
    )
    assert row.status == "reserved" and row.held_until is not None

    # A private free plan: never listed to businesses; the operator gives it.
    created = await api.post(
        "/api/v1/operator/pi/plans",
        json={
            "key": "partner-free",
            "name": "Partner (free)",
            "monthly_price": "0",
            "visibility": "private",
            "status": "available",
            "features": ["inbox", "knowledge", "campaigns"],
            "allowances": {"messages": 500, "numbers": 1},
        },
    )
    assert created.status_code == 201 and created.json()["free"], created.text
    public = [p["key"] for p in (await client.get("/api/v1/pi-app/plans")).json()]
    assert "partner-free" not in public
    given = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant_id}/subscription",
        json={"plan": "partner-free", "status": "active", "reason": "Launch partner"},
    )
    assert given.status_code == 200, given.text
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant_id)
    )
    assert sub.current_period_end is None  # free plans don't expire

    # The held number connected by itself, with its webhook.
    await business_db.refresh(row)
    assert row.status == "assigned" and row.held_until is None
    assert provider.webhooks["6100000001"][0]["url"] == f"{PUBLIC}/api/v1/webhooks/kapso"
    assert (await client.get("/api/v1/pi-app/whatsapp/access")).json()["ok"]
    titles = await _titles(client)
    for expected in (
        "Welcome to Pi, Noor Tailors",
        "+1 415 555 0201 is held for you",
        "We received your business details",
        "Please update your business details",
        "Your business is approved",
        "Partner (free) is active",
        "Your WhatsApp number is connected",
    ):
        assert expected in titles, (expected, titles)
    billing = (await client.get("/api/v1/pi-app/billing")).json()
    assert any(p["key"] == "partner-free" for p in billing["plans"])  # their own plan shows
    await client.aclose()
    await other.aclose()


async def test_payment_found_by_the_sweep_connects_and_holds_expire(api, app, business_db):
    provider = _provider(app)
    await _operator(api, business_db)
    pool = await _pool(
        api, provider, ("6200000001", "+1 415 555 0301"), ("6200000002", "+1 415 555 0302")
    )
    paying, idle = pi_client(app), pi_client(app)
    paying_view = await pi_register(paying, "Hira Bakers")
    idle_view = await pi_register(idle, "Slow Shop")
    paying_id, idle_id = (
        await _tenant(business_db, paying_view),
        await _tenant(business_db, idle_view),
    )
    await paying.post(
        f"/api/v1/pi-app/whatsapp/numbers/{pool['+1 415 555 0301']['id']}/choose", json={}
    )
    await idle.post(
        f"/api/v1/pi-app/whatsapp/numbers/{pool['+1 415 555 0302']['id']}/choose", json={}
    )
    await paying.put("/api/v1/pi-app/business-review", json=DETAILS)
    await paying.post("/api/v1/pi-app/business-review/submit")
    await api.post(f"/api/v1/operator/pi/accounts/{paying_id}/review", json={"action": "approve"})

    # A payment arrives by another path (Stripe webhook, bank/cash verification).
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == paying_id)
    )
    sub.status, sub.current_period_end = "active", datetime.now(UTC) + timedelta(days=30)
    idle_row = await business_db.scalar(
        select(PiPoolNumber).where(PiPoolNumber.phone_number_id == "6200000002")
    )
    idle_row.held_until = datetime.now(UTC) - timedelta(minutes=1)
    await business_db.flush()
    settings, http = app.state.settings, app.state.http
    await lifecycle_notify.sweep(business_db, settings, http)
    await business_db.flush()

    paid_row = await business_db.scalar(
        select(PiPoolNumber).where(PiPoolNumber.phone_number_id == "6200000001")
    )
    assert paid_row.status == "assigned" and paid_row.assigned_tenant_id == paying_id
    titles = await _titles(paying)
    assert "Payment received: Starter is active" in titles or any(
        t.startswith("Payment received") for t in titles
    )
    assert "Your WhatsApp number is connected" in titles
    await business_db.refresh(idle_row)
    assert idle_row.status == "available" and idle_row.assigned_tenant_id is None
    assert "Your held WhatsApp number was released" in await _titles(idle)
    # Sweeping again changes nothing and sends nothing twice.
    before = len(await _titles(paying))
    await lifecycle_notify.sweep(business_db, settings, http)
    assert len(await _titles(paying)) == before
    assert idle_id
    prefs = await paying.put(
        "/api/v1/pi-app/notification-settings", json={"email": {"trial": False, "bogus": True}}
    )
    by_key = {c["key"]: c for c in prefs.json()["categories"]}
    assert by_key["trial"]["email"] is False and by_key["review"]["email"] is True
    assert "bogus" not in by_key
    await paying.aclose()
    await idle.aclose()


async def test_operator_platform_keys_are_write_only_and_owner_only(api, app, business_db):
    provider = _provider(app)
    me = await _operator(api, business_db, role="operations_admin")
    assert (await api.get("/api/v1/operator/pi/platform-keys")).status_code == 403
    member = await business_db.scalar(
        select(PiOperatorMember).where(PiOperatorMember.user_id == UUID(me["user"]["id"]))
    )
    member.role = "owner"
    await business_db.flush()
    settings = app.state.settings
    listing = (await api.get("/api/v1/operator/pi/platform-keys")).json()
    keys = {i["key"]: i for i in listing["items"]}
    assert keys["KAPSO_API_KEY"]["set"] and keys["KAPSO_API_KEY"]["source"] == "env"
    assert (
        "value" not in keys["KAPSO_API_KEY"] and "PLATFORM_SMTP_HOST" in listing["missing_required"]
    )
    assert keys["DATABASE_URL"]["server_only"] and "value" not in keys["DATABASE_URL"]

    secret = "sk-ant-test-" + "x" * 30 + "WXYZ"
    saved = await api.put(
        "/api/v1/operator/pi/platform-keys/ANTHROPIC_API_KEY", json={"value": secret}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["hint"] == "…WXYZ" and saved.json()["source"] == "dashboard"
    assert secret not in saved.text
    assert settings.anthropic_api_key.get_secret_value() == secret  # live for the AI gateway
    row = await business_db.get(PiPlatformSetting, "ANTHROPIC_API_KEY")
    assert row.value is None and secret not in row.value_encrypted
    models = await api.put(
        "/api/v1/operator/pi/platform-keys/ANTHROPIC_MODELS",
        json={"value": {"agent": "claude-sonnet-5-5", "router": " "}},
    )
    assert models.json()["value"] == {"agent": "claude-sonnet-5-5"}
    order = await api.put(
        "/api/v1/operator/pi/platform-keys/PRIMARY_LLM_PROVIDER", json={"value": "anthropic"}
    )
    assert order.status_code == 200 and settings.primary_llm_provider == "anthropic"
    bad = await api.put(
        "/api/v1/operator/pi/platform-keys/PRIMARY_LLM_PROVIDER", json={"value": "skynet"}
    )
    assert bad.status_code == 422
    url = await api.put(
        "/api/v1/operator/pi/platform-keys/PI_APP_PUBLIC_URL", json={"value": "app.example.com"}
    )
    assert url.status_code == 422
    server = await api.put(
        "/api/v1/operator/pi/platform-keys/DATABASE_URL", json={"value": "x" * 20}
    )
    assert server.status_code == 422 and server.json()["error"]["code"] == "SERVER_ONLY"
    tested = (await api.post("/api/v1/operator/pi/platform-keys/KAPSO_API_KEY/test")).json()
    assert tested["ok"] and "number" in tested["message"]
    template = (await api.get("/api/v1/operator/pi/platform-keys/env-template")).text
    assert "PLATFORM_SMTP_HOST=" in template and "ANTHROPIC_API_KEY=" not in template

    audits = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi_operator.platform_key_saved")
        )
    )
    assert audits and all(secret not in str(a.details) for a in audits)
    removed = await api.delete("/api/v1/operator/pi/platform-keys/ANTHROPIC_API_KEY")
    assert removed.json()["set"] is False and settings.anthropic_api_key is None
    assert provider is not None


async def test_operator_manages_plans(api, app, business_db):
    _provider(app)
    await _operator(api, business_db)
    body = {"key": "pro-plus", "name": "Pro Plus", "monthly_price": "49", "status": "available"}
    assert (await api.post("/api/v1/operator/pi/plans", json=body)).status_code == 201
    assert (await api.post("/api/v1/operator/pi/plans", json=body)).status_code == 409
    unknown = await api.put("/api/v1/operator/pi/plans/pro-plus", json={"features": ["teleport"]})
    assert unknown.status_code == 422
    updated = await api.put(
        "/api/v1/operator/pi/plans/pro-plus",
        json={"features": ["campaigns", "inbox"], "trial_days": 0, "sort_order": 5},
    )
    assert (
        updated.json()["features"] == ["inbox", "campaigns"] and updated.json()["trial_days"] == 0
    )
    trial = await api.delete("/api/v1/operator/pi/plans/starter")
    assert trial.status_code == 422 and trial.json()["error"]["code"] == "TRIAL_PLAN"
    deleted = await api.delete("/api/v1/operator/pi/plans/pro-plus")
    assert deleted.json()["result"] == "deleted"
    catalog = (await api.get("/api/v1/operator/pi/plan-features")).json()
    assert "campaigns" in catalog["features"] and "numbers" in catalog["allowances"]
