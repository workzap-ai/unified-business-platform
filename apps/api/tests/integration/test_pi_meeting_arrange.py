"""The team arranges a meeting from its request in one step: the time and link go into
the answer, and pi tells the customer. A Google Meet link needs a connected calendar."""

from uuid import UUID

import pytest
from test_pi_deals import _customer_in_chat
from test_pi_pipeline import pi_workspace

from app.modules.pi.service_conversation import ask_for_meeting, invented
from app.modules.pi_saas.models import PiStaffRequest
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration
DESK = "/api/v1/pi/requests"


async def _meeting_request(pi) -> str:
    _, conversation = await _customer_in_chat(pi)
    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    await ask_for_meeting(pi.db, scope, conversation, "Wants a call", "Can we meet on Zoom?")
    await pi.db.commit()
    desk = (await pi.api.get(DESK)).json()
    [request] = [r for r in desk["items"] if r["kind"] == "meeting"]
    assert desk["google_meet"] is False  # no calendar connected here
    return request["id"]


async def test_a_meeting_with_their_own_link_goes_to_pi(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    request_id = await _meeting_request(pi)
    done = await api.post(
        f"{DESK}/{request_id}/meeting",
        json={
            "starts_at": "2026-10-20T17:00",
            "duration_minutes": 45,
            "how": "link",
            "link": "https://zoom.us/j/123456789",
        },
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "answered"
    assert "https://zoom.us/j/123456789" in body["answer"] and "45 minutes" in body["answer"]
    jobs = [a for n, a in pi.app.state.queue.jobs if n == "pi_reply_with_team_answer"]
    assert jobs == [(request_id,)]  # pi tells the customer itself
    # pi may repeat the team's link and confirmation; nothing else would pass the guard.
    context = {"team_answer_now": {"answer": body["answer"]}}
    assert invented("Done: Monday 5 PM on Zoom https://zoom.us/j/123456789", context) == ""
    await pi.close()


async def test_in_person_needs_a_place_and_meet_needs_a_calendar(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    request_id = await _meeting_request(pi)
    no_place = await api.post(
        f"{DESK}/{request_id}/meeting",
        json={"starts_at": "2026-10-20T17:00", "how": "in_person"},
    )
    assert no_place.status_code == 422
    no_calendar = await api.post(
        f"{DESK}/{request_id}/meeting",
        json={"starts_at": "2026-10-20T17:00", "how": "google_meet"},
    )
    assert no_calendar.status_code == 409
    assert "Google Calendar" in no_calendar.json()["error"]["message"]
    row = await business_db.get(PiStaffRequest, UUID(request_id))
    assert row.status == "open"  # nothing was answered
    await pi.close()


async def _asked_for(pi, request_id: str, when: str, how: str = "google_meet") -> None:
    from app.modules.pi.models import PiConversation

    row = await business_db_row(pi, request_id)
    conversation = await pi.db.get(PiConversation, row.conversation_id)
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "meeting": {"starts_at": when, "how": how},
    }
    await pi.db.commit()


async def business_db_row(pi, request_id: str) -> PiStaffRequest:
    return await pi.db.get(PiStaffRequest, UUID(request_id))


async def test_the_teams_yes_with_a_link_arranges_the_time_the_customer_asked_for(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    request_id = await _meeting_request(pi)
    await _asked_for(pi, request_id, "2026-10-20T17:00")
    done = await api.post(
        f"{DESK}/{request_id}/answer",
        json={"answer": "Yes confirmed, use https://zoom.us/j/987654321"},
    )
    assert done.status_code == 200, done.text
    answer = done.json()["answer"]
    assert answer.startswith("Meeting confirmed by the team:")
    assert "05:00 PM" in answer and "https://zoom.us/j/987654321" in answer
    await pi.close()


async def test_a_bare_yes_without_a_calendar_asks_for_a_link_and_pi_never_confirms(
    api, business_db
):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    request_id = await _meeting_request(pi)
    await _asked_for(pi, request_id, "2026-10-20T17:00")
    yes = await api.post(f"{DESK}/{request_id}/answer", json={"answer": "Yes, do confirmed"})
    assert yes.status_code == 409
    assert "link" in yes.json()["error"]["message"]
    assert (await business_db_row(pi, request_id)).status == "open"
    # A plain team note is not a meeting: pi can't call it confirmed.
    context = {"team_answer_now": {"answer": "Yes, do confirmed"}}
    assert invented("Your meeting is confirmed for 5 PM on Google Meet.", context)
    await pi.close()


async def test_without_a_time_the_answer_is_a_plain_note(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    request_id = await _meeting_request(pi)
    done = await api.post(
        f"{DESK}/{request_id}/answer", json={"answer": "Yes, ask them which day suits"}
    )
    assert done.status_code == 200, done.text
    assert done.json()["answer"] == "Yes, ask them which day suits"
    await pi.close()


async def test_asking_for_a_link_nobody_arranged_goes_back_to_the_team(api, business_db):
    from app.modules.pi.service_conversation import waiting_for_meeting_link

    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi)
    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    asked = {"meeting_requested": True}
    assert await waiting_for_meeting_link(pi.db, scope, conversation, asked, "send link?")
    assert not await waiting_for_meeting_link(pi.db, scope, conversation, {}, "send link?")
    assert not await waiting_for_meeting_link(pi.db, scope, conversation, asked, "thanks")
    await pi.close()


def test_thanks_counts_as_nothing_more():
    from app.modules.pi.service_conversation import CLOSING

    assert CLOSING.match("thank you looking forward to it")
    assert CLOSING.match("Shukriya")


async def test_pi_books_the_google_meet_itself_and_sends_the_link(api, business_db, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from test_pi_service_conversations import mock_turns, turn

    from app.modules.pi.models import PiConversation, PiMessage
    from app.modules.pi_saas import meetings

    link = "https://meet.google.com/abc-defg-hij"

    async def fake_meet(*args, **kwargs):
        return link, "event-1"

    async def ready(*args, **kwargs):
        return True

    monkeypatch.setattr(meetings, "_google_meet", fake_meet)
    monkeypatch.setattr(meetings, "calendar_ready", ready)
    mock_turns(
        monkeypatch, turn(reply=f"Your meeting is confirmed. Join here: {link}", language="en")
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi)
    when = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT17:00")
    row = await pi.db.get(PiConversation, conversation.id)
    row.service_brief = {**row.service_brief, "meeting": {"starts_at": when, "how": ""}}
    pi.db.add(
        PiMessage(
            tenant_id=UUID(pi.tenant_id),
            environment_id=UUID(pi.environment_id),
            conversation_id=conversation.id,
            direction="inbound",
            sender_type="customer",
            message_type="text",
            body="Day after tomorrow 5pm on Google Meet",
            status="processed",
        )
    )
    await pi.db.commit()

    request_id = await meetings.book_for_customer(pi.ctx, str(conversation.id))
    assert request_id is not None
    request = await business_db_row(pi, request_id)
    await pi.db.refresh(request)
    assert request.status == "answered" and link in request.answer
    sent = list(
        await pi.db.scalars(
            select(PiMessage).where(
                PiMessage.conversation_id == conversation.id, PiMessage.sender_type == "ai"
            )
        )
    )
    assert [m.body for m in sent] == [f"Your meeting is confirmed. Join here: {link}"]
    # Booked once: running the job again makes nothing new.
    assert await meetings.book_for_customer(pi.ctx, str(conversation.id)) is None
    await pi.close()
