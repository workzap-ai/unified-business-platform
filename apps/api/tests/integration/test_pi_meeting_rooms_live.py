"""The live view of a call: staff and guests poll it, guests never see tips, staff keep a note as a
draft finding, and the agent's feed saves each line to the room."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import Provider as BaseProvider
from test_pi_meeting_rooms import open_room, the_room
from test_pi_meeting_rooms_limits import enter, guest, switch
from test_pi_meeting_routes import BASE

from app.modules.pi_meetings import room_agent_claim, room_live, room_live_wire, room_routes
from app.modules.pi_meetings.models import PiMeetingInsight

pytestmark = pytest.mark.integration

GUEST_LIVE = "/api/v1/public/meeting-room/live"


@pytest.fixture
def provider(monkeypatch):
    p = BaseProvider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def started_room(api, db, phone, **flags):
    pi, conv, scope = await workspace(api, db, phone)
    await switch(api, meeting_room_speak=True, **flags)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(db, mid)
    live = room_live.empty()
    room_live.add_line(live, role="customer", name="Ayesha", text="mujhe order chahiye", lang="ur")
    room_live.set_translation(live, 1, "I need an order", "en")
    room_live.add_line(live, role="staff", name="Sam", text="Sure, what do you sell", lang="en")
    room_live.add_tip(live, "tip", "Ask which products they sell")
    room_live.add_tip(live, "note", "They need an order system", "requirement_explicit")
    room.live = live
    await db.commit()
    return pi, mid, room, scope


async def test_staff_poll_gets_lines_tips_and_only_what_changed(api, business_db, provider):
    pi, mid, room, scope = await started_room(
        api, business_db, "369700001", meeting_room_live=True, meeting_room_copilot=True
    )
    got = (await api.get(f"{BASE}/{mid}/room/live")).json()
    assert got["enabled"] == {"live": True, "copilot": True}
    assert [x["text"] for x in got["lines"]][0] == "mujhe order chahiye"
    assert got["lines"][0]["tr"] == "I need an order"
    assert [t["kind"] for t in got["tips"]] == ["tip", "note"]
    newer = (await api.get(f"{BASE}/{mid}/room/live", params={"after": got["seq"]})).json()
    assert newer["lines"] == [] and newer["tips"] == [] and newer["reset"] is False
    stale = (await api.get(f"{BASE}/{mid}/room/live", params={"after": got["seq"] + 99})).json()
    assert stale["reset"] is True
    await pi.close()


async def test_tips_are_hidden_when_the_copilot_flag_is_off(api, business_db, provider):
    pi, mid, room, scope = await started_room(api, business_db, "369700002", meeting_room_live=True)
    got = (await api.get(f"{BASE}/{mid}/room/live")).json()
    assert got["enabled"] == {"live": True, "copilot": False}
    assert got["lines"] and "tips" not in got
    await pi.close()


async def test_a_guest_gets_captions_with_translation_and_never_tips(api, business_db, provider):
    pi, mid, room, scope = await started_room(
        api, business_db, "369700003", meeting_room_live=True, meeting_room_copilot=True
    )
    token, _ = await guest(api, mid)
    assert (await enter(api, token)).status_code == 200
    got = await api.get(GUEST_LIVE, headers={"X-Guest-Token": token})
    assert got.status_code == 200
    body = got.json()
    assert body["lines"][0]["tr"] == "I need an order"
    assert "tips" not in body and body["enabled"] == {"live": True, "copilot": False}
    assert "Ask which products" not in got.text and "order system" not in got.text
    assert (await api.get(GUEST_LIVE, headers={"X-Guest-Token": "x" * 43})).status_code in (
        404,
        422,
    )
    assert (await api.get(GUEST_LIVE)).status_code == 422  # no token at all
    await pi.close()


async def test_keeping_a_note_makes_one_pending_draft_finding(api, business_db, provider):
    pi, mid, room, scope = await started_room(
        api, business_db, "369700004", meeting_room_live=True, meeting_room_copilot=True
    )
    url = f"{BASE}/{mid}/room/live/keep"
    note_n = next(t["n"] for t in room.live["tips"] if t["kind"] == "note")
    tip_n = next(t["n"] for t in room.live["tips"] if t["kind"] == "tip")
    first = await api.post(url, json={"note": note_n})
    assert first.status_code == 200 and first.json() == {"kept": True, "created": True}
    again = await api.post(url, json={"note": note_n})
    assert again.json() == {"kept": True, "created": False}
    business_db.expire_all()
    rows = (
        await business_db.scalars(
            select(PiMeetingInsight).where(PiMeetingInsight.text == "They need an order system")
        )
    ).all()
    assert len(rows) == 1
    assert (rows[0].kind, rows[0].basis, rows[0].review_status) == (
        "requirement_explicit",
        "inferred",
        "pending",
    )
    assert rows[0].segment_refs == [] and rows[0].owner_label == "" and rows[0].due_text == ""
    assert (await api.post(url, json={"note": tip_n})).status_code == 404  # a tip is not a note
    assert (await api.post(url, json={"note": 9999})).status_code == 404
    assert (await api.post(url, json={})).status_code == 422
    await pi.close()


async def test_the_agents_feed_saves_each_line_with_who_said_it(api, business_db, provider):
    pi, mid, room, scope = await started_room(
        api, business_db, "369700005", meeting_room_live=True, meeting_room_copilot=True
    )
    token, _ = await guest(api, mid)
    entered = (await enter(api, token)).json()
    await api.post(f"{BASE}/{mid}/room/token")
    staff_user = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]

    @asynccontextmanager
    async def sessions():
        yield business_db

    orders = room_agent_claim.Orders(
        room_id=room.id,
        meeting_id=room.meeting_id,
        started_at=None,
        call_id=room.call_id,
        scope=scope,
        speak=True,
        muted=False,
        intake=False,
        language="en",
        stay=True,
        live=True,
        copilot=True,
        live_state={},
    )

    class Manager:
        async def complete(self, scope, **kwargs):
            class Reply:
                text = "I need an online ordering system"

            return Reply()

        async def complete_structured(self, scope, schema, **kwargs):
            class Result:
                value = schema(tip="Ask how orders arrive today", note="", note_kind="")

            return Result()

    feed = room_live_wire.build_feed(orders, sessions, Manager(), lambda: {})
    assert feed is not None
    await feed.heard(entered["user_id"], "mujhe online order system chahiye abhi")
    await feed.heard(staff_user, "Sure, tell me how orders come in today")
    await feed.said("Could you tell me what you sell")
    await feed.settle()
    row = await the_room(business_db, mid)
    who = [(x["role"], x["name"]) for x in row.live["lines"]]
    assert who == [("customer", "Ayesha"), ("staff", "Staff"), ("pi", "pi")] or (
        who[0][0] == "customer" and who[1][0] == "staff" and who[2] == ("pi", "pi")
    )
    assert row.live["lines"][0]["tr"] == "I need an online ordering system"
    assert any(t["text"] == "Ask how orders arrive today" for t in row.live["tips"])
    assert (
        room_live_wire.build_feed(
            room_agent_claim.Orders(**{**orders.__dict__, "live": False, "copilot": False}),
            sessions,
            Manager(),
            lambda: {},
        )
        is None
    )
    await pi.close()


async def test_the_agent_reads_both_flags_from_the_workspace_and_defaults_to_off(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369700006")
    await switch(api, meeting_room_speak=True)
    assert await room_agent_claim.live_flags(business_db, scope) == (False, False)
    await switch(api, meeting_room_speak=True, meeting_room_live=True)
    assert await room_agent_claim.live_flags(business_db, scope) == (True, False)
    await switch(api, meeting_room_speak=True, meeting_room_copilot=True)
    assert await room_agent_claim.live_flags(business_db, scope) == (False, True)
    await pi.close()
