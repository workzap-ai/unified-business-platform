"""pi picks unfinished conversations back up: a check-in a couple of hours after the
customer went quiet (asking for the business details it still doesn't know), and an
answer to a message that was missed. Once per message, never over a person."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import _customer_in_chat
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import mock_turns, turn

from app.modules.pi import check_in as check_in_module
from app.modules.pi.check_in import check_in, missing_profile, unfinished
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service_conversation import CLOSING, unknown_customer

pytestmark = pytest.mark.integration


def _message(pi, conversation, direction: str, body: str, minutes_ago: float, **extra):
    sender = {"inbound": "customer", "outbound": "ai"}[direction]
    return PiMessage(
        tenant_id=UUID(pi.tenant_id),
        environment_id=UUID(pi.environment_id),
        conversation_id=conversation.id,
        direction=direction,
        sender_type=extra.pop("sender_type", sender),
        message_type="text",
        body=body,
        status="processed" if direction == "inbound" else "read",
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        **extra,
    )


async def _ai_messages(pi, conversation) -> list[PiMessage]:
    return list(
        await pi.db.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation.id, PiMessage.sender_type == "ai")
            .order_by(PiMessage.created_at)
        )
    )


@pytest.fixture(autouse=True)
def _daytime(monkeypatch):
    monkeypatch.setattr(check_in_module, "quiet_until", lambda *a, **k: None)


async def test_quiet_customer_gets_one_check_in_that_asks_for_their_business(
    api, business_db, monkeypatch
):
    contexts = mock_turns(
        monkeypatch,
        turn(
            reply="Picking up your ERP for daily sales reporting: what's your business "
            "called, and what does it sell?",
            language="en",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi, hours_ago=3)
    row = await pi.db.get(PiConversation, conversation.id)
    row.service_brief = {"awaiting_customer": True, "projects": []}
    pi.db.add(_message(pi, conversation, "inbound", "I need an ERP for my sales team", 180))
    asked = _message(pi, conversation, "outbound", "Which reports do you need daily?", 170)
    pi.db.add(asked)
    await pi.db.commit()

    queued = await check_in(pi.ctx, conversation.id, datetime.now(UTC))
    assert queued is not None
    again = await check_in(pi.ctx, conversation.id, datetime.now(UTC) + timedelta(hours=1))
    assert again is None  # once per message pi sent

    context = json.loads(contexts[0])
    assert context["check_in_now"]["missed"] is False
    assert "their business name" in context["check_in_now"]["missing_profile"]
    assert "Which reports" in context["check_in_now"]["your_last_message"]
    replies = await _ai_messages(pi, conversation)
    assert replies[-1].body.startswith("Picking up your ERP")
    assert replies[-1].media == {"check_in": "quiet"} and replies[-1].status == "queued"
    await pi.db.refresh(row)
    assert [c["since"] for c in row.service_brief["check_ins"]] == [str(asked.id)]
    await pi.close()


async def test_a_missed_message_gets_answered(api, business_db, monkeypatch):
    contexts = mock_turns(
        monkeypatch,
        turn(
            reply="Sorry for the wait. Noted, nothing more for now. The team will prepare "
            "your ERP proposal and share it here.",
            language="en",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi, hours_ago=1)
    pi.db.add(_message(pi, conversation, "outbound", "These points are noted.", 40))
    pi.db.add(_message(pi, conversation, "inbound", "Not at the moment", 30))
    await pi.db.commit()

    assert await check_in(pi.ctx, conversation.id, datetime.now(UTC)) is not None
    context = json.loads(contexts[0])
    assert context["check_in_now"]["missed"] is True
    assert context["latest_customer_message"] == "Not at the moment"
    assert (await _ai_messages(pi, conversation))[-1].media == {"check_in": "missed"}
    await pi.close()


async def test_no_check_in_too_soon_over_a_person_or_when_nothing_is_open(
    api, business_db, monkeypatch
):
    mock_turns(monkeypatch)  # any model call would fail the test
    pi = await pi_workspace(api, business_db, business_type="service_business")
    _, conversation = await _customer_in_chat(pi, hours_ago=3)
    row = await pi.db.get(PiConversation, conversation.id)
    row.service_brief = {"awaiting_customer": True}
    pi.db.add(_message(pi, conversation, "inbound", "Logo please", 180))
    pi.db.add(_message(pi, conversation, "outbound", "Which colours?", 60))
    await pi.db.commit()
    assert await check_in(pi.ctx, conversation.id, datetime.now(UTC)) is None  # only 1h

    # A person from the team wrote in this chat: pi stays out.
    pi.db.add(_message(pi, conversation, "outbound", "Hi, Sara here", 170, sender_type="human"))
    await pi.db.commit()
    later = datetime.now(UTC) + timedelta(hours=2)
    assert await check_in(pi.ctx, conversation.id, later) is None
    await pi.close()


def test_what_counts_as_unfinished_and_missing():
    assert missing_profile({"name": "Mukarram"}, False) == [
        "their business name",
        "what their business does",
    ]
    assert missing_profile({"name": "M", "business_type": "distribution"}, False) == []
    assert missing_profile({}, True) == [
        "their name",
        "their business name",
        "what their business does",
    ]
    confirmed = {"ready_for_team": True, "projects": [{"status": "confirmed"}]}
    assert not unfinished(confirmed, "The team will share the proposal here.", [])
    assert unfinished(confirmed, "Which city?", [])
    assert unfinished({"projects": [{"status": "collecting"}]}, "Noted.", [])
    assert CLOSING.match("Not at the moment")
    assert CLOSING.match("abhi nahi")


def test_a_new_customers_brief_waits_for_their_business():
    ready = turn(reply="Sent to the team.", ready_for_team=True)
    assert unknown_customer(ready, {"customer_profile": {"name": "Ali"}})
    assert unknown_customer(ready, {"returning_customer": True}) is None
    assert unknown_customer(ready, {"customer_profile": {"business_name": "Ali Traders"}}) is None
    asking = turn(reply="What's your business called?", ready_for_team=True)
    assert unknown_customer(asking, {}) is None
