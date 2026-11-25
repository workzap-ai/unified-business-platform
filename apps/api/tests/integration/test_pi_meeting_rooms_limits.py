"""Limits of a video room: staff can remove a guest from a live call (blocked at the provider, no
new token), at most eight people per room, a time limit enforced by the worker, a monthly allowance,
and a pause switch that stops new rooms and tokens and ends live calls."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import (
    JOIN,
    ROOM_TOKEN,
    open_room,
    the_room,
)
from test_pi_meeting_rooms import (
    Provider as BaseProvider,
)
from test_pi_meeting_routes import BASE

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import room_jobs, room_limits, room_routes
from app.modules.pi_meetings.room_provider import RoomProviderError

pytestmark = pytest.mark.integration


@pytest.fixture
def provider(monkeypatch):
    p = BaseProvider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def switch(api, **extra):
    brain = {"meeting_intel": True, "meeting_room": True, "meeting_guests": True, **extra}
    r = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain", "brain": brain}}
    )
    assert r.status_code == 200, r.text


async def guest(api, mid, name="Ayesha", link=None):
    token = link or (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    joined = await api.post(f"{JOIN}/{token}", json={"name": name, "consent": True})
    return joined.json()["guest_token"], token


async def enter(api, guest_token):
    return await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest_token})


def worker(business_db, monkeypatch, provider):
    @asynccontextmanager
    async def sessions():
        yield business_db

    monkeypatch.setattr(room_jobs, "build_provider", lambda settings, http: provider)
    return {"sessions": sessions, "settings": None, "http": None}


async def test_staff_remove_a_guest_who_is_blocked_and_cannot_come_back(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "369300001")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    token, _ = await guest(api, mid)
    entered = (await enter(api, token)).json()
    status = (await api.get(f"{BASE}/{mid}/room")).json()
    person = next(p for p in status["people"] if p["label"] == "Ayesha")
    assert person == {**person, "staff": False, "removed": False}
    assert status["limits"] == {"minutes": 90, "people": 8}

    gone = await api.post(f"{BASE}/{mid}/room/people/{person['id']}/remove")
    assert gone.status_code == 200 and gone.json() == {"removed": True}
    assert provider.blocked == [(provider.created[0][0], entered["user_id"])]
    again = await enter(api, token)
    assert again.status_code == 403 and again.json()["error"]["code"] == "MEETING_ROOM_REMOVED"
    status = (await api.get(f"{BASE}/{mid}/room")).json()
    assert [p["removed"] for p in status["people"] if p["label"] == "Ayesha"] == [True]
    audit = await business_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "pi.meeting_room_person_removed")
    )
    assert audit is not None
    await pi.close()


async def test_staff_cannot_be_removed_a_failed_block_removes_nothing_and_ended_rooms_refuse(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369300002")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    await api.post(f"{BASE}/{mid}/room/token")
    token, _ = await guest(api, mid)
    await enter(api, token)
    people = (await api.get(f"{BASE}/{mid}/room")).json()["people"]
    staff = next(p for p in people if p["staff"])
    other = next(p for p in people if not p["staff"])
    no = await api.post(f"{BASE}/{mid}/room/people/{staff['id']}/remove")
    assert no.status_code == 409 and no.json()["error"]["code"] == "MEETING_ROOM_STAFF"
    provider.fail_block = RoomProviderError("ROOM_PROVIDER_BUSY", "busy", 429)
    busy = await api.post(f"{BASE}/{mid}/room/people/{other['id']}/remove")
    assert busy.status_code == 429
    assert (await enter(api, token)).status_code == 200  # still allowed: nothing was removed
    unknown = await api.post(
        f"{BASE}/{mid}/room/people/00000000-0000-0000-0000-000000000000/remove"
    )
    assert unknown.status_code == 404
    provider.fail_block = None
    await api.post(f"{BASE}/{mid}/room/end")
    late = await api.post(f"{BASE}/{mid}/room/people/{other['id']}/remove")
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_ROOM_CLOSED"
    await pi.close()


async def test_a_ninth_person_is_refused_and_a_removed_person_does_not_free_a_seat(
    api, business_db, provider, monkeypatch
):
    monkeypatch.setattr(room_limits, "MAX_PEOPLE", 2)
    pi, conv, scope = await workspace(api, business_db, "369300003")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    assert (await api.post(f"{BASE}/{mid}/room/token")).status_code == 200
    first, link = await guest(api, mid, "One")
    assert (await enter(api, first)).status_code == 200
    second, _ = await guest(api, mid, "Two", link)
    full = await enter(api, second)
    assert full.status_code == 409 and full.json()["error"]["code"] == "MEETING_ROOM_FULL"
    # someone already seated can come back (a refresh), the staff member too
    assert (await enter(api, first)).status_code == 200
    assert (await api.post(f"{BASE}/{mid}/room/token")).status_code == 200
    # removing the guest does not open the seat for the second one
    seated = (await api.get(f"{BASE}/{mid}/room")).json()["people"]
    one = next(p for p in seated if p["label"] == "One")
    await api.post(f"{BASE}/{mid}/room/people/{one['id']}/remove")
    assert (await enter(api, second)).status_code == 409
    await pi.close()


async def test_a_call_past_the_time_limit_is_ended_by_the_worker_and_a_fresh_one_is_not(
    api, business_db, provider, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "369300004")
    await switch(api)
    old = (await open_room(api)).json()["meeting"]["id"]
    fresh = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, old)
    room.state = "live"
    room.started_at = datetime.now(UTC) - timedelta(minutes=room_limits.MAX_CALL_MINUTES + 5)
    call_id = room.call_id
    await business_db.commit()
    other = await the_room(business_db, fresh)
    other.state = "live"
    other.started_at = datetime.now(UTC) - timedelta(minutes=10)
    await business_db.commit()
    ctx = worker(business_db, monkeypatch, provider)
    assert await room_jobs.close_rooms(ctx) == 1
    business_db.expire_all()
    assert provider.ended == [call_id]
    closed = await the_room(business_db, old)
    assert closed.state == "ended" and closed.transcript_state == "pending"
    assert (await the_room(business_db, fresh)).state == "live"
    audit = await business_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "pi.meeting_room_closed")
    )
    assert audit is not None and audit.details == {"why": "time_limit"}
    assert await room_jobs.close_rooms(ctx) == 0  # nothing left to close
    await pi.close()


async def test_the_pause_switch_refuses_new_rooms_and_tokens_and_ends_live_calls(
    api, business_db, provider, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "369300005")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    token, _ = await guest(api, mid)
    await switch(api, meeting_room_kill=True)
    new = await open_room(api)
    assert new.status_code == 503 and new.json()["error"]["code"] == "MEETING_ROOM_PAUSED"
    staff = await api.post(f"{BASE}/{mid}/room/token")
    assert staff.status_code == 503
    assert (await enter(api, token)).status_code == 503
    assert await room_jobs.close_rooms(worker(business_db, monkeypatch, provider)) == 1
    business_db.expire_all()
    assert (await the_room(business_db, mid)).state == "ended"
    audit = await business_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "pi.meeting_room_closed")
    )
    assert audit.details == {"why": "paused"}
    await pi.close()


async def test_the_month_allowance_refuses_a_new_room_once_it_is_used_up(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369300006")
    await switch(api, meeting_room_month_minutes=30)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    now = datetime.now(UTC)
    room.state = "ended"
    room.started_at = now - timedelta(minutes=45)
    room.ended_at = now - timedelta(minutes=10)  # 35 minutes of call time
    await business_db.commit()
    if now.day == 1 and now.hour == 0 and now.minute < 45:
        pytest.skip("the call would fall in last month")
    refused = await open_room(api)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "MEETING_ROOM_MONTH_LIMIT"
    await switch(api, meeting_room_month_minutes=120)
    assert (await open_room(api)).status_code == 201
    await pi.close()


async def test_a_paused_or_bad_limit_setting_is_validated(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "369300007")
    for brain in ({"meeting_room_kill": "yes"}, {"meeting_room_month_minutes": -1}):
        r = await api.patch(
            "/api/v1/pi/settings/response_rules",
            json={"value": {"pi_mode": "brain", "brain": brain}},
        )
        assert r.status_code == 422, r.text
    await pi.close()
