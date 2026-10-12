"""pi keeps the chat unless a person is really needed. A question it can't answer goes
on the team's request desk and the customer keeps talking to pi; asking for a person,
a complaint or a payment issue still hands the chat to the team."""

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration


async def test_a_question_for_the_team_goes_on_the_desk_and_pi_keeps_talking(
    api, business_db, monkeypatch
):
    mock_turns(
        monkeypatch,
        turn(
            reply="Noted: daily reporting and sales tracking. I'll check with the team.",
            request_human=True,
        ),
        turn(reply="Great, I'll prepare the summary for you to confirm."),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("I need daily reporting and tracking of my sales team", "keep-1")
    conversation = await pi.conversation()
    assert conversation.mode == "ai"  # no handoff: nothing here needs a person
    [request] = list(
        await business_db.scalars(
            select(PiStaffRequest).where(PiStaffRequest.conversation_id == conversation.id)
        )
    )
    assert request.kind == "question" and request.status == "open"

    await pi.process("Not at the moment", "keep-2")
    await business_db.refresh(conversation)
    assert conversation.mode == "ai"
    replies = [m.body for m in await pi.outbound()]
    assert "Great, I'll prepare the summary for you to confirm." in replies
    await pi.close()


async def test_asking_for_a_person_still_hands_off(api, business_db, monkeypatch):
    mock_turns(
        monkeypatch,
        turn(reply="Sure, a person from the team will reply here.", request_human=True),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("I want to talk to a real person please", "keep-3")
    assert (await pi.conversation()).mode == "human"
    await pi.close()
