"""Meeting links: staff make a link, other people open it without signing in and join with their own
consent. The token is the only key and is stored as a hash; a link works only while it is open,
unexpired, for an open meeting, within its guest limit, and with the workspace flag on."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body

from app.modules.pi_meetings import guest_routes
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
    assert seen.status_code == 200 and set(seen.json()) == {"title"}  # nothing else is shown

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
