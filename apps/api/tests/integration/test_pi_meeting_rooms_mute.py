"""The host can hold one guest muted in a live call and let them speak again; staff, ended rooms,
removed people and a failed provider call change nothing."""

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import Provider as BaseProvider
from test_pi_meeting_rooms import open_room
from test_pi_meeting_rooms_limits import enter, guest, switch
from test_pi_meeting_routes import BASE

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import room_routes
from app.modules.pi_meetings.room_provider import RoomProviderError

pytestmark = pytest.mark.integration


@pytest.fixture
def provider(monkeypatch):
    p = BaseProvider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def people(api, mid):
    return (await api.get(f"{BASE}/{mid}/room")).json()["people"]


async def test_a_guest_is_muted_and_unmuted_and_the_panel_shows_it(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "369400001")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    token, _ = await guest(api, mid)
    entered = (await enter(api, token)).json()
    person = next(p for p in await people(api, mid) if p["label"] == "Ayesha")
    assert person["muted"] is False

    url = f"{BASE}/{mid}/room/people/{person['id']}/mute"
    on = await api.post(url, json={"muted": True})
    assert on.status_code == 200 and on.json() == {"muted": True}
    call = provider.created[0][0]
    assert provider.muted == [(call, entered["user_id"], True)]
    assert next(p for p in await people(api, mid) if p["label"] == "Ayesha")["muted"] is True

    off = await api.post(url, json={"muted": False})
    assert off.status_code == 200 and provider.muted[-1] == (call, entered["user_id"], False)
    assert next(p for p in await people(api, mid) if p["label"] == "Ayesha")["muted"] is False
    actions = {
        a.action
        for a in (
            await business_db.scalars(
                select(AuditEvent).where(AuditEvent.action.like("pi.meeting_room_person_%mute%"))
            )
        ).all()
    }
    assert actions == {"pi.meeting_room_person_muted", "pi.meeting_room_person_unmuted"}
    await pi.close()


async def test_staff_removed_people_ended_rooms_and_a_failed_call_are_not_muted(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369400002")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    await api.post(f"{BASE}/{mid}/room/token")
    token, _ = await guest(api, mid)
    await enter(api, token)
    everyone = await people(api, mid)
    staff = next(p for p in everyone if p["staff"])
    other = next(p for p in everyone if not p["staff"])

    no = await api.post(f"{BASE}/{mid}/room/people/{staff['id']}/mute", json={"muted": True})
    assert no.status_code == 409 and no.json()["error"]["code"] == "MEETING_ROOM_STAFF"
    provider.fail_mute = RoomProviderError("ROOM_PROVIDER_BUSY", "busy", 429)
    busy = await api.post(f"{BASE}/{mid}/room/people/{other['id']}/mute", json={"muted": True})
    assert busy.status_code == 429
    assert next(p for p in await people(api, mid) if not p["staff"])["muted"] is False
    provider.fail_mute = None
    unknown = await api.post(
        f"{BASE}/{mid}/room/people/00000000-0000-0000-0000-000000000000/mute", json={"muted": True}
    )
    assert unknown.status_code == 404
    await api.post(f"{BASE}/{mid}/room/people/{other['id']}/remove")
    gone = await api.post(f"{BASE}/{mid}/room/people/{other['id']}/mute", json={"muted": True})
    assert gone.status_code == 409 and gone.json()["error"]["code"] == "MEETING_ROOM_REMOVED"
    assert provider.muted == []
    await api.post(f"{BASE}/{mid}/room/end")
    late = await api.post(f"{BASE}/{mid}/room/people/{other['id']}/mute", json={"muted": True})
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_ROOM_CLOSED"
    await pi.close()
