"""Saved recordings: audio goes with each transcribed part, video as its own parts, both land in the
workspace's own storage (replaced here by a dictionary), play back through short-lived links, and
leave with the meeting. A storage problem never costs the transcript."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_meeting_data import workspace
from test_pi_meeting_recording_flow import WEBM, Speech
from test_pi_meeting_routes import BASE, body, switch_on

from app.modules.pi_meetings import erase, media, media_routes, recording_routes
from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia, PiMeetingSegment

pytestmark = pytest.mark.integration


class Bucket:
    """The workspace's storage, in memory."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.broken = False

    async def put(self, session, scope, request, key, data, mime):
        if self.broken:
            raise media.StorageFailed("DOWN")
        self.objects[key] = data

    async def sign(self, session, scope, request, keys):
        if self.broken:
            raise media.StorageFailed("DOWN")
        return [f"https://bucket.test/{key}?expires=3600" for key in keys]

    async def remove(self, session, scope, request, keys):
        if self.broken:
            raise media.StorageFailed("DOWN")
        for key in keys:
            self.objects.pop(key, None)


@pytest.fixture
def bucket(monkeypatch):
    store = Bucket()
    monkeypatch.setattr(media, "_put", store.put)
    monkeypatch.setattr(media, "_sign", store.sign)
    monkeypatch.setattr(media, "_remove", store.remove)

    async def connected(session, scope):
        return True  # a storage bucket is connected in these tests

    monkeypatch.setattr(media, "has_bucket", connected)
    monkeypatch.setattr(recording_routes, "build_llm_manager", lambda *a, **k: Speech())
    return store


def audio_part(api, mid, index, **extra):
    return api.post(
        f"{BASE}/{mid}/recording/parts",
        data={
            "index": str(index),
            "offset_ms": str(index * 240_000),
            "duration_ms": "60000",
            **extra,
        },
        files={"file": ("part.webm", WEBM, "audio/webm;codecs=opus")},
    )


def video_part(api, mid, index, mime="video/webm", data=WEBM):
    return api.post(
        f"{BASE}/{mid}/recording/media/video/{index}",
        data={"offset_ms": str(index * 120_000), "duration_ms": "120000"},
        files={"file": ("part.webm", data, mime)},
    )


async def test_audio_and_video_are_saved_and_play_back(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366200001")
    customer_id = conv.customer_id  # read now: expire_all() below would make it a lazy load
    await switch_on(api)
    mid = (await api.post(BASE, json=body(customer_id=str(customer_id)))).json()["id"]

    heard = await audio_part(api, mid, 0, keep="true")
    assert heard.status_code == 200 and heard.json()["saved"] is True
    for index in (0, 1):
        saved = await video_part(api, mid, index)
        assert saved.status_code == 200, saved.text
        assert saved.json()["kind"] == "video" and saved.json()["bytes"] == len(WEBM)
    assert len(bucket.objects) == 3
    assert all(f"/e/{scope.environment_id}/meetings/{mid}/" in key for key in bucket.objects)

    detail = (await api.get(f"{BASE}/{mid}")).json()
    assert detail["has_recording"] is True
    until = datetime.fromisoformat(detail["retention_until"])
    assert timedelta(days=360) < until - datetime.now(UTC) <= timedelta(days=366)  # kept a year

    played = (await api.get(f"{BASE}/{mid}/recording")).json()
    assert [(p["kind"], p["index"]) for p in played["parts"]] == [
        ("audio", 0),
        ("video", 0),
        ("video", 1),
    ]
    assert all(p["url"].startswith("https://bucket.test/") for p in played["parts"])

    # a part sent again replaces its row and its object: nothing is doubled
    await video_part(api, mid, 1)
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingMedia)) == 3
    assert len(bucket.objects) == 3

    # erasing the customer reports every key so none is forgotten
    keys = await erase.recording_keys(business_db, scope, customer_id)
    assert sorted(keys) == sorted(bucket.objects)
    await pi.close()


async def test_a_storage_problem_never_costs_the_transcript(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366200002")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    bucket.broken = True
    heard = await audio_part(api, mid, 0, keep="true")
    assert heard.status_code == 200
    assert heard.json()["segments"] == 2 and heard.json()["saved"] is False
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingSegment)) == 2
    refused = await video_part(api, mid, 0)
    assert refused.status_code == 502
    assert refused.json()["error"]["code"] == "MEETING_MEDIA_STORE_FAILED"
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingMedia)) == 0
    assert (await api.get(f"{BASE}/{mid}")).json()["has_recording"] is False
    await pi.close()


async def test_only_real_recordings_are_saved(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366200003")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    for mime, data in (
        ("video/webm", b"not a recording at all"),  # the bytes do not match the type
        ("application/pdf", WEBM),  # a type that is not a recording
        ("video/webm", b""),
    ):
        refused = await video_part(api, mid, 0, mime=mime, data=data)
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "MEETING_MEDIA_INVALID"
    assert bucket.objects == {}
    # the kind is part of the address: anything else is not a route
    assert (
        await api.post(f"{BASE}/{mid}/recording/media/other/0", files={"file": ("a", WEBM)})
    ).status_code == 422
    await pi.close()


async def test_deleting_a_meeting_removes_its_recording_first(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366200004")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await audio_part(api, mid, 0, keep="true")
    await video_part(api, mid, 0)
    assert len(bucket.objects) == 2

    bucket.broken = True  # the bucket cannot be reached: nothing is lost, nothing half-deleted
    stuck = await api.delete(f"{BASE}/{mid}")
    assert (
        stuck.status_code == 409 and stuck.json()["error"]["code"] == "RECORDING_DELETE_UNAVAILABLE"
    )
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingMedia)) == 2
    assert await business_db.scalar(select(func.count()).select_from(PiMeeting)) == 1

    bucket.broken = False
    gone = await api.delete(f"{BASE}/{mid}")
    assert gone.status_code == 200 and gone.json() == {"deleted": True}
    assert bucket.objects == {}  # the files left the storage
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingMedia)) == 0
    assert await business_db.scalar(select(func.count()).select_from(PiMeeting)) == 0
    await pi.close()


async def test_another_workspace_cannot_play_or_add_to_a_recording(api, business_db, bucket):
    first, _, _ = await workspace(api, business_db, "366200005")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await video_part(api, mid, 0)
    second, _, _ = await workspace(api, business_db, "366200006")
    await switch_on(api)
    assert (await api.get(f"{BASE}/{mid}/recording")).status_code == 404
    assert (await video_part(api, mid, 1)).status_code == 404
    await first.close()
    await second.close()


async def test_a_closed_meeting_takes_no_more_video(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366200007")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await audio_part(api, mid, 0)
    done = await api.post(
        f"{BASE}/{mid}/recording/complete", json={"duration_ms": 60_000, "parts": 1}
    )
    assert done.status_code == 200
    late = await video_part(api, mid, 0)
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_CLOSED"
    assert SimpleNamespace(**media_routes.ALLOWED)  # the allowed types are published, not implied
    await pi.close()
