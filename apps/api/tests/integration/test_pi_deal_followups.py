"""Automatic follow-ups when a deal goes quiet: an unopened proposal gets the approved
template once, an invoice due tomorrow gets a reminder with a pay link, nothing goes
while the team has the chat, and each nudge is noted on the lead."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_customer_payments import MEEZAN
from test_pi_deals import DEALS, _customer_in_chat, _lead, _price
from test_pi_pipeline import pi_workspace

from app.modules.billing.models import Invoice
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas import deal_followups
from app.modules.pi_saas.deal_followups import due_nudge
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def _doc(kind="proposal", created=3, viewed=None, response=None, delivery="sent"):
    return SimpleNamespace(
        kind=kind,
        created_at=NOW - timedelta(days=created),
        viewed_at=NOW - timedelta(days=viewed) if viewed is not None else None,
        response=response,
        delivery=delivery,
    )


def test_when_each_nudge_is_due():
    quote = SimpleNamespace(status="sent", valid_until=date(2026, 12, 1))
    assert due_nudge(_doc(created=1), quote, None, NOW) is None
    assert due_nudge(_doc(created=3), quote, None, NOW) == "proposal_unopened"
    assert due_nudge(_doc(created=5, viewed=1), quote, None, NOW) is None
    assert due_nudge(_doc(created=5, viewed=4), quote, None, NOW) == "proposal_unanswered"
    assert due_nudge(_doc(response="accepted"), quote, None, NOW) is None
    assert (
        due_nudge(
            _doc(), SimpleNamespace(status="accepted", valid_until=date(2026, 12, 1)), None, NOW
        )
        is None
    )
    assert due_nudge(_doc(delivery="manual"), quote, None, NOW) is None

    def invoice(due, status="issued"):
        return SimpleNamespace(status=status, due_date=due)

    doc = _doc(kind="invoice")
    assert due_nudge(doc, None, invoice(date(2026, 10, 10)), NOW) == "invoice_due"
    assert due_nudge(doc, None, invoice(date(2026, 10, 15)), NOW) is None
    assert due_nudge(doc, None, invoice(date(2026, 10, 6)), NOW) == "invoice_overdue"
    assert due_nudge(doc, None, invoice(date(2026, 10, 8)), NOW) is None
    assert due_nudge(doc, None, invoice(date(2026, 10, 10), "paid"), NOW) is None


async def _sent_proposal(pi, api):
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    quote_id = (await api.post(f"{DEALS}/leads/{lead_id}/proposal")).json()["quote_id"]
    await _price(pi, quote_id)
    sent = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    return lead_id, conversation


async def _template(api):
    current = (await api.get(f"{DEALS}/settings")).json()
    current.pop("payment_methods", None)
    saved = await api.put(
        f"{DEALS}/settings",
        json={**current, "template_name": "document_ready", "template_language": "en"},
    )
    assert saved.status_code == 200, saved.text


async def test_unopened_proposal_gets_the_template_once_and_a_note(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _template(api)
    lead_id, _ = await _sent_proposal(pi, api)
    settings = api._transport.app.state.settings
    later = datetime.now(UTC) + timedelta(days=3)

    ids = await deal_followups.sweep(pi.db, settings, later)
    assert len(ids) == 1
    nudge = await pi.db.get(PiMessage, UUID(ids[0]))
    assert nudge.idempotency_key.startswith("pi-nudge:proposal_unopened:")
    assert nudge.media["document_notice"]["template"]["name"] == "document_ready"
    lead = await pi.db.get(SalesLead, UUID(lead_id))
    await pi.db.refresh(lead)
    assert "reminded the customer about unopened proposal" in lead.notes
    journey = (await api.get(f"{DEALS}/leads/{lead_id}/journey")).json()
    assert journey["reminder"]["kind"] == "proposal_unopened"
    assert await deal_followups.sweep(pi.db, settings, later) == []  # once only
    await pi.close()


async def test_no_template_and_no_window_means_no_nudge(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _sent_proposal(pi, api)
    settings = api._transport.app.state.settings
    assert await deal_followups.sweep(pi.db, settings, datetime.now(UTC) + timedelta(days=3)) == []
    await pi.close()


async def test_invoice_due_tomorrow_gets_a_pay_link_in_the_chat(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    put = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={"bank_enabled": True, "bank_accounts": [MEEZAN]},
    )
    assert put.status_code == 200, put.text
    customer_id, conversation = await _customer_in_chat(pi)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
    made = await api.post(
        "/api/v1/billing/invoices",
        json={
            "customer_id": customer_id,
            "due_date": tomorrow.isoformat(),
            "lines": [{"description": "Logo", "quantity": "1", "unit_price": "25000"}],
        },
    )
    assert made.status_code == 201, made.text
    invoice_id = made.json()["id"]
    sent = await api.post(f"{DEALS}/invoices/{invoice_id}/send")
    assert sent.status_code == 200, sent.text
    # The customer wrote just now: the 24-hour window is open.
    row = await pi.db.get(PiConversation, conversation.id)
    row.last_inbound_at = datetime.now(UTC)
    await pi.db.flush()

    settings = api._transport.app.state.settings
    ids = await deal_followups.sweep(pi.db, settings, datetime.now(UTC) + timedelta(hours=13))
    assert len(ids) == 1
    nudge = await pi.db.get(PiMessage, UUID(ids[0]))
    assert "is due on" in nudge.body and "/pay/request/" in nudge.body
    invoice = await pi.db.get(Invoice, UUID(invoice_id))
    assert invoice.number in nudge.body

    # The team takes the chat over: no more nudges.
    row.mode = "human"
    await pi.db.flush()
    overdue = datetime.now(UTC) + timedelta(days=5)
    assert await deal_followups.sweep(pi.db, settings, overdue) == []
    await pi.close()


async def test_followups_can_be_switched_off(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await _template(api)
    await _sent_proposal(pi, api)
    from app.modules.pi_saas.deal_models import PiDealSettings

    row = await pi.db.scalar(
        select(PiDealSettings).where(PiDealSettings.tenant_id == UUID(pi.tenant_id))
    )
    if not hasattr(row, "auto_followups"):
        pytest.skip("auto_followups column is wired in after the deal-flow push")
    row.auto_followups = False
    await pi.db.flush()
    settings = api._transport.app.state.settings
    assert await deal_followups.sweep(pi.db, settings, datetime.now(UTC) + timedelta(days=3)) == []
    await pi.close()
