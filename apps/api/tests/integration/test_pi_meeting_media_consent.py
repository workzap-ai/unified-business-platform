# ruff: noqa: F811  (the `bucket` fixture is imported, then named as a test argument)
"""Saving a recording needs its own yes (kept by the server), playing it needs its own permission,
and every listening session leaves a record with ids only."""

import pytest
from sqlalchemy import delete, select
from test_pi_meeting_data import workspace
from test_pi_meeting_media_flow import audio_part, bucket, video_part  # noqa: F401
from test_pi_meeting_routes import BASE, body, switch_on

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia

pytestmark = pytest.mark.integration


async def test_nothing_is_saved_before_the_yes_and_the_server_remembers_it(
    api, business_db, bucket
):
    pi, conv, scope = await workspace(api, business_db, "366500001")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]

    heard = await audio_part(api, mid, 0, keep="true")  # no yes yet: the words are safe, no audio
    assert heard.status_code == 200 and heard.json()["saved"] is False and heard.json()["segments"]
    refused = await video_part(api, mid, 0)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "MEETING_MEDIA_CONSENT_REQUIRED"
    assert bucket.objects == {}
    assert (await api.get(f"{BASE}/{mid}")).json()["media_consent_at"] is None

    said = await api.post(f"{BASE}/{mid}/recording/save-consent")
    assert said.status_code == 200
    first = said.json()["media_consent_at"]
    assert (await api.post(f"{BASE}/{mid}/recording/save-consent")).json()[
        "media_consent_at"
    ] == first  # asking again keeps the first answer
    business_db.expire_all()
    meeting = await business_db.scalar(select(PiMeeting))
    assert meeting.media_consent_at is not None and meeting.media_consent_by is not None

    assert (await audio_part(api, mid, 1, keep="true")).json()["saved"] is True
    assert (await video_part(api, mid, 0)).status_code == 200
    assert len(bucket.objects) == 2
    await pi.close()


async def test_playing_needs_its_own_permission_and_is_recorded(api, business_db, bucket):
    pi, conv, scope = await workspace(api, business_db, "366500002")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await api.post(f"{BASE}/{mid}/recording/save-consent")
    await video_part(api, mid, 0)

    assert (await api.get(f"{BASE}/{mid}/recording")).status_code == 200
    opened = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi.meeting_recording_opened")
        )
    )
    assert len(opened) == 1 and opened[0].details == {"parts": 1}  # ids and counts, never audio

    from app.modules.access.models import RolePermission

    await business_db.execute(
        delete(RolePermission).where(RolePermission.permission == "pi.meetings.recording")
    )
    await business_db.commit()
    assert (await api.get(f"{BASE}/{mid}/recording")).status_code == 403
    assert await business_db.scalar(select(PiMeetingMedia.id)) is not None  # still stored
    await pi.close()
