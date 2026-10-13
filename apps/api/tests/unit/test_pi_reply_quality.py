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


# From a real chat (2026-10-12): "Sorry tomorrow" answered pi's meeting question, and
# pi sent an unagreed brief to the team in Roman Urdu instead.
MEETING_CHAT = {
    "brief": {},
    "latest_customer_message": "Sorry tomorrow",
    "latest_message_kind": "text",
    "history": [
        {"role": "customer", "text": "Yesterday 10am"},
        {"role": "ai", "text": "Please let me know which day and time works best for you."},
    ],
}


def test_a_brief_goes_to_the_team_only_when_the_customer_agrees():
    from app.modules.pi.service_conversation import ServiceTurn, unconfirmed_brief

    turn = ServiceTurn(reply="Sent to the team.", ready_for_team=True)
    assert unconfirmed_brief(turn, MEETING_CHAT)
    for yes in ("yes send it", "haan theek hai", "ok", "that's all", "ye hi bnao"):
        assert unconfirmed_brief(turn, {**MEETING_CHAT, "latest_customer_message": yes}) is None
    already = {**MEETING_CHAT, "brief": {"ready_for_team": True}}
    assert unconfirmed_brief(turn, already) is None


def test_an_answer_to_the_meeting_question_is_never_ignored():
    from app.modules.pi.service_conversation import ServiceTurn, meeting_answer_missed

    assert meeting_answer_missed(ServiceTurn(reply="Brief noted."), MEETING_CHAT)
    booked = ServiceTurn(reply="Booked.", meeting_time="2026-10-13T10:00")
    assert meeting_answer_missed(booked, MEETING_CHAT) is None
    other = {**MEETING_CHAT, "latest_customer_message": "I also want a logo"}
    assert meeting_answer_missed(ServiceTurn(reply="Noted."), other) is None


def test_a_short_question_about_the_company_gets_a_full_answer():
    from app.modules.pi.service_conversation import too_long

    services = (
        "Artwing Studios is a creative agency.\n• Branding\n• Video\n• SEO\nWhat do you need?"
    )
    ask = {"latest_customer_message": "Tell me your services", "latest_message_kind": "text"}
    assert too_long(services, ask) is None
    thanks = {"latest_customer_message": "ok thanks", "latest_message_kind": "text"}
    assert too_long(services, thanks)


def test_replies_are_polished_and_a_filler_only_reply_is_caught():
    from app.modules.pi.service_conversation import polished, says_nothing

    assert (
        polished(
            "Hi Muhammad! Your Google Meet link is: https://meet.jit.si/pi-meeting-1. **Done**"
        )
        == "Hi Muhammad. Your video call link is: https://meet.jit.si/pi-meeting-1. *Done*"
    )
    assert polished("Link: https://meet.google.com/abc!x") == "Link: https://meet.google.com/abc!x"
    assert says_nothing("If you need any further assistance, feel free to ask.")
    assert says_nothing("The team replies here.") is None


def test_the_knowledge_search_understands_what_is_asked():
    from app.modules.pi.knowledge import search_terms
    from app.modules.pi.service_conversation import brief_words

    assert search_terms("aap kya kaam karte ho").startswith("services:* | offer:*")
    assert "price:*" in search_terms("iski qeemat kitni hai")
    words = brief_words({"projects": [{"title": "Logo", "status": "collecting"}], "mood": "calm"})
    assert words == "Logo"  # never the JSON field names ("status", "mood", ...)


def test_a_project_is_known_deeply_and_nothing_known_is_lost():
    from app.modules.pi.service_conversation import (
        Project,
        Requirements,
        ServiceTurn,
        merge_projects,
        project_requirements,
    )

    earlier = Project(
        title="Furniture store",
        problem="Orders come only through Instagram DMs and get lost",
        features=["Online catalogue", "Cart"],
        questions=["Which payment gateway?"],
    ).model_dump()
    now = Project(
        title="Furniture store",
        goal="Sell online across Pakistan",
        features=["cart", "Stock tracking"],
        decisions=["Payment gateway: JazzCash"],
        questions=["Which payment gateway?"],
    )
    [merged] = merge_projects([earlier], ServiceTurn(reply="ok", projects=[now]))
    assert merged.problem == "Orders come only through Instagram DMs and get lost"
    assert merged.goal == "Sell online across Pakistan"
    assert merged.features == ["Online catalogue", "Cart", "Stock tracking"]
    fields = project_requirements(merged, Requirements().model_dump(), True)
    assert fields["problem"].startswith("Orders come only")
    assert fields["features"] == ["Online catalogue", "Cart", "Stock tracking"]
    # A single string from the model still becomes a list.
    assert Project.model_validate({"title": "X", "features": "Cart"}).features == ["Cart"]


def test_a_paid_project_shows_as_being_built_not_as_a_proposal_to_prepare():
    from app.modules.pi_saas.customer_overview import follow_deals

    issues = [
        {
            "title": "Website and Logo Design",
            "stage": "on_it",
            "ball_with": "team",
            "next_step": "Team: prepare the proposal",
            "open_question": "",
        },
        {
            "title": "Employee tracking system",
            "stage": "on_it",
            "ball_with": "team",
            "next_step": "Team: x",
            "open_question": "",
        },
    ]
    projects = [
        {
            "title": "Website and Logo Design",
            "stage": "won",
            "steps_done": 8,
            "steps_total": 11,
            "next": {"title": "Start the work"},
        },
        {"title": "Website and Logo Design", "stage": "new"},
    ]
    follow_deals(issues, projects)
    assert issues[0]["stage"] == "building"
    assert issues[0]["next_step"] == "Team: Start the work"
    assert issues[1]["stage"] == "on_it"  # no won deal: unchanged
