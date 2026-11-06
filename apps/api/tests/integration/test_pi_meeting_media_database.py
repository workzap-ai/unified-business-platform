"""Recordings without a storage bucket: the audio is kept in the database (capped per meeting),
played back through an authenticated route that supports byte ranges, removed with the meeting, and
video is refused with a clear message. No bucket is connected in these tests: nothing is faked."""

import pytest
from sqlalchemy import func, select
from test_pi_meeting_data import workspace
from test_pi_meeting_media_flow import agreed
from test_pi_meeting_recording_flow import WEBM, Speech
from test_pi_meeting_routes import BASE, switch_on

from app.modules.pi_meetings import erase, media, recording_routes
from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia, PiMeetingMediaData

pytestmark = pytest.mark.integration
AUDIO = WEBM + bytes(range(200))  # recognisable, and long enough to cut into ranges


@pytest.fixture(autouse=True)
def speech(monkeypatch):
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: Speech())


def audio_part(api, mid, index, data=AUDIO, keep="true"):
    return api.post(
        f"{BASE}/{mid}/recording/parts",
        data={
            "index": str(index),
            "offset_ms": str(index * 240_000),
            "duration_ms": "60000",
            "keep": keep,
        },
        files={"file": ("part.webm", data, "audio/webm;codecs=opus")},
    )


async def count(db, model):
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(model))


async def test_audio_is_kept_in_the_database_and_plays_back(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366300001")
    customer_id = conv.customer_id
    await switch_on(api)
    mid = await agreed(api, customer_id=str(customer_id))

    saved = await audio_part(api, mid, 0)
    assert saved.status_code == 200 and saved.json()["saved"] is True
    assert (await audio_part(api, mid, 0)).json()["saved"] is True  # again: replaced, not doubled
    assert await count(business_db, PiMeetingMedia) == 1
    assert await count(business_db, PiMeetingMediaData) == 1
    key = await business_db.scalar(select(PiMeetingMedia.key))
    assert key.startswith("db/")

    detail = (await api.get(f"{BASE}/{mid}")).json()
    assert detail["has_recording"] is True and detail["retention_until"]
    played = (await api.get(f"{BASE}/{mid}/recording")).json()
    [part] = played["parts"]
    assert part["kind"] == "audio" and part["url"].endswith("/recording/media/audio/0/file")
    assert part["url"].startswith("/api/v1/pi/meeting-intel/")

    whole = await api.get(f"{BASE}/{mid}/recording/media/audio/0/file")
    assert whole.status_code == 200 and whole.content == AUDIO
    assert whole.headers["accept-ranges"] == "bytes"
    ranged = await api.get(
        f"{BASE}/{mid}/recording/media/audio/0/file", headers={"Range": "bytes=10-19"}
    )
    assert ranged.status_code == 206 and ranged.content == AUDIO[10:20]
    assert ranged.headers["content-range"] == f"bytes 10-19/{len(AUDIO)}"
    tail = await api.get(
        f"{BASE}/{mid}/recording/media/audio/0/file", headers={"Range": "bytes=-5"}
    )
    assert tail.status_code == 206 and tail.content == AUDIO[-5:]
    past = await api.get(
        f"{BASE}/{mid}/recording/media/audio/0/file", headers={"Range": "bytes=9999-"}
    )
    assert past.status_code == 416 and past.headers["content-range"] == f"bytes */{len(AUDIO)}"

    # audio kept in the database has no object to delete: nothing to report to the storage step
    assert await erase.recording_keys(business_db, scope, customer_id) == []
    await pi.close()


async def test_video_needs_a_bucket_and_says_so(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366300002")
    await switch_on(api)
    mid = await agreed(api)
    refused = await api.post(
        f"{BASE}/{mid}/recording/media/video/0",
        data={"offset_ms": "0", "duration_ms": "60000"},
        files={"file": ("part.webm", WEBM, "video/webm")},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "MEETING_VIDEO_NEEDS_STORAGE"
    assert await count(business_db, PiMeetingMedia) == 0
    await pi.close()


async def test_one_meeting_cannot_fill_the_database(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366300003")
    await switch_on(api)
    monkeypatch.setattr(media, "DATABASE_AUDIO_CAP", len(AUDIO) * 2)
    mid = await agreed(api)
    assert (await audio_part(api, mid, 0)).json()["saved"] is True
    assert (await audio_part(api, mid, 1)).json()["saved"] is True
    full = await audio_part(api, mid, 2)
    # the words are safe; only the audio was not kept
    assert (
        full.status_code == 200 and full.json()["saved"] is False and full.json()["segments"] == 2
    )
    assert await count(business_db, PiMeetingMedia) == 2
    # a part already kept can still be replaced at the cap
    assert (await audio_part(api, mid, 1)).json()["saved"] is True
    await pi.close()


async def test_audio_declined_means_nothing_is_kept(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366300004")
    await switch_on(api)
    mid = await agreed(api)
    heard = await audio_part(api, mid, 0, keep="false")
    assert heard.status_code == 200 and heard.json()["saved"] is False
    assert await count(business_db, PiMeetingMedia) == 0
    assert (await api.get(f"{BASE}/{mid}")).json()["has_recording"] is False
    await pi.close()


async def test_deleting_the_meeting_removes_the_kept_audio(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366300005")
    await switch_on(api)
    mid = await agreed(api)
    await audio_part(api, mid, 0)
    assert await count(business_db, PiMeetingMediaData) == 1
    gone = await api.delete(f"{BASE}/{mid}")  # no bucket is needed: the audio is in the database
    assert gone.status_code == 200 and gone.json() == {"deleted": True}
    assert await count(business_db, PiMeetingMediaData) == 0
    assert await count(business_db, PiMeetingMedia) == 0
    assert await count(business_db, PiMeeting) == 0
    await pi.close()


async def test_another_workspace_cannot_hear_it(api, business_db):
    first, _, _ = await workspace(api, business_db, "366300006")
    await switch_on(api)
    mid = await agreed(api)
    await audio_part(api, mid, 0)
    second, _, _ = await workspace(api, business_db, "366300007")
    await switch_on(api)
    assert (await api.get(f"{BASE}/{mid}/recording/media/audio/0/file")).status_code == 404
    assert (await api.get(f"{BASE}/{mid}/recording")).status_code == 404
    await first.close()
    await second.close()
