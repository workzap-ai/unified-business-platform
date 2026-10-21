# ruff: noqa: F811 - pytest fixtures imported from the portal tests
"""Reliability of pi's automatic follow-ups: the ladder (day 3, 7, 14 templates), the caps,
quiet hours and Friday prayers, a person having just replied, the team's 48-hour
escalation, STOP and every other way a customer opts out, and the two senders
(``sweep_followups`` and ``run_ladder``) never writing to one chat twice.

Time is injected (``run_ladder(ctx, now)``), nothing here sends a real WhatsApp message.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pi_saas_support import worker_ctx
from sqlalchemy import func, select
from test_pi_customer_engine import _linked_chat
from test_pi_customer_portal import (  # noqa: F401 - fixtures
    CUSTOMER,
    NUMBER,
    PORTAL,
    app,
    provider,
)
from test_pi_saas import _kapso, _message_event, _run_jobs
from test_pi_service_conversations import mock_turns, reminder_workspace, turn

from app.modules.notifications.models import Notification
from app.modules.pi.buttons import FOLLOW_UP
from app.modules.pi.followups import sweep_followups
from app.modules.pi.models import PiConversation, PiMessage, PiSettings
from app.modules.pi_customer import engine
from app.modules.pi_customer.engine import STOP, prayer_or_quiet

pytestmark = pytest.mark.integration

# A Wednesday at 11:00 UTC: not quiet hours, not Friday prayers.
NOW = datetime(2026, 11, 4, 11, 0, tzinfo=UTC)
TEMPLATES = {
    lang: {step: {"name": f"pi_{step}", "language": "en_US"} for step in ("day3", "day7", "day14")}
    for lang in ("en", "roman_ur")
}


def _iso(moment: datetime) -> str:
    return moment.isoformat()


async def _policy(db, conversation) -> PiSettings:
    # A business has one settings row per environment: the chat's own.
    return await db.scalar(
        select(PiSettings).where(
            PiSettings.tenant_id == conversation.tenant_id,
            PiSettings.environment_id == conversation.environment_id,
        )
    )


async def _state(
    db,
    conversation_id,
    *,
    now=NOW,
    waited,
    consent="granted",
    nudges=None,
    team_waited=None,
    timezone="UTC",
):
    """The chat as it is ``waited`` after pi's open question (customer's turn), or with the
    team owing an update for ``team_waited``. The customer's last message is as old."""
    conversation = await db.get(PiConversation, conversation_id)
    await db.refresh(conversation)
    brief = dict(conversation.service_brief)
    report = dict(brief["customer_issues"])
    report["waiting"] = {
        "client": _iso(now - waited) if waited is not None else None,
        "team": _iso(now - team_waited) if team_waited is not None else None,
    }
    brief["customer_issues"] = report
    brief["reminder_consent"] = consent
    brief["nudges"] = list(nudges or [])
    brief.pop("customer_waiting_until", None)
    conversation.service_brief = brief
    ago = waited if waited is not None else team_waited
    conversation.last_inbound_at = now - ago
    conversation.last_message_at = now - timedelta(hours=1)
    policy = await _policy(db, conversation)
    policy.timezone = timezone
    policy.whatsapp_config = {
        **policy.whatsapp_config,
        "ladder_templates": TEMPLATES,
        "quiet_start": 21,
        "quiet_end": 9,
    }
    await db.commit()
    return conversation


async def _clock(db, conversation_id, *, now, since):
    """Move the same chat forward: the question has now been open since ``since``."""
    conversation = await db.get(PiConversation, conversation_id)
    await db.refresh(conversation)
    brief = dict(conversation.service_brief)
    report = dict(brief["customer_issues"])
    report["waiting"] = {"client": _iso(since), "team": None}
    brief["customer_issues"] = report
    conversation.service_brief = brief
    conversation.last_inbound_at = since
    conversation.last_message_at = now - timedelta(hours=1)
    await db.commit()


def _entry(step: str, at: datetime, since: datetime) -> dict:
    return {"at": _iso(at), "since": _iso(since), "step": step}


async def _steps(db, queued) -> list[str]:
    out = []
    for message_id in queued:
        message = await db.get(PiMessage, message_id)
        media = message.media or {}
        out.append(media["ladder"]["step"] if "ladder" in media else str(media.get("nudge")))
    return out


