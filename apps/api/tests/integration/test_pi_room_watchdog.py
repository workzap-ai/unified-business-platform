"""Staff are told, once per room, when pi has dropped out of a call or a transcript is stuck."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import Provider as BaseProvider
from test_pi_meeting_rooms import open_room, the_room
from test_pi_meeting_rooms_limits import switch

from app.modules.notifications.models import Notification
from app.modules.pi_meetings import room_routes, room_watchdog

pytestmark = pytest.mark.integration


@pytest.fixture
def provider(monkeypatch):
    p = BaseProvider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


async def alerts(db):
    db.expire_all()
    return (
        await db.scalars(select(Notification).where(Notification.kind == room_watchdog.KIND))
    ).all()


async def live_room(api, db, phone, **fields):
    pi, conv, scope = await workspace(api, db, phone)
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(db, mid)
    room.state = "live"
    room.started_at = NOW - timedelta(minutes=10)
    for name, value in fields.items():
        setattr(room, name, value)
    await db.commit()
    return pi, mid, room


async def test_a_live_room_whose_agent_went_quiet_alerts_staff_once(api, business_db, provider):
    pi, mid, room = await live_room(
        api,
        business_db,
        "369500001",
        pi_mode="speak",
        agent_id="agent-1",
        agent_beat_at=NOW - timedelta(seconds=room_watchdog.AGENT_DEAD_S + 5),
    )
    assert await room_watchdog.agent_missing(business_db, NOW) == 1
    assert await room_watchdog.agent_missing(business_db, NOW) == 1  # asked again: still one alert
    found = await alerts(business_db)
    assert len(found) == 1
    alert = found[0]
    assert alert.severity == "critical" and alert.required_permission == "pi.meetings.record"
    assert alert.link == f"/pi/meetings/{mid}/room" and "pi is not in the call" in alert.title
    await pi.close()


async def test_a_healthy_or_silent_room_raises_no_alert(api, business_db, provider):
    pi, mid, room = await live_room(
        api,
        business_db,
        "369500002",
        pi_mode="speak",
        agent_id="agent-1",
        agent_beat_at=NOW - timedelta(seconds=10),
    )
    assert await room_watchdog.agent_missing(business_db, NOW) == 0  # it beat 10 s ago
    room.pi_mode = "off"  # pi is not meant to be there
    room.agent_beat_at = NOW - timedelta(minutes=5)
    await business_db.commit()
    assert await room_watchdog.agent_missing(business_db, NOW) == 0
    room.pi_mode = "speak"
    room.agent_id = None
    room.agent_beat_at = None
    room.started_at = NOW - timedelta(seconds=20)  # only just started: the agent has not had time
    await business_db.commit()
    assert await room_watchdog.agent_missing(business_db, NOW) == 0
    room.started_at = NOW - timedelta(minutes=5)  # five minutes and no agent ever came
    await business_db.commit()
    assert await room_watchdog.agent_missing(business_db, NOW) == 1
    assert len(await alerts(business_db)) == 1
    await pi.close()


async def test_an_ended_call_whose_transcript_never_arrives_alerts_as_a_warning(
    api, business_db, provider
):
    pi, mid, room = await live_room(
        api,
        business_db,
        "369500003",
        state="ended",
        transcript_state="pending",
        ended_at=NOW - timedelta(seconds=room_watchdog.STUCK_S + 60),
    )
    assert await room_watchdog.transcripts_stuck(business_db, NOW) == 1
    (alert,) = await alerts(business_db)
    assert alert.severity == "warning" and "stuck" in alert.title
    room.ended_at = NOW - timedelta(minutes=2)  # a normal wait is not an alert
    await business_db.commit()
    assert await room_watchdog.transcripts_stuck(business_db, NOW) == 0
    await pi.close()


async def test_a_failing_watchdog_never_raises(api, business_db, provider):
    class Broken:
        async def scalars(self, *args, **kwargs):
            raise RuntimeError("db down")

        async def rollback(self):
            pass

    assert await room_watchdog.agent_missing(Broken(), NOW) == 0
    assert await room_watchdog.transcripts_stuck(Broken(), NOW) == 0
