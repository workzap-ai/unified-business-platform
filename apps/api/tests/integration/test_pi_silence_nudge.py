"""Brain mode: the one "still here" nudge after silence mid-description (spec 3.9.1)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import followups
from app.modules.pi.models import PiConversation, PiMessage

pytestmark = pytest.mark.integration

STILL_HERE = "Still here whenever you want to carry on."


def asks(context, n):
    return turn(reply="Where do you notice it most: sales, stock, staff or cash?", language="en")


@pytest.fixture(autouse=True)
def any_hour(monkeypatch):
    """Quiet hours and Jumu'ah depend on the real clock: these tests are about the nudge."""
    monkeypatch.setattr(followups, "quiet_until", lambda *a, **k: None)
    monkeypatch.setattr(followups, "_friday_prayer", lambda tz: False)


async def waiting_chat(api, db, monkeypatch):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, db)
    await say(pi, "everything is a mess honestly", "sn-1")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    return pi, conversation


async def make_due(db, conversation, hours_since_last_message=21):
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(hours=hours_since_last_message)
    conversation.followup_due_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()


async def nudges(db):
    rows = await db.scalars(select(PiMessage).where(PiMessage.direction == "outbound"))
    return [m for m in rows if (m.media or {}).get("followup", {}).get("kind") == "silent"]


async def test_after_a_question_the_nudge_is_scheduled_about_20_hours_out(
    api, business_db, monkeypatch
):
    pi, conversation = await waiting_chat(api, business_db, monkeypatch)
    assert conversation.service_brief["followup_kind"] == "silent"
    gap = conversation.followup_due_at - conversation.last_inbound_at
    assert timedelta(hours=19, minutes=59) <= gap <= timedelta(hours=20, minutes=1)
    await pi.close()


async def test_the_nudge_goes_once_as_free_text_and_never_twice(api, business_db, monkeypatch):
    pi, conversation = await waiting_chat(api, business_db, monkeypatch)
    await make_due(business_db, conversation)
    await followups.sweep_followups(pi.ctx)
    [nudge] = await nudges(business_db)
    assert nudge.body.startswith(STILL_HERE) and "?" not in nudge.body
    await business_db.refresh(conversation)
    assert conversation.followup_due_at is None
    assert conversation.service_brief["followups_sent"] == {"silent": 1}
    await followups.sweep_followups(pi.ctx)  # nothing more is due
    assert len(await nudges(business_db)) == 1
    await pi.close()


async def test_nothing_is_sent_after_stop_or_once_the_person_wrote(api, business_db, monkeypatch):
    pi, conversation = await waiting_chat(api, business_db, monkeypatch)
    brief = dict(conversation.service_brief)
    brief["reminder_consent"] = "declined"  # what "STOP" leaves behind (note_opt_out)
    conversation.service_brief = brief
    await make_due(business_db, conversation)
    await followups.sweep_followups(pi.ctx)
    assert await nudges(business_db) == []
    await pi.close()


async def test_a_nudge_that_would_fall_outside_the_24_hour_window_is_dropped(
    api, business_db, monkeypatch
):
    pi, conversation = await waiting_chat(api, business_db, monkeypatch)
    await make_due(business_db, conversation, hours_since_last_message=26)
    await followups.sweep_followups(pi.ctx)
    assert await nudges(business_db) == []  # no template exists for it: it is simply skipped
    await business_db.refresh(conversation)
    assert conversation.followup_due_at is None
    await pi.close()


async def test_other_workspaces_keep_the_old_reminder_behaviour(api, business_db, monkeypatch):
    from test_pi_service_conversations import pi_workspace

    adaptive(monkeypatch, asks)
    pi = await pi_workspace(api, business_db, business_type="service_business")  # no brain mode
    await say(pi, "everything is a mess honestly", "sn-9")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert "followup_kind" not in (conversation.service_brief or {})
    assert (await business_db.scalar(select(PiConversation.id))) is not None
    await pi.close()
