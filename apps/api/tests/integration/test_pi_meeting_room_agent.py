"""pi speaking in a video room: the host switches it on and mutes it, one agent holds a room, the
claim is lost when not renewed, and nothing happens unless the workspace allows it."""

from datetime import UTC, datetime, timedelta

import pytest
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import Provider, open_room, the_room
from test_pi_meeting_rooms_limits import switch
from test_pi_meeting_routes import BASE

from app.modules.pi_meetings import room_agent_claim as claim
from app.modules.pi_meetings import room_routes

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def room_with_pi(api, business_db, phone, **flags):
    pi, conv, scope = await workspace(api, business_db, phone)
    await switch(api, meeting_room_speak=True, **flags)
    mid = (await open_room(api)).json()["meeting"]["id"]
    return pi, mid


async def test_the_host_switches_pi_on_mutes_it_and_the_view_says_so(api, business_db, provider):
    pi, mid = await room_with_pi(api, business_db, "369400001")
    off = (await api.get(f"{BASE}/{mid}/room")).json()["room"]["pi"]
    assert off == {"mode": "off", "muted": False, "intake": False, "here": False}
    on = await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak", "intake": True})
    assert on.status_code == 200
    assert on.json()["room"]["pi"]["mode"] == "speak" and on.json()["room"]["pi"]["intake"]
    mute = await api.post(f"{BASE}/{mid}/room/pi", json={"muted": True})
    pi_view = mute.json()["room"]["pi"]
    assert pi_view["muted"] and pi_view["mode"] == "speak"  # a field left out is left as it was
    await pi.close()


async def test_speech_cannot_be_switched_on_when_the_workspace_has_not_allowed_it(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369400002")
    await switch(api)  # rooms on, speech not
    mid = (await open_room(api)).json()["meeting"]["id"]
    no = await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    assert no.status_code == 403 and no.json()["error"]["code"] == "MEETING_ROOM_SPEAK_OFF"
    ok = await api.post(f"{BASE}/{mid}/room/pi", json={"muted": True})  # muting is always fine
    assert ok.status_code == 200
    bad = await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "shout"})
    assert bad.status_code == 422
    await pi.close()


async def test_pi_cannot_be_set_in_a_room_that_has_ended(api, business_db, provider):
    pi, mid = await room_with_pi(api, business_db, "369400003")
    await api.post(f"{BASE}/{mid}/room/end")
    late = await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_ROOM_CLOSED"
    await pi.close()


async def test_one_agent_holds_a_room_and_a_second_one_is_refused(api, business_db, provider):
    pi, mid = await room_with_pi(api, business_db, "369400004")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    mine = await claim.claim(business_db, "agent-a", NOW)
    assert [r.meeting_id.hex for r in mine if str(r.meeting_id) == mid] == [mid.replace("-", "")]
    await business_db.commit()
    assert await claim.claim(business_db, "agent-b", NOW + timedelta(seconds=5)) == []
    room = await the_room(business_db, mid)
    assert room.agent_id == "agent-a"
    await pi.close()


async def test_a_lease_that_is_not_renewed_passes_to_another_agent(api, business_db, provider):
    pi, mid = await room_with_pi(api, business_db, "369400005")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    later = NOW + timedelta(seconds=claim.LEASE_S + 1)
    taken = await claim.claim(business_db, "agent-b", later)
    assert any(str(r.meeting_id) == mid for r in taken)
    await business_db.commit()
    room = await the_room(business_db, mid)
    lost = await claim.beat(business_db, room.id, "agent-a", later)
    assert lost is None  # the old agent learns it must leave
    kept = await claim.beat(business_db, room.id, "agent-b", later)
    assert kept is not None and kept.stay and kept.speak and not kept.muted
    await pi.close()


async def test_mute_intake_and_pause_reach_the_agent_on_its_next_beat(api, business_db, provider):
    pi, mid = await room_with_pi(api, business_db, "369400006")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak", "intake": True})
    room_id = (await the_room(business_db, mid)).id
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    orders = await claim.beat(business_db, room_id, "agent-a", NOW)
    assert orders.intake and not orders.muted
    await api.post(f"{BASE}/{mid}/room/pi", json={"muted": True})
    business_db.expire_all()
    assert (await claim.beat(business_db, room_id, "agent-a", NOW)).muted
    await switch(api, meeting_room_speak=True, meeting_room_kill=True)  # the pause switch
    business_db.expire_all()
    paused = await claim.beat(business_db, room_id, "agent-a", NOW)
    assert not paused.stay and not paused.speak
    await pi.close()


async def test_a_room_with_pi_off_or_a_workspace_without_speech_is_never_claimed(
    api, business_db, provider
):
    pi, mid = await room_with_pi(api, business_db, "369400007")
    assert [
        r for r in await claim.claim(business_db, "agent-a", NOW) if str(r.meeting_id) == mid
    ] == []
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await switch(api, meeting_room_speak=False)
    business_db.expire_all()
    assert [
        r for r in await claim.claim(business_db, "agent-a", NOW) if str(r.meeting_id) == mid
    ] == []
    await pi.close()


async def test_releasing_frees_the_room_for_a_restarted_agent(api, business_db, provider):
    pi, mid = await room_with_pi(api, business_db, "369400008")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    room = await the_room(business_db, mid)
    await claim.release(business_db, room.id, "agent-b")  # not the holder: nothing happens
    assert room.agent_id == "agent-a"
    await claim.release(business_db, room.id, "agent-a")
    assert room.agent_id is None
    await pi.close()


