"""'Send payment link' on an invoice: issue a draft, then the pay link goes out on
WhatsApp (and email when the customer has one and email is connected)."""

from uuid import UUID

import pytest
from test_pi_customer_payments import MEEZAN
from test_pi_deals import _customer_in_chat, _send
from test_pi_pipeline import pi_workspace

from app.modules.billing.models import Invoice

pytestmark = pytest.mark.integration


async def _draft_invoice(api, customer_id: str) -> str:
    made = await api.post(
        "/api/v1/billing/invoices",
        json={
            "customer_id": customer_id,
            "lines": [{"description": "Logo design", "quantity": "1", "unit_price": "25000"}],
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def test_send_payment_link_issues_the_invoice_and_sends_the_link(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    settings = await api.put(
        "/api/v1/pi/customer-payments/settings",
        json={"bank_enabled": True, "bank_accounts": [MEEZAN]},
    )
    assert settings.status_code == 200, settings.text
    customer_id, _ = await _customer_in_chat(pi)
    invoice_id = await _draft_invoice(api, customer_id)

    sent = await api.post(f"/api/v1/billing/invoices/{invoice_id}/payment-link/send", json={})
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["whatsapp"]["delivery"] == "sent"
    assert body["pay_link"] and "/pay/request/" in body["pay_link"]
    # No email address on this customer: WhatsApp still went, email says why not.
    assert body["email"] is None and body["email_error"]
    assert (await business_db.get(Invoice, UUID(invoice_id))).status == "issued"
    texts = await _send(pi)
    assert any("Meezan Bank" in t and "/pay/request/" in t for t in texts)
    await pi.close()


async def test_without_any_payment_setup_the_invoice_still_goes_out(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, _ = await _customer_in_chat(pi)
    invoice_id = await _draft_invoice(api, customer_id)
    sent = await api.post(
        f"/api/v1/billing/invoices/{invoice_id}/payment-link/send",
        json={"whatsapp": True, "email": False},
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["whatsapp"]["delivery"] == "sent" and body["pay_link"] is None
    assert any("/d/" in t for t in await _send(pi))
    nothing = await api.post(
        f"/api/v1/billing/invoices/{invoice_id}/payment-link/send",
        json={"whatsapp": False, "email": False},
    )
    assert nothing.status_code == 422
    await pi.close()
