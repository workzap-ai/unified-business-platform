"""Q-6 in real chats (database): open items across chats, the workspace wall and the erase.

WRITTEN, NOT RUN when it was committed: integration tests need the disposable database and its
lock was held by another run. Collect-only was checked. The unit file
`test_pi_open_items_carry_scope.py` runs the same questions against a fake session.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import pi_workspace
from test_pi_slot_carry_flow import HELLO, chats, close_with, first_chat, talk

from app.modules.pi import brain_erase, open_items
from app.modules.pi.open_item_models import PiOpenItem

pytestmark = pytest.mark.integration

QUESTION = "how long will the delivery of my order take to Lahore"


async def open_item(db, pi, conversation, text=QUESTION, hours_old=6):
    row = PiOpenItem(
        tenant_id=pi.tenant_id,
        environment_id=pi.scope().environment_id,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        kind="owner_question",
        key="q:written-by-test",
        text=text,
        status="open",
        language="en",
    )
    db.add(row)
    await db.flush()
    row.created_at = datetime.now(UTC) - timedelta(hours=hours_old)
    await db.flush()
    return row


async def count(db, pi) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(PiOpenItem).where(PiOpenItem.tenant_id == pi.tenant_id)
        )
        or 0
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "GAP Q6-1: open items are read per conversation (open_items.py:190-203); a new chat of "
        "the same owner does not name an open item of the earlier chat. Remove the marker with "
        "the carry fix."
    ),
)
async def test_an_open_item_of_an_earlier_chat_is_named_when_the_owner_returns_in_a_new_chat(
    api, business_db, monkeypatch
):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    await open_item(business_db, pi, one)
    await close_with(business_db, one, {}, age_days=1)
    await talk(pi, business_db, HELLO, "q6-1")
    new = (await chats(business_db, pi))[-1]
    assert new.id != one.id
    found = await open_items.load_for_return(business_db, pi.scope(), new, hours_away=30)
    assert len(found) == 1
    await pi.close()


async def test_an_item_of_another_workspace_is_never_named_here(api, business_db, monkeypatch):
    seen, mine, one = await first_chat(api, business_db, monkeypatch)
    theirs = await pi_workspace(
        api, business_db, business_type="service_business", number="987654321"
    )
    await theirs.process(HELLO, "q6-t0")
    await theirs.deliver_all()
    [other] = await chats(business_db, theirs)
    await open_item(business_db, theirs, other)
    assert await open_items.load_for_return(business_db, mine.scope(), one, hours_away=30) == []
    await mine.close()
    await theirs.close()


async def test_erasing_the_customer_removes_their_open_items_and_not_another_workspaces(
    api, business_db, monkeypatch
):
    seen, mine, one = await first_chat(api, business_db, monkeypatch)
    theirs = await pi_workspace(
        api, business_db, business_type="service_business", number="987654321"
    )
    await theirs.process(HELLO, "q6-e0")
    await theirs.deliver_all()
    [other] = await chats(business_db, theirs)
    await open_item(business_db, mine, one)
    await open_item(business_db, theirs, other)
    assert await count(business_db, mine) == 1
    await brain_erase.erase_customer(business_db, mine.scope(), one.customer_id)
    await business_db.flush()
    assert await count(business_db, mine) == 0
    assert await count(business_db, theirs) == 1
    await mine.close()
    await theirs.close()
