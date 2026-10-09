"""The automatic deal journey: the customer confirms the brief in the chat → pi writes
the proposal with catalog prices and sends it → the customer accepts (or asks for
changes) in the chat → order, invoice and payment link, or a revised proposal. The lead's
notes and journey show each step and the next one. Real database/webhook/worker; the AI
and WhatsApp are mocked."""

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_service_lifecycle import create

from app.ai.manager import LLMManager
from app.modules.billing.models import Invoice
from app.modules.catalog.models import CatalogVariant
from app.modules.notifications.models import Notification
from app.modules.orders.models import Order
from app.modules.pi.service_conversation import Project, Requirements
from app.modules.pi_saas import payment_link
from app.modules.pi_saas.deals import NOTES_END, NOTES_START
from app.modules.pi_saas.jobs import draft_pi_proposal
from app.modules.pi_saas.proposal_writer import DraftLine, ProposalDraft
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration

DEALS = "/api/v1/pi/deals"


def confirmed(title: str, **changes) -> object:
    data = dict(
        reply="Thanks, I'm pi, the company's AI assistant. Noted: your brief is confirmed.",
        language="en",
        summary=f"Customer: a bakery\nWants: {title}\nBudget: their words\nNext step: proposal",
        requirements=Requirements(service=title, scope=f"{title} for a bakery"),
        missing=[],
        projects=[Project(title=title, details="Five pages", status="confirmed")],
        ready_for_team=True,
        awaiting_customer=False,
    )
    data.update(changes)
    return turn(**data)


def mock_ai(monkeypatch, turns, draft=None):
    """pi's chat turns in order, and the proposal writer's draft (None: it fails)."""
    replies = iter(turns)
    last: list = []

    async def complete(self, scope, output, **kwargs):
        if kwargs["purpose"] == "pi_proposal":
            if draft is None:
                raise RuntimeError("writer unavailable")
            return SimpleNamespace(value=await draft(), response=SimpleNamespace(attempts=[]))

        if not kwargs["messages"][-1].text().startswith("Don't send that draft"):
            last.append(next(replies))  # a self-check rewrite gets the same scripted turn
        return SimpleNamespace(value=last[-1], response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)


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


async def _turn(pi, text: str, mid: str) -> SalesLead:
    """One customer message, then the proposal job (the worker runs it after commit)."""
    await pi.process(text, mid)
    lead = await _lead(pi)
    await draft_pi_proposal(pi.ctx, str(lead.id))
    await pi.deliver_all()
    return await _lead(pi)


async def test_confirmed_brief_becomes_a_sent_proposal_with_catalog_prices(
    api, business_db, monkeypatch
):
    mock_turns(monkeypatch, confirmed("Website"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _catalog(api, "Website", "1500.00")
    lead = await _turn(pi, "I need a website for my bakery, yes that's all", "journey-1")
    assert lead.stage == "proposal"
    quote = await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id))
    assert quote is not None and quote.status == "sent" and quote.total == 1500
    assert quote.notes == ""  # internal lead notes never reach the customer page
    assert lead.estimated_value == 1500
    bodies = [m.body for m in await pi.outbound()]
    assert any("/d/" in body and "1,500.00" in body and "reply here" in body for body in bodies)
    assert lead.notes.startswith(NOTES_START)
    assert "Customer: a bakery" in lead.notes and "Budget: their words" in lead.notes
    assert "customer confirmed the brief" in lead.notes
    assert f"proposal {quote.number} (USD 1,500.00) sent on WhatsApp" in lead.notes

    journey = (await api.get(f"{DEALS}/leads/{lead.id}/journey")).json()
    done = {step["key"]: step["done"] for step in journey["steps"]}
    assert done["brief"] and done["proposal"] and done["sent"] and not done["paid"]
    assert journey["next"]["title"] == "Waiting for the customer" and journey["next"]["auto"]
    await pi.close()


