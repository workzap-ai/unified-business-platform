"""Meeting links: staff make a link, other people open it without signing in and join with their own
consent. The token is the only key and is stored as a hash; a link works only while it is open,
unexpired, for an open meeting, within its guest limit, and with the workspace flag on."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body

from app.ai.errors import GatewayUnavailable
from app.modules.pi_meetings import guest_routes, recording_routes
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingGuest,
    PiMeetingInvite,
    PiMeetingParticipant,
)

pytestmark = pytest.mark.integration
JOIN = "/api/v1/public/meeting-join"


async def switch_on(api, guests=True):
    brain = {"meeting_intel": True, "meeting_guests": guests}
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain", "brain": brain}}
    )
    assert response.status_code == 200, response.text


async def made(api, **fields):
    mid = (await api.post(BASE, json=body())).json()["id"]
    invite = await api.post(f"{BASE}/{mid}/invite", json=fields)
    assert invite.status_code == 201, invite.text
    return mid, invite.json()["token"]


async def count(db, model):
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(model))


async def test_the_link_is_off_until_the_workspace_turns_it_on(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366600001")
    await switch_on(api, guests=False)
    mid = (await api.post(BASE, json=body())).json()["id"]
    off = await api.post(f"{BASE}/{mid}/invite", json={})
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_GUESTS_OFF"
    assert await count(business_db, PiMeetingInvite) == 0
    await pi.close()


async def test_a_guest_looks_and_joins_with_consent_and_only_a_hash_is_stored(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366600002")
    await switch_on(api)
    mid, token = await made(api)

    seen = await api.get(f"{JOIN}/{token}")
    assert seen.status_code == 200 and set(seen.json()) == {"title", "pi_voice"}
    assert seen.json()["pi_voice"] is False  # pi does not talk unless a person turned it on

    no = await api.post(f"{JOIN}/{token}", json={"name": "Ali", "consent": False})
    assert no.status_code == 422 and no.json()["error"]["code"] == "MEETING_CONSENT_REQUIRED"
    assert await count(business_db, PiMeetingGuest) == 0

    joined = await api.post(f"{JOIN}/{token}", json={"name": "Ali", "consent": True})
    assert joined.status_code == 201
    out = joined.json()
    assert out["slot"] == 1 and out["label"] == "Ali" and out["guest_token"]
    anon = await api.post(f"{JOIN}/{token}", json={"consent": True})
    assert anon.json()["label"] == "Participant 2" and anon.json()["slot"] == 2
    same = await api.post(f"{JOIN}/{token}", json={"name": "Ali", "consent": True})
    assert same.json()["label"] == "Ali (3)"  # speaker labels are unique in a meeting

    business_db.expire_all()
    invite = await business_db.scalar(select(PiMeetingInvite))
    guest = await business_db.scalar(select(PiMeetingGuest).where(PiMeetingGuest.slot == 1))
    assert invite.token_hash != token and len(invite.token_hash) == 64
    assert guest.token_hash != out["guest_token"] and guest.consent_at is not None
    speaker = await business_db.scalar(
        select(PiMeetingParticipant).where(PiMeetingParticipant.label == "Ali")
    )
    assert speaker.role == "unknown"  # never assumed to be the customer
    await pi.close()


async def test_a_name_is_redacted_and_a_bad_or_unknown_token_is_just_not_found(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366600003")
    await switch_on(api)
    _, token = await made(api)
    joined = await api.post(f"{JOIN}/{token}", json={"name": "0300 1234567", "consent": True})
    assert joined.status_code == 201 and "1234567" not in joined.json()["label"]
    assert (await api.get(f"{JOIN}/{'x' * 43}")).status_code == 404
    assert (await api.get(f"{JOIN}/short")).status_code == 422
    assert (await api.post(f"{JOIN}/{'y' * 43}", json={"consent": True})).status_code == 404
    await pi.close()


async def test_expired_revoked_closed_and_flag_off_links_stop_working(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366600004")
    await switch_on(api)
    mid, token = await made(api)
    assert (await api.get(f"{JOIN}/{token}")).status_code == 200

    await business_db.execute(
        update(PiMeetingInvite).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await business_db.commit()
    assert (await api.get(f"{JOIN}/{token}")).status_code == 404  # expired

    mid2, token = await made(api)  # a new link for another meeting
    assert (await api.get(f"{JOIN}/{token}")).status_code == 200
    revoked = await api.delete(f"{BASE}/{mid2}/invite")
    assert revoked.status_code == 200 and revoked.json() == {"closed": 1}
    assert (await api.get(f"{JOIN}/{token}")).status_code == 404

    _, token = await made(api)
    await business_db.execute(update(PiMeeting).values(status="analysing"))
    await business_db.commit()
    assert (await api.get(f"{JOIN}/{token}")).status_code == 404  # the meeting is closed
    refused = await api.post(f"{BASE}/{mid}/invite", json={})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "MEETING_NOT_OPEN"

    await business_db.execute(update(PiMeeting).values(status="created"))
    await business_db.commit()
    assert (await api.get(f"{JOIN}/{token}")).status_code == 200
    await switch_on(api, guests=False)
    assert (await api.get(f"{JOIN}/{token}")).status_code == 404  # switched off again
    await pi.close()


async def test_a_link_admits_only_as_many_people_as_it_was_made_for(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366600005")
    await switch_on(api)
    mid, token = await made(api, max_guests=2)
    assert (await api.post(f"{JOIN}/{token}", json={"consent": True})).status_code == 201
    assert (await api.post(f"{JOIN}/{token}", json={"consent": True})).status_code == 201
    full = await api.post(f"{JOIN}/{token}", json={"consent": True})
    assert full.status_code == 409 and full.json()["error"]["code"] == "MEETING_FULL"
    assert await count(business_db, PiMeetingGuest) == 2

    status = (await api.get(f"{BASE}/{mid}/invite")).json()
    assert status["open"] is True and [g["slot"] for g in status["guests"]] == [1, 2]
    guest_id = status["guests"][0]["id"]
    assert (await api.delete(f"{BASE}/{mid}/guests/{guest_id}")).json() == {"removed": True}
    assert (await api.get(f"{BASE}/{mid}/invite")).json()["guests"][0]["removed"] is True
    await pi.close()


async def test_a_new_link_closes_the_old_one_and_another_workspace_sees_nothing(api, business_db):
    first, _, _ = await workspace(api, business_db, "366600006")
    await switch_on(api)
    mid, old = await made(api)
    newer = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    assert (await api.get(f"{JOIN}/{old}")).status_code == 404
    assert (await api.get(f"{JOIN}/{newer}")).status_code == 200

    second, _, _ = await workspace(api, business_db, "366600007")
    await switch_on(api)
    assert (await api.get(f"{BASE}/{mid}/invite")).status_code == 404
    assert (await api.post(f"{BASE}/{mid}/invite", json={})).status_code == 404
    assert (await api.delete(f"{BASE}/{mid}/invite")).status_code == 404
    await first.close()
    await second.close()


async def test_deleting_the_meeting_removes_its_links_and_guests(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366600008")
    await switch_on(api)
    mid, token = await made(api)
    await api.post(f"{JOIN}/{token}", json={"name": "Sara", "consent": True})
    assert await count(business_db, PiMeetingGuest) == 1
    assert (await api.delete(f"{BASE}/{mid}")).status_code == 200
    assert await count(business_db, PiMeetingGuest) == 0
    assert await count(business_db, PiMeetingInvite) == 0
    assert await count(business_db, PiMeetingParticipant) == 0
    await pi.close()


def test_tokens_are_long_random_and_hashed():
    assert len({guest_routes.new_token() for _ in range(50)}) == 50
    token = guest_routes.new_token()
    assert len(token) >= 40 and guest_routes.digest(token) != token
    assert len(guest_routes.digest(token)) == 64


# ---- guests send their own audio

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
MINUTE = 60_000
GUEST = f"{JOIN}/guest"


class Voice:
    """Speech-to-text that answers with what the test says each caller said."""

    def __init__(self):
        self.text = "We need a list by Friday."
        self.fail = False

    async def transcribe(self, scope, audio, mime, **kw):
        if self.fail:
            raise GatewayUnavailable()
        return SimpleNamespace(text=self.text, language="en")


@pytest.fixture
def voice(monkeypatch):
    v = Voice()
    monkeypatch.setattr(guest_routes, "build_llm_manager", lambda *a, **k: v)
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: v)
    monkeypatch.setattr(guest_routes, "GUEST_MIN_GAP_S", 0)  # the gap has its own test
    return v


async def at(db, spoken_ms):
    """Put the meeting's clock where a one-minute FIRST part sent now began at `spoken_ms`."""
    started = datetime.now(UTC) - timedelta(milliseconds=spoken_ms + MINUTE)
    await db.execute(update(PiMeeting).values(recording_started_at=started))
    await db.commit()


