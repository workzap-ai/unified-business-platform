"""Kapso for Owner OS workspaces and the platform number pool.

Covered: own number via setup link; automatic webhook; inbound routing; the pool
(blocking warnings, one owner per number, operator offer then the business accepts,
retire on release); connecting an existing number without storing its token."""

import json
from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from sqlalchemy import func, select, text
from test_pi_pipeline import pi_workspace
from test_pi_saas import _kapso, _message_event, _run_jobs
from test_service_lifecycle import register

from app.modules.pi.models import PiMessage, WhatsAppConnection
from app.modules.pi_saas.models import (
    PiOperatorMember,
    PiPlatformState,
    PiPoolNumber,
    PiProviderConnection,
)

pytestmark = pytest.mark.integration
PUBLIC = "https://api.example.test"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


def _provider(app) -> FakeProvider:
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    app.state.settings.integrations_public_base_url = PUBLIC
    return fake


async def test_owner_os_workspace_connects_its_own_number_through_kapso(api, app, business_db):
    pi = await pi_workspace(api, business_db, number="111222333")  # an older Meta number
    provider = _provider(app)
    try:
        status = (await api.get("/api/v1/pi/whatsapp/kapso")).json()
        assert status["provider_available"] and status["webhook_ready"]
        started = await api.post("/api/v1/pi/whatsapp/kapso/setup", json={})
        assert started.status_code == 200, started.text
        assert started.json()["setup_url"].startswith("https://app.kapso.ai/")
        row = await business_db.scalar(
            select(PiProviderConnection).where(PiProviderConnection.tenant_id == UUID(pi.tenant_id))
        )
        provider.add_number(row.external_customer_id, "4040404040", "+92 300 1234567")
        confirmed = await api.post("/api/v1/pi/whatsapp/kapso/confirm")
        assert confirmed.json()["status"] == "connected"
        # The number's webhook was created for us, once.
        [hook] = provider.webhooks["4040404040"]
        assert hook["url"] == f"{PUBLIC}/api/v1/webhooks/kapso"
        assert "whatsapp.message.received" in hook["events"]
        await api.post("/api/v1/pi/whatsapp/kapso/confirm")
        assert len(provider.webhooks["4040404040"]) == 1
        # The Kapso number is now the workspace's active number; the Meta one stops.
        current = (await api.get("/api/v1/pi/whatsapp")).json()
        assert current["provider"] == "kapso" and current["status"] == "active"
        old = await business_db.scalar(
            select(WhatsAppConnection).where(WhatsAppConnection.phone_number_id == "111222333")
        )
        assert old.status == "disabled"
        # A customer message on the Kapso number reaches this Owner OS workspace.
        await _kapso(
            api,
            "whatsapp.message.received",
            _message_event("4040404040", "923001234567", "Salam, order status?", "wamid.os1"),
        )
        await _run_jobs(app, provider, business_db)
        message = await business_db.scalar(
            select(PiMessage).where(PiMessage.provider_message_id == "wamid.os1")
        )
        assert message is not None and str(message.tenant_id) == pi.tenant_id
    finally:
        await pi.close()


async def _operator(api, business_db) -> dict:
    identity = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner"))
    await business_db.flush()
    return identity


