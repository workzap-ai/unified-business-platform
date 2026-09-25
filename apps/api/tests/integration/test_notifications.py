"""Notification delivery, per-user read state and bulk-read regression checks."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert

from app.modules.notifications.models import Notification
from tests.support.workspace import add_member, product, receive, set_business

pytestmark = pytest.mark.integration


async def seed(stack, actor, count=1, **overrides):
    rows = [
        {
            "id": uuid4(),
            "tenant_id": UUID(actor.tenant_id),
            "environment_id": UUID(actor.environment_id),
            "kind": "system",
            "title": f"Notification {i}",
            "required_permission": "notifications.read",
            **overrides,
        }
        for i in range(count)
    ]
    await stack.app.state.test_connection.execute(insert(Notification), rows)
    return [str(row["id"]) for row in rows]


async def unread(actor):
    response = await actor.get("notifications/unread-count")
    assert response.status_code == 200, response.text
    return response.json()["unread"]


async def test_mark_all_reads_more_than_500_notifications_and_is_idempotent(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await seed(stack, owner, 525)
        assert await unread(owner) == 525

        # An explicit empty selection is a no-op, not "mark all".
        assert (await owner.post("notifications/read", {"ids": []})).status_code == 204
        assert await unread(owner) == 525
        assert (await owner.post("notifications/read", {"ids": None})).status_code == 204
        assert await unread(owner) == 0
        assert (await owner.post("notifications/read", {"ids": None})).status_code == 204
        assert await unread(owner) == 0
        page = (await owner.get("notifications", params={"page_size": 100})).json()
        assert page["total"] == 525
        assert all(row["read"] for row in page["items"])
        assert (await owner.get("notifications", params={"unread_only": True})).json()["total"] == 0


async def test_audience_isolation_and_read_state_are_per_user(stack):
    async with stack.browser() as a, stack.browser() as b, stack.browser() as c:
        owner = await stack.register(a)
        email = await add_member(owner, ["support"])
        member = await stack.login(b, email)
        outsider = await stack.register(c)
        shared = (await seed(stack, owner))[0]
        restricted = (await seed(stack, owner, required_permission="hr.read"))[0]
        personal = (await seed(stack, owner, recipient_user_id=UUID(owner.session["user"]["id"])))[
            0
        ]
        foreign = (await seed(stack, outsider))[0]

        assert await unread(owner) == 3
        assert await unread(member) == 1
        assert await unread(outsider) == 1
        assert {n["id"] for n in (await member.get("notifications")).json()["items"]} == {shared}
        assert (
            await member.post("notifications/read", {"ids": [restricted, personal, foreign]})
        ).status_code == 204
        assert await unread(member) == 1

        response = await member.post("notifications/read", {"ids": [shared, shared]})
        assert response.status_code == 204
        assert await unread(member) == 0
        assert await unread(owner) == 3
        assert (await owner.post("notifications/read", {"ids": None})).status_code == 204
        assert await unread(outsider) == 1

        navigation = (await owner.get("navigation")).json()
        notification_nav = next(
            item
            for section in navigation["sections"]
            for item in section["items"]
            if item["key"] == "notifications"
        )
        assert notification_nav["badge"] is None


async def test_mark_all_does_not_cross_environments(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        production = owner.environment_id
        await seed(stack, owner, 2)
        staging = await owner.create(
            "environments", {"key": "staging", "name": "Staging", "kind": "staging"}
        )
        await owner.switch(owner.tenant_id, staging["id"])
        await seed(stack, owner)
        assert await unread(owner) == 1
        assert (await owner.post("notifications/read", {"ids": None})).status_code == 204
        assert await unread(owner) == 0
        await owner.switch(owner.tenant_id, production)
        assert await unread(owner) == 2


async def test_notification_read_payload_validation(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await seed(stack, owner)
        for payload in ({"ids": ["invalid"]}, {"ids": [str(uuid4())] * 501}, {"all": True}):
            assert (await owner.post("notifications/read", payload)).status_code == 422
        assert await unread(owner) == 1


async def test_low_stock_delivery_links_to_filtered_stock_and_deduplicates(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, business_type="hybrid_business", low_stock_threshold=10)
        item = await product(owner, tracked=True)
        variant_id = item["variants"][0]["id"]
        await receive(owner, variant_id, 20)
        for quantity in (-11, -1):
            await owner.create(
                "inventory/adjustments",
                {
                    "variant_id": variant_id,
                    "quantity": quantity,
                    "kind": "adjustment",
                    "reason": "Stock count correction",
                },
            )
        page = (await owner.get("notifications")).json()
        assert page["total"] == 1
        alert = page["items"][0]
        assert alert["kind"] == "inventory"
        assert alert["severity"] == "warning"
        assert alert["link"] == "/inventory/stock?low_only=true"
        assert alert["read"] is False
