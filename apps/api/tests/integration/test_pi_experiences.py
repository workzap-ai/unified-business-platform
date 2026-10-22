"""Scoring pi's replies by what happened next (spec 8.3): text-free rows, observe only."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.experience_models import PiExperience
from app.modules.pi.experience_scorer import health, score_new
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


def asks(context, n):
    if "samajh" in context["latest_customer_message"]:  # they were lost: rephrase, give choices
        return turn(reply="Kya ye stock, cash ya staff ke baare mein hai?", language="roman_ur")
    return turn(reply="Where do you notice it most: sales, stock, staff or cash?", language="en")


async def spread(db, pi, ids):
    """One test transaction stamps every row with the same time: give each its own."""
    start = datetime.now(UTC) - timedelta(minutes=30)
    for n, mid in enumerate(ids):
        inbound = (
            await db.scalars(select(PiMessage).where(PiMessage.provider_message_id == mid))
        ).one()
        reply = await pi.reply_to(mid)
        inbound.created_at = start + timedelta(minutes=2 * n)
        reply.created_at = start + timedelta(minutes=2 * n, seconds=30)
    await db.flush()


async def test_each_reply_is_scored_by_the_next_message_and_silence(api, business_db, monkeypatch):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await say(pi, "everything is a mess honestly", "ex-1")
    await say(pi, "samajh nahi aaya", "ex-2")
    await spread(business_db, pi, ["ex-1", "ex-2"])
    # The first reply's outcome is known (they were confused); the second reply is too new.
    assert await score_new(business_db) == 1
    [first] = (await business_db.scalars(select(PiExperience))).all()
    assert first.signals == ["confusion"] and first.reward == -2
    assert first.situation["turn_kind"] == "question" and first.situation["language"]
    assert "message" not in first.situation and "body" not in str(first.situation)  # no text kept
    assert await score_new(business_db) == 0  # scored once
    # A day of silence after a question is a drop-off.
    later = datetime.now(UTC) + timedelta(hours=25)
    assert await score_new(business_db, now=later) == 1
    rows = (await business_db.scalars(select(PiExperience))).all()
    assert sorted(r.reward for r in rows) == [-2, -1]
    shown = await health(business_db, since=later - timedelta(days=2))
    assert shown["scored"] == 2 and shown["average_reward"] == -1.5
    assert shown["signals"] == {"confusion": 1, "drop_off": 1}
    await pi.close()
