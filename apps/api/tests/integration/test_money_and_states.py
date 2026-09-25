"""Decimal money (ROUND_HALF_UP, never float), currency rules, and state machines."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.support.workspace import (
    Actor,
    accepted_quote,
    add_member,
    error_code,
    product,
    set_business,
)

pytestmark = pytest.mark.integration


async def expect(actor: Actor, method: str, path: str, body, status: int, code: str | None = None):
    response = await actor.client.request(method, f"/api/v1/{path}", json=body)
    assert response.status_code == status, (method, path, response.text)
    if code is not None:
        assert error_code(response) == code, (method, path, response.text)
    return response


async def test_quote_totals_round_half_up_at_every_step(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, tax_rate="0.075")
        item = await product(owner, price="33.35")
        customer = await owner.create("customers", {"name": "Totals"})
        quote = await owner.create(
            "quotes",
            {
                "customer_id": customer["id"],
                "lines": [
                    {"variant_id": item["variants"][0]["id"], "quantity": "3"},
                    # 1.5 x 10.03 = 15.045: HALF_UP gives 15.05 (banker's rounding: 15.04).
                    {
                        "description": "Custom work",
                        "quantity": "1.5",
                        "unit_price": "10.03",
                        "discount": "0.10",
                    },
                ],
            },
        )
        assert [line["line_total"] for line in quote["lines"]] == ["100.05", "14.95"]
        assert quote["subtotal"] == "115.10"
        assert quote["discount_total"] == "0.10"
        # taxable 115.00 x 0.075 = 8.625 -> 8.63 (banker's: 8.62)
        assert quote["tax_rate"] == "0.0750" and quote["tax_total"] == "8.63"
        assert quote["total"] == "123.63"
        assert quote["lines"][1]["quantity"] == "1.500"


async def test_order_and_invoice_totals_are_exact_decimals(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, tax_rate="0.075")
        item = await product(owner, price="19.99")
        customer = await owner.create("customers", {"name": "Exact"})
        order = await owner.create(
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [
                    {"variant_id": item["variants"][0]["id"], "quantity": 3, "discount": "0.97"}
                ],
            },
        )
        # 59.97 - 0.97 = 59.00; tax 4.425 -> 4.43
        assert (order["subtotal"], order["discount_total"]) == ("59.97", "0.97")
        assert (order["tax_total"], order["total"]) == ("4.43", "63.43")
        assert order["lines"][0]["unit_price"] == "19.99"  # catalog price, never input
        invoice = await owner.create(
            "billing/invoices",
            {
                "customer_id": customer["id"],
                "lines": [{"description": "Hours", "quantity": "2.5", "unit_price": "3.33"}],
            },
        )
        # 8.325 -> 8.33; tax 0.62475 -> 0.62
        assert (invoice["subtotal"], invoice["tax_total"], invoice["total"]) == (
            "8.33",
            "0.62",
            "8.95",
        )
        assert invoice["balance_due"] == "8.95"


@pytest.mark.parametrize(
    "variant_patch",
    [{"price": "10.001"}, {"price": "-1.00"}, {"price": "123456789012345.00"}, {"price": "abc"}],
    ids=["three-dp", "negative", "too-large", "text"],
)
async def test_invalid_money_inputs_are_rejected(stack, variant_patch):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        item = await product(owner, price="10.00")
        response = await owner.patch(f"catalog/variants/{item['variants'][0]['id']}", variant_patch)
        assert response.status_code == 422
        detail = (await owner.get(f"catalog/products/{item['id']}")).json()
        assert detail["variants"][0]["price"] == "10.00"


async def test_discounts_and_client_prices_are_constrained(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        item = await product(owner, price="5.00")
        vid = item["variants"][0]["id"]
        customer = await owner.create("customers", {"name": "Discounts"})
        await expect(
            owner,
            "POST",
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": vid, "quantity": 1, "discount": "5.01"}],
            },
            422,
            "INVALID_DISCOUNT",
        )
        # Catalog lines cannot carry a client-chosen price; orders have no price field at all.
        await expect(
            owner,
            "POST",
            "quotes",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": vid, "quantity": "1", "unit_price": "0.01"}],
            },
            422,
        )
        await expect(
            owner,
            "POST",
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": vid, "quantity": 1, "unit_price": "0.01"}],
            },
            422,
        )
        await expect(
            owner,
            "POST",
            "orders",
            {"customer_id": customer["id"], "lines": [{"variant_id": vid, "quantity": 0}]},
            422,
        )
        assert (await owner.get("orders")).json()["total"] == 0


async def test_currency_mismatch_is_rejected(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        euro = await product(owner, price="10.00", currency="EUR")
        dollar = await product(owner, price="10.00", currency="USD")
        customer = await owner.create("customers", {"name": "Currency"})
        for path, qty in (("quotes", "1"), ("orders", 1)):
            await expect(
                owner,
                "POST",
                path,
                {
                    "customer_id": customer["id"],
                    "lines": [{"variant_id": euro["variants"][0]["id"], "quantity": qty}],
                },
                422,
                "CURRENCY_MISMATCH",
            )
        draft = await owner.create(
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": dollar["variants"][0]["id"], "quantity": 1}],
            },
        )
        await expect(
            owner,
            "PUT",
            f"orders/{draft['id']}/lines",
            {"lines": [{"variant_id": euro["variants"][0]["id"], "quantity": 1}]},
            422,
            "CURRENCY_MISMATCH",
        )
        await set_business(owner, default_currency="EUR")
        euro_order = await owner.create(
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": euro["variants"][0]["id"], "quantity": 1}],
            },
        )
        assert euro_order["currency"] == "EUR"
        # The earlier USD draft keeps its currency and cannot be re-priced in EUR items silently.
        assert (await owner.get(f"orders/{draft['id']}")).json()["currency"] == "USD"


async def test_pipeline_totals_never_mix_currencies(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await owner.create("sales/leads", {"title": "Dollar", "estimated_value": "100.00"})
        await owner.create(
            "sales/leads", {"title": "Euro", "estimated_value": "50.00", "currency": "EUR"}
        )
        stages = {s["stage"]: s for s in (await owner.get("sales/pipeline")).json()}
        assert stages["new"]["count"] == 2
        assert stages["new"]["value"] == "100.00"
        assert stages["won"]["value"] == "0.00"


async def test_quote_state_machine_rejects_illegal_moves(stack):
    async with stack.browser() as ob, stack.browser() as sb:
        owner = await stack.register(ob)
        await set_business(owner, max_discount_rate="0.05")
        item = await product(owner, price="100.00")
        vid = item["variants"][0]["id"]
        customer = await owner.create("customers", {"name": "States"})
        quote = await owner.create(
            "quotes",
            {"customer_id": customer["id"], "lines": [{"variant_id": vid, "quantity": "1"}]},
        )
        qid = quote["id"]
        assert quote["status"] == "draft" and quote["next_actions"] == ["submit", "cancel"]
        for action in ("send", "accept", "reject", "expire"):
            await expect(
                owner,
                "POST",
                f"quotes/{qid}/actions",
                {"action": action},
                422,
                "INVALID_TRANSITION",
            )
        await expect(
            owner, "POST", f"quotes/{qid}/actions", {"action": "delete"}, 422, "VALIDATION_ERROR"
        )
        await expect(
            owner, "PATCH", f"quotes/{qid}", {"status": "accepted"}, 422, "VALIDATION_ERROR"
        )
        await expect(owner, "PATCH", f"quotes/{qid}", {"total": "0.01"}, 422, "VALIDATION_ERROR")
        await expect(owner, "POST", f"quotes/{qid}/order", None, 422, "QUOTE_NOT_ACCEPTED")
        past = str(date.today() - timedelta(days=1))
        await expect(
            owner, "PATCH", f"quotes/{qid}", {"valid_until": past}, 422, "INVALID_VALIDITY"
        )
        assert (await owner.get(f"quotes/{qid}")).json()["status"] == "draft"

        # A 10% discount exceeds max_discount_rate, so submission needs an approver.
        updated = await owner.patch(
            f"quotes/{qid}", {"lines": [{"variant_id": vid, "quantity": "1", "discount": "10.00"}]}
        )
        assert updated.json()["requires_approval"] is True and updated.json()["total"] == "90.00"
        pending = await owner.create(f"quotes/{qid}/actions", {"action": "submit"})
        assert pending["status"] == "pending_approval"
        await expect(
            owner, "POST", f"quotes/{qid}/actions", {"action": "submit"}, 422, "INVALID_TRANSITION"
        )
        await expect(
            owner, "POST", f"quotes/{qid}/actions", {"action": "send"}, 422, "INVALID_TRANSITION"
        )
        await expect(owner, "PATCH", f"quotes/{qid}", {"notes": "edit"}, 422, "QUOTE_LOCKED")
        seller = await stack.login(sb, await add_member(owner, ["sales"]))
        await expect(
            seller, "POST", f"quotes/{qid}/actions", {"action": "approve"}, 403, "FORBIDDEN"
        )
        assert (await owner.get(f"quotes/{qid}")).json()["status"] == "pending_approval"
        approved = await owner.create(f"quotes/{qid}/actions", {"action": "approve"})
        assert approved["status"] == "approved" and approved["approved_at"]
        sent = await seller.create(f"quotes/{qid}/actions", {"action": "send"})
        assert sent["next_actions"] == ["accept", "reject", "expire", "cancel"]
        cancelled = await owner.create(f"quotes/{qid}/actions", {"action": "cancel"})
        assert cancelled["next_actions"] == []
        for action in ("submit", "approve", "return_to_draft", "send", "accept", "cancel"):
            await expect(owner, "POST", f"quotes/{qid}/actions", {"action": action}, 422)
        assert (await owner.get(f"quotes/{qid}")).json()["status"] == "cancelled"


async def test_expired_quote_cannot_be_sent_or_accepted(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        item = await product(owner, price="20.00")
        customer = await owner.create("customers", {"name": "Expiry"})
        lines = [{"variant_id": item["variants"][0]["id"], "quantity": "1"}]
        sent = await owner.create("quotes", {"customer_id": customer["id"], "lines": lines})
        for action in ("submit", "send"):
            sent = await owner.create(f"quotes/{sent['id']}/actions", {"action": action})
        approved = await owner.create("quotes", {"customer_id": customer["id"], "lines": lines})
        approved = await owner.create(f"quotes/{approved['id']}/actions", {"action": "submit"})
        await stack.app.state.test_connection.execute(
            text("UPDATE quotes SET valid_until = CURRENT_DATE - 1 WHERE id IN (:a, :b)"),
            {"a": sent["id"], "b": approved["id"]},
        )
        await _expired_checks(owner, sent, approved)


async def _expired_checks(owner, sent, approved):
    await expect(
        owner, "POST", f"quotes/{approved['id']}/actions", {"action": "send"}, 422, "QUOTE_EXPIRED"
    )
    await expect(
        owner, "POST", f"quotes/{sent['id']}/actions", {"action": "accept"}, 422, "QUOTE_EXPIRED"
    )
    expired = await owner.create(f"quotes/{sent['id']}/actions", {"action": "expire"})
    assert expired["status"] == "expired"


async def test_order_state_machine_and_locked_fields(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, business_type="product_business")
        item = await product(owner, price="8.00", offering_type="product")
        vid = item["variants"][0]["id"]
        customer = await owner.create("customers", {"name": "Order states"})
        body = {"customer_id": customer["id"], "lines": [{"variant_id": vid, "quantity": 1}]}
        await expect(
            owner, "POST", "orders", {**body, "status": "delivered"}, 422, "VALIDATION_ERROR"
        )
        await expect(owner, "POST", "orders", {**body, "total": "0.00"}, 422, "VALIDATION_ERROR")
        order = await owner.create("orders", body)
        oid = order["id"]
        assert order["status"] == "draft" and order["next_actions"] == ["confirm", "cancel"]
        for action in ("start_processing", "ship", "deliver", "complete"):
            await expect(owner, "POST", f"orders/{oid}/actions", {"action": action}, 422)
        await expect(
            owner, "POST", f"orders/{oid}/actions", {"action": "refund"}, 422, "VALIDATION_ERROR"
        )

        # A price change after drafting blocks confirmation instead of charging silently.
        await owner.patch(f"catalog/variants/{vid}", {"price": "9.00"})
        await expect(
            owner, "POST", f"orders/{oid}/actions", {"action": "confirm"}, 422, "PRICE_CHANGED"
        )
        detail = (await owner.get(f"orders/{oid}")).json()
        assert detail["status"] == "draft" and detail["invoice_id"] is None
        repriced = await owner.put(
            f"orders/{oid}/lines", {"lines": [{"variant_id": vid, "quantity": 1}]}
        )
        assert repriced.json()["total"] == "9.00"

        for action, status in (
            ("confirm", "confirmed"),
            ("start_processing", "processing"),
            ("ship", "shipped"),
        ):
            order = await owner.create(f"orders/{oid}/actions", {"action": action})
            assert order["status"] == status
        await expect(
            owner, "PUT", f"orders/{oid}/lines", {"lines": body["lines"]}, 422, "ORDER_LOCKED"
        )
        await expect(
            owner, "POST", f"orders/{oid}/actions", {"action": "confirm"}, 422, "INVALID_TRANSITION"
        )
        await expect(
            owner, "POST", f"orders/{oid}/actions", {"action": "cancel"}, 422, "INVALID_TRANSITION"
        )
        order = await owner.create(f"orders/{oid}/actions", {"action": "deliver"})
        assert order["status"] == "delivered" and order["next_actions"] == []
        for action in ("confirm", "start_processing", "ship", "deliver", "cancel", "complete"):
            await expect(owner, "POST", f"orders/{oid}/actions", {"action": action}, 422)


async def test_invoice_and_payment_rules(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        customer = await owner.create("customers", {"name": "Invoices"})
        lines = [{"description": "Work", "quantity": "1", "unit_price": "100.00"}]
        invoice = await owner.create(
            "billing/invoices", {"customer_id": customer["id"], "lines": lines}
        )
        iid = invoice["id"]
        assert invoice["status"] == "draft" and invoice["next_actions"] == ["issue", "void"]
        pay = f"billing/invoices/{iid}/payments"
        await expect(
            owner, "POST", pay, {"amount": "10.00", "method": "cash"}, 422, "INVOICE_NOT_OPEN"
        )
        await expect(
            owner,
            "POST",
            f"billing/invoices/{iid}/actions",
            {"action": "pay"},
            422,
            "VALIDATION_ERROR",
        )
        issued = await owner.create(f"billing/invoices/{iid}/actions", {"action": "issue"})
        assert issued["status"] == "issued" and issued["due_date"]
        await expect(
            owner,
            "POST",
            f"billing/invoices/{iid}/actions",
            {"action": "issue"},
            422,
            "INVALID_TRANSITION",
        )
        for amount in ("0", "-5.00", "10.001"):
            await expect(
                owner, "POST", pay, {"amount": amount, "method": "cash"}, 422, "VALIDATION_ERROR"
            )
        await expect(
            owner, "POST", pay, {"amount": "10.00", "method": "barter"}, 422, "VALIDATION_ERROR"
        )
        await expect(owner, "POST", pay, {"amount": "100.01", "method": "cash"}, 422, "OVERPAYMENT")
        payment = await owner.create(pay, {"amount": "33.33", "method": "card"})
        assert payment["amount"] == "33.33" and payment["currency"] == "USD"
        detail = (await owner.get(f"billing/invoices/{iid}")).json()
        assert (detail["status"], detail["amount_paid"], detail["balance_due"]) == (
            "partially_paid",
            "33.33",
            "66.67",
        )
        await expect(
            owner,
            "POST",
            f"billing/invoices/{iid}/actions",
            {"action": "void"},
            422,
            "INVOICE_HAS_PAYMENTS",
        )
        await expect(owner, "POST", pay, {"amount": "66.68", "method": "cash"}, 422, "OVERPAYMENT")
        await owner.create(pay, {"amount": "66.67", "method": "bank_transfer"})
        detail = (await owner.get(f"billing/invoices/{iid}")).json()
        assert (detail["status"], detail["balance_due"], detail["next_actions"]) == (
            "paid",
            "0.00",
            [],
        )
        await expect(
            owner, "POST", pay, {"amount": "0.01", "method": "cash"}, 422, "INVOICE_NOT_OPEN"
        )
        await expect(owner, "POST", f"billing/invoices/{iid}/actions", {"action": "void"}, 422)
        numbers = [p["number"] for p in (await owner.get("billing/payments")).json()["items"]]
        assert sorted(numbers) == ["PAY-000001", "PAY-000002"]

        other = await owner.create(
            "billing/invoices", {"customer_id": customer["id"], "lines": lines}
        )
        voided = await owner.create(f"billing/invoices/{other['id']}/actions", {"action": "void"})
        assert voided["status"] == "void"
        await expect(
            owner,
            "POST",
            f"billing/invoices/{other['id']}/payments",
            {"amount": "1.00", "method": "cash"},
            422,
            "INVOICE_NOT_OPEN",
        )
        await expect(
            owner,
            "POST",
            f"billing/invoices/{other['id']}/actions",
            {"action": "issue"},
            422,
            "INVALID_TRANSITION",
        )
        summary = (await owner.get("billing/summary")).json()
        assert summary["outstanding"] == "0.00" and summary["draft_count"] == 0


async def test_expense_lead_and_customer_state_rules(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        today = date.today()
        body = {
            "category": "travel",
            "description": "Taxi",
            "amount": "12.50",
            "incurred_on": str(today),
        }
        await expect(
            owner,
            "POST",
            "finance/expenses",
            {**body, "incurred_on": str(today + timedelta(days=1))},
            422,
            "FUTURE_DATE",
        )
        await expect(
            owner, "POST", "finance/expenses", {**body, "amount": "0"}, 422, "VALIDATION_ERROR"
        )
        await expect(
            owner, "POST", "finance/expenses", {**body, "status": "void"}, 422, "VALIDATION_ERROR"
        )
        expense = await owner.create("finance/expenses", body)
        await owner.create(f"finance/expenses/{expense['id']}/void", None)
        await expect(
            owner, "POST", f"finance/expenses/{expense['id']}/void", None, 422, "ALREADY_VOID"
        )
        period = {"start": str(today - timedelta(days=400)), "end": str(today)}
        await expect(
            owner,
            "GET",
            "finance/summary?start={start}&end={end}".format(**period),
            None,
            422,
            "INVALID_PERIOD",
        )

        lead = await owner.create("sales/leads", {"title": "Deal"})
        await expect(
            owner,
            "PUT",
            f"sales/leads/{lead['id']}/stage",
            {"stage": "won"},
            422,
            "INVALID_TRANSITION",
        )
        await expect(
            owner,
            "PUT",
            f"sales/leads/{lead['id']}/stage",
            {"stage": "closed"},
            422,
            "VALIDATION_ERROR",
        )
        for stage in ("qualified", "proposal", "won"):
            moved = await owner.put(f"sales/leads/{lead['id']}/stage", {"stage": stage})
            assert moved.status_code == 200
        assert moved.json()["closed_at"]
        await expect(
            owner,
            "PUT",
            f"sales/leads/{lead['id']}/stage",
            {"stage": "lost"},
            422,
            "INVALID_TRANSITION",
        )

        customer = await owner.create("customers", {"name": "Status"})
        await expect(
            owner,
            "PUT",
            f"customers/{customer['id']}/status",
            {"status": "deleted"},
            422,
            "VALIDATION_ERROR",
        )
        await expect(
            owner,
            "PATCH",
            f"customers/{customer['id']}",
            {"status": "archived"},
            422,
            "VALIDATION_ERROR",
        )
        await expect(
            owner,
            "PATCH",
            f"customers/{customer['id']}",
            {"source": "import"},
            422,
            "VALIDATION_ERROR",
        )
        assert (await owner.get(f"customers/{customer['id']}")).json()["status"] == "active"


async def test_accepted_quote_prices_carry_over_even_if_catalog_changes(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        item = await product(owner, price="40.00")
        vid = item["variants"][0]["id"]
        customer = await owner.create("customers", {"name": "Agreed price"})
        quote = await accepted_quote(owner, customer["id"], [{"variant_id": vid, "quantity": "2"}])
        await owner.patch(f"catalog/variants/{vid}", {"price": "55.00"})
        order = await owner.create(f"quotes/{quote['id']}/order", {})
        assert order["total"] == quote["total"] == "80.00"
        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
        invoice = (await owner.get(f"billing/invoices/{confirmed['invoice_id']}")).json()
        assert invoice["total"] == "80.00" and invoice["lines"][0]["unit_price"] == "40.00"
