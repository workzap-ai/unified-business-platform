"""Salam and Eid replies, and the one confirmation after "stop" (R-LANG-08, R-FUP-02)."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiConversation, PiMessage

pytestmark = pytest.mark.integration


def asks(context, n):
    return turn(reply="Noted. Which items run out first?", language="en")


async def replies(db):
    rows = await db.scalars(
        select(PiMessage).where(PiMessage.direction == "outbound").order_by(PiMessage.created_at)
    )
    return [m.body for m in rows]


async def test_a_first_salam_gets_the_courtesy_and_the_ai_disclosure(api, business_db, monkeypatch):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await say(pi, "Assalam o alaikum", "co-1")
    [reply] = await replies(business_db)
    # "Assalam o alaikum" is Roman Urdu, so the fixed opening comes in Roman Urdu (R-LANG-02)
    assert reply.startswith("Wa alaikum assalam.") and "pi hoon" in reply and "AI" in reply
    conversation = (await business_db.scalars(select(PiConversation))).one()
    assert conversation.flow_state == "S1_LISTENING"
    await pi.close()


async def test_stop_is_confirmed_once_and_nothing_more_is_sent(api, business_db, monkeypatch):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await say(pi, "stock runs out in two shops", "co-2")
    before = len(await replies(business_db))
    await say(pi, "please stop messaging me", "co-3")
    sent = await replies(business_db)
    assert len(sent) == before + 1 and sent[-1].startswith("Understood. I won't message you again")
    await say(pi, "stop", "co-4")  # a second stop is not confirmed again with a new reply
    assert len(await replies(business_db)) == before + 1
    await pi.close()