def say(api, token, seq=0, mime="audio/webm;codecs=opus", data=WEBM, duration="60000"):
    return api.post(
        f"{GUEST}/parts",
        headers={"X-Guest-Token": token},
        data={"seq": str(seq), "duration_ms": duration},
        files={"file": ("part.webm", data, mime)},
    )


def host(api, mid, index, offset_ms):
    return api.post(
        f"{BASE}/{mid}/recording/parts",
        data={"index": str(index), "offset_ms": str(offset_ms), "duration_ms": "60000"},
        files={"file": ("part.webm", WEBM, "audio/webm;codecs=opus")},
    )


async def joined(api, token, name):
    response = await api.post(f"{JOIN}/{token}", json={"name": name, "consent": True})
    return response.json()["guest_token"]


async def lines_of(api, mid):
    segments = (await api.get(f"{BASE}/{mid}")).json()["segments"]
    return [(s["speaker"], s["text"]) for s in segments]


async def test_guest_lines_sort_with_the_hosts_in_the_order_they_were_spoken(
    api, business_db, voice
):
    pi, conv, scope = await workspace(api, business_db, "366600010")
    await switch_on(api)
    mid, invite = await made(api)
    ali, sara = await joined(api, invite, "Ali"), await joined(api, invite, "Sara")

    voice.text = "Host one."
    assert (await host(api, mid, 0, 0)).status_code == 200  # the first minute
    voice.text = "Ali speaks in minute one."
    await at(business_db, 70_000)
    assert (await say(api, ali)).json() == {"segments": 1}
    voice.text = "Sara speaks in minute one too."
    await at(business_db, 75_000)  # each guest's first part fixes where their minutes sit
    assert (await say(api, sara)).status_code == 200
    voice.text = "Host two."
    assert (await host(api, mid, 1, MINUTE)).status_code == 200  # the second minute
    voice.text = "Ali speaks in minute five."
    assert (await say(api, ali, seq=4)).status_code == 200  # four minutes after Ali's first part

    detail = (await api.get(f"{BASE}/{mid}")).json()
    assert [(s["speaker"], s["text"]) for s in detail["segments"]] == [
        ("Speaker 1", "Host one."),
        ("Speaker 1", "Host two."),  # the host's second minute, then the guests of that minute
        ("Ali", "Ali speaks in minute one."),
        ("Sara", "Sara speaks in minute one too."),
        ("Ali", "Ali speaks in minute five."),
    ]
    assert detail["status"] == "transcribing"
    await pi.close()


