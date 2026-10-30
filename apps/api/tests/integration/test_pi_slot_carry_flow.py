"""S4 in real chats: a returning owner is not asked an answered question again, a workspace never
reads another's, stale data stays behind, and erasing the customer erases the copies too."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update
from test_pi_brain_problems import OPENING, say, workspace
from test_pi_learning_loop import SECOND
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import brain_erase, slot_carry
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.runtime import send_pi_message

pytestmark = pytest.mark.integration

HELLO = "hello"
ASKED = "Which shop is it?"
OTHER = "Since when has stock been running out?"
SLOTS = [{"slot": "shops.where", "q": ASKED}]


def models(monkeypatch):
    seen = {"rewrites": 0}

    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if text.startswith("{"):
            if json.loads(text).get("latest_customer_message") == HELLO:
                value = turn(reply=f"{OPENING} What is your business called?", language="en")
            else:
                value = turn(reply=f"Stock running out costs sales. {ASKED}", language="en")
        else:
            seen["rewrites"] += 1
            value = turn(reply=f"Stock running out costs sales. {OTHER}", language="en")
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    return seen


async def chats(db, pi):
    return list(
        await db.scalars(
            select(PiConversation)
            .where(PiConversation.tenant_id == pi.tenant_id)
            .order_by(PiConversation.last_message_at)  # created_at is one value in a test
        )
    )


async def talk(pi, db, text, key):
    """One owner message, then every queued reply of every chat is sent (Pi.deliver_all reads only
    the first chat of the workspace, so a reply in a second chat would stay queued)."""
    await pi.process(text, key)
    for chat in await chats(db, pi):
        queued = await db.scalars(
            select(PiMessage).where(
                PiMessage.conversation_id == chat.id,
                PiMessage.direction == "outbound",
                PiMessage.status == "queued",
            )
        )
        for message in list(queued):
            await send_pi_message(pi.ctx, str(message.id))


async def close_with(db, conversation, brief, age_days=3):
    """The first chat ends with this brief, last active `age_days` days ago."""
    await db.execute(
        update(PiConversation)
        .where(PiConversation.id == conversation.id)
        .values(
            status="closed",
            service_brief=brief,
            last_message_at=datetime.now(UTC) - timedelta(days=age_days),
        )
    )
    await db.flush()
    await db.refresh(conversation)


async def first_chat(api, db, monkeypatch):
    seen = models(monkeypatch)
    pi = await workspace(api, db)
    await say(pi, HELLO, "c-0")
    [one] = await chats(db, pi)
    return seen, pi, one


async def test_a_returning_owner_is_not_asked_the_same_question_again(
    api, business_db, monkeypatch
):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    await close_with(business_db, one, {"closed_slots": SLOTS})
    await talk(pi, business_db, HELLO, "c-1")  # a new chat: the opening exchange
    await talk(pi, business_db, "my stock runs out in some of the shops", "c-2")
    assert seen["rewrites"] == 1, "the repeated question was not stopped"
    newest = (await chats(business_db, pi))[-1]
    replies = list(
        await business_db.scalars(
            select(PiMessage.body).where(
                PiMessage.conversation_id == newest.id, PiMessage.direction == "outbound"
            )
        )
    )  # every message of a test shares one timestamp, so no "last one" is picked
    assert not any(ASKED in (body or "") for body in replies)
    assert any(OTHER in (body or "") for body in replies)
    await pi.close()


async def test_the_copy_is_made_once_and_holds_only_the_allowed_keys(api, business_db, monkeypatch):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    private = {
        "closed_slots": SLOTS,
        "requirements": {"service": "Website"},
        "customer_profile": {"name": "Ali"},
        "last_question": {"slot": "x", "q": "What is your bank balance?"},
        "summary": "the owner said his brother steals",
    }
    await close_with(business_db, one, private)
    await say(pi, HELLO, "p-1")
    _, new = await chats(business_db, pi)
    brief = new.service_brief or {}
    assert [c["q"] for c in brief["closed_slots"]][:1] == [ASKED]
    assert all(c.get("carried") is True for c in brief["closed_slots"][:1])
    text = json.dumps(brief)
    assert "Ali" not in text and "brother" not in text and "bank balance" not in text
    assert "requirements" not in brief and "customer_profile" not in brief
    await pi.close()


async def test_nothing_crosses_into_another_workspace_or_customer(api, business_db, monkeypatch):
    seen, mine, one = await first_chat(api, business_db, monkeypatch)
    await close_with(business_db, one, {"closed_slots": SLOTS})
    theirs = await pi_workspace(
        api, business_db, business_type="service_business", number="987654321"
    )
    await theirs.process(HELLO, "t-0")
    await theirs.deliver_all()
    [other] = await chats(business_db, theirs)
    assert "closed_slots" not in (other.service_brief or {})
    # the same workspace, a different customer (another phone number)
    await mine.process(HELLO, "s-0", sender=SECOND)
    await mine.deliver_all()
    everyone = await chats(business_db, mine)
    second = [c for c in everyone if c.contact_wa_id == SECOND]
    assert second and "closed_slots" not in (second[0].service_brief or {})
    await mine.close()
    await theirs.close()


async def test_stale_and_generic_data_stays_behind(api, business_db, monkeypatch):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    old = slot_carry.CARRY_SLOTS_DAYS + 5
    brief = {
        "closed_slots": [*SLOTS, {"slot": "anything_else", "q": "Anything else?"}],
        "asked_facts": ["business_name"],
    }
    await close_with(business_db, one, brief, age_days=old)
    await say(pi, HELLO, "o-1")
    _, new = await chats(business_db, pi)
    assert "closed_slots" not in (new.service_brief or {})
    assert "asked_facts" not in (new.service_brief or {})
    await pi.close()


async def test_erasing_the_customer_erases_the_copies_and_nothing_is_copied_after(
    api, business_db, monkeypatch
):
    seen, pi, one = await first_chat(api, business_db, monkeypatch)
    await close_with(
        business_db, one, {"closed_slots": SLOTS, "asked_facts": ["business_name"]}, age_days=1
    )
    await say(pi, HELLO, "e-1")
    _, new = await chats(business_db, pi)
    assert (new.service_brief or {}).get("closed_slots")  # the copy exists
    assert (new.service_brief or {}).get("asked_facts")
    await brain_erase.erase_customer(business_db, pi.scope(), new.customer_id)
    await business_db.flush()
    for chat in await chats(business_db, pi):
        await business_db.refresh(chat)
        assert chat.service_brief == {"erased": True}
    # an erased chat is never a source: the next chat starts clean
    await business_db.execute(
        update(PiConversation)
        .where(PiConversation.tenant_id == pi.tenant_id)
        .values(status="closed")
    )
    await business_db.flush()
    await say(pi, HELLO, "e-2")
    latest = (await chats(business_db, pi))[-1]
    assert "closed_slots" not in (latest.service_brief or {})
    assert "asked_facts" not in (latest.service_brief or {})
    await pi.close()
