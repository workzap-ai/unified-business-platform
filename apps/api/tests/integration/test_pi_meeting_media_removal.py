"""Recordings are never orphaned: erasing a customer, deleting a meeting (even one whose
`recording_key` is empty) and replacing a part under a new key all remove the old object first, and
stop without changing anything when the storage cannot be reached."""

# ruff: noqa: F811  (the `bucket` fixture is imported, then named as a test argument)
import pytest
from sqlalchemy import func, select, update
from test_pi_meeting_data import workspace
from test_pi_meeting_media_flow import agreed, audio_part, bucket, video_part  # noqa: F401
from test_pi_meeting_recording_flow import WEBM
from test_pi_meeting_routes import BASE, switch_on

from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia

pytestmark = pytest.mark.integration
MP4 = b"\x00\x00\x00\x18ftypmp42" + bytes(range(40))


async def count(db, model):
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(model))


async def test_erasing_a_customer_removes_their_recordings_from_storage(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366400001")
    customer_id = conv.customer_id
    await switch_on(api)
    mid = await agreed(api, customer_id=str(customer_id))
    await audio_part(api, mid, 0, keep="true")
    await video_part(api, mid, 0)
    assert len(bucket.objects) == 2

    bucket.broken = True  # cannot be reached: nothing is erased, no key is forgotten
    stuck = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={"confirm": True})
    assert stuck.status_code == 409
    assert stuck.json()["error"]["code"] == "RECORDING_DELETE_UNAVAILABLE"
    assert await count(business_db, PiMeetingMedia) == 2
    assert await count(business_db, PiMeeting) == 1

    bucket.broken = False
    done = await api.post(f"/api/v1/pi/brain-erasure/{customer_id}", json={"confirm": True})
    assert done.status_code == 200
    assert bucket.objects == {}  # the files left the storage
    assert await count(business_db, PiMeetingMedia) == 0
    assert await count(business_db, PiMeeting) == 0
    await pi.close()


async def test_a_meeting_with_parts_but_no_recording_key_still_removes_them(
    api, business_db, bucket
):
    pi, conv, scope = await workspace(api, business_db, "366400002")
    await switch_on(api)
    mid = await agreed(api)
    await video_part(api, mid, 0)
    await business_db.execute(update(PiMeeting).values(recording_key=None))
    await business_db.commit()
    assert len(bucket.objects) == 1

    bucket.broken = True
    assert (await api.delete(f"{BASE}/{mid}")).status_code == 409
    bucket.broken = False
    assert (await api.delete(f"{BASE}/{mid}")).status_code == 200
    assert bucket.objects == {}
    assert await count(business_db, PiMeetingMedia) == 0
    await pi.close()


async def test_a_part_replaced_under_a_new_key_leaves_no_old_object(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366400003")
    await switch_on(api)
    mid = await agreed(api)
    url = f"{BASE}/{mid}/recording/media/audio/0"
    first = await api.post(url, files={"file": ("p.webm", WEBM, "audio/webm")})
    assert first.status_code == 200
    [old_key] = bucket.objects
    assert old_key.endswith(".webm")

    # the same part comes back as mp4: a different key, so the first object must go
    second = await api.post(url, files={"file": ("p.mp4", MP4, "audio/mp4")})
    assert second.status_code == 200
    [new_key] = bucket.objects
    assert new_key.endswith(".m4a") and new_key != old_key
    assert await business_db.scalar(select(PiMeetingMedia.key)) == new_key
    await pi.close()


async def test_a_replacement_is_abandoned_when_the_old_object_cannot_be_removed(
    api, business_db, bucket
):
    pi, conv, scope = await workspace(api, business_db, "366400004")
    await switch_on(api)
    mid = await agreed(api)
    url = f"{BASE}/{mid}/recording/media/audio/0"
    await api.post(url, files={"file": ("p.webm", WEBM, "audio/webm")})
    [old_key] = bucket.objects

    async def cannot_remove(session, scope, request, keys):
        from app.modules.pi_meetings import media

        raise media.StorageFailed("DOWN")

    from app.modules.pi_meetings import media

    original = media._remove
    media._remove = cannot_remove
    try:
        refused = await api.post(url, files={"file": ("p.mp4", MP4, "audio/mp4")})
    finally:
        media._remove = original
    assert refused.status_code == 502
    assert refused.json()["error"]["code"] == "MEETING_MEDIA_STORE_FAILED"
    # the row still names the first object, which is still there: nothing was forgotten
    assert await business_db.scalar(select(PiMeetingMedia.key)) == old_key
    assert old_key in bucket.objects
    await pi.close()