async def test_guests_are_in_the_order_of_their_minutes(api, business_db, voice):
    pi, conv, scope = await workspace(api, business_db, "366600016")
    await switch_on(api)
    mid, invite = await made(api)
    ali, sara = await joined(api, invite, "Ali"), await joined(api, invite, "Sara")
    voice.text = "Ali in the fourth minute."
    await at(business_db, 190_000)
    await say(api, ali)  # slot 1, minute 3
    voice.text = "Sara in the first minute."
    await at(business_db, 5_000)
    await say(api, sara)  # slot 2, minute 0: earlier in time, so earlier in the transcript
    assert await lines_of(api, mid) == [
        ("Sara", "Sara in the first minute."),
        ("Ali", "Ali in the fourth minute."),
    ]
    await pi.close()


async def test_the_server_clock_places_a_guest_and_a_retry_changes_nothing(api, business_db, voice):
    pi, conv, scope = await workspace(api, business_db, "366600015")
    await switch_on(api)
    mid, invite = await made(api)
    ali = await joined(api, invite, "Ali")
    # the host's recorder starts the meeting clock once; a second call keeps the first time
    first = (await api.post(f"{BASE}/{mid}/recording/start")).json()["recording_started_at"]
    assert first and (await api.post(f"{BASE}/{mid}/recording/start")).json() == {
        "recording_started_at": first
    }
    await at(business_db, 130_000)  # the first part began two minutes and ten seconds in
    voice.text = "Placed by the server."
    assert (await say(api, ali)).status_code == 200
    voice.text = "A minute later."
    assert (await say(api, ali, seq=1)).status_code == 200
    starts = [s["start_ms"] for s in (await api.get(f"{BASE}/{mid}")).json()["segments"]]
    assert 129_000 <= starts[0] <= 131_000 and 189_000 <= starts[1] <= 191_000

    # a retry of a part that already went through (the answer was lost) changes nothing
    voice.text = "A retry must not rewrite this."
    again = await say(api, ali, seq=1)
    assert again.status_code == 200 and again.json() == {"segments": 0, "again": True}
    assert len(await lines_of(api, mid)) == 2

    # with no host clock yet the first guest part starts it
    mid2, invite2 = await made(api)
    bea = await joined(api, invite2, "Bea")
    assert (await say(api, bea)).status_code == 200
    business_db.expire_all()
    started = await business_db.scalar(
        select(PiMeeting.recording_started_at).where(PiMeeting.id == UUID(mid2))
    )
    assert started is not None
    await pi.close()


