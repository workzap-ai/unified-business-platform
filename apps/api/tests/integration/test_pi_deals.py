"""The deal flow end to end: lead → proposal from the brief → priced and sent on
WhatsApp → the customer accepts on the proposal page → order, invoice and payment link
go out by themselves → paid → thank-you. Plus: asking for changes, declining, the
24-hour window (template + release on reply), and a deal started from just a number."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from test_pi_customer_payments import MEEZAN
from test_pi_pipeline import Pi, pi_workspace
from test_service_lifecycle import create

from app.modules.billing.models import Invoice
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.runtime import send_pi_message
from app.modules.pi_saas import deals
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead

pytestmark = pytest.mark.integration

CUSTOMER = "15550000001"
DEALS = "/api/v1/pi/deals"


def _public(api: httpx.AsyncClient) -> httpx.AsyncClient:
    settings = api._transport.app.state.settings  # type: ignore[attr-defined]
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"origin": settings.pi_app_origins[0]},
    )


async def _customer_in_chat(pi: Pi, *, hours_ago: float = 1) -> tuple[str, PiConversation]:
    """A customer who wrote on WhatsApp ``hours_ago`` (the chat pi already has)."""
    customer = await create(pi.api, "customers", {"name": "Ayesha Khan", "phone": f"+{CUSTOMER}"})
    connection = await pi.db.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == UUID(pi.tenant_id))
    )
    when = datetime.now(UTC) - timedelta(hours=hours_ago)
    conversation = PiConversation(
        tenant_id=UUID(pi.tenant_id),
        environment_id=UUID(pi.environment_id),
        customer_id=UUID(customer["id"]),
        connection_id=connection.id,
        contact_wa_id=CUSTOMER,
        last_message_at=when,
        last_inbound_at=when,
        service_brief={
            "projects": [
                {
                    "title": "Logo",
                    "service": "Branding",
                    "details": "Modern logo for Crescent Bakers",
                    "status": "confirmed",
                },
                {"title": "Website", "details": "Five-page site", "status": "confirmed"},
            ]
        },
    )
    pi.db.add(conversation)
    await pi.db.flush()
    return customer["id"], conversation


async def _lead(pi: Pi, customer_id: str, conversation: PiConversation) -> str:
    lead = await create(
        pi.api, "sales/leads", {"title": "Branding for Crescent Bakers", "customer_id": customer_id}
    )
    row = await pi.db.get(SalesLead, UUID(lead["id"]))
    row.conversation_id = conversation.id
    await pi.db.flush()
    return lead["id"]


async def _price(pi: Pi, quote_id: str) -> None:
    response = await pi.api.patch(
        f"/api/v1/quotes/{quote_id}",
        json={
            "lines": [
                {"description": "Logo", "quantity": "1", "unit_price": "25000"},
                {"description": "Website", "quantity": "1", "unit_price": "75000"},
            ]
        },
    )
    assert response.status_code == 200, response.text


async def _send(pi: Pi) -> list[str]:
    """Deliver queued outbound messages; return their texts."""
    messages = list(
        await pi.db.scalars(
            select(PiMessage).where(
                PiMessage.tenant_id == UUID(pi.tenant_id),
                PiMessage.direction == "outbound",
                PiMessage.status == "queued",
            )
        )
    )
    for message in messages:
        await send_pi_message(pi.ctx, str(message.id))
    return [str(m.get("text", {}).get("body", "")) for m in pi.sent]


def _token(link: str) -> str:
    return link.rsplit("/d/", 1)[1]


async def test_proposal_to_paid_invoice_runs_by_itself(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    put = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={
            "bank_enabled": True,
            "bank_accounts": [MEEZAN],
        },
    )
    assert put.status_code == 200, put.text
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)

    made = await api.post(f"{DEALS}/leads/{lead_id}/proposal")
    assert made.status_code == 201, made.text
    quote_id = made.json()["quote_id"]
    draft = (await api.get(f"/api/v1/quotes/{quote_id}")).json()
    assert [line["description"] for line in draft["lines"]] == [
        "Logo: Modern logo for Crescent Bakers",
        "Website: Five-page site",
    ]
    unpriced = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert unpriced.status_code == 422 and unpriced.json()["error"]["code"] == "QUOTE_NOT_PRICED"

    await _price(pi, quote_id)
    sent = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    view = sent.json()
    assert view["delivery"] == "sent" and "/d/" in view["link"]
    texts = await _send(pi)
    assert any("proposal" in t and "/d/" in t and "100,000.00" in t for t in texts)
    assert (await business_db.get(SalesLead, UUID(lead_id))).stage == "proposal"

    public = _public(api)
    token = _token(view["link"])
    page = (await public.get(f"/api/v1/pi-app/docs/{token}")).json()
    assert page["kind"] == "proposal" and page["can_respond"] is True
    assert page["total"] == "100000.00" and len(page["lines"]) == 2

    accepted = await public.post(
        f"/api/v1/pi-app/docs/{token}/respond", json={"action": "accepted"}
    )
    assert accepted.status_code == 200, accepted.text
    again = await public.post(f"/api/v1/pi-app/docs/{token}/respond", json={"action": "accepted"})
    assert again.status_code == 422

    quote = await business_db.get(Quote, UUID(quote_id))
    assert quote.status == "accepted"
    assert (await business_db.get(SalesLead, UUID(lead_id))).stage == "won"
    order = await business_db.scalar(select(Order).where(Order.quote_id == quote.id))
    assert order is not None and order.status == "confirmed"
    invoice = await business_db.scalar(select(Invoice).where(Invoice.order_id == order.id))
    assert invoice is not None and invoice.status == "issued"
    request = await business_db.scalar(
        select(PiPaymentRequest).where(PiPaymentRequest.invoice_id == invoice.id)
    )
    assert request is not None and request.method == "bank_transfer"
    texts = await _send(pi)
    paid_text = texts[-1]
    assert "Thank you" in paid_text and "Meezan Bank" in paid_text and "Pay online:" in paid_text

    board = (await api.get(f"{DEALS}/board")).json()
    item = next(i for i in board["items"] if i["id"] == lead_id)
    assert item["stage"] == "won" and item["next"] == "Waiting for payment"

    payment = await api.post(
        f"/api/v1/billing/invoices/{invoice.id}/payments",
        json={"amount": "100000.00", "method": "bank_transfer"},
    )
    assert payment.status_code == 201, payment.text
    texts = await _send(pi)
    assert texts[-1].startswith("Payment received for invoice")
    board = (await api.get(f"{DEALS}/board")).json()
    assert next(i for i in board["items"] if i["id"] == lead_id)["next"] == "Paid: deliver the work"
    await public.aclose()
    await pi.close()


async def test_changes_and_decline_move_the_lead_back_or_lose_it(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    public = _public(api)
    for action, stage in (("changes", "qualified"), ("rejected", "lost")):
        lead_id = await _lead(pi, customer_id, conversation)
        quote_id = (await api.post(f"{DEALS}/leads/{lead_id}/proposal")).json()["quote_id"]
        await _price(pi, quote_id)
        token = _token((await api.post(f"{DEALS}/quotes/{quote_id}/send")).json()["link"])
        if action == "changes":
            no_note = await public.post(
                f"/api/v1/pi-app/docs/{token}/respond", json={"action": "changes"}
            )
            assert no_note.status_code == 422
        answered = await public.post(
            f"/api/v1/pi-app/docs/{token}/respond",
            json={"action": action, "note": "Please make the logo blue"},
        )
        assert answered.status_code == 200, answered.text
        assert (await business_db.get(Quote, UUID(quote_id))).status == "rejected"
        assert (await business_db.get(SalesLead, UUID(lead_id))).stage == stage
    await public.aclose()
    await pi.close()


async def test_outside_the_window_a_template_asks_and_the_link_follows_the_reply(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi, hours_ago=48)
    lead_id = await _lead(pi, customer_id, conversation)
    quote_id = (await api.post(f"{DEALS}/leads/{lead_id}/proposal")).json()["quote_id"]
    await _price(pi, quote_id)

    manual = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert manual.json()["delivery"] == "manual"  # no template yet: the team shares it
    assert manual.json()["share"].startswith(f"https://wa.me/{CUSTOMER}?text=")

    settings = await api.put(
        f"{DEALS}/settings",
        json={
            "auto_order": True,
            "auto_invoice": True,
            "auto_payment_request": True,
            "thank_you_on_paid": True,
            "payment_method": "auto",
            "template_name": "document_ready",
            "template_language": "en",
        },
    )
    assert settings.status_code == 200, settings.text
    waiting = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert waiting.json()["delivery"] == "waiting"
    notice = await business_db.scalar(
        select(PiMessage).where(
            PiMessage.tenant_id == UUID(pi.tenant_id), PiMessage.status == "queued"
        )
    )
    assert notice.media["document_notice"]["template"]["name"] == "document_ready"

    # The customer replies: the window opens and the link goes out.
    reply = PiMessage(
        tenant_id=UUID(pi.tenant_id),
        environment_id=UUID(pi.environment_id),
        conversation_id=conversation.id,
        direction="inbound",
        sender_type="customer",
        message_type="text",
        body="ok",
        status="received",
    )
    business_db.add(reply)
    await business_db.flush()
    released = await deals.release_waiting(business_db, pi.scope(), reply)
    assert len(released) == 1
    link = await business_db.get(PiMessage, UUID(released[0]))
    assert "/d/" in link.body and link.status == "queued"
    assert await deals.release_waiting(business_db, pi.scope(), reply) == []  # once only
    await pi.close()


async def test_a_deal_can_start_from_just_a_whatsapp_number(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    bad = await api.post(f"{DEALS}/start", json={"phone": "12-34"})
    assert bad.status_code == 422
    started = await api.post(
        f"{DEALS}/start",
        json={"phone": "+92 300 1234567", "name": "Bilal", "title": "Shop website"},
    )
    assert started.status_code == 201, started.text
    lead = await business_db.get(SalesLead, UUID(started.json()["lead_id"]))
    assert lead.title == "Shop website" and lead.stage == "new"
    quote = await create(
        api,
        "quotes",
        {
            "customer_id": started.json()["customer_id"],
            "lead_id": str(lead.id),
            "lines": [{"description": "Website", "quantity": "1", "unit_price": "60000"}],
        },
    )
    sent = await api.post(f"{DEALS}/quotes/{quote['id']}/send")
    assert sent.status_code == 200, sent.text
    # Never messaged: no window, no template → the team gets the link to share.
    assert sent.json()["delivery"] == "manual"
    assert sent.json()["share"].startswith("https://wa.me/923001234567?text=")
    assert (await business_db.get(SalesLead, lead.id)).stage == "proposal"
    conversation = await business_db.scalar(
        select(PiConversation).where(PiConversation.contact_wa_id == "923001234567")
    )
    assert conversation is not None  # the chat is ready for when they reply
    assert Decimal(quote["total"]) == Decimal("60000.00")
    await pi.close()


async def test_settings_need_a_complete_template(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    current = (await api.get(f"{DEALS}/settings")).json()
    assert current["auto_order"] is True and current["template_name"] == ""
    half = await api.put(
        f"{DEALS}/settings",
        json={
            **{
                k: current[k]
                for k in (
                    "auto_order",
                    "auto_invoice",
                    "auto_payment_request",
                    "thank_you_on_paid",
                    "payment_method",
                )
            },
            "template_name": "document_ready",
            "template_language": "",
        },
    )
    assert half.status_code == 422
    await pi.close()


async def test_the_pi_app_has_the_deal_flow_with_its_own_session(api):
    from pi_saas_support import FakeProvider, configure, pi_client, pi_register

    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    client = pi_client(app)
    await pi_register(client)
    client.headers["x-csrf-token"] = client.cookies["pi_csrf"]
    started = await client.post(
        "/api/v1/pi-app/pi/deals/start",
        json={"phone": "+92 300 7654321", "name": "Sana", "title": "Logo design"},
    )
    assert started.status_code == 201, started.text
    quote = await client.post(
        "/api/v1/pi-app/quotes",
        json={
            "customer_id": started.json()["customer_id"],
            "lead_id": started.json()["lead_id"],
            "lines": [{"description": "Logo", "quantity": "1", "unit_price": "20000"}],
        },
    )
    assert quote.status_code == 201, quote.text
    sent = await client.post(f"/api/v1/pi-app/pi/deals/quotes/{quote.json()['id']}/send")
    assert sent.status_code == 200, sent.text
    board = (await client.get("/api/v1/pi-app/pi/deals/board")).json()
    assert board["counts"] == {"proposal": 1}
    assert board["items"][0]["next"] == "Waiting for the customer's answer"
    pipeline = await client.get("/api/v1/pi-app/sales/pipeline")
    assert pipeline.status_code == 200
    await client.aclose()
