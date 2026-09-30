"""Customer payments (a business collecting from its own customers): Pakistani bank
transfer, wallets and cash, verified by staff; Stripe via the business's own connection.
AI is mocked; no provider is called for bank/wallet/cash."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn
from test_service_lifecycle import create

from app.modules.billing.models import Payment
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.customer_payments import iban_valid

pytestmark = pytest.mark.integration

MEEZAN = {
    "bank": "Meezan Bank",
    "account_title": "Brightline Studio",
    "account_number": "0101 0101 0101",
    "iban": "PK36SCBL0000001123456702",
    "branch": "Gulberg, Lahore",
}


def test_iban_validation():
    assert iban_valid("PK36SCBL0000001123456702")
    assert iban_valid("pk36 scbl 0000 0011 2345 6702")
    assert not iban_valid("PK36SCBL0000001123456703")  # checksum
    assert not iban_valid("PK36SCBL00000011234567")  # length
    assert iban_valid("GB82WEST12345698765432")


async def _invoice(api, customer_id: str, amount: str = "15000.00") -> dict:
    invoice = await create(
        api,
        "billing/invoices",
        {
            "customer_id": customer_id,
            "lines": [{"description": "Website design", "quantity": "1", "unit_price": amount}],
        },
    )
    await create(api, f"billing/invoices/{invoice['id']}/actions", {"action": "issue"})
    return invoice


async def _enable(api, **values) -> dict:
    body = {
        "bank_enabled": True,
        "bank_accounts": [MEEZAN],
        "wallet_enabled": True,
        "wallets": [
            {"provider": "jazzcash", "account_title": "Brightline Studio", "number": "03001234567"}
        ],
        "cash_enabled": True,
        "cash_instructions": "Pay cash at our Gulberg office.",
        **values,
    }
    response = await api.put("/api/v1/pi/customer-payments/settings", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def test_bank_transfer_is_only_paid_after_staff_verification(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        bad = await api.put(
            "/api/v1/pi/customer-payments/settings",
            json={"bank_enabled": True, "bank_accounts": []},
        )
        assert bad.status_code == 422
        bad_iban = await api.put(
            "/api/v1/pi/customer-payments/settings",
            json={"bank_enabled": True, "bank_accounts": [{**MEEZAN, "iban": "PK00BAD"}]},
        )
        assert bad_iban.status_code == 422
        # Card can't be switched on without Stripe, but it never blocks saving the rest.
        no_stripe = await api.put(
            "/api/v1/pi/customer-payments/settings",
            json={"stripe_enabled": True, "cash_enabled": True, "cash_instructions": "Office"},
        )
        assert no_stripe.status_code == 200, no_stripe.text
        assert no_stripe.json()["stripe_enabled"] is False
        assert no_stripe.json()["enabled_methods"] == ["cash"]
        settings = await _enable(api)
        assert settings["enabled_methods"] == ["bank_transfer", "mobile_wallet", "cash"]
        customer = await create(api, "customers", {"name": "Bilal", "tags": []})
        invoice = await _invoice(api, customer["id"])
        key = str(uuid4())
        body = {"invoice_id": invoice["id"], "method": "bank_transfer", "request_key": key}
        first = await create(api, "pi/payment-requests", body)
        again = await create(api, "pi/payment-requests", body)
        assert first["id"] == again["id"] and first["reference"].startswith("PAY-")
        assert first["amount"] == "15000.00" and first["status"] == "open"
        assert (
            "PK36SCBL0000001123456702" in first["message"]
            and first["reference"] in first["message"]
        )
        # Bank details changing later never alters the instructions already sent.
        await _enable(api, bank_accounts=[{**MEEZAN, "account_title": "New title"}])
        listed = (await api.get("/api/v1/pi/payment-requests")).json()
        assert "Brightline Studio" in listed[0]["message"]
        # "Not received" records nothing.
        response = await api.post(
            f"/api/v1/pi/payment-requests/{first['id']}/verify", json={"received": False}
        )
        assert response.status_code == 200 and response.json()["status"] == "open"
        assert (await api.get(f"/api/v1/billing/invoices/{invoice['id']}")).json()[
            "status"
        ] == "issued"
        verified = await api.post(
            f"/api/v1/pi/payment-requests/{first['id']}/verify",
            json={"received": True, "reference": "FT-99812"},
        )
        assert verified.status_code == 200 and verified.json()["status"] == "paid"
        paid = (await api.get(f"/api/v1/billing/invoices/{invoice['id']}")).json()
        assert paid["status"] == "paid"
        payment = await business_db.scalar(
            select(Payment).where(Payment.invoice_id == UUID(invoice["id"]))
        )
        assert payment.method == "bank_transfer" and payment.reference == "FT-99812"
        twice = await api.post(
            f"/api/v1/pi/payment-requests/{first['id']}/verify", json={"received": True}
        )
        assert twice.status_code == 409  # never recorded twice
    finally:
        await pi.close()


async def test_cash_and_wallet_record_the_right_method(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        await _enable(api)
        customer = await create(api, "customers", {"name": "Sara", "tags": []})
        for method, expected in (("cash", "cash"), ("mobile_wallet", "mobile_wallet")):
            invoice = await _invoice(api, customer["id"], "2500.00")
            request = await create(
                api, "pi/payment-requests", {"invoice_id": invoice["id"], "method": method}
            )
            if method == "mobile_wallet":
                assert "JazzCash: 03001234567" in request["message"]
            if method == "cash":
                # Another method for the same invoice is a separate request, created once.
                wallet = {"invoice_id": invoice["id"], "method": "mobile_wallet"}
                first = await create(api, "pi/payment-requests", wallet)
                second = await create(api, "pi/payment-requests", wallet)
                assert first["id"] == second["id"] != request["id"]
                assert first["method"] == "mobile_wallet"
            await create(api, f"pi/payment-requests/{request['id']}/verify", {"received": True})
            payment = await business_db.scalar(
                select(Payment).where(Payment.invoice_id == UUID(invoice["id"]))
            )
            assert payment.method == expected
    finally:
        await pi.close()


async def test_pi_sends_exact_payment_details_for_the_customers_own_invoice(
    api, business_db, monkeypatch
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    try:
        await _enable(api)
        for tool in ("request_payment", "get_payment_status"):
            response = await api.put(f"/api/v1/pi/tools/{tool}/enabled", json={"enabled": True})
            assert response.status_code == 200, response.text
        mock_turns(
            monkeypatch,
            turn(reply="Assalam o alaikum! Kaise madad karoon?"),
            turn(
                reply="Zaroor, yeh raha payment ka tareeqa.",
                action="payment",
                payment_method="bank_transfer",
            ),
            turn(reply="Shukriya! Hamari team payment check kar ke confirm karegi."),
        )
        await pi.process("Salam", "pay-1")
        conversation = await pi.conversation()
        other = await create(api, "customers", {"name": "Someone else", "tags": []})
        await _invoice(api, other["id"], "99000.00")  # never offered to this customer
        own = await _invoice(api, str(conversation.customer_id), "15000.00")
        await pi.process("Main payment kaise karoon?", "pay-2")
        reply = await pi.reply_to("pay-2")
        assert "Amount due: 15,000.00" in reply.body and "99,000" not in reply.body
        assert "IBAN: PK36SCBL0000001123456702" in reply.body
        request = await business_db.scalar(
            select(PiPaymentRequest).where(PiPaymentRequest.invoice_id == UUID(own["id"]))
        )
        assert request is not None and request.customer_id == conversation.customer_id
        assert request.status == "open"  # a message is not a payment
        # Another customer's invoice can't be sent into this conversation.
        others = await _invoice(api, other["id"], "1000.00")
        mismatch = await api.post(
            "/api/v1/pi/payment-requests",
            json={
                "invoice_id": others["id"],
                "method": "cash",
                "conversation_id": str(conversation.id),
            },
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["error"]["code"] == "CONVERSATION_MISMATCH"
        # The customer reports paying: staff see it to verify; it is still not paid.
        await pi.process(f"Maine bhej diya hai, ref {request.reference}", "pay-3")
        await business_db.refresh(request)
        assert request.status == "awaiting_verification"
        assert request.reference in request.proof_note and request.proof_message_id
        queue = (await api.get("/api/v1/pi/payment-requests", params={"status": "active"})).json()
        assert [r["id"] for r in queue] == [str(request.id)]
    finally:
        await pi.close()
