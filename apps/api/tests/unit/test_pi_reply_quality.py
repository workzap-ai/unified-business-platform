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


def test_a_status_line_never_replaces_what_the_customer_wants():
    from app.modules.pi.service_conversation import Project, ServiceTurn, merge_projects

    before = [
        {
            "title": "Furniture E-commerce Website",
            "details": "Online store for 200 products with card payment",
            "status": "confirmed",
        }
    ]
    turn = ServiceTurn(
        reply="ok",
        projects=[
            Project(
                title="Furniture E-commerce Website",
                details="Proposal is being drafted; will be shared soon.",
                status="collecting",
            )
        ],
    )
    [project] = merge_projects(before, turn)
    assert project.details == "Online store for 200 products with card payment"
    assert project.status == "confirmed"  # never goes back to collecting


def test_a_meeting_that_already_happened_is_never_sent_again():
    from datetime import UTC, datetime

    from app.modules.pi.service_conversation import arranged_meeting, meeting_over

    note = (
        "Meeting confirmed by the team: Monday 12 October, 06:00 PM (Asia/Karachi), "
        "30 minutes, on a video call (opens in the browser, no sign-up): "
        "https://meet.jit.si/pi-meeting-43ada63cddd3d2a1."
    )
    notes = [{"kind": "answer", "note": note}]
    before = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)  # 5:00 PM in Karachi
    after = datetime(2026, 10, 12, 15, 32, tzinfo=UTC)  # 8:32 PM in Karachi
    assert meeting_over({}, notes, "Asia/Karachi", before) is None
    assert meeting_over({}, notes, "Asia/Karachi", after) == "Monday 12 October, 06:00 PM"
    upcoming = {"team_notes": notes, "brief": {}}
    assert arranged_meeting(upcoming)["link"].startswith("https://meet.jit.si/")
    assert arranged_meeting({**upcoming, "meeting_over": "Monday 12 October, 06:00 PM"}) == {}


def test_what_would_you_like_to_discuss_is_open_ended():
    from app.modules.pi.service_conversation import OPEN_ENDED

    assert OPEN_ENDED.search("Sure, let's continue. Do you want to discuss any specific project?")
