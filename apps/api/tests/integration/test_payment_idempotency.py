"""BL-05: an optional Idempotency-Key on the invoice payment route.

A repeat with the same key and the same body returns the first payment and writes nothing; the
same key with another body is refused; keys are per workspace; no key keeps today's behaviour.
"""

import asyncio

import pytest

from tests.integration.test_domain_events import events
from tests.support.workspace import Actor, error_code

pytestmark = pytest.mark.integration

KEY = "pay-2026-10-31-aaaa"
BODY = {"amount": "40.00", "method": "cash", "reference": "slip 1"}


async def issued_invoice(owner: Actor, total: str = "100.00") -> str:
    customer = await owner.create("customers", {"name": "Idem"})
    lines = [{"description": "Work", "quantity": "1", "unit_price": total}]
    invoice = await owner.create(
        "billing/invoices", {"customer_id": customer["id"], "lines": lines}
    )
    await owner.create(f"billing/invoices/{invoice['id']}/actions", {"action": "issue"})
    return str(invoice["id"])


async def pay(owner: Actor, invoice_id: str, body: dict, key: str | None = None):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return await owner.post(f"billing/invoices/{invoice_id}/payments", body, headers=headers)


async def invoice_state(owner: Actor, invoice_id: str) -> tuple[str, str, int]:
    detail = (await owner.get(f"billing/invoices/{invoice_id}")).json()
    return detail["status"], detail["amount_paid"], len(detail["payments"])


async def audit_count(owner: Actor, name: str) -> int:
    page = (await owner.get("audit/events", params={"page_size": 100})).json()
    return sum(1 for e in page["items"] if e["action"] == name)


async def test_double_submit_with_a_key_records_one_payment(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        iid = await issued_invoice(owner)
        first = await pay(owner, iid, BODY, KEY)
        second = await pay(owner, iid, BODY, KEY)
        assert first.status_code == 201 and second.status_code == 201, second.text
        assert second.json() == first.json()
        assert await invoice_state(owner, iid) == ("partially_paid", "40.00", 1)
        numbers = [p["number"] for p in (await owner.get("billing/payments")).json()["items"]]
        assert numbers == ["PAY-000001"]


async def test_a_repeat_after_the_invoice_is_paid_still_replays(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        iid = await issued_invoice(owner)
        full = {"amount": "100.00", "method": "bank_transfer"}
        first = await pay(owner, iid, full, KEY)
        again = await pay(owner, iid, full, KEY)
        assert again.status_code == 201 and again.json() == first.json()
        assert await invoice_state(owner, iid) == ("paid", "100.00", 1)
        # without the key the same body is the old refusal
        plain = await pay(owner, iid, full)
        assert plain.status_code == 422 and error_code(plain) == "INVOICE_NOT_OPEN"


async def test_same_key_with_another_body_is_refused(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        iid = await issued_invoice(owner)
        assert (await pay(owner, iid, BODY, KEY)).status_code == 201
        for changed in (
            {**BODY, "amount": "41.00"},
            {**BODY, "method": "card"},
            {**BODY, "reference": "slip 2"},
            {**BODY, "received_on": "2026-01-02"},
        ):
            refused = await pay(owner, iid, changed, KEY)
            assert refused.status_code == 409, refused.text
            assert error_code(refused) == "IDEMPOTENCY_KEY_REUSED"
        assert await invoice_state(owner, iid) == ("partially_paid", "40.00", 1)


async def test_same_key_on_another_invoice_is_refused(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        first, second = await issued_invoice(owner), await issued_invoice(owner)
        assert (await pay(owner, first, BODY, KEY)).status_code == 201
        refused = await pay(owner, second, BODY, KEY)
        assert refused.status_code == 409 and error_code(refused) == "IDEMPOTENCY_KEY_REUSED"
        assert await invoice_state(owner, second) == ("issued", "0.00", 0)


async def test_keys_are_per_workspace(stack):
    async with stack.browser() as one, stack.browser() as two:
        alice, bob = await stack.register(one), await stack.register(two)
        a, b = await issued_invoice(alice), await issued_invoice(bob)
        first = await pay(alice, a, BODY, KEY)
        other = await pay(bob, b, BODY, KEY)
        assert first.status_code == 201 and other.status_code == 201, other.text
        assert first.json()["id"] != other.json()["id"]
        assert await invoice_state(alice, a) == ("partially_paid", "40.00", 1)
        assert await invoice_state(bob, b) == ("partially_paid", "40.00", 1)


async def test_no_key_keeps_today_behaviour(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        iid = await issued_invoice(owner)
        assert (await pay(owner, iid, BODY)).status_code == 201
        assert (await pay(owner, iid, BODY)).status_code == 201
        assert await invoice_state(owner, iid) == ("partially_paid", "80.00", 2)


@pytest.mark.parametrize(
    "bad",
    ["short", "x" * 129, "has space in it", "slash/not/allowed", "émoji-key-1234", "a" * 8 + "\n"],
)
async def test_malformed_keys_are_rejected_before_anything_is_written(stack, bad):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        iid = await issued_invoice(owner)
        try:
            refused = await pay(owner, iid, BODY, bad)
        except Exception:  # noqa: BLE001 - the client itself may refuse a header like this
            return
        assert refused.status_code == 422, refused.text
        assert error_code(refused) == "INVALID_IDEMPOTENCY_KEY"
        assert await invoice_state(owner, iid) == ("issued", "0.00", 0)


async def test_a_repeat_writes_no_second_audit_entry_or_event(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        iid = await issued_invoice(owner)
        await pay(owner, iid, BODY, KEY)
        before = await audit_count(owner, "payment.recorded")
        await pay(owner, iid, BODY, KEY)
        await pay(owner, iid, {**BODY, "amount": "1.00"}, KEY)  # refused, also writes nothing
        assert before == 1 and await audit_count(owner, "payment.recorded") == 1
        types = [e.event_type for e in await events(stack, owner.tenant_id)]
        assert types.count("payment.received") == 1


async def test_concurrent_submits_with_one_key_record_one_payment(live_stack):
    async with live_stack.browser() as browser:
        owner = await live_stack.register(browser)
        iid = await issued_invoice(owner)
        responses = await asyncio.gather(*(pay(owner, iid, BODY, KEY) for _ in range(8)))
        assert [r.status_code for r in responses] == [201] * 8, [r.text for r in responses]
        assert len({r.json()["id"] for r in responses}) == 1
        assert await invoice_state(owner, iid) == ("partially_paid", "40.00", 1)


async def test_concurrent_submits_with_one_key_on_two_invoices_record_one_payment(live_stack):
    async with live_stack.browser() as browser:
        owner = await live_stack.register(browser)
        first, second = await issued_invoice(owner), await issued_invoice(owner)
        responses = await asyncio.gather(
            *(pay(owner, iid, BODY, KEY) for iid in (first, second, first, second))
        )
        assert sorted(r.status_code for r in responses) == [201, 201, 409, 409], [
            r.text for r in responses
        ]
        states = [await invoice_state(owner, first), await invoice_state(owner, second)]
        assert sorted(s[2] for s in states) == [0, 1]
