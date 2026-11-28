"""Staff start, move and stop what pi presents; the room agent reads it; nothing shows when it is
off, when pi is not in the room, or when there is nothing approved or noted."""

import pytest
from sqlalchemy import select
from test_pi_meeting_data import insight, workspace
from test_pi_meeting_rooms import Provider as BaseProvider
from test_pi_meeting_rooms import open_room, the_room
from test_pi_meeting_rooms_limits import switch
from test_pi_meeting_routes import BASE

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import room_agent_claim, room_live, room_present, room_routes
from app.modules.pi_meetings.models import PiMeeting

pytestmark = pytest.mark.integration


@pytest.fixture
def provider(monkeypatch):
    p = BaseProvider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def room_with_history(api, db, phone, *, approved=True, present_flag=True, mode="speak"):
    pi, conv, scope = await workspace(api, db, phone)
    await switch(api, meeting_room_speak=True, meeting_room_present=present_flag)
    # an earlier call of the same customer, with one approved and one pending point
    earlier = PiMeeting(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=conv.customer_id,
        title="Earlier call",
        status="review",
    )
    db.add(earlier)
    await db.flush()
    if approved:
        db.add_all(
            [
                insight(
                    scope,
                    earlier.id,
                    kind="decision",
                    text="Start with the shop page",
                    review_status="approved",
                ),
                insight(
                    scope,
                    earlier.id,
                    kind="next_step",
                    text="A draft nobody checked",
                    review_status="pending",
                ),
            ]
        )
    await db.commit()
    opened = await open_room(api, customer_id=str(conv.customer_id))
    mid = opened.json()["meeting"]["id"]
    room = await the_room(db, mid)
    room.state = "live"
    room.pi_mode = mode
    await db.commit()
    return pi, scope, mid, room


async def test_staff_start_move_and_stop_a_recap(api, business_db, provider):
    pi, scope, mid, room = await room_with_history(api, business_db, "369900001")
    started = await api.post(f"{BASE}/{mid}/room/present", json={})
    assert started.status_code == 200
    now = started.json()["present"]
    assert now["on"] and now["index"] == 0 and now["total"] == 3
    assert now["heading"] == room_present.TITLE

    stored = (await the_room(business_db, mid)).present
    assert [s["heading"] for s in stored["slides"]][1].startswith("Our call on")
    assert "A draft nobody checked" not in str(stored)  # only approved points

    nxt = await api.post(f"{BASE}/{mid}/room/present/go", json={"step": 1})
    assert nxt.json()["present"]["index"] == 1
    far = await api.post(f"{BASE}/{mid}/room/present/go", json={"step": 20})
    assert far.json()["present"]["index"] == 2  # never past the last slide
    direct = await api.post(f"{BASE}/{mid}/room/present/go", json={"index": 0})
    assert direct.json()["present"]["index"] == 0
    assert (await api.get(f"{BASE}/{mid}/room")).json()["room"]["present"]["on"] is True

    stopped = await api.post(f"{BASE}/{mid}/room/present/stop")
    assert stopped.json()["present"] == {"on": False, "index": 0, "total": 0, "heading": ""}
    assert (await the_room(business_db, mid)).present["slides"] == []  # nothing is kept
    actions = {
        a.action
        for a in (
            await business_db.scalars(
                select(AuditEvent).where(AuditEvent.action.like("pi.meeting_room_present_%"))
            )
        ).all()
    }
    assert actions == {"pi.meeting_room_present_started", "pi.meeting_room_present_stopped"}
    await pi.close()


async def test_it_needs_the_flag_pi_in_the_room_an_open_room_and_something_to_show(
    api, business_db, provider
):
    pi, scope, mid, room = await room_with_history(
        api, business_db, "369900002", present_flag=False
    )
    off = await api.post(f"{BASE}/{mid}/room/present", json={})
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_ROOM_PRESENT_OFF"
    await switch(api, meeting_room_speak=True, meeting_room_present=True)

    room = await the_room(business_db, mid)
    room.pi_mode = "off"
    await business_db.commit()
    quiet = await api.post(f"{BASE}/{mid}/room/present", json={})
    assert quiet.status_code == 409 and quiet.json()["error"]["code"] == "MEETING_ROOM_PI_OFF"

    notyet = await api.post(f"{BASE}/{mid}/room/present/go", json={"step": 1})
    assert notyet.status_code == 409
    assert notyet.json()["error"]["code"] == "MEETING_ROOM_NOT_PRESENTING"
    bad = await api.post(f"{BASE}/{mid}/room/present/go", json={"step": 99})
    assert bad.status_code == 422  # outside what a step may be
    extra = await api.post(f"{BASE}/{mid}/room/present", json={"source": "anything"})
    assert extra.status_code == 422

    room = await the_room(business_db, mid)
    room.pi_mode = "speak"
    room.state = "ended"
    await business_db.commit()
    closed = await api.post(f"{BASE}/{mid}/room/present", json={})
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "MEETING_ROOM_CLOSED"
    await pi.close()


async def test_nothing_approved_and_nothing_noted_means_nothing_to_present(
    api, business_db, provider
):
    pi, scope, mid, room = await room_with_history(api, business_db, "369900003", approved=False)
    none = await api.post(f"{BASE}/{mid}/room/present", json={})
    assert none.status_code == 422
    assert none.json()["error"]["code"] == "MEETING_ROOM_NOTHING_TO_PRESENT"
    # a note pi took in THIS call is enough to show
    room = await the_room(business_db, mid)
    live = room_live.empty()
    room_live.add_tip(live, "note", "They need delivery in Lahore", "requirement_explicit")
    room.live = live
    await business_db.commit()
    ok = await api.post(f"{BASE}/{mid}/room/present", json={})
    assert ok.status_code == 200 and ok.json()["present"]["total"] == 3
    await pi.close()


async def test_the_agent_gets_the_slides_only_when_the_flag_is_on_and_ending_clears_them(
    api, business_db, provider
):
    pi, scope, mid, room = await room_with_history(api, business_db, "369900004")
    await api.post(f"{BASE}/{mid}/room/present", json={})
    room = await the_room(business_db, mid)
    room.agent_id = "agent-1"
    await business_db.commit()
    from datetime import UTC, datetime

    orders = await room_agent_claim.beat(business_db, room.id, "agent-1", datetime.now(UTC))
    assert orders is not None and orders.present["on"] and len(orders.present["slides"]) == 3
    await switch(api, meeting_room_speak=True, meeting_room_present=False)
    orders = await room_agent_claim.beat(business_db, room.id, "agent-1", datetime.now(UTC))
    assert orders is not None and orders.present == {}  # the flag went off: nothing is shown
    await switch(api, meeting_room_speak=True, meeting_room_present=True)
    ended = await api.post(f"{BASE}/{mid}/room/end")
    assert ended.status_code == 200
    assert (await the_room(business_db, mid)).present["slides"] == []
    await pi.close()