async def test_pi_lines_join_the_final_transcript_in_the_order_they_were_said(
    api, business_db, monkeypatch
):
    from datetime import timedelta

    from test_pi_meeting_rooms import lines
    from test_pi_meeting_rooms_stt import BEGIN, Manager, end_it, run, said
    from test_pi_meeting_rooms_stt import Provider as SttProvider

    from app.modules.pi_meetings import room_agent_lines as pilines
    from app.modules.pi_meetings.room_provider import RoomRecording

    stt = SttProvider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: stt)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    pi, conv, scope = await workspace(api, business_db, "369400009")
    await switch(api, meeting_room_speak=True, meeting_room_audio=True)
    mid = (await open_room(api)).json()["meeting"]["id"]
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    room = await the_room(business_db, mid)
    orders = await claim.beat(business_db, room.id, "agent-a", NOW)
    began = orders.started_at
    assert await pilines.store_pi_line(
        business_db,
        orders,
        "Hi, I'm pi, an AI assistant from Workzap. Which part is slowest?",
        now=began + timedelta(seconds=6),
    )
    assert await pilines.store_pi_line(
        business_db, orders, "Call me on 0300 1234567?", now=began + timedelta(seconds=10)
    )
    await business_db.commit()

    stt.files = [RoomRecording(staff, "https://cdn/staff", BEGIN)]
    stt.bytes = {"https://cdn/staff": b"S"}
    manager = Manager()
    manager.said = {b"S": said(("First.", 0.5), ("Second", 5.0), ("line.", 5.4), ("Third.", 12.0))}
    room = await end_it(api, business_db, mid)
    out, meeting = await run(business_db, room, stt, manager)
    assert out == "done"
    got = await lines(business_db, mid)
    assert [(label, o) for o, label, _ in got] == [
        ("Staff", 0),
        ("pi (AI)", 1),
        ("Staff", 2),
        ("pi (AI)", 3),
        ("Staff", 4),
    ]
    assert "1234567" not in got[3][2]  # nothing pi says carries a phone number either
    assert got[1][2].startswith("Hi, I'm pi, an AI")
    await pi.close()


async def test_what_pi_did_survives_an_agent_restart(api, business_db, provider):
    """The speech cap, the AI disclosure and an emergency stop are kept in the room, so a restarted
    agent does not introduce itself again, start the cap afresh or speak after an emergency."""
    pi, mid = await room_with_pi(api, business_db, "369400020")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    room = await the_room(business_db, mid)
    spoke = NOW + timedelta(seconds=30)
    assert (
        await claim.save_state(
            business_db,
            room.id,
            "agent-b",
            spoken=3,
            disclosed=True,
            halted=False,
            last_spoke_at=spoke,
        )
        is False
    )  # not the holder: nothing is kept
    notes = {"facts": ["bakery, four people, one oven"], "language": "ur", "ideas": 1, "recent": []}
    assert await claim.save_state(
        business_db,
        room.id,
        "agent-a",
        spoken=3,
        disclosed=True,
        halted=False,
        last_spoke_at=spoke,
        notes=notes,
    )
    await business_db.commit()
    # a smaller or later-reset value never lowers what was kept; a halt is never undone
    await claim.save_state(
        business_db, room.id, "agent-a", spoken=1, disclosed=False, halted=True, last_spoke_at=None
    )
    await business_db.commit()
    await claim.release(business_db, room.id, "agent-a")
    await claim.claim(business_db, "agent-c", NOW + timedelta(minutes=2))
    orders = await claim.beat(business_db, room.id, "agent-c", NOW + timedelta(minutes=2))
    assert orders is not None
    assert (orders.spoken, orders.disclosed, orders.halted) == (3, True, True)
    assert orders.last_spoke_at == spoke
    assert orders.notes == notes  # what pi noted comes back after a restart
    await pi.close()


async def test_pi_lines_are_timed_from_the_rooms_real_start_not_from_when_it_was_opened(
    api, business_db, provider
):
    """Found live (test 16): the agent read its orders before the call began, so pi's lines were
    timed from when the room was OPENED and sorted minutes after everything the customer said."""
    from sqlalchemy import select

    from app.modules.pi_meetings import room_agent_lines as pilines
    from app.modules.pi_meetings.models import PiMeetingSegment

    pi, mid = await room_with_pi(api, business_db, "369400010")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    room = await the_room(business_db, mid)
    orders = await claim.beat(business_db, room.id, "agent-a", NOW)  # read before the call began
    started = orders.started_at + timedelta(minutes=10)  # the call really began 10 minutes later
    room.started_at = started
    await business_db.commit()
    assert await pilines.store_pi_line(
        business_db, orders, "Hi, I'm pi, an AI from Workzap.", now=started + timedelta(seconds=30)
    )
    await business_db.commit()
    seg = await business_db.scalar(select(PiMeetingSegment).order_by(PiMeetingSegment.ordinal))
    assert 29_000 <= seg.end_ms <= 31_000  # 30 s into the call, not 10 minutes and 30 s
    await pi.close()


async def test_the_agents_orders_carry_the_meetings_agent_for_its_character(
    api, business_db, provider
):
    pi, mid = await room_with_pi(api, business_db, "369400011")
    await api.post(f"{BASE}/{mid}/room/pi", json={"mode": "speak"})
    await claim.claim(business_db, "agent-a", NOW)
    await business_db.commit()
    room = await the_room(business_db, mid)
    orders = await claim.beat(business_db, room.id, "agent-a", NOW)
    assert orders.agent_key == "pi" and orders.persona == ""  # the default personality
    assert (
        await api.put(f"{BASE}/{mid}/agent", json={"agent_key": "sales_coach"})
    ).status_code == 200
    again = await claim.beat(business_db, room.id, "agent-a", NOW)
    assert again.agent_key == "sales_coach" and "Sales Coach" in again.persona
    await pi.close()
