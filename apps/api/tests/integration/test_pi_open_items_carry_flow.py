"""Q-6 in real chats (database): open items carried into a new chat, the workspace wall, the erase.

WRITTEN, NOT RUN when it was committed: integration tests need the disposable database and its
lock was held by another run; the integrator runs them under the mutex. Collect-only was checked.
The unit file `test_pi_open_items_carry_scope.py` runs the same questions against a fake session.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import pi_workspace
from test_pi_slot_carry_flow import HELLO, chats, close_with, first_chat, talk

from app.modules.pi import brain_erase, open_items
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration

QUESTION = "how long will the delivery of my order take to Lahore"


async def open_item(db, pi, conversation, hours_old=6, kind="owner_question", key=None):
    row = PiOpenItem(
        tenant_id=pi.tenant_id,
        environment_id=pi.scope().environment_id,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        kind=kind,
        key=key or f"q:written-by-test-{hours_old}",
        text=QUESTION,
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


async def test_an_open_item_of_an_earlier_chat_is_carried_into_the_new_chat(
    api, business_db, monkeypatch
):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    row = await open_item(business_db, pi, one)
    await close_with(business_db, one, {}, age_days=1)
    await talk(pi, business_db, HELLO, "q6-1")  # a new chat: slot_carry runs at the top of the turn
    new = (await chats(business_db, pi))[-1]
    assert new.id != one.id
    await business_db.refresh(row)
    assert row.conversation_id == new.id, "the open item was not carried into the new chat"
    assert row.source_message_id is None
    found = await open_items.load_for_return(business_db, pi.scope(), new, hours_away=30)
    assert [f["id"] for f in found] == [str(row.id)]
    await pi.close()


async def test_a_carried_request_reaches_the_new_brief_and_an_old_item_does_not(
    api, business_db, monkeypatch
):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    await open_item(business_db, pi, one, kind="owner_request", key="timeline")
    await open_item(business_db, pi, one, hours_old=24 * 40, key="q:too-old")
    await close_with(business_db, one, {}, age_days=1)
    await talk(pi, business_db, HELLO, "q6-2")
    new = (await chats(business_db, pi))[-1]
    entries = (new.service_brief or {}).get("open_requests") or []
    assert entries == [{"kind": "timeline", "turns": 0}]
    old = await business_db.scalar(
        select(PiOpenItem).where(
            PiOpenItem.key == "q:too-old", PiOpenItem.tenant_id == pi.tenant_id
        )
    )
    assert old.conversation_id == one.id  # past the 30 days: it stays where it was
    await pi.close()


async def staffed_chat(api, business_db, monkeypatch, status):
    """An open question in chat one, a staff request about it under chat one, then a new chat."""
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    row = await open_item(business_db, pi, one, hours_old=5)
    business_db.add(
        PiStaffRequest(
            tenant_id=pi.tenant_id,
            environment_id=pi.scope().environment_id,
            conversation_id=one.id,  # the staff request keeps the OLD conversation id
            customer_id=one.customer_id,
            question=QUESTION,
            kind="question",
            status=status,
            answer="Three days." if status == "answered" else None,
            resolved_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await business_db.flush()
    await close_with(business_db, one, {}, age_days=1)
    await talk(pi, business_db, HELLO, "q6-3a")  # the new chat: the question is carried into it
    new = (await chats(business_db, pi))[-1]
    await business_db.refresh(row)
    assert row.conversation_id == new.id and row.source_message_id is None
    return pi, new, row


async def test_the_teams_answer_to_the_old_chat_closes_the_carried_question_in_a_real_turn(
    api, business_db, monkeypatch
):
    pi, new, row = await staffed_chat(api, business_db, monkeypatch, "answered")
    await talk(pi, business_db, "ok thanks", "q6-3b")  # open_items.sync runs on this turn
    await business_db.refresh(row)
    assert row.status == "answered" and row.closed_reason == "reply_answered"
    await pi.close()


async def test_a_dismissed_request_does_not_close_the_carried_question_in_a_real_turn(
    api, business_db, monkeypatch
):
    pi, new, row = await staffed_chat(api, business_db, monkeypatch, "dismissed")
    await talk(pi, business_db, "ok thanks", "q6-3c")
    await business_db.refresh(row)
    assert row.status == "open"
    await pi.close()


async def test_an_item_of_another_workspace_with_the_same_phone_is_never_moved_or_named(
    api, business_db, monkeypatch
):
    seen, mine, one = await first_chat(api, business_db, monkeypatch)
    theirs = await pi_workspace(
        api, business_db, business_type="service_business", number="987654321"
    )
    await theirs.process(HELLO, "q6-t0", sender=one.contact_wa_id)  # the very same customer phone
    await theirs.deliver_all()
    [other] = await chats(business_db, theirs)
    assert other.contact_wa_id == one.contact_wa_id and other.tenant_id != one.tenant_id
    foreign = await open_item(business_db, theirs, other)
    await close_with(business_db, one, {}, age_days=1)
    await talk(mine, business_db, HELLO, "q6-t1")
    new = (await chats(business_db, mine))[-1]
    await business_db.refresh(foreign)
    assert foreign.conversation_id == other.id, "another workspace's item was moved"
    assert str(foreign.tenant_id) == str(theirs.tenant_id)  # the helper holds a str, the row a UUID
    assert await open_items.load_for_return(business_db, mine.scope(), new, hours_away=30) == []
    await mine.close()
    await theirs.close()


async def test_erasing_removes_the_carried_items_by_the_new_conversation_id_alone(
    api, business_db, monkeypatch
):
    seen, mine, one = await first_chat(api, business_db, monkeypatch)
    theirs = await pi_workspace(
        api, business_db, business_type="service_business", number="987654321"
    )
    await theirs.process(HELLO, "q6-e0", sender=one.contact_wa_id)
    await theirs.deliver_all()
    [other] = await chats(business_db, theirs)
    first = await open_item(business_db, mine, one, key="q:carried")
    second = await open_item(business_db, mine, one, hours_old=7, key="q:stays")
    await open_item(business_db, theirs, other)
    await close_with(business_db, one, {}, age_days=1)
    await talk(mine, business_db, HELLO, "q6-e1")  # both move to the new chat
    new = (await chats(business_db, mine))[-1]
    for row in (first, second):
        await business_db.refresh(row)
        assert row.conversation_id == new.id  # the move happened: not the old chat's rows any more
    assert await count(business_db, mine) == 2
    # erase by the NEW conversation id only: the old chat's id plays no part in the removal
    removed, _skipped = await brain_erase._erase_conversation_extras(
        business_db, mine.scope(), [new.id]
    )
    assert removed["open_items"] == 2
    assert await count(business_db, mine) == 0
    assert await count(business_db, theirs) == 1
    await mine.close()
    await theirs.close()
