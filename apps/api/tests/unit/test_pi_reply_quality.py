"""Reply checks from a real test chat: a Roman Urdu line in an English chat, "sent to
the team" plus "shall I send it?", an exact repeat, and generic closing lines."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.pi.models import PiConversation, PiSettings
from app.modules.pi.service_conversation import (
    ServiceTurn,
    compose_service_turn,
    contradicts_itself,
    mixed_line,
    too_long,
    without_filler,
)
from app.shared.scope import WorkspaceScope

REPLY = (
    "• Modern advanced website for online sales\n"
    "• Management of high stocks and volumes\n"
    "Ye brief team ko bhej diya hai. Shall I send this to the team?"
)


def test_a_roman_urdu_line_in_an_english_chat_is_caught():
    assert mixed_line(REPLY, "en") == "roman_ur"
    assert mixed_line("Thanks, noted. How many products will the shop have?", "en") is None


def test_sent_and_shall_i_send_together_is_caught():
    assert contradicts_itself(REPLY, {})
    assert contradicts_itself("Shall I send this to the team?", {}) is None


def test_repeating_the_last_message_is_caught():
    said = "• Online store for 200 products\n• Stock management\nHow many staff will use it?"
    context = {"history": [{"role": "customer", "text": "hi"}, {"role": "ai", "text": said}]}
    assert "repeats" in str(contradicts_itself(said.replace("\n", "\n\n"), context))


def test_generic_closings_are_dropped_but_real_questions_stay():
    assert (
        without_filler(
            "Workzap offers an AI assistant. If you have specific needs, feel free to share!"
        )
        == "Workzap offers an AI assistant."
    )
    assert without_filler("Noted. How many products?") == "Noted. How many products?"


def test_a_short_message_does_not_need_a_project_before_length_is_checked():
    context = {"latest_customer_message": "Hi", "latest_message_kind": "text"}
    goals = "Our goals:\n• Better service quality\n• Innovative solutions\n• Timely delivery"
    assert too_long(goals, context)
    assert too_long("Hi, I'm pi, your AI assistant. How can I help you today?", context) is None
    assert too_long(goals, {**context, "latest_customer_message": "List your goals"}) is None


@pytest.mark.parametrize("event", ["check_in_now", "team_answer_now", "operator_review_required"])
async def test_a_greeting_in_history_does_not_replace_a_system_triggered_reply(event):
    drafted = ServiceTurn(reply="I'm pi, your AI assistant. The team can help with your request.")
    complete = AsyncMock(
        return_value=SimpleNamespace(value=drafted, response=SimpleNamespace(attempts=[]))
    )
    result = await compose_service_turn(
        SimpleNamespace(complete_structured=complete),
        WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "PI"),
        PiConversation(id=uuid4()),
        PiSettings(ai_config={}, response_rules={}),
        {
            "latest_customer_message": "Hi",
            "latest_message_kind": "text",
            "reply_language": "en",
            event: {"message": "Follow up on the request"},
        },
    )
    complete.assert_awaited_once()
    assert result.reply == drafted.reply
    assert not result._greeting_only


def test_hi_from_a_returning_customer_picks_up_their_open_project():
    from app.modules.pi.service_conversation import greeting_reply

    first = greeting_reply({"company": "Workzap Studio"})
    assert first.startswith("Hi, I'm pi, Workzap Studio's AI assistant.")
    assert "only you and the team see it" in first and "free" in first
    returning = {
        "history": [{"role": "ai", "text": "Earlier reply"}],
        "customer_profile": {"name": "Muhammad Ahtisham Khan"},
        "brief": {"projects": [{"title": "Website for Furniture Shop", "status": "collecting"}]},
    }
    assert greeting_reply(returning) == (
        "Hi Muhammad. Shall we carry on with your Website for Furniture Shop?"
    )
    done = {**returning, "brief": {"projects": [{"title": "Logo", "status": "confirmed"}]}}
    assert greeting_reply(done) == "Hi Muhammad. How can I help you today?"
