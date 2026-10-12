"""A proposal's "Download PDF": the business's letterhead, the lines and totals, and
the bank details (only in the PDF). Opening it doesn't mark the proposal viewed."""

from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_customer_payments import MEEZAN
from test_pi_deals import DEALS, _customer_in_chat, _lead, _price, _public, _token
from test_pi_pipeline import pi_workspace

from app.modules.pi_saas.deal_models import PiDocument
from app.modules.quotes.models import Quote

pytestmark = pytest.mark.integration


async def test_a_proposal_downloads_as_a_pdf_with_the_bank_details(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    put = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={"bank_enabled": True, "bank_accounts": [MEEZAN]},
    )
    assert put.status_code == 200, put.text
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    made = await api.post(f"{DEALS}/leads/{lead_id}/proposal")
    assert made.status_code == 201, made.text
    quote_id = made.json()["quote_id"]
    await _price(pi, quote_id)
    sent = await api.post(f"{DEALS}/quotes/{quote_id}/send")
    assert sent.status_code == 200, sent.text
    token = _token(sent.json()["link"])
    number = (await business_db.get(Quote, UUID(quote_id))).number

    public = _public(api)
    response = await public.get(f"/api/v1/pi-app/docs/{token}/pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert number in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    pdf = response.content
    assert pdf.startswith(b"%PDF-")
    assert number.encode() in pdf
    assert b"Bank details" in pdf and MEEZAN["iban"].encode() in pdf
    assert b"Branding for Crescent Bakers" in pdf and b"100,000.00" in pdf
    # Only reading: the proposal still counts as not yet opened.
    doc = await business_db.scalar(select(PiDocument).where(PiDocument.quote_id == UUID(quote_id)))
    await business_db.refresh(doc)
    assert doc.viewed_at is None

    missing = await public.get("/api/v1/pi-app/docs/not-a-real-token/pdf")
    assert missing.status_code == 404
    await public.aclose()
    await pi.close()
