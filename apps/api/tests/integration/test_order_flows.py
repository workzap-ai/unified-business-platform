"""End-to-end business flows: quote -> order -> stock -> invoice -> payment, and reversals."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.service import InventoryService
from app.modules.orders.service import OrderService
from app.shared.scope import WorkspaceScope
from tests.support.workspace import (
    Actor,
    accepted_quote,
    error_code,
    on_hand,
    product,
    receive,
    set_business,
)

pytestmark = pytest.mark.integration


async def product_workspace(stack, browser) -> tuple[Actor, str, str]:
    owner = await stack.register(browser)
    await set_business(owner, business_type="product_business", tax_rate="0.10")
    item = await product(owner, price="12.50", tracked=True)
    vid = item["variants"][0]["id"]
    await receive(owner, vid, 10)
    customer = await owner.create("customers", {"name": "Flow customer"})
    return owner, vid, customer["id"]


async def movements(actor: Actor, variant_id: str) -> list[dict]:
    page = await actor.get(
        "inventory/movements", params={"variant_id": variant_id, "page_size": 100}
    )
    return page.json()["items"]


async def test_quote_to_order_to_stock_invoice_and_payments(stack):
    async with stack.browser() as browser:
        owner, vid, customer_id = await product_workspace(stack, browser)
        quote = await accepted_quote(owner, customer_id, [{"variant_id": vid, "quantity": "3"}])
        assert quote["total"] == "41.25"  # 37.50 + 10% tax 3.75

        order = await owner.create(f"quotes/{quote['id']}/order", {})
        assert order["status"] == "draft" and order["source"] == "quote"
        assert order["total"] == quote["total"] and order["quote_id"] == quote["id"]
        again = await owner.create(f"quotes/{quote['id']}/order", {})
        assert again["id"] == order["id"]  # conversion is idempotent
        assert (await owner.get(f"quotes/{quote['id']}")).json()["next_actions"] == []
        assert await on_hand(owner, vid) == 10  # drafts reserve nothing

        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
        assert confirmed["status"] == "confirmed" and confirmed["confirmed_at"]
        assert await on_hand(owner, vid) == 7
        sale = [m for m in await movements(owner, vid) if m["kind"] == "sale"]
        assert len(sale) == 1 and sale[0]["quantity"] == -3 and sale[0]["balance_after"] == 7
        assert sale[0]["ref_type"] == "order" and sale[0]["ref_id"] == order["id"]

        # Repeating the confirm is rejected and never moves stock twice.
        repeat = await owner.post(f"orders/{order['id']}/actions", {"action": "confirm"})
        assert repeat.status_code == 422 and error_code(repeat) == "INVALID_TRANSITION"
        assert await on_hand(owner, vid) == 7
        assert len([m for m in await movements(owner, vid) if m["kind"] == "sale"]) == 1

        invoice = (await owner.get(f"billing/invoices/{confirmed['invoice_id']}")).json()
        assert invoice["status"] == "issued" and invoice["order_id"] == order["id"]
        assert (invoice["subtotal"], invoice["tax_total"], invoice["total"]) == (
            "37.50",
            "3.75",
            "41.25",
        )
        assert invoice["lines"][0]["quantity"] == "3.000" and invoice["due_date"]
        assert (await owner.get("billing/invoices")).json()["total"] == 1

        pay = f"billing/invoices/{invoice['id']}/payments"
        await owner.create(pay, {"amount": "20.00", "method": "cash"})
        over = await owner.post(pay, {"amount": "21.26", "method": "cash"})
        assert over.status_code == 422 and error_code(over) == "OVERPAYMENT"
        # An order with money received cannot be cancelled, and nothing is half-applied.
        blocked = await owner.post(f"orders/{order['id']}/actions", {"action": "cancel"})
        assert blocked.status_code == 422 and error_code(blocked) == "INVOICE_HAS_PAYMENTS"
        assert (await owner.get(f"orders/{order['id']}")).json()["status"] == "confirmed"
        assert await on_hand(owner, vid) == 7
        await owner.create(pay, {"amount": "21.25", "method": "card"})
        invoice = (await owner.get(f"billing/invoices/{invoice['id']}")).json()
        assert invoice["status"] == "paid" and invoice["balance_due"] == "0.00"
        customer = (await owner.get(f"customers/{customer_id}")).json()
        assert customer["summary"]["outstanding_balance"] == "0.00"
        assert customer["summary"]["order_count"] == 1

        kinds = [
            a["kind"]
            for a in (await owner.get(f"customers/{customer_id}/activities")).json()["items"]
        ]
        assert {"quote", "order", "invoice", "payment"} <= set(kinds)
        audit = (await owner.get("audit/events", params={"entity_id": order["id"]})).json()
        assert {"order.created_from_quote", "order.confirm"} <= {
            e["action"] for e in audit["items"]
        }


async def test_cancel_after_confirm_restores_stock_and_voids_invoice(stack):
    async with stack.browser() as browser:
        owner, vid, customer_id = await product_workspace(stack, browser)
        order = await owner.create(
            "orders", {"customer_id": customer_id, "lines": [{"variant_id": vid, "quantity": 4}]}
        )
        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
        invoice_id = confirmed["invoice_id"]
        assert await on_hand(owner, vid) == 6
        await owner.create(f"orders/{order['id']}/actions", {"action": "start_processing"})
        cancelled = await owner.create(f"orders/{order['id']}/actions", {"action": "cancel"})
        assert cancelled["status"] == "cancelled" and cancelled["cancelled_at"]
        assert cancelled["invoice_id"] is None  # the voided invoice is no longer linked
        assert await on_hand(owner, vid) == 10
        history = await movements(owner, vid)
        returned = [m for m in history if m["kind"] == "return"]
        assert (
            len(returned) == 1
            and returned[0]["quantity"] == 4
            and returned[0]["balance_after"] == 10
        )
        invoice = (await owner.get(f"billing/invoices/{invoice_id}")).json()
        assert invoice["status"] == "void"
        again = await owner.post(f"orders/{order['id']}/actions", {"action": "cancel"})
        assert again.status_code == 422
        assert await on_hand(owner, vid) == 10 and len(await movements(owner, vid)) == len(history)
        summary = (await owner.get("billing/summary")).json()
        assert summary["outstanding"] == "0.00"


async def test_draft_cancel_moves_nothing_and_insufficient_stock_rolls_back(stack):
    async with stack.browser() as browser:
        owner, vid, customer_id = await product_workspace(stack, browser)
        draft = await owner.create(
            "orders", {"customer_id": customer_id, "lines": [{"variant_id": vid, "quantity": 2}]}
        )
        await owner.create(f"orders/{draft['id']}/actions", {"action": "cancel"})
        assert await on_hand(owner, vid) == 10 and len(await movements(owner, vid)) == 1

        # A second tracked line exists so a partial stock move would be visible.
        other = await product(owner, price="1.00", tracked=True)
        other_vid = other["variants"][0]["id"]
        await receive(owner, other_vid, 5)
        too_big = await owner.create(
            "orders",
            {
                "customer_id": customer_id,
                "lines": [
                    {"variant_id": other_vid, "quantity": 1},
                    {"variant_id": vid, "quantity": 11},
                ],
            },
        )
        response = await owner.post(f"orders/{too_big['id']}/actions", {"action": "confirm"})
        assert response.status_code == 422 and error_code(response) == "INSUFFICIENT_STOCK"
        detail = (await owner.get(f"orders/{too_big['id']}")).json()
        assert detail["status"] == "draft" and detail["invoice_id"] is None
        assert await on_hand(owner, other_vid) == 5 and await on_hand(owner, vid) == 10
        assert (await owner.get("billing/invoices")).json()["total"] == 0

        negative = await owner.post(
            "inventory/adjustments",
            {"variant_id": vid, "quantity": -11, "kind": "adjustment", "reason": "Shrinkage"},
        )
        assert error_code(negative) == "INSUFFICIENT_STOCK"
        receipt = await owner.post(
            "inventory/adjustments",
            {"variant_id": vid, "quantity": -1, "kind": "receipt", "reason": "Bad receipt"},
        )
        assert error_code(receipt) == "INVALID_QUANTITY"
        zero = await owner.post(
            "inventory/adjustments",
            {"variant_id": vid, "quantity": 0, "kind": "adjustment", "reason": "Nothing"},
        )
        assert error_code(zero) == "INVALID_QUANTITY"
        assert await on_hand(owner, vid) == 10


async def test_untracked_services_do_not_move_stock_and_auto_invoice_can_be_disabled(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, auto_invoice_on_order_confirm=False)
        service = await product(owner, price="80.00")
        customer = await owner.create("customers", {"name": "Service client"})
        order = await owner.create(
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": service["variants"][0]["id"], "quantity": 2}],
            },
        )
        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
        assert confirmed["invoice_id"] is None
        assert (await owner.get("billing/invoices")).json()["total"] == 0
        await set_business(owner, business_type="hybrid_business")
        assert (await owner.get("inventory/movements")).json()["total"] == 0


async def test_stock_effects_are_idempotent_at_the_service_layer(stack):
    """Replaying confirm effects (e.g. a retried worker job) cannot double-move stock."""
    async with stack.browser() as browser:
        owner, vid, customer_id = await product_workspace(stack, browser)
        order = await owner.create(
            "orders", {"customer_id": customer_id, "lines": [{"variant_id": vid, "quantity": 2}]}
        )
        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
    session_user = owner.session
    permissions = frozenset(session_user["permissions"])
    connection = stack.app.state.test_connection
    async with AsyncSession(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as session:
        scope = WorkspaceScope.system(
            UUID(session_user["tenant"]["id"]),
            UUID(session_user["environment"]["id"]),
            permissions,
            "retry",
        )
        service = OrderService(session, scope)
        row = await service.orders.get(UUID(order["id"]))
        lines = await service.lines_for(row.id)
        await service._confirm_effects(row, lines)
        await service._confirm_effects(row, lines)
        inventory = InventoryService(session, scope)
        replay = await inventory.move(
            UUID(vid),
            -2,
            "sale",
            "replay",
            idempotency_key=f"order:{row.id}:line:{lines[0].id}:sale",
        )
        assert replay is None
        availability = (await inventory.availability([UUID(vid)]))[UUID(vid)]
        assert availability.on_hand == 8
        await session.flush()
    async with stack.browser() as browser:
        again = await stack.login(browser, owner.email)
        assert await on_hand(again, vid) == 8
        invoices = (await again.get("billing/invoices")).json()
        assert invoices["total"] == 1 and invoices["items"][0]["id"] == confirmed["invoice_id"]
