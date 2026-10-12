"""Meetings for every business: a customer asking for a meeting, call, demo or visit gets
a "meeting" request on the team's desk while pi keeps the chat; the deal's journey shows
the meeting until the team answers with a time."""

from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import DEALS, _customer_in_chat, _lead
from test_pi_pipeline import pi_workspace

from app.modules.pi.models import PiConversation
from app.modules.pi.service_conversation import ask_for_meeting, asks_for_meeting
from app.modules.pi_saas.models import PiStaffRequest
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration
DESK = "/api/v1/pi/requests"


def test_meeting_words():
    for text in (
        "Can we have a meeting tomorrow?",
        "please call me after 5",
        "Kal mulaqat ho sakti hai?",
        "can I get a demo",
        "I want to visit your showroom",
        "کیا ملاقات ہو سکتی ہے",
    ):
        assert asks_for_meeting(text), text
    for text in ("visit your website", "does it meet our needs", "price kya hai", None):
        assert not asks_for_meeting(text), text


async def test_product_business_meeting_request_keeps_the_chat(api, business_db):
    pi = await pi_workspace(api, business_db)  # a product business: no service brief
    await pi.process("I want to talk to a real person on a video call", "meet-p1")
    conversation = await pi.conversation()
    assert conversation.mode == "ai"  # no handoff: the team proposes a time through pi
    [request] = list(
        await business_db.scalars(
            select(PiStaffRequest).where(PiStaffRequest.conversation_id == conversation.id)
        )
    )
    assert request.kind == "meeting" and request.status == "open"
    [reply] = await pi.outbound()
    assert "Which days and times suit you?" in reply.body

    await pi.process("Can a real person do the video call on Friday?", "meet-p2")
    await business_db.refresh(request)
    assert "Friday" in request.question  # the same request gathers their times
    count = len(
        list(
            await business_db.scalars(
                select(PiStaffRequest).where(PiStaffRequest.conversation_id == conversation.id)
            )
        )
    )
    assert count == 1
    await pi.close()


async def test_journey_shows_the_meeting_until_the_team_sends_a_time(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    journey = (await api.get(f"{DEALS}/leads/{lead_id}/journey")).json()
    assert "meeting" not in [s["key"] for s in journey["steps"]]  # only when asked for

    scope = WorkspaceScope.system(
        UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "PI"
    )
    row = await pi.db.get(PiConversation, conversation.id)
    await ask_for_meeting(pi.db, scope, row, "Wants to discuss the logo", "Can we meet Monday?")
    await pi.db.commit()

    journey = (await api.get(f"{DEALS}/leads/{lead_id}/journey")).json()
    [step] = [s for s in journey["steps"] if s["key"] == "meeting"]
    assert step["label"] == "Meeting requested" and not step["done"]
    assert journey["next"]["title"] == "Arrange the meeting"
    request_id = journey["meeting"]["request_id"]
    assert journey["next"]["href"] == f"/pi/requests?request={request_id}"

    answered = await api.post(
        f"{DESK}/{request_id}/answer",
        json={"answer": "Monday 3pm on Google Meet, link: meet.google.com/abc"},
    )
    assert answered.status_code == 200, answered.text
    jobs = [a for n, a in pi.app.state.queue.jobs if n == "pi_reply_with_team_answer"]
    assert jobs == [(request_id,)]  # pi confirms the time to the customer itself
    journey = (await api.get(f"{DEALS}/leads/{lead_id}/journey")).json()
    [step] = [s for s in journey["steps"] if s["key"] == "meeting"]
    assert step["label"] == "Meeting time sent" and step["done"]
    assert "Monday 3pm" in step["detail"]
    assert journey["next"]["title"] != "Arrange the meeting"
    await pi.close()
