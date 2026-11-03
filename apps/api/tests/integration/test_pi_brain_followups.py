"""Brain mode follow-ups: documents, paused and kickoff (spec 3.9.1, R-FUP-01 to R-FUP-05)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.notifications.models import Notification
from app.modules.pi import brain_followups
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


def asks(context, n):
    return turn(reply="Where do you notice it most: sales, stock, staff or cash?", language="en")


@pytest.fixture(autouse=True)
def any_hour(monkeypatch):
    monkeypatch.setattr(brain_followups, "quiet_until", lambda *a, **k: None)
    monkeypatch.setattr(brain_followups, "_friday_prayer", lambda tz: False)


async def chat(api, db, monkeypatch, state, **brief):
    adaptive(monkeypatch, asks)
    pi = await workspace(api, db)
    await say(pi, "everything is a mess honestly", "bf-1")
    conversation = await pi.conversation()
    await db.refresh(conversation)
    conversation.flow_state = state
    conversation.service_brief = {**(conversation.service_brief or {}), **brief}
    return pi, conversation


async def followups(db):
    rows = await db.scalars(select(PiMessage).where(PiMessage.direction == "outbound"))
    return [m for m in rows if (m.media or {}).get("followup")]


async def configure(db, pi, **templates):
    settings = await settings_row(db, pi.scope())
    settings.whatsapp_config = {**settings.whatsapp_config, **templates}
    await db.flush()


def ago(**kw):
    return (datetime.now(UTC) - timedelta(**kw)).isoformat()


async def test_a_document_follow_up_without_a_template_tells_staff_and_sends_nothing(
    api, business_db, monkeypatch
):
    pi, conversation = await chat(
        api,
        business_db,
        monkeypatch,
        "S7_DELIVERED",
        offer={"sent_at": ago(days=3)},
        reminder_consent="granted",
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(days=3)
    await business_db.flush()
    assert await brain_followups.sweep(pi.ctx) == []
    assert await followups(business_db) == []
    titles = [n.title for n in await business_db.scalars(select(Notification))]
    assert "pi needs an approved WhatsApp template for a follow-up" in titles
    await pi.close()


async def test_a_document_follow_up_goes_once_as_the_approved_template(
    api, business_db, monkeypatch
):
    pi, conversation = await chat(
        api,
        business_db,
        monkeypatch,
        "S7_DELIVERED",
        offer={"sent_at": ago(days=3)},
        reminder_consent="granted",
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(days=3)
    await configure(
        business_db,
        pi,
        followup_templates={"en": {"documents": {"name": "docs_nudge", "language": "en"}}},
    )
    [queued] = await brain_followups.sweep(pi.ctx)
    message = await business_db.get(PiMessage, queued)
    assert message.media["ladder"]["template"] == {"name": "docs_nudge", "language": "en"}
    await business_db.refresh(conversation)
    assert conversation.service_brief["followups_sent"] == {"documents": 1}
    assert await brain_followups.sweep(pi.ctx) == []  # the second one is not due for days
    await pi.close()


async def test_no_template_message_without_consent_and_nothing_after_stop(
    api, business_db, monkeypatch
):
    pi, conversation = await chat(
        api, business_db, monkeypatch, "S7_DELIVERED", offer={"sent_at": ago(days=3)}
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(days=3)
    await configure(
        business_db,
        pi,
        followup_templates={"en": {"documents": {"name": "docs_nudge", "language": "en"}}},
    )
    assert await brain_followups.sweep(pi.ctx) == []  # consent was never given
    conversation.service_brief = {**conversation.service_brief, "reminder_consent": "declined"}
    await business_db.flush()
    assert await brain_followups.sweep(pi.ctx) == []
    await pi.close()


async def test_a_customer_reply_restarts_the_document_clock(api, business_db, monkeypatch):
    pi, conversation = await chat(
        api,
        business_db,
        monkeypatch,
        "S8_REVIEW",
        offer={"sent_at": ago(days=3)},
        reminder_consent="granted",
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(hours=5)  # they wrote since
    await configure(
        business_db,
        pi,
        followup_templates={"en": {"documents": {"name": "docs_nudge", "language": "en"}}},
    )
    assert await brain_followups.sweep(pi.ctx) == []
    await pi.close()


async def test_a_kickoff_reminder_inside_the_window_is_plain_text_with_the_time(
    api, business_db, monkeypatch
):
    at = datetime.now(UTC) + timedelta(hours=23)
    pi, conversation = await chat(
        api, business_db, monkeypatch, "S12_KICKOFF", kickoff={"at": at.isoformat()}
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(hours=1)
    [queued] = await brain_followups.sweep(pi.ctx)
    message = await business_db.get(PiMessage, queued)
    assert message.body.startswith("Reminder: your Workzap kickoff is ") and "?" not in message.body
    assert message.media["followup"]["kind"] == "kickoff_24h"
    await pi.close()


async def test_a_kickoff_that_has_passed_is_not_reminded(api, business_db, monkeypatch):
    at = datetime.now(UTC) - timedelta(minutes=10)
    pi, conversation = await chat(
        api, business_db, monkeypatch, "S12_KICKOFF", kickoff={"at": at.isoformat()}
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(hours=1)
    assert await brain_followups.sweep(pi.ctx) == []
    await pi.close()


async def test_a_declined_offer_is_never_followed_up(api, business_db, monkeypatch):
    pi, conversation = await chat(
        api,
        business_db,
        monkeypatch,
        "S5B_DECLINED",
        offer={"sent_at": ago(days=9)},
        reminder_consent="granted",
    )
    conversation.last_inbound_at = datetime.now(UTC) - timedelta(days=9)
    assert await brain_followups.sweep(pi.ctx) == []
    await pi.close()
