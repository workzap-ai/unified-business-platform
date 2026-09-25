"""Business mutations write outbox events in the same transaction (outbound webhooks)."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integrations.models import OutboxEvent
from tests.support.workspace import accepted_quote, product, receive, set_business

pytestmark = pytest.mark.integration


async def events(stack, tenant_id: str) -> list[OutboxEvent]:
    async with AsyncSession(
        bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
    ) as session:
        rows = await session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.tenant_id == UUID(tenant_id))
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
        )
        return list(rows)


async def test_order_lifecycle_emits_typed_events_once(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, business_type="product_business", low_stock_threshold=5)
        item = await product(owner, price="10.00", tracked=True)
        vid = item["variants"][0]["id"]
        await receive(owner, vid, 8)
        customer = await owner.create("customers", {"name": "Event customer"})
        await owner.ok("PATCH", f"customers/{customer['id']}", {"company": "Acme"})
        quote = await accepted_quote(owner, customer["id"], [{"variant_id": vid, "quantity": "4"}])
        order = await owner.create(f"quotes/{quote['id']}/order", {})
        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})

        # A rejected mutation emits nothing.
        repeat = await owner.post(f"orders/{order['id']}/actions", {"action": "confirm"})
        assert repeat.status_code == 422

        invoice_id = confirmed["invoice_id"]
        await owner.create(
            f"billing/invoices/{invoice_id}/payments", {"amount": "10.00", "method": "cash"}
        )
        rest = (await owner.get(f"billing/invoices/{invoice_id}")).json()["balance_due"]
        await owner.create(
            f"billing/invoices/{invoice_id}/payments", {"amount": rest, "method": "card"}
        )

        rows = await events(stack, owner.tenant_id)
        types = [e.event_type for e in rows]
        for expected in (
            "customer.created",
            "customer.updated",
            "quote.approved",
            "order.created",
            "order.confirmed",
            "invoice.issued",
            "inventory.low",
            "payment.received",
            "invoice.paid",
        ):
            assert expected in types, (expected, types)
        assert types.count("order.confirmed") == 1
        assert types.count("payment.received") == 2 and types.count("invoice.paid") == 1
        assert types.count("inventory.low") == 1  # 8 -> 4 crosses the threshold of 5 once

        by_type = {e.event_type: e for e in rows}
        confirmed_event = by_type["order.confirmed"]
        assert confirmed_event.payload["order_id"] == order["id"]
        assert confirmed_event.payload["total"] == confirmed["total"]  # decimal string
        assert confirmed_event.entity_type == "order"
        assert all(e.environment_id == UUID(owner.environment_id) for e in rows)
        assert all(e.status == "pending" for e in rows)


async def test_events_are_scoped_to_the_acting_workspace(stack):
    async with stack.browser() as a_browser, stack.browser() as b_browser:
        a = await stack.register(a_browser)
        b = await stack.register(b_browser)
        await a.create("customers", {"name": "Only in A"})
        assert [e.event_type for e in await events(stack, a.tenant_id)] == ["customer.created"]
        assert await events(stack, b.tenant_id) == []
