"""Concurrency safety with real connections and real commits.

These tests commit to the disposable *_test database (each uses a fresh, uniquely named
tenant) because row locks only matter between separate transactions.
"""

import asyncio
from collections import Counter

import pytest

from tests.support.workspace import (
    accepted_quote,
    error_code,
    on_hand,
    product,
    receive,
    set_business,
)

pytestmark = pytest.mark.integration


async def workspace(live_stack, browser, stock: int = 0):
    owner = await live_stack.register(browser)
    await set_business(owner, business_type="product_business")
    item = await product(owner, price="10.00", tracked=True)
    vid = item["variants"][0]["id"]
    if stock:
        await receive(owner, vid, stock)
    customer = await owner.create("customers", {"name": "Concurrent"})
    return owner, vid, customer["id"]


async def test_concurrent_stock_decrements_never_oversell(live_stack):
    async with live_stack.browser() as browser:
        owner, vid, _ = await workspace(live_stack, browser, stock=10)
        body = {
            "variant_id": vid,
            "quantity": -1,
            "kind": "adjustment",
            "reason": "Concurrent pick",
        }
        responses = await asyncio.gather(
            *(owner.post("inventory/adjustments", body) for _ in range(20))
        )
        statuses = Counter(r.status_code for r in responses)
        assert statuses == {201: 10, 422: 10}, statuses
        assert {error_code(r) for r in responses if r.status_code == 422} == {"INSUFFICIENT_STOCK"}
        balances = sorted(r.json()["balance_after"] for r in responses if r.status_code == 201)
        assert balances == list(range(10))  # every decrement saw the previous one
        assert await on_hand(owner, vid) == 0
        ledger = (await owner.get("inventory/movements", params={"variant_id": vid})).json()
        assert ledger["total"] == 11  # one receipt + ten decrements


async def test_concurrent_confirms_move_stock_and_invoice_exactly_once(live_stack):
    async with live_stack.browser() as browser:
        owner, vid, customer_id = await workspace(live_stack, browser, stock=5)
        order = await owner.create(
            "orders", {"customer_id": customer_id, "lines": [{"variant_id": vid, "quantity": 3}]}
        )
        responses = await asyncio.gather(
            *(owner.post(f"orders/{order['id']}/actions", {"action": "confirm"}) for _ in range(6))
        )
        statuses = Counter(r.status_code for r in responses)
        assert statuses == {200: 1, 422: 5}, statuses
        assert await on_hand(owner, vid) == 2
        assert (await owner.get("billing/invoices")).json()["total"] == 1
        sales = (await owner.get("inventory/movements", params={"variant_id": vid})).json()
        assert [m["kind"] for m in sales["items"]].count("sale") == 1


async def test_concurrent_quote_conversion_creates_one_order(live_stack):
    async with live_stack.browser() as browser:
        owner, vid, customer_id = await workspace(live_stack, browser)
        quote = await accepted_quote(owner, customer_id, [{"variant_id": vid, "quantity": "1"}])
        responses = await asyncio.gather(
            *(owner.post(f"quotes/{quote['id']}/order") for _ in range(5))
        )
        assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
        assert len({r.json()["id"] for r in responses}) == 1
        assert (await owner.get("orders")).json()["total"] == 1


async def test_document_numbers_are_unique_and_gapless_under_concurrency(live_stack):
    async with live_stack.browser() as browser:
        owner, vid, customer_id = await workspace(live_stack, browser)
        body = {"customer_id": customer_id, "lines": [{"variant_id": vid, "quantity": 1}]}
        orders, invoices = await asyncio.gather(
            asyncio.gather(*(owner.post("orders", body) for _ in range(12))),
            asyncio.gather(
                *(
                    owner.post(
                        "billing/invoices",
                        {
                            "customer_id": customer_id,
                            "lines": [{"description": "x", "quantity": "1", "unit_price": "1.00"}],
                        },
                    )
                    for _ in range(8)
                )
            ),
        )
        assert all(r.status_code == 201 for r in (*orders, *invoices))
        order_numbers = sorted(r.json()["number"] for r in orders)
        assert order_numbers == [f"ORD-{n:06d}" for n in range(1, 13)]
        invoice_numbers = sorted(r.json()["number"] for r in invoices)
        assert invoice_numbers == [f"INV-{n:06d}" for n in range(1, 9)]


async def test_concurrent_payments_cannot_overpay(live_stack):
    async with live_stack.browser() as browser:
        owner, _, customer_id = await workspace(live_stack, browser)
        invoice = await owner.create(
            "billing/invoices",
            {
                "customer_id": customer_id,
                "lines": [{"description": "Work", "quantity": "1", "unit_price": "100.00"}],
            },
        )
        await owner.create(f"billing/invoices/{invoice['id']}/actions", {"action": "issue"})
        responses = await asyncio.gather(
            *(
                owner.post(
                    f"billing/invoices/{invoice['id']}/payments",
                    {"amount": "40.00", "method": "cash"},
                )
                for _ in range(5)
            )
        )
        statuses = Counter(r.status_code for r in responses)
        assert statuses == {201: 2, 422: 3}, statuses
        detail = (await owner.get(f"billing/invoices/{invoice['id']}")).json()
        assert detail["amount_paid"] == "80.00" and detail["balance_due"] == "20.00"
        assert len(detail["payments"]) == 2