async def test_a_part_replaces_only_itself_and_the_host_resend_keeps_guest_lines(
    api, business_db, voice
):
    pi, conv, scope = await workspace(api, business_db, "366600011")
    await switch_on(api)
    mid, invite = await made(api)
    ali, sara = await joined(api, invite, "Ali"), await joined(api, invite, "Sara")
    await at(business_db, 10_000)
    voice.text = "Ali first."
    await say(api, ali)
    voice.text = "Sara first."
    await say(api, sara)  # the same minute, another person: not the same lines
    voice.text = "Host."
    await host(api, mid, 0, 0)
    voice.text = "Host replaced."
    await host(api, mid, 0, 0)  # the host resend must not remove the guests lines

    texts = sorted(t for _, t in await lines_of(api, mid))
    assert texts == ["Ali first.", "Host replaced.", "Sara first."]
    await pi.close()


async def test_a_guest_is_refused_everything_but_their_own_audio(api, business_db, voice):
    pi, conv, scope = await workspace(api, business_db, "366600012")
    await switch_on(api)
    mid, invite = await made(api)
    ali = await joined(api, invite, "Ali")

    assert (await say(api, "z" * 43)).status_code == 404  # unknown token
    assert (await say(api, invite)).status_code == 404  # an invite token is not a guest token
    assert (await say(api, "short")).status_code == 422  # not even shaped like a token
    assert (await say(api, ali, mime="text/plain")).status_code == 422
    assert (await say(api, ali, data=b"")).status_code == 422
    assert (await say(api, ali, duration="999999")).status_code == 422
    assert (await say(api, ali, duration="0")).status_code == 422
    assert (await say(api, ali, seq=10**6)).status_code == 422
    assert (await say(api, ali, seq=50)).status_code == 422  # far ahead of the minutes they were in
    no_seq = await api.post(
        f"{GUEST}/parts",
        headers={"X-Guest-Token": ali},
        data={"duration_ms": "60000"},
        files={"file": ("p.webm", WEBM, "audio/webm")},
    )
    assert no_seq.status_code == 422
    # size: over the audio cap but under the body cap, and over the body cap (refused unread)
    assert (await say(api, ali, data=WEBM * 20_000)).status_code == 413
    assert (await say(api, ali, data=WEBM * 40_000)).status_code == 413
    await at(business_db, 10**9)  # a time no meeting reaches
    assert (await say(api, ali)).status_code == 422
    await at(business_db, 0)
    voice.fail = True
    down = await say(api, ali)
    assert down.status_code == 502 and down.json()["error"]["code"] == "MEETING_TRANSCRIBE_FAILED"
    assert (await api.get(f"{BASE}/{mid}")).json()["status"] == "created"  # a guest cannot fail it
    assert (await api.get(f"{GUEST}/parts")).status_code in (404, 405)  # nothing to read
    await pi.close()


