"""End to end: a business is approved, gets a free plan, its pool number connects, it
launches, and a customer's WhatsApp messages get Pi's replies through Kapso."""

import pytest
from sqlalchemy import select
from test_pi_business_journey import DETAILS, _operator, _pool, _provider, _tenant
from test_pi_saas import _kapso, _message_event, _onboard, _publish_all_drafts, _run_jobs

from app.modules.pi.models import PiMessage
from app.modules.pi_saas.models import PiPoolNumber

pytestmark = pytest.mark.integration


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


def _sends(provider, number: str) -> list:
    return [r for r in provider.requests if r.url.path.endswith(f"/{number}/messages")]


async def test_approved_business_talks_to_customers_on_its_number(
    api, app, business_db, monkeypatch
):
    from pi_saas_support import pi_client, pi_register
    from test_pi_service_conversations import mock_turns, turn

    provider = _provider(app)
    await _operator(api, business_db)
    pool = await _pool(api, provider, ("6300000001", "+1 415 555 0401"))
    client = pi_client(app)
    view = await pi_register(client, "Hira Bakers")
    tenant_id = await _tenant(business_db, view)
    await _onboard(client)
    await _publish_all_drafts(client)

    # The business picks a number before approval: it is held, not connected.
    held = await client.post(
        f"/api/v1/pi-app/whatsapp/numbers/{pool['+1 415 555 0401']['id']}/choose", json={}
    )
    assert held.json()["state"] == "held", held.text

    # Review → approval → free plan: the held number connects by itself.
    await client.put("/api/v1/pi-app/business-review", json=DETAILS)
    assert (await client.post("/api/v1/pi-app/business-review/submit")).status_code == 200
    approved = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant_id}/review", json={"action": "approve"}
    )
    assert approved.json()["status"] == "approved"
    created = await api.post(
        "/api/v1/operator/pi/plans",
        json={
            "key": "starter-free",
            "name": "Starter (free)",
            "monthly_price": "0",
            "visibility": "private",
            "status": "available",
            "features": ["inbox", "knowledge"],
        },
    )
    assert created.status_code == 201, created.text
    given = await api.post(
        f"/api/v1/operator/pi/accounts/{tenant_id}/subscription",
        json={"plan": "starter-free", "status": "active", "reason": "Pilot"},
    )
    assert given.status_code == 200, given.text
    row = await business_db.scalar(
        select(PiPoolNumber).where(PiPoolNumber.phone_number_id == "6300000001")
    )
    assert row.status == "assigned" and row.assigned_tenant_id == tenant_id
    whatsapp = (await client.get("/api/v1/pi-app/whatsapp")).json()
    assert whatsapp["production"]["status"] == "connected"
    assert (await client.get("/api/v1/pi-app/whatsapp/access")).json()["ok"]

    launched = await client.post("/api/v1/pi-app/account/launch")
    assert launched.status_code == 200, launched.text

    # A customer says salam; Pi's reply goes out through Kapso on the business number.
    mock_turns(monkeypatch, turn(reply="Wa alaikum salam! Aaj kya order karna chahenge?"))
    received = await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("6300000001", "923001112233", "Salam", "wamid.conv1"),
    )
    assert received.status_code in (200, 202), received.text
    await _run_jobs(app, provider, business_db)
    inbound = await business_db.scalar(
        select(PiMessage).where(PiMessage.provider_message_id == "wamid.conv1")
    )
    assert inbound is not None and inbound.tenant_id == tenant_id
    reply = await business_db.scalar(
        select(PiMessage)
        .where(
            PiMessage.conversation_id == inbound.conversation_id,
            PiMessage.direction == "outbound",
        )
        .order_by(PiMessage.created_at.desc())
    )
    assert reply is not None and reply.status == "sent", reply and reply.status
    assert "salam" in reply.body.lower()
    assert len(_sends(provider, "6300000001")) == 1

    # The conversation continues in the same thread.
    mock_turns(monkeypatch, turn(reply="Hamare cakes 1,200 se shuru hote hain."))
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("6300000001", "923001112233", "Cake ka rate?", "wamid.conv2"),
    )
    await _run_jobs(app, provider, business_db)
    second = await business_db.scalar(
        select(PiMessage).where(PiMessage.provider_message_id == "wamid.conv2")
    )
    assert second.conversation_id == inbound.conversation_id
    inbox = (await client.get("/api/v1/pi-app/pi/conversations")).json()
    items = inbox["items"] if isinstance(inbox, dict) else inbox
    assert any(str(c["id"]) == str(inbound.conversation_id) for c in items)
    await client.aclose()