async def test_pi_writes_the_proposal_and_only_catalog_options_carry_prices(
    api, business_db, monkeypatch
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _catalog(api, "Website", "1500.00")

    async def draft():
        variant = await pi.db.scalar(
            select(CatalogVariant).where(CatalogVariant.tenant_id == UUID(pi.tenant_id))
        )
        return ProposalDraft(
            intro="A five page website for your bakery, with online orders.",
            scope=["Home, menu, about, gallery and contact pages", "Costs only $99 extra"],
            deliverables=["A live website on your domain"],
            next_steps="Accept here and your order is confirmed.",
            lines=[
                DraftLine(title="Website", description="Five pages", offering_id=str(variant.id)),
                DraftLine(title="Logo refresh", description="Cleaner logo", offering_id="nope"),
            ],
        )

    mock_ai(monkeypatch, [confirmed("Website")], draft)
    lead = await _turn(pi, "Website for my bakery, that's all", "write-1")
    quote = await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id))
    assert quote is not None
    lines = list(await pi.db.scalars(select(QuoteLine).where(QuoteLine.quote_id == quote.id)))
    prices = sorted(line.unit_price for line in lines)
    assert prices == [0, 1500]  # the invented id got no price
    assert "Scope\n• Home, menu" in quote.notes and "Deliverables" in quote.notes
    assert "$" not in quote.notes  # amounts the model wrote are dropped
    # A line without a catalog price: the draft waits for the team.
    assert quote.status == "draft" and "add prices to send it" in lead.notes
    await pi.close()


async def test_customer_accepts_in_the_chat_and_gets_the_invoice(api, business_db, monkeypatch):
    accept = turn(
        reply="Shukriya. Order confirmation aur invoice abhi yahin aa rahi hai.",
        language="roman_ur",
        summary="Customer accepted the proposal.",
        requirements=Requirements(service="Website", scope="Website for a bakery"),
        missing=[],
        projects=[Project(title="Website", details="Five pages", status="confirmed")],
        ready_for_team=True,
        awaiting_customer=False,
        proposal_answer="accepted",
        proposal_evidence="haan accept hai",
    )
    mock_ai(monkeypatch, [confirmed("Website"), accept])
    # pi's payment methods are off here: the Stripe integration's link is used, and the
    # same link is emailed (both stubbed; their own tests cover them).
    emailed: list[tuple[str | None, str | None]] = []

    async def stripe_link(session, settings, http, scope, invoice):
        return "https://checkout.stripe.com/c/pay/cs_test_1"

    async def email_link(session, scope, invoice, pay_url, invoice_url):
        emailed.append((pay_url, invoice_url))

    monkeypatch.setattr(payment_link, "stripe_link", stripe_link)
    monkeypatch.setattr(payment_link, "email_link", email_link)
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _catalog(api, "Website", "1500.00")
    await _turn(pi, "Website for my bakery, that's all", "accept-1")
    lead = await _turn(pi, "haan accept hai, kaam shuru karein", "accept-2")
    quote = await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id))
    assert quote is not None and quote.status == "accepted"
    assert lead.stage == "won"
    order = await pi.db.scalar(select(Order).where(Order.quote_id == quote.id))
    assert order is not None
    invoice = await pi.db.scalar(select(Invoice).where(Invoice.order_id == order.id))
    assert invoice is not None and invoice.status == "issued"
    bodies = [m.body for m in await pi.outbound()]
    assert any(
        "Invoice:" in body and "Pay by card: https://checkout.stripe.com/" in body
        for body in bodies
    )
    assert emailed and emailed[0][0] == "https://checkout.stripe.com/c/pay/cs_test_1"
    assert emailed[0][1] and "/d/" in emailed[0][1]
    assert f"customer accepted {quote.number} in the WhatsApp chat" in lead.notes
    await pi.close()