async def test_parts_cannot_come_faster_than_a_person_talks(api, business_db, voice, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366600017")
    await switch_on(api)
    mid, invite = await made(api)
    ali = await joined(api, invite, "Ali")
    monkeypatch.setattr(guest_routes, "GUEST_MIN_GAP_S", 20)  # the real rule
    assert (await say(api, ali)).status_code == 200
    soon = await say(api, ali, seq=1)
    assert soon.status_code == 429 and soon.json()["error"]["code"] == "MEETING_PART_TOO_SOON"
    # after the gap it goes through
    await business_db.execute(
        update(PiMeetingGuest).values(last_part_at=datetime.now(UTC) - timedelta(seconds=25))
    )
    await business_db.commit()
    assert (await say(api, ali, seq=1)).status_code == 200
    await pi.close()


async def test_a_guest_token_runs_out_and_leaving_stops_it(api, business_db, voice):
    pi, conv, scope = await workspace(api, business_db, "366600018")
    await switch_on(api)
    mid, invite = await made(api)
    old, leaver = await joined(api, invite, "Old"), await joined(api, invite, "Leaver")
    assert (await say(api, old)).status_code == 200
    await business_db.execute(
        update(PiMeetingGuest)
        .where(PiMeetingGuest.slot == 1)
        .values(consent_at=datetime.now(UTC) - timedelta(hours=13))
    )
    await business_db.commit()
    assert (
        await say(api, old, seq=1)
    ).status_code == 404  # a guest token is good for hours, not days

    left = await api.post(f"{GUEST}/leave", headers={"X-Guest-Token": leaver})
    assert left.status_code == 200 and left.json() == {"left": True}
    assert (await say(api, leaver)).status_code == 404
    assert (
        await api.post(f"{GUEST}/leave", headers={"X-Guest-Token": "q" * 43})
    ).status_code == 404
    await pi.close()


async def test_a_guest_cannot_take_the_hosts_name_or_steer_the_language(api, business_db, voice):
    pi, conv, scope = await workspace(api, business_db, "366600019")
    await switch_on(api)
    mid, invite = await made(api)
    sneaky = await api.post(f"{JOIN}/{invite}", json={"name": "speaker 1", "consent": True})
    assert sneaky.status_code == 201 and sneaky.json()["label"].lower() != "speaker 1"
    twin_a = await api.post(f"{JOIN}/{invite}", json={"name": "Ali", "consent": True})
    twin_b = await api.post(f"{JOIN}/{invite}", json={"name": "ali", "consent": True})
    assert twin_a.json()["label"] != twin_b.json()["label"]  # never a clash on the unique label
    # the host's first part still becomes "Speaker 1", not the guest
    voice.text = "Host words."
    assert (await host(api, mid, 0, 0)).status_code == 200
    assert ("Speaker 1", "Host words.") in await lines_of(api, mid)
    # a guest's detected language is not written to the meeting
    assert (await say(api, sneaky.json()["guest_token"])).status_code == 200
    business_db.expire_all()
    assert (await business_db.scalar(select(PiMeeting.language))) in ("", "en")
    await pi.close()


async def test_lines_the_findings_cite_are_never_rewritten_by_a_late_guest_part(
    api, business_db, monkeypatch
):
    from test_pi_meeting_recording_flow import Mapper, analyse_part

    pi, conv, scope = await workspace(api, business_db, "366600020")
    await switch_on(api)
    mapper = Mapper()
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: mapper)
    monkeypatch.setattr(guest_routes, "build_llm_manager", lambda *a, **k: mapper)
    monkeypatch.setattr(guest_routes, "GUEST_MIN_GAP_S", 0)
    mid, invite = await made(api)
    ali = await joined(api, invite, "Ali")
    assert (await host(api, mid, 0, 0)).status_code == 200
    assert (await analyse_part(api, mid, 0)).status_code == 200  # the findings now exist
    await at(business_db, 10_000)
    assert (await say(api, ali)).status_code == 200  # a new place in the window: fine
    # a different part landing on the same place as an analysed one is refused, not rewritten
    await business_db.execute(update(PiMeetingGuest).values(last_seq=None, last_part_at=None))
    await business_db.commit()
    clash = await say(api, ali)
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "MEETING_PART_ANALYSED"
    await pi.close()