async def _add_message(db, conversation, *, sender, media=None, created_at, status="sent"):
    message = PiMessage(
        tenant_id=conversation.tenant_id,
        environment_id=conversation.environment_id,
        conversation_id=conversation.id,
        direction="outbound",
        sender_type=sender,
        body="hello",
        status=status,
        media=media or {},
    )
    db.add(message)
    await db.flush()
    message.created_at = created_at
    await db.commit()
    return message


async def _chat(app, provider, db, monkeypatch):
    business, customer, conversation_id = await _linked_chat(app, provider, db, monkeypatch)
    return business, customer, conversation_id, worker_ctx(app, db)


async def _close(*clients):
    for client in clients:
        await client.aclose()


# ------------------------------------------------------------------- the day 3/7/14 steps


async def test_day_3_7_and_14_templates_go_out_one_at_a_time(
    app, provider, business_db, monkeypatch
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    since = NOW
    await _state(
        business_db,
        cid,
        now=since + timedelta(days=2, hours=21),
        waited=timedelta(days=2, hours=21),
    )
    assert await engine.run_ladder(ctx, since + timedelta(days=2, hours=21)) == []  # too early

    for days, step in ((3, "day3"), (7, "day7"), (14, "day14")):
        at = since + timedelta(days=days, hours=1)
        await _clock(business_db, cid, now=at, since=since)
        queued = await engine.run_ladder(ctx, at)
        assert await _steps(business_db, queued) == [step]
        message = await business_db.get(PiMessage, queued[0])
        assert message.media["ladder"]["template"]["name"] == f"pi_{step}"
        assert await engine.run_ladder(ctx, at + timedelta(minutes=1)) == []  # once each
    await _close(business, customer)


@pytest.mark.parametrize("consent", ["unknown", "declined"])
async def test_templates_need_the_customers_consent(
    app, provider, business_db, monkeypatch, consent
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    waited = timedelta(days=4)
    await _state(business_db, cid, waited=waited, consent=consent)
    assert await engine.run_ladder(ctx, NOW) == []
    await _close(business, customer)


async def test_a_missing_template_tells_the_team_and_sends_nothing(
    app, provider, business_db, monkeypatch
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    conversation = await _state(business_db, cid, waited=timedelta(days=4))
    policy = await _policy(business_db, conversation)
    policy.whatsapp_config = {**policy.whatsapp_config, "ladder_templates": {}}
    await business_db.commit()
    assert await engine.run_ladder(ctx, NOW) == []
    kinds = list(
        await business_db.scalars(
            select(Notification.kind).where(Notification.tenant_id == conversation.tenant_id)
        )
    )
    assert "pi.ladder_template_missing" in kinds
    await _close(business, customer)


async def test_an_earlier_step_never_goes_out_after_a_later_one(
    app, provider, business_db, monkeypatch
):
    """Consent given late (or a pause) can make day 7 the first step sent; day 3 must not
    follow it three days later."""
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    since = NOW - timedelta(days=11)
    await _state(
        business_db,
        cid,
        waited=timedelta(days=11),
        nudges=[_entry("day7", NOW - timedelta(days=4), since)],
    )
    assert await engine.run_ladder(ctx, NOW) == []
    await _close(business, customer)


# ------------------------------------------------------------------------------- the caps


async def test_four_touches_are_the_most_one_question_gets(app, provider, business_db, monkeypatch):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    since = NOW - timedelta(days=14, hours=2)
    log = [
        _entry("nudge1", since + timedelta(hours=20), since),
        _entry("day3", since + timedelta(days=3), since),
        _entry("day7", since + timedelta(days=7), since),
        _entry("extra", since + timedelta(days=8), since),
    ]
    await _state(business_db, cid, waited=timedelta(days=14, hours=2), nudges=log)
    assert await engine.run_ladder(ctx, NOW) == []  # day 14 is due, but that would be a fifth
    await _close(business, customer)


async def test_one_template_per_72_hours(app, provider, business_db, monkeypatch):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    since = NOW - timedelta(days=8)
    recent = [_entry("day3", NOW - timedelta(days=2), since)]
    await _state(business_db, cid, waited=timedelta(days=8), nudges=recent)
    assert await engine.run_ladder(ctx, NOW) == []  # day 7 is due, the last template is 2 days old
    older = [_entry("day3", NOW - timedelta(days=3, hours=1), since)]
    await _state(business_db, cid, waited=timedelta(days=8), nudges=older)
    assert await _steps(business_db, await engine.run_ladder(ctx, NOW)) == ["day7"]
    await _close(business, customer)


async def test_a_template_from_the_other_sender_counts_towards_the_72_hours(
    app, provider, business_db, monkeypatch
):
    """``sweep_followups`` (one reminder template) and the ladder share the same 72 hours."""
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    conversation = await _state(business_db, cid, waited=timedelta(days=8))
    await _add_message(
        business_db,
        conversation,
        sender="ai",
        media={"reminder": {"template": {"name": "service_followup"}}},
        created_at=NOW - timedelta(days=1),
    )
    assert await engine.run_ladder(ctx, NOW) == []
    await _close(business, customer)


async def test_the_reminder_sweep_waits_when_the_ladder_just_sent_a_template(
    api, business_db, monkeypatch
):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    await _add_message(
        business_db,
        conversation,
        sender="ai",
        media={"ladder": {"step": "day3", "template": {"name": "pi_day3"}}},
        created_at=datetime.now(UTC) - timedelta(hours=20),
    )
    await sweep_followups(pi.ctx)
    assert [m for m in await pi.outbound() if m.media.get("reminder")] == []
    await business_db.refresh(conversation)
    assert conversation.followup_due_at is not None  # asked again later, not dropped
    assert conversation.followup_due_at > datetime.now(UTC) + timedelta(hours=40)
    await pi.close()


# ---------------------------------------------------------------- a person just replied


async def test_pi_stays_quiet_for_12_hours_after_a_person_replied(
    app, provider, business_db, monkeypatch
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    waited = timedelta(hours=20, minutes=30)
    conversation = await _state(business_db, cid, waited=waited)
    person = await _add_message(
        business_db, conversation, sender="human", created_at=NOW - timedelta(hours=2)
    )
    assert await engine.run_ladder(ctx, NOW) == []
    person.created_at = NOW - timedelta(hours=13)
    await business_db.commit()
    assert await _steps(business_db, await engine.run_ladder(ctx, NOW)) == ["nudge1"]
    await _close(business, customer)


# -------------------------------------------------------- quiet hours and Friday prayers


@pytest.mark.parametrize(
    ("utc", "timezone", "quiet"),
    [
        ("2026-11-04T16:00:00+00:00", "Asia/Karachi", True),  # 21:00 Wednesday: quiet starts
        ("2026-11-04T15:59:00+00:00", "Asia/Karachi", False),  # 20:59
        ("2026-11-04T03:59:00+00:00", "Asia/Karachi", True),  # 08:59: still quiet
        ("2026-11-04T04:00:00+00:00", "Asia/Karachi", False),  # 09:00: over
        ("2026-11-06T07:29:00+00:00", "Asia/Karachi", False),  # Friday 12:29
        ("2026-11-06T07:30:00+00:00", "Asia/Karachi", True),  # Friday 12:30: prayers
        ("2026-11-06T09:29:00+00:00", "Asia/Karachi", True),  # Friday 14:29
        ("2026-11-06T09:30:00+00:00", "Asia/Karachi", False),  # Friday 14:30: over
        ("2026-11-05T07:30:00+00:00", "Asia/Karachi", False),  # Thursday 12:30: no prayers
        ("2026-11-06T09:00:00+00:00", "Asia/Dubai", True),  # Friday 13:00 in Dubai: prayers
        ("2026-11-06T10:30:00+00:00", "Asia/Dubai", False),  # Friday 14:30 in Dubai: over
    ],
)
def test_quiet_hours_and_friday_prayers(utc, timezone, quiet):
    from types import SimpleNamespace

    policy = SimpleNamespace(timezone=timezone, whatsapp_config={})
    assert prayer_or_quiet(policy, datetime.fromisoformat(utc)) is quiet


async def test_the_ladder_obeys_the_real_quiet_hours_and_prayer_times(
    app, provider, business_db, monkeypatch
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    waited = timedelta(hours=20, minutes=30)
    for utc, sends in (
        (datetime(2026, 11, 6, 8, 0, tzinfo=UTC), False),  # Friday 13:00 in Karachi
        (datetime(2026, 11, 5, 17, 30, tzinfo=UTC), False),  # Thursday 22:30
        (datetime(2026, 11, 5, 3, 0, tzinfo=UTC), False),  # Thursday 08:00
        (datetime(2026, 11, 6, 10, 0, tzinfo=UTC), True),  # Friday 15:00
    ):
        await _state(business_db, cid, now=utc, waited=waited, timezone="Asia/Karachi")
        queued = await engine.run_ladder(ctx, utc)
        assert bool(queued) is sends, utc
    await _close(business, customer)


# -------------------------------------------------------------- the team's 48-hour escalation


async def test_the_team_is_alerted_at_12_24_and_48_hours_once_each(
    app, provider, business_db, monkeypatch
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    conversation = await _state(business_db, cid, waited=None, team_waited=timedelta(hours=49))
    conversation.last_inbound_at = NOW - timedelta(hours=13)  # inside the 24-hour window
    await business_db.commit()
    queued = await engine.run_ladder(ctx, NOW)
    assert len(queued) == 1  # the customer hears once that the team is on it
    again = await engine.run_ladder(ctx, NOW + timedelta(minutes=1))
    assert again == []

    async def alerts():
        return sorted(
            (n.title, n.severity)
            for n in await business_db.scalars(
                select(Notification).where(
                    Notification.tenant_id == conversation.tenant_id,
                    Notification.kind == "pi.team_sla",
                )
            )
        )

    assert await alerts() == [
        ("A customer has waited 12h for the team", "info"),
        ("A customer has waited 24h for the team", "warning"),
        ("A customer has waited 48h for the team", "critical"),
    ]
    await _close(business, customer)


async def test_no_alert_once_a_person_has_answered(app, provider, business_db, monkeypatch):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    conversation = await _state(business_db, cid, waited=None, team_waited=timedelta(hours=49))
    await _add_message(
        business_db, conversation, sender="human", created_at=NOW - timedelta(hours=1)
    )
    assert await engine.run_ladder(ctx, NOW) == []
    count = await business_db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.tenant_id == conversation.tenant_id, Notification.kind == "pi.team_sla")
    )
    assert count == 0
    await _close(business, customer)


# ---------------------------------------------------------- STOP, replies and every opt-out


@pytest.mark.parametrize(
    "text",
    [
        "STOP",
        "stop please",
        "Stop reminders",
        "band karo",
        "Band kardo yaar",
        "mat bhejo",
        "unsubscribe",
        "don't message me again",
        "Reminders band karo",
        "أوقف التذكيرات",
    ],
)
def test_these_words_opt_a_customer_out(text):
    assert STOP.search(text)


@pytest.mark.parametrize(
    "text", ["Let's continue", "Remind me later", "Baad mein yaad dilao", "ok"]
)
def test_these_words_do_not(text):
    assert not STOP.search(text)


def test_every_stop_button_pi_sends_is_understood_as_a_stop():
    for language, titles in FOLLOW_UP.items():
        assert STOP.search(titles[2]), language


@pytest.mark.parametrize("consent", ["granted", "unknown"])
@pytest.mark.parametrize("stop_text", ["band karo", "Stop reminders", "أوقف التذكيرات"])
async def test_a_stop_is_remembered_even_when_the_customer_writes_again(
    app, provider, business_db, monkeypatch, stop_text, consent
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    conversation = await _state(business_db, cid, waited=timedelta(hours=1), consent=consent)
    for number, text in enumerate((stop_text, "ok shukriya")):
        mock_turns(monkeypatch, turn(reply="Theek hai, ab reminders nahi aayenge."))
        await _kapso(
            business,
            "whatsapp.message.received",
            _message_event(NUMBER, CUSTOMER, text, f"wamid.stop-{number}"),
        )
        await _run_jobs(app, provider, business_db)
    await business_db.refresh(conversation)
    assert conversation.service_brief["reminder_consent"] == "declined"
    # 21 hours later nothing is sent: not the 20-hour nudge, not a template.
    later = NOW + timedelta(days=5)
    await _clock(business_db, cid, now=later, since=NOW)
    assert await engine.run_ladder(ctx, later) == []
    await _close(business, customer)


@pytest.mark.parametrize("waiting_state", ["declined", "paused"])
async def test_opt_out_and_pauses_silence_every_automatic_message(
    app, provider, business_db, monkeypatch, waiting_state
):
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    conversation = await _state(
        business_db,
        cid,
        waited=timedelta(hours=20, minutes=30),
        consent="declined" if waiting_state == "declined" else "granted",
    )
    if waiting_state == "paused":
        brief = dict(conversation.service_brief)
        brief["customer_waiting_until"] = _iso(NOW + timedelta(days=2))
        conversation.service_brief = brief
        await business_db.commit()
    assert await engine.run_ladder(ctx, NOW) == []
    await _close(business, customer)


async def test_a_reply_starts_the_wait_again(app, provider, business_db, monkeypatch):
    """A new customer message moves "since": the old question's touches no longer count and
    nothing goes out until the new wait is old enough."""
    business, customer, cid, ctx = await _chat(app, provider, business_db, monkeypatch)
    old_since = NOW - timedelta(days=5)
    log = [_entry("nudge1", old_since + timedelta(hours=20), old_since)]
    since = NOW + timedelta(hours=2, minutes=30)  # the new question: 13:30
    await _state(
        business_db, cid, now=since + timedelta(hours=2), waited=timedelta(hours=2), nudges=log
    )
    assert await engine.run_ladder(ctx, since + timedelta(hours=2)) == []
    later = since + timedelta(hours=20, minutes=30)  # 10:00 next morning
    await _clock(business_db, cid, now=later, since=since)
    assert await _steps(business_db, await engine.run_ladder(ctx, later)) == ["nudge1"]
    await _close(business, customer)


@pytest.mark.parametrize("cancel", ["declined", "paused", "unknown"])
async def test_the_reminder_sweep_never_sends_without_consent_or_during_a_pause(
    api, business_db, monkeypatch, cancel
):
    pi, conversation = await reminder_workspace(api, business_db, monkeypatch)
    brief = dict(conversation.service_brief)
    if cancel == "paused":
        brief["customer_waiting_until"] = _iso(datetime.now(UTC) + timedelta(days=2))
    else:
        brief["reminder_consent"] = cancel
    conversation.service_brief = brief
    await business_db.commit()
    await sweep_followups(pi.ctx)
    assert [m for m in await pi.outbound() if m.media.get("reminder")] == []
    await pi.close()


# ------------------------------------------------------------------ the scheduler and stream


def test_the_follow_up_sweeps_are_scheduled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/test")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    from app.worker import WorkerSettings

    jobs = {job.coroutine.__name__: job for job in WorkerSettings.cron_jobs}
    journeys = jobs["sweep_customer_journeys"]
    assert journeys.unique and journeys.second == {50} and journeys.minute is None  # every minute
    assert jobs["sweep_followups"].minute == set(range(0, 60, 5))
    assert {"sweep_check_ins", "sweep_session_snapshots"} <= set(jobs)


async def test_the_dashboard_stream_announces_a_change(app, provider, business_db, monkeypatch):
    business, customer, cid, _ = await _chat(app, provider, business_db, monkeypatch)
    # The stream opens its own database sessions (not the request's): point them at the test DB.
    monkeypatch.setattr(app.state, "sessions", worker_ctx(app, business_db)["sessions"])
    real_sleep = asyncio.sleep
    changed = []

    async def quick(delay, *args, **kwargs):
        if delay == 3 and not changed:  # something changes while the stream is open
            changed.append(True)
            conversation = await business_db.get(PiConversation, cid)
            await business_db.refresh(conversation)
            conversation.last_message_at = datetime.now(UTC) + timedelta(seconds=5)
            await business_db.commit()
        return await real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", quick)
    response = await customer.get(f"{PORTAL}/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.startswith("retry: 5000")
    assert response.text.count("event: update") == 1  # one change, one event
    await _close(business, customer)
