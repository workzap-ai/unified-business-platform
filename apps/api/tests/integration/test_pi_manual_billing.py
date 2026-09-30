"""Local DB acceptance for subscription collection, with mocked external providers."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from sqlalchemy import select
from test_service_lifecycle import register

from app.modules.pi_saas import billing, manual_billing
from app.modules.pi_saas.models import PiBillingEvent, PiOperatorMember, PiPlan, PiSubscription
from app.modules.pi_saas.payment_models import PiCollectionSettings, PiManualPayment

pytestmark = pytest.mark.integration
CLIENT = "/api/v1/pi-app/billing"
ADMIN = "/api/v1/operator/pi/billing"
# Published-format example used only in the isolated test database.
CONFIG = {
    "seller_name": "Test Pi",
    "bank_enabled": True,
    "bank_name": "Test bank",
    "account_title": "Test Pi",
    "iban": "PK36SCBL0000001123456702",
    "cash_enabled": True,
    "cash_instructions": "Pay the test cashier at the test office",
}


@pytest.fixture
async def collection(api, business_db):
    app = api._transport.app
    provider = FakeProvider()
    configure(app, provider)
    identity = await register(api)
    operator = PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner")
    business_db.add(operator)
    await business_db.flush()
    response = await api.put(ADMIN + "/settings", json=CONFIG)
    assert response.status_code == 200, response.text
    plan = await business_db.scalar(select(PiPlan).where(PiPlan.key == "starter"))
    plan.manual_monthly_price_pkr = Decimal("2500.00")
    plan.monthly_price, plan.stripe_price_id = Decimal("10.00"), "price_starterTEST1"
    await business_db.flush()
    client = pi_client(app)
    view = await pi_register(client)
    yield app, client, view["business"]["id"], operator, provider
    await client.aclose()


async def request(client, method="cash", **extra):
    body = {"request_key": str(uuid4()), "plan": "starter", "method": method, **extra}
    response = await client.post(CLIENT + "/payments", json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


async def submit(client, row, reference=""):
    response = await client.post(
        CLIENT + f"/payments/{row['id']}/submit",
        json={
            "payer_name": "Test payer",
            "reference": reference,
            "paid_on": datetime.now(UTC).date().isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def review(api, tenant, row, action="approve"):
    response = await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{row['id']}/review",
        json={"action": action, "note": "Receipt independently checked", "verified_received": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_cash_claim_never_activates_until_review_and_duplicate_review_does_not_extend(
    collection, api, business_db
):
    _, client, tenant, _, _ = collection
    row, body = await request(client, months=3)
    assert row["amount"] == "7500.00"
    retry = await client.post(CLIENT + "/payments", json=body)
    assert retry.json()["id"] == row["id"]
    conflict = await client.post(CLIENT + "/payments", json={**body, "months": 6})
    assert conflict.status_code == 409
    await submit(client, row)
    before = (await client.get(CLIENT)).json()["subscription"]
    assert before["status"] == "trialing"
    assert (await client.get(CLIENT + f"/payments/{row['id']}/receipt")).status_code == 409
    approved = await review(api, tenant, row)
    again = await review(api, tenant, row)
    assert again["period_end"] == approved["period_end"]
    assert again["receipt_number"] == approved["receipt_number"]
    subscription = (await client.get(CLIENT)).json()["subscription"]
    assert (
        subscription["status"] == "active"
        and subscription["current_period_end"] == approved["period_end"]
    )
    receipt = await client.get(CLIENT + f"/payments/{row['id']}/receipt")
    assert receipt.status_code == 200 and "7,500.00" in receipt.text
    assert receipt.headers["cache-control"] == "no-store"
    assert (await client.post(CLIENT + f"/payments/{row['id']}/cancel")).status_code == 409


async def test_bank_receipt_and_reference_are_required_and_cannot_be_reused_between_tenants(
    collection, api, business_db
):
    app, client, tenant, _, _ = collection
    row, _ = await request(client, "bank_transfer")
    claim = {
        "payer_name": "Amina",
        "reference": "TRX-101",
        "paid_on": datetime.now(UTC).date().isoformat(),
    }
    missing_proof = await client.post(CLIENT + f"/payments/{row['id']}/submit", json=claim)
    assert (
        missing_proof.status_code == 422
        and missing_proof.json()["error"]["code"] == "PROOF_REQUIRED"
    )
    assert (
        await client.post(
            CLIENT + f"/payments/{row['id']}/proof",
            files={"file": ("bad.html", b"<script>alert(1)</script>", "text/html")},
        )
    ).status_code == 415
    proof = await client.post(
        CLIENT + f"/payments/{row['id']}/proof",
        files={"file": ("receipt.pdf", b"%PDF-1.4 test receipt", "application/pdf")},
    )
    assert proof.status_code == 200 and proof.json()["has_proof"]
    assert (
        await client.post(CLIENT + f"/payments/{row['id']}/submit", json=claim)
    ).status_code == 200
    assert (
        await client.post(CLIENT + f"/payments/{row['id']}/submit", json=claim)
    ).status_code == 200
    assert (
        await client.post(
            CLIENT + f"/payments/{row['id']}/proof",
            files={"file": ("changed.pdf", b"%PDF-1.4 changed")},
        )
    ).status_code == 409
    other = pi_client(app)
    await pi_register(other, "Another business")
    assert (await other.get(CLIENT + f"/payments/{row['id']}/proof")).status_code == 404
    assert (await other.get(CLIENT + f"/payments/{row['id']}/receipt")).status_code == 404
    second, _ = await request(other, "bank_transfer")
    await other.post(
        CLIENT + f"/payments/{second['id']}/proof", files={"file": ("proof.pdf", b"%PDF-1.4 copy")}
    )
    duplicate = await other.post(
        CLIENT + f"/payments/{second['id']}/submit", json={**claim, "reference": "trx 101"}
    )
    assert duplicate.status_code == 409
    assert "already" in duplicate.text
    await review(api, tenant, row)
    await other.aclose()


async def test_permissions_settings_validation_and_exact_amount_are_enforced(
    collection, api, business_db
):
    _, client, tenant, operator, _ = collection
    assert (await client.get(ADMIN + "/settings")).status_code == 401
    bad = await api.put(ADMIN + "/settings", json={**CONFIG, "iban": "PK00SCBL0000001123456702"})
    assert bad.status_code == 422
    tamper = await client.post(
        CLIENT + "/payments",
        json={"request_key": str(uuid4()), "plan": "starter", "method": "cash", "amount": "1"},
    )
    assert tamper.status_code == 422
    row, _ = await request(client)
    await submit(client, row)
    operator.role = "support"
    await business_db.flush()
    denied = await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{row['id']}/review",
        json={"action": "approve", "note": "Attempted review", "verified_received": True},
    )
    assert denied.status_code == 403
    operator.role = "billing"
    await business_db.flush()
    assert (await api.put(ADMIN + "/settings", json=CONFIG)).status_code == 403
    unverified = await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{row['id']}/review",
        json={"action": "approve", "note": "Not checked yet"},
    )
    assert unverified.status_code == 422 and unverified.json()["error"]["code"] == "VERIFY_RECEIPT"
    await review(api, tenant, row, "reject")
    assert (await client.get(CLIENT)).json()["subscription"]["status"] == "trialing"


async def test_manual_renewal_and_recorded_refund_preserve_previous_paid_period(
    collection, api, business_db
):
    _, client, tenant, _, _ = collection
    first, _ = await request(client)
    await submit(client, first)
    first = await review(api, tenant, first)
    second, _ = await request(client)
    await submit(client, second)
    second = await review(api, tenant, second)
    assert second["period_start"] == first["period_end"]
    refund = {
        "reference": "refund-receipt-12",
        "reason": "Full cash amount returned",
        "already_refunded": True,
    }
    url = ADMIN + f"/accounts/{tenant}/payments/{second['id']}/refund"
    response = await api.post(url, json=refund)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "refunded"
    assert (await api.post(url, json=refund)).status_code == 200
    assert (await client.get(CLIENT)).json()["subscription"]["current_period_end"] == first[
        "period_end"
    ]
    canceled = await client.post(CLIENT + "/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["subscription"]["cancel_at_period_end"] is True
    assert canceled.json()["subscription"]["entitled"] is True


async def test_operator_cash_receipt_is_idempotent_and_audited(collection, api):
    _, client, tenant, _, _ = collection
    data = {
        "request_key": str(uuid4()),
        "plan": "starter",
        "payer_name": "Cash payer",
        "paid_on": datetime.now(UTC).date().isoformat(),
        "verified_received": True,
        "note": "Cash counted at reception",
    }
    url = ADMIN + f"/accounts/{tenant}/cash"
    first = await api.post(url, json=data)
    assert first.status_code == 201, first.text
    second = await api.post(url, json=data)
    assert second.status_code == 201 and second.json()["id"] == first.json()["id"]
    assert (await client.get(CLIENT + "/payments")).json()["total"] == 1


async def test_stripe_retry_reuses_persisted_key_and_existing_session(collection, business_db):
    app, client, _, _, provider = collection
    captured = []

    def transport(req):
        if req.url.path == "/v1/checkout/sessions":
            captured.append((req.headers["idempotency-key"], req.content))
            if len(captured) == 1:
                raise httpx.ReadTimeout("ambiguous timeout", request=req)
        return provider(req)

    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    first = await client.post(CLIENT + "/checkout", json={"plan": "starter"})
    assert first.status_code == 503
    second = await client.post(CLIENT + "/checkout", json={"plan": "starter"})
    assert second.status_code == 200, second.text
    third = await client.post(CLIENT + "/checkout", json={"plan": "starter"})
    assert third.json() == second.json() and len(captured) == 2
    assert captured[0] == captured[1]
    conflict = await client.post(
        CLIENT + "/payments",
        json={"request_key": str(uuid4()), "plan": "starter", "method": "cash"},
    )
    assert conflict.status_code == 409


async def test_delayed_invoice_failure_does_not_undo_paid_invoice(collection, business_db):
    app, _, tenant, _, _ = collection
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(tenant))
    )
    sub.billing_provider, sub.external_subscription_id, sub.external_customer_id, sub.status = (
        "stripe",
        "sub_order",
        "cus_order",
        "past_due",
    )
    now = int(datetime.now(UTC).timestamp())
    base = {
        "id": "in_order",
        "object": "invoice",
        "subscription": "sub_order",
        "customer": "cus_order",
        "currency": "usd",
        "amount_due": 1000,
        "amount_paid": 1000,
        "status": "paid",
    }
    paid = PiBillingEvent(
        provider="stripe",
        event_id="evt_paid_order",
        event_type="invoice.paid",
        payload={"created": now, "object": base},
    )
    stale = PiBillingEvent(
        provider="stripe",
        event_id="evt_stale_order",
        event_type="invoice.payment_failed",
        payload={"created": now - 30, "object": {**base, "status": "open", "amount_paid": 0}},
    )
    business_db.add_all([paid, stale])
    await business_db.flush()
    await billing.apply_event(business_db, app.state.settings, paid)
    await business_db.flush()
    await billing.apply_event(business_db, app.state.settings, stale)
    assert sub.status == "active"


async def test_bank_configuration_and_runtime_never_return_secrets(collection, api):
    _, _, _, _, _ = collection
    response = await api.get(ADMIN + "/settings")
    assert response.status_code == 200
    raw = json.dumps(response.json())
    assert "sk_test_platform" not in raw and "kapso-test-project-key" not in raw
    assert response.json()["runtime"]["stripe"]["mode"] == "test"


def test_month_end_renewal_keeps_a_calendar_month():
    end = manual_billing.add_months(datetime(2026, 1, 31, 12, tzinfo=UTC), 1)
    assert end == datetime(2026, 2, 28, 12, tzinfo=UTC)


async def test_summary_counts_verified_money_and_refunds_once(collection, api):
    _, client, tenant, _, _ = collection
    row, _ = await request(client, months=3)
    await submit(client, row)
    before = (await api.get(ADMIN + "/summary")).json()
    assert before["pending_count"] == 1 and Decimal(before["received_pkr"]) == 0
    await review(api, tenant, row)
    response = await api.post(
        ADMIN + f"/accounts/{tenant}/payments/{row['id']}/refund",
        json={
            "reference": "returned-789",
            "reason": "Cash returned in full",
            "already_refunded": True,
        },
    )
    assert response.status_code == 200
    summary = (await api.get(ADMIN + "/summary")).json()
    assert Decimal(summary["received_pkr"]) == Decimal(summary["refunded_pkr"]) == 7500
    assert Decimal(summary["net_pkr"]) == 0 and summary["pending_count"] == 0


async def test_manual_expiry_updates_status_and_blocks_entitlement(collection, api, business_db):
    _, client, tenant, _, _ = collection
    row, _ = await request(client)
    await submit(client, row)
    await review(api, tenant, row)
    sub = await business_db.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == UUID(tenant))
    )
    sub.current_period_end = sub.grace_ends_at = datetime.now(UTC) - timedelta(seconds=1)
    await business_db.flush()
    assert await billing.sweep_lifecycle(business_db) == 1
    result = (await client.get(CLIENT)).json()["subscription"]
    assert result["status"] == "suspended" and result["entitled"] is False


async def test_simultaneous_approvals_extend_only_once(live_stack):
    app = live_stack.app
    configure(app, FakeProvider())
    client = pi_client(app)
    view = await pi_register(client)
    sessions = app.state.sessions
    async with sessions() as session:
        from app.modules.pi_saas.models import PiBusinessAccount

        account = await session.scalar(
            select(PiBusinessAccount).where(
                PiBusinessAccount.tenant_id == UUID(view["business"]["id"])
            )
        )
        actor = account.created_by_user_id
        config = await session.scalar(
            select(PiCollectionSettings).where(PiCollectionSettings.key == "platform")
        )
        if config:
            config.config = CONFIG
        else:
            session.add(PiCollectionSettings(key="platform", config=CONFIG))
        plan = await session.scalar(select(PiPlan).where(PiPlan.key == "starter"))
        plan.manual_monthly_price_pkr = Decimal("2500")
        await session.commit()
    row, _ = await request(client)
    await submit(client, row)

    async def approve():
        async with sessions() as session:
            payment = await manual_billing.decide_payment(
                session, account.tenant_id, UUID(row["id"]), actor, "approve", "Received cash"
            )
            result = (payment.receipt_number, payment.period_end)
            await session.commit()
            return result

    results = await asyncio.gather(*(approve() for _ in range(4)))
    assert len(set(results)) == 1
    async with sessions() as session:
        payment = await session.get(PiManualPayment, UUID(row["id"]))
        sub = await session.scalar(
            select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
        )
        assert sub.current_period_end == payment.period_end
    await client.aclose()
