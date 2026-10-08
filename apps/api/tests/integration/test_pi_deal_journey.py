"""The automatic deal journey: the customer confirms the brief in the chat → pi makes
the proposal with catalog prices and sends it → the lead's notes and journey show each
step and the next one. Real database/webhook/worker; the AI and WhatsApp are mocked."""

from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_service_lifecycle import create

from app.modules.notifications.models import Notification
from app.modules.pi.service_conversation import Project, Requirements
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration

DEALS = "/api/v1/pi/deals"


def confirmed(title: str) -> object:
    return turn(
        reply="Thanks, I'm pi, the company's AI assistant. Noted: your brief is confirmed.",
        language="en",
        summary=f"Customer wants a {title}. Brief confirmed.",
        requirements=Requirements(service=title, scope=f"{title} for a bakery"),
        missing=[],
        projects=[Project(title=title, details="Five pages", status="confirmed")],
        ready_for_team=True,
        awaiting_customer=False,
    )


async def _catalog(api, name: str, price: str) -> None:
    await create(
        api,
        "catalog/products",
        {
            "name": name,
            "offering_type": "service",
            "variants": [
                {"sku": name[:3].upper(), "name": "Standard", "price": price, "currency": "USD"}
            ],
        },
    )


async def _lead(pi) -> SalesLead:
    lead = await pi.db.scalar(select(SalesLead).where(SalesLead.tenant_id == UUID(pi.tenant_id)))
    assert lead is not None
    await pi.db.refresh(lead)
    return lead


async def test_confirmed_brief_becomes_a_sent_proposal_with_catalog_prices(
    api, business_db, monkeypatch
):
    mock_turns(monkeypatch, confirmed("Website"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _catalog(api, "Website", "1500.00")
    await pi.process("I need a website for my bakery, yes that's all", "journey-1")
    await pi.deliver_all()
    lead = await _lead(pi)
    assert lead.stage == "proposal"
    quote = await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id))
    assert quote is not None and quote.status == "sent" and quote.total == 1500
    assert quote.notes == ""  # internal lead notes never reach the customer page
    bodies = [m.body for m in await pi.outbound()]
    assert any("/d/" in body and "1,500.00" in body for body in bodies)
    assert lead.notes.startswith("From the WhatsApp chat (written by pi):")
    assert "customer confirmed the brief" in lead.notes
    assert f"proposal {quote.number} (USD 1,500.00) sent on WhatsApp" in lead.notes

    journey = (await api.get(f"{DEALS}/leads/{lead.id}/journey")).json()
    done = {step["key"]: step["done"] for step in journey["steps"]}
    assert done["brief"] and done["proposal"] and done["sent"] and not done["paid"]
    assert journey["next"]["title"] == "Waiting for the customer" and journey["next"]["auto"]
    await pi.close()


async def test_without_a_catalog_price_the_draft_waits_for_the_team(api, business_db, monkeypatch):
    mock_turns(monkeypatch, confirmed("Mobile app"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("A mobile app please, that's everything", "journey-2")
    await pi.deliver_all()
    lead = await _lead(pi)
    assert lead.stage == "qualified"
    quote = await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id))
    assert quote is not None and quote.status == "draft" and quote.total == 0
    assert all("/d/" not in m.body for m in await pi.outbound())
    assert "add prices to send it" in lead.notes
    assert await pi.db.scalar(
        select(Notification).where(
            Notification.tenant_id == UUID(pi.tenant_id),
            Notification.title == f"Price proposal {quote.number}",
        )
    )
    journey = (await api.get(f"{DEALS}/leads/{lead.id}/journey")).json()
    assert journey["next"]["title"] == "Add prices"
    assert journey["next"]["href"] == f"/quotes/{quote.id}/edit"
    await pi.close()


async def test_auto_proposal_can_be_switched_off(api, business_db, monkeypatch):
    mock_turns(monkeypatch, confirmed("Website"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _catalog(api, "Website", "1500.00")
    current = (await api.get(f"{DEALS}/settings")).json()
    current.pop("payment_methods")
    saved = await api.put(f"{DEALS}/settings", json={**current, "auto_proposal": False})
    assert saved.status_code == 200 and saved.json()["auto_proposal"] is False
    await pi.process("Website for my bakery, confirmed", "journey-3")
    await pi.deliver_all()
    lead = await _lead(pi)
    assert await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id)) is None
    journey = (await api.get(f"{DEALS}/leads/{lead.id}/journey")).json()
    assert journey["next"]["action"] == "proposal_from_brief"
    await pi.close()