async def test_an_answer_without_an_open_proposal_does_nothing(api, business_db, monkeypatch):
    stray = confirmed("Website", proposal_answer="accepted", proposal_evidence="accept")
    mock_ai(monkeypatch, [stray])
    pi = await pi_workspace(api, business_db, business_type="service_business")
    lead = await _turn(pi, "accept", "stray-1")
    assert lead.stage == "qualified"  # brief confirmed, nothing accepted
    assert await pi.db.scalar(select(Order).where(Order.tenant_id == UUID(pi.tenant_id))) is None
    await pi.close()


async def test_changes_in_the_chat_lead_to_a_revised_proposal(api, business_db, monkeypatch):
    changes = turn(
        reply="Noted: blue colours. Is the updated brief right? I'll send the new proposal.",
        language="en",
        summary="Customer wants changes.",
        requirements=Requirements(service="Website", scope="Website for a bakery, blue"),
        missing=[],
        projects=[Project(title="Website", details="Five pages, blue", status="confirmed")],
        ready_for_team=True,
        awaiting_customer=True,
        proposal_answer="changes",
        proposal_evidence="make it blue",
    )
    mock_ai(monkeypatch, [confirmed("Website"), changes, confirmed("Website")])
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _catalog(api, "Website", "1500.00")
    await _turn(pi, "Website for my bakery, that's all", "change-1")
    lead = await _turn(pi, "please make it blue", "change-2")
    first = await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id))
    assert first is not None and first.status == "rejected" and lead.stage == "qualified"
    brief = (await pi.conversation()).service_brief
    assert brief["projects"][0]["status"] == "awaiting_confirmation"
    assert brief["proposal_changes"] == "make it blue"

    lead = await _turn(pi, "yes that's right", "change-3")
    quotes = list(await pi.db.scalars(select(Quote).where(Quote.lead_id == lead.id)))
    assert len(quotes) == 2
    revised = next(q for q in quotes if q.id != first.id)
    assert revised.status == "sent" and lead.stage == "proposal"
    assert "customer confirmed the updated brief" in lead.notes
    assert f"revised proposal {revised.number}" in lead.notes
    assert "proposal_changes" not in (await pi.conversation()).service_brief
    await pi.close()


async def test_pi_keeps_its_notes_and_leaves_the_teams_alone(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        turn(
            summary="Customer: a bakery\nWants: Website", requirements=Requirements(service="Web")
        ),
        turn(
            summary="Customer: a bakery\nWants: Website, blue",
            requirements=Requirements(service="Web"),
        ),
        turn(summary="Customer: changed again", requirements=Requirements(service="Web")),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("I need a website", "notes-1")
    lead = await _lead(pi)
    assert lead.notes == f"{NOTES_START}\nCustomer: a bakery\nWants: Website\n{NOTES_END}"
    lead.notes = f"Owner: call them Friday\n\n{lead.notes}"
    await pi.db.commit()
    await pi.process("blue please", "notes-2")
    lead = await _lead(pi)
    assert lead.notes.startswith("Owner: call them Friday\n\n" + NOTES_START)
    assert "Wants: Website, blue" in lead.notes and "Wants: Website\n" not in lead.notes
    lead.notes = "Owner: my own notes only"  # the team deletes pi's block
    await pi.db.commit()
    await pi.process("one more thing", "notes-3")
    assert (await _lead(pi)).notes == "Owner: my own notes only"
    await pi.close()


async def test_without_a_catalog_price_the_draft_waits_for_the_team(api, business_db, monkeypatch):
    mock_turns(monkeypatch, confirmed("Mobile app"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    lead = await _turn(pi, "A mobile app please, that's everything", "journey-2")
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
    lead = await _turn(pi, "Website for my bakery, confirmed", "journey-3")
    assert await pi.db.scalar(select(Quote).where(Quote.lead_id == lead.id)) is None
    journey = (await api.get(f"{DEALS}/leads/{lead.id}/journey")).json()
    assert journey["next"]["action"] == "proposal_from_brief"
    await pi.close()
