"""Receipts: every payment gets a PDF receipt, kept in the customer's files, listed on
the invoice and sent to the customer with a link to its page; options are respected."""

import io
from uuid import UUID

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from test_pi_deals import DEALS, _customer_in_chat, _public, _send
from test_pi_pipeline import pi_workspace

from app.modules.customers.models import CustomerActivity, CustomerFile
from app.modules.pi_saas.deal_models import PiDocument

pytestmark = pytest.mark.integration


async def _invoice(api, customer_id: str) -> dict:
    made = await api.post(
        "/api/v1/billing/invoices",
        json={
            "customer_id": customer_id,
            "lines": [{"description": "Brand refresh", "quantity": "1", "unit_price": "10000"}],
        },
    )
    assert made.status_code == 201, made.text
    issued = await api.post(
        f"/api/v1/billing/invoices/{made.json()['id']}/actions", json={"action": "issue"}
    )
    assert issued.status_code == 200, issued.text
    return issued.json()


async def _pay(api, invoice_id: str, amount: str, reference: str) -> None:
    paid = await api.post(
        f"/api/v1/billing/invoices/{invoice_id}/payments",
        json={"amount": amount, "method": "bank_transfer", "reference": reference},
    )
    assert paid.status_code in (200, 201), paid.text


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


async def test_each_payment_gets_a_receipt_kept_and_sent(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, _ = await _customer_in_chat(pi)
    invoice = await _invoice(api, customer_id)

    await _pay(api, invoice["id"], "4000", "MZN-1")
    await _pay(api, invoice["id"], "6000", "MZN-2")

    receipts = (await api.get(f"/api/v1/billing/invoices/{invoice['id']}/receipts")).json()
    assert len(receipts) == 2 and all(r["source"] == "receipt" for r in receipts)
    first, last = sorted(receipts, key=lambda r: r["name"])
    assert first["name"].startswith("RCPT-000001") and last["name"].startswith("RCPT-000002")

    partial = await api.get(f"/api/v1/customer-files/{first['id']}/download")
    text = _text(partial.content)
    assert "4,000.00" in text and "Balance" in text and invoice["number"] in text
    assert "Ayesha Khan" in text and "Brand refresh" in text and "PAID IN FULL" not in text
    full = _text((await api.get(f"/api/v1/customer-files/{last['id']}/download")).content)
    assert "PAID IN FULL" in full and "6,000.00" in full

    timeline = [
        a.summary
        for a in await business_db.scalars(
            select(CustomerActivity).where(CustomerActivity.customer_id == UUID(customer_id))
        )
    ]
    assert any(t.startswith("Receipt RCPT-000001") for t in timeline)

    texts = await _send(pi)
    receipts_sent = [t for t in texts if "/d/" in t and "receipt" in t.lower()]
    assert len(receipts_sent) == 2
    assert not any(t.startswith("Payment received for invoice") for t in texts)  # no 2nd thanks

    token = receipts_sent[-1].rsplit("/d/", 1)[1].split()[0]
    public = _public(api)
    page = (await public.get(f"/api/v1/pi-app/docs/{token}")).json()
    assert page["kind"] == "receipt" and page["receipt"]["name"].startswith("RCPT-000002")
    pdf = await public.get(f"/api/v1/pi-app/docs/{token}/file")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    await pi.close()


async def test_receipt_options_are_respected(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, _ = await _customer_in_chat(pi)
    current = (await api.get(f"{DEALS}/settings")).json()
    current.pop("payment_methods", None)
    saved = await api.put(
        f"{DEALS}/settings",
        json={
            **current,
            "receipt_customer_details": False,
            "receipt_whatsapp": False,
            "receipt_footer": "NTN 1234567 - thank you for your business",
        },
    )
    assert saved.status_code == 200, saved.text
    invoice = await _invoice(api, customer_id)
    await _pay(api, invoice["id"], "10000", "CASH-1")
    [receipt] = (await api.get(f"/api/v1/billing/invoices/{invoice['id']}/receipts")).json()
    text = _text((await api.get(f"/api/v1/customer-files/{receipt['id']}/download")).content)
    assert "Ayesha Khan" not in text and "NTN 1234567" in text
    doc = await pi.db.scalar(
        select(PiDocument).where(
            PiDocument.kind == "receipt", PiDocument.tenant_id == UUID(pi.tenant_id)
        )
    )
    assert doc is not None and doc.delivery == "manual"  # not sent on WhatsApp

    # Switched off: no receipt at all.
    saved = await api.put(f"{DEALS}/settings", json={**current, "auto_receipt": False})
    assert saved.status_code == 200
    second = await _invoice(api, customer_id)
    await _pay(api, second["id"], "10000", "CASH-2")
    assert (await api.get(f"/api/v1/billing/invoices/{second['id']}/receipts")).json() == []
    count = len(
        list(
            await pi.db.scalars(
                select(CustomerFile).where(
                    CustomerFile.source == "receipt",
                    CustomerFile.tenant_id == UUID(pi.tenant_id),
                )
            )
        )
    )
    assert count == 1
    await pi.close()