async def test_pool_numbers_are_chosen_once_offered_and_retired(api, app, business_db):
    provider = _provider(app)
    first, second = pi_client(app), pi_client(app)
    await pi_register(first, "Noor Tailors")
    await pi_register(second, "Zara Boutique")
    await _operator(api, business_db)
    inventory = (await api.get("/api/v1/operator/pi/numbers")).json()
    pool_customer = inventory["pool_customer_id"]
    state = await business_db.get(PiPlatformState, "kapso_pool_customer")
    assert state.value["customer_id"] == pool_customer
    provider.add_number(pool_customer, "5000000001", "+1 415 555 0101")
    provider.add_number(pool_customer, "5000000002", "+1 415 555 0102")
    provider.add_number(
        pool_customer, "5000000003", "+1 555 453 9407", name_status="PENDING_REVIEW"
    )
    provider.add_number("someone-else", "5000000009", "+1 212 555 0100")
    inventory = (await api.get("/api/v1/operator/pi/numbers")).json()
    pool = {n["display_phone_number"]: n for n in inventory["pool"]}
    assert set(pool) == {"+1 415 555 0101", "+1 415 555 0102", "+1 555 453 9407"}
    test_number = pool["+1 555 453 9407"]
    assert {"meta_test_number", "display_name_not_approved"} <= set(test_number["warnings"])
    foreign = next(n for n in inventory["numbers"] if n["phone_number_id"] == "5000000009")
    assert not foreign["in_pool"] and "default_customer" in foreign["warnings"]
    await api.patch(
        f"/api/v1/operator/pi/numbers/{pool['+1 415 555 0101']['id']}",
        json={"price_label": "Included in Growth", "country": "US"},
    )

    offered = (await first.get("/api/v1/pi-app/whatsapp/numbers")).json()
    assert [n["display_phone_number"] for n in offered] == ["+1 415 555 0101", "+1 415 555 0102"]
    assert offered[0]["price_label"] == "Included in Growth" and "phone_number_id" not in offered[0]
    chosen = await first.post(f"/api/v1/pi-app/whatsapp/numbers/{offered[0]['id']}/choose", json={})
    assert chosen.status_code == 200 and chosen.json()["status"] == "connected", chosen.text
    assert provider.webhooks["5000000001"][0]["url"] == f"{PUBLIC}/api/v1/webhooks/kapso"
    taken = await second.post(f"/api/v1/pi-app/whatsapp/numbers/{offered[0]['id']}/choose", json={})
    assert taken.status_code == 409
    blocked = await second.post(
        f"/api/v1/pi-app/whatsapp/numbers/{test_number['id']}/choose", json={}
    )
    assert blocked.status_code in (409, 422)

    # The operator sets the other number aside for an Owner OS workspace; it accepts.
    workspace = await pi_workspace(api, business_db, number="777000111")
    try:
        # The workspace owner is also an operator here, so one session can do both.
        business_db.add(
            PiOperatorMember(user_id=UUID(workspace.identity["user"]["id"]), role="owner")
        )
        await business_db.flush()
        offer = await api.post(
            f"/api/v1/operator/pi/numbers/{pool['+1 415 555 0102']['id']}/offer",
            json={"tenant_id": workspace.tenant_id, "environment_id": workspace.environment_id},
        )
        assert offer.status_code == 200, offer.text
        assert offer.json()["status"] == "reserved"
        assert not [
            n
            for n in (await second.get("/api/v1/pi-app/whatsapp/numbers")).json()
            if n["display_phone_number"] == "+1 415 555 0102"
        ]  # reserved numbers are not offered to others
        mine = (await api.get("/api/v1/pi/whatsapp/numbers")).json()
        assert mine[0]["offered_to_you"] is True
        accepted = await api.post(f"/api/v1/pi/whatsapp/numbers/{mine[0]['id']}/choose")
        assert accepted.status_code == 200 and accepted.json()["status"] == "connected"
        panel = (
            await api.get(f"/api/v1/operator/workspaces/{workspace.tenant_id}/whatsapp")
        ).json()
        assert panel["connection"]["status"] == "connected"
        # Releasing retires the number; it can't be handed to someone else afterwards.
        await api.post("/api/v1/pi/whatsapp/kapso/disconnect", json={})
        row = await business_db.scalar(
            select(PiPoolNumber).where(PiPoolNumber.phone_number_id == "5000000002")
        )
        assert row.status == "retired"
        reuse = await api.patch(
            f"/api/v1/operator/pi/numbers/{row.id}", json={"status": "available"}
        )
        assert reuse.status_code == 422
    finally:
        await workspace.close()
    await first.aclose()
    await second.aclose()


async def test_connecting_an_existing_number_never_stores_the_token(api, app, business_db):
    provider = _provider(app)
    await _operator(api, business_db)
    secret = "EAAG" + "x" * 120
    added = await api.post(
        "/api/v1/operator/pi/numbers/connect",
        json={
            "phone_number_id": "6000000001",
            "business_account_id": "1665058565187400",
            "access_token": secret,
            "country": "US",
        },
    )
    assert added.status_code == 201, added.text
    assert added.json()["status"] == "available"
    assert provider.connected_tokens == [secret]  # sent to Kapso once
    # Nothing we store contains it: pool rows, audit events, request logs.
    for table in ("pi_pool_numbers", "audit_events", "pi_platform_state"):
        found = await business_db.scalar(
            text(f"select count(*) from {table} where cast({table}.* as text) like :t"),
            {"t": f"%{secret[:30]}%"},
        )
        assert found == 0, table
    bad = await api.post(
        "/api/v1/operator/pi/numbers/connect",
        json={
            "phone_number_id": "6000000002",
            "business_account_id": "12345",
            "access_token": "short",
        },
    )
    assert bad.status_code == 422
    count = await business_db.scalar(select(func.count()).select_from(PiPoolNumber))
    assert count == 1
    assert json.dumps(added.json()).find(secret[:30]) == -1
