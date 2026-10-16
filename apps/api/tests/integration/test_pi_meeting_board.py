"""The Meeting Board: arranged meetings, free time and waiting requests in one week, and
the team moves, cancels, reminds and records outcomes from it."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import _customer_in_chat
from test_pi_pipeline import pi_workspace

from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service_conversation import ask_for_meeting
from app.modules.pi_saas.meeting_board import free_slots, meeting_hours
from app.modules.pi_saas.models import PiConversationNote
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration
DESK = "/api/v1/pi/requests"
BOARD = "/api/v1/pi/meetings"


def _day(offset: int) -> str:
    """A weekday at least ``offset`` days ahead (meeting hours are Monday to Saturday)."""
    day = datetime.now(UTC).date() + timedelta(days=offset)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return day.isoformat()


async def _arranged(pi, when: str) -> UUID:
    _, conversation = await _customer_in_chat(pi)
    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    await ask_for_meeting(pi.db, scope, conversation, "Wants a call", "Can we meet on Zoom?")
    conversation.last_inbound_at = datetime.now(UTC)  # they wrote just now
    await pi.db.commit()
    desk = (await pi.api.get(DESK)).json()
    [request] = [r for r in desk["items"] if r["kind"] == "meeting"]
    board = (await pi.api.get(BOARD, params={"start": when[:10]})).json()
    assert [w["request_id"] for w in board["waiting"]] == [request["id"]]
    done = await pi.api.post(
        f"{DESK}/{request['id']}/meeting",
        json={"starts_at": when, "how": "link", "link": "https://zoom.us/j/42"},
    )
    assert done.status_code == 200, done.text
    return conversation.id


async def _sent(pi, conversation_id: UUID) -> list[str]:
    rows = await pi.db.scalars(
        select(PiMessage)
        .where(PiMessage.conversation_id == conversation_id, PiMessage.direction == "outbound")
        .order_by(PiMessage.created_at)
    )
    return [m.body for m in rows]


async def test_the_board_shows_the_meeting_and_takes_its_time(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    day = _day(2)
    chat = await _arranged(pi, f"{day}T11:00")
    board = (await api.get(BOARD, params={"start": day, "days": 7})).json()
    [meeting] = board["meetings"]
    assert meeting["conversation_id"] == str(chat)
    assert meeting["status"] == "scheduled" and meeting["link"] == "https://zoom.us/j/42"
    assert board["waiting"] == []  # the request was answered
    free_that_day = [s["local"] for s in board["free"] if s["local"].startswith(day)]
    assert f"{day}T10:30" in free_that_day and f"{day}T11:00" not in free_that_day
    assert board["calendar"] == "none" and board["stats"]["waiting"] == 0
    await pi.close()


async def test_move_remind_change_and_outcome(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    day = _day(3)
    chat = await _arranged(pi, f"{day}T11:00")

    moved = await api.post(f"{BOARD}/{chat}/move", json={"starts_at": f"{day}T15:00"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["told_customer"] is True
    assert any(
        "03:00 PM" in body and "https://zoom.us/j/42" in body for body in await _sent(pi, chat)
    )

    reminded = await api.post(f"{BOARD}/{chat}/remind")
    assert reminded.status_code == 200, reminded.text
    assert (await _sent(pi, chat))[-1].startswith("Reminder: ")

    conversation = await pi.db.get(PiConversation, chat)
    await pi.db.refresh(conversation)
    conversation.service_brief = {
        **conversation.service_brief,
        "meeting": {**conversation.service_brief["meeting"], "change_to": f"{day}T16:30"},
    }
    await pi.db.commit()
    board = (await api.get(BOARD, params={"start": day})).json()
    assert board["meetings"][0]["change_label"] and board["stats"]["change_requests"] == 1
    accepted = await api.post(f"{BOARD}/{chat}/accept-change")
    assert accepted.status_code == 200, accepted.text
    await pi.db.refresh(conversation)
    assert conversation.service_brief["meeting"]["starts_at"] == f"{day}T16:30"
    assert "change_to" not in conversation.service_brief["meeting"]

    done = await api.post(
        f"{BOARD}/{chat}/outcome", json={"status": "done", "note": "They want the ERP first"}
    )
    assert done.status_code == 200, done.text
    await pi.db.refresh(conversation)
    assert "meeting" not in conversation.service_brief  # pi never sends this link again
    assert conversation.service_brief["meetings_past"][-1]["status"] == "done"
    [note] = list(
        await pi.db.scalars(
            select(PiConversationNote).where(PiConversationNote.conversation_id == chat)
        )
    )
    assert "They want the ERP first" in note.body  # pi reads it as a team note
    board = (await api.get(BOARD, params={"start": day})).json()
    assert board["history"][0]["status"] == "done"
    assert (await api.post(f"{BOARD}/{chat}/remind")).status_code == 404
    await pi.close()


async def test_cancel_tells_the_customer(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    day = _day(2)
    chat = await _arranged(pi, f"{day}T12:00")
    cancelled = await api.post(f"{BOARD}/{chat}/cancel", json={"reason": "Our team is away."})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["told_customer"] is True
    assert "has been cancelled. Our team is away." in (await _sent(pi, chat))[-1]
    board = (await api.get(BOARD, params={"start": day})).json()
    assert board["history"][0]["status"] == "cancelled"
    free_that_day = [s["local"] for s in board["free"] if s["local"].startswith(day)]
    assert f"{day}T12:00" in free_that_day  # the time is free again
    await pi.close()


def test_free_slots_skip_closed_days_and_taken_time():
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Karachi")
    hours = meeting_hours(None)
    monday = datetime(2030, 1, 7, tzinfo=tz).date()  # a Monday
    taken = [(datetime(2030, 1, 7, 9, 0, tzinfo=tz), datetime(2030, 1, 7, 10, 0, tzinfo=tz))]
    now = datetime(2030, 1, 1, tzinfo=tz)
    slots = [s["local"] for s in free_slots(hours, tz, monday, 7, taken, now)]
    assert "2030-01-07T09:00" not in slots and "2030-01-07T09:30" not in slots
    assert "2030-01-07T10:00" in slots and "2030-01-07T17:30" in slots
    assert not [s for s in slots if s.startswith("2030-01-13")]  # Sunday is closed


async def test_a_meeting_within_the_hour_is_reminded_once(api, business_db):
    from zoneinfo import ZoneInfo

    from app.modules.pi.models import PiSettings
    from app.modules.pi_saas.meeting_board import remind_upcoming

    pi = await pi_workspace(api, business_db, business_type="service_business")
    settings = await pi.db.scalar(
        select(PiSettings).where(PiSettings.tenant_id == UUID(pi.tenant_id))
    )
    soon = datetime.now(ZoneInfo(settings.timezone if settings else "UTC")) + timedelta(minutes=40)
    chat = await _arranged(pi, f"{soon:%Y-%m-%dT%H:%M}")
    assert await remind_upcoming(pi.ctx) == 1
    assert await remind_upcoming(pi.ctx) == 0  # one reminder per meeting
    assert (await _sent(pi, chat))[-1].startswith("Reminder: ")
    await pi.close()


async def test_the_team_books_a_meeting_from_the_customer_profile(api, business_db):
    from test_service_lifecycle import create

    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    day = _day(2)
    booked = await api.post(
        f"{BOARD}/book",
        json={
            "customer_id": customer_id,
            "starts_at": f"{day}T14:00",
            "how": "link",
            "link": "https://zoom.us/j/77",
            "note": "Logo review",
        },
    )
    assert booked.status_code == 200, booked.text
    body = booked.json()
    assert body["conversation_id"] == str(conversation.id) and body["told_customer"] is True
    assert body["link"] == "https://zoom.us/j/77"
    jobs = [n for n, _ in pi.app.state.queue.jobs if n == "pi_reply_with_team_answer"]
    assert jobs  # pi sends the time and link
    board = (await api.get(BOARD, params={"start": day})).json()
    [meeting] = board["meetings"]
    assert meeting["customer_name"] == "Ayesha Khan" and meeting["local"] == f"{day}T14:00"

    # No WhatsApp number: pi can't reach them, so nothing is booked.
    nobody = await create(api, "customers", {"name": "No Phone"})
    refused = await api.post(
        f"{BOARD}/book", json={"customer_id": nobody["id"], "starts_at": f"{day}T15:00"}
    )
    assert refused.status_code == 422, refused.text
    await pi.close()