async def test_removing_a_guest_or_closing_the_link_or_the_meeting_stops_their_audio(
    api, business_db, voice
):
    pi, conv, scope = await workspace(api, business_db, "366600013")
    await switch_on(api)
    mid, invite = await made(api)
    ali = await joined(api, invite, "Ali")
    sara = await joined(api, invite, "Sara")
    omar = await joined(api, invite, "Omar")
    for token in (ali, sara, omar):
        assert (await say(api, token)).status_code == 200

    status = (await api.get(f"{BASE}/{mid}/invite")).json()
    ali_id = next(g["id"] for g in status["guests"] if g["label"] == "Ali")
    await api.delete(f"{BASE}/{mid}/guests/{ali_id}")
    assert (await say(api, ali, seq=1)).status_code == 404  # removed
    assert (await say(api, sara, seq=1)).status_code == 200  # the others carry on

    # an expired link only stops new people: someone already in keeps going
    await business_db.execute(
        update(PiMeetingInvite).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await business_db.commit()
    assert (await say(api, sara, seq=2)).status_code == 200
    assert (await api.post(f"{JOIN}/{invite}", json={"consent": True})).status_code == 404

    await api.delete(f"{BASE}/{mid}/invite")  # revoked: everyone stops
    assert (await say(api, sara, seq=3)).status_code == 404
    assert (await say(api, omar, seq=1)).status_code == 404

    await business_db.execute(update(PiMeeting).values(status="analysing"))
    await business_db.commit()
    assert (await say(api, omar, seq=1)).status_code == 404
    await pi.close()


async def test_a_guests_words_are_redacted_and_the_audio_is_not_kept(api, business_db, voice):
    from app.modules.pi_meetings.models import PiMeetingMedia

    pi, conv, scope = await workspace(api, business_db, "366600014")
    await switch_on(api)
    mid, invite = await made(api)
    ali = await joined(api, invite, "Ali")
    voice.text = "My card is 4111 1111 1111 1111 and it keeps failing."
    assert (await say(api, ali)).status_code == 200
    words = " ".join(t for _, t in await lines_of(api, mid))
    assert "4111" not in words and "failing" in words
    assert await count(business_db, PiMeetingMedia) == 0
    await pi.close()


def test_guest_numbers_stay_inside_their_slice_of_the_window():
    seen = set()
    for slot in range(1, 21):
        for within in (0, 5, 59_999):  # anywhere inside the first one-minute window
            base = guest_routes.guest_base(within, slot)
            assert 500 <= base and base + guest_routes.GUEST_SEGMENTS <= 1000
        base = guest_routes.guest_base(5, slot)
        lines = set(range(base, base + guest_routes.GUEST_SEGMENTS))
        assert not lines & seen  # no two guests in a window ever share a line number
        seen |= lines
    # window first, then guest: any guest's first minute sorts before every guest's second
    assert max(guest_routes.guest_base(0, s) for s in range(1, 21)) < min(
        guest_routes.guest_base(60_000, s) for s in range(1, 21)
    )
    assert guest_routes.guest_base(60_000, 1) >= 1000  # the next window is the next thousand
    assert guest_routes.WINDOW_MS == 60_000 == guest_routes.GUEST_PART_MS
    assert guest_routes.guest_base(0, 21) is None and guest_routes.guest_base(0, 0) is None
    assert guest_routes.pack(["a", "b", "c", "d", "e", "f", "g"], 6) == ["a b", "c d", "e f", "g"]
