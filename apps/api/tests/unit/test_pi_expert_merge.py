# ruff: noqa: E501
"""One independent engine: the expert advisor, with the best of the earlier work merged in: the
owner's gold ideas as examples of level, a rejection answered by the expert, and the cue-chosen
library as the last resort so a client never meets a dead end (scripted model, no database)."""

from types import SimpleNamespace

import pytest
from test_pi_expert_advisor import GOOD_ONE, GOOD_TWO, Scripted, advise, diag
from test_pi_expert_wiring import Manager, make_context, make_policy, run

from app.modules.pi import gold_ideas, solution_context

pytestmark = pytest.mark.asyncio

RESTAURANT = "cash is short and stock goes missing from the kitchen at night"


def test_the_gold_examples_are_the_nearest_trades_and_never_far_ones() -> None:
    got = gold_ideas.examples(RESTAURANT, "restaurants")
    assert got and got[0].startswith("Count the cash drawer with two people")
    assert gold_ideas.examples("zzzz qqqq", "") == []


async def test_the_expert_prompt_shows_the_gold_idea_as_an_example_of_level() -> None:
    model = Scripted(diag([GOOD_ONE, GOOD_TWO]))
    await advise(model, owner_said=[RESTAURANT, "give me a solution"], industry="Restaurants")
    sent = model.users["pi_expert_diag"]
    assert (
        "Count the cash drawer with two people" in sent and "examples_of_level_not_to_copy" in sent
    )


def test_a_rejection_is_answered_by_the_expert_like_a_request() -> None:
    conversation = SimpleNamespace(flow_state="S3_NOTED", service_brief={})
    noted = [{"title": "Excess stock to sell off"}]
    held = solution_context._expert_hold(conversation, "solution glt hai again den", noted, False)  # type: ignore[arg-type]
    assert held is not None and held["solution_why"] == "expert"
    assert solution_context._expert_hold(conversation, "theek hai", noted, False) is None  # type: ignore[arg-type]


async def test_when_the_expert_and_the_free_ideas_give_nothing_the_library_still_answers() -> None:
    manager = Manager("this is not json", free='{"ideas": []}')
    context = make_context(
        latest_customer_message="give me a solution",
        noted_problems=[
            {
                "title": "Cash is short and stock goes missing",
                "user_words": ["chori ka shak hai"],
                "group": "loss_security",
            }
        ],
    )
    conversation, turn = await run(manager, make_policy(), context)
    assert turn.reply.count("•") == 2 and turn._free and turn.awaiting_customer
    assert (
        conversation.service_brief["ideas_given"] == 2
        and len(conversation.service_brief["library_given"]) == 2
    )


async def test_the_library_fallback_never_repeats_what_was_given() -> None:
    manager = Manager("this is not json", free='{"ideas": []}')
    noted = [
        {
            "title": "Cash is short and stock goes missing",
            "user_words": ["chori ka shak hai"],
            "group": "loss_security",
        }
    ]
    _c, first = await run(manager, make_policy(), make_context(noted_problems=noted))
    given = [line for line in first.reply.splitlines() if line.startswith("•")]
    brief = {"library_given": [g.lstrip("• ") for g in given], "ideas_given": 2}
    _c, second = await run(manager, make_policy(), make_context(noted_problems=noted), brief)
    again = [line for line in second.reply.splitlines() if line.startswith("•")]
    assert not set(given) & set(again)


# --- the language the expert read the owner writing in (for a language the code does not know) ---

SWAHILI = "Nina duka la nguo na mauzo yamepungua sana, wateja hawarudi tena"


async def test_a_language_the_code_does_not_know_is_taken_from_the_expert_and_remembered() -> None:
    answer = diag([GOOD_ONE, GOOD_TWO]).replace(
        '"problem"', '"owner_language": "Swahili", "problem"', 1
    )
    context = make_context(latest_customer_message=SWAHILI)
    context.pop("reply_language", None)  # the code found nothing it knows
    conversation, turn = await run(Manager(answer), make_policy(judge=False), context)
    assert context["reply_language_other"] == "Swahili"
    assert conversation.service_brief["owner_language"] == "Swahili" and turn.reply.count("•") == 2


async def test_the_codes_own_detection_is_never_overridden_by_the_model() -> None:
    answer = diag([GOOD_ONE, GOOD_TWO]).replace(
        '"problem"', '"owner_language": "Swahili", "problem"', 1
    )
    context = make_context(reply_language="roman_ur")
    conversation, _turn = await run(Manager(answer), make_policy(judge=False), context)
    assert (
        "reply_language_other" not in context and "owner_language" not in conversation.service_brief
    )


async def test_english_or_nonsense_from_the_model_changes_nothing() -> None:
    for named in ("English", "unknown", "12345", "Roman Urdu"):
        answer = diag([GOOD_ONE, GOOD_TWO]).replace(
            '"problem"', f'"owner_language": "{named}", "problem"', 1
        )
        context = make_context()
        context.pop("reply_language", None)
        conversation, _turn = await run(Manager(answer), make_policy(judge=False), context)
        assert "reply_language_other" not in context, named
        assert "owner_language" not in conversation.service_brief, named


def test_the_diagnosis_parser_reads_the_language() -> None:
    from app.modules.pi import expert_advisor

    parsed = expert_advisor.parse_diagnosis(
        diag([GOOD_ONE]).replace('"problem"', '"owner_language": "Pashto", "problem"', 1)
    )
    assert parsed is not None and parsed.language == "Pashto"


def test_a_trade_outside_the_packs_is_the_one_the_owner_named() -> None:
    from app.modules.pi.service_conversation import trade_name

    named = SimpleNamespace(
        service_brief={
            "customer_profile": {"business_type": "school bus service"},
            "industry_confirmed": True,
        }
    )
    assert trade_name(named, []) == "school bus service"
    assert trade_name(SimpleNamespace(service_brief={}), []) is None
    pack = trade_name(named, ["restaurants"])
    assert pack and pack != "school bus service"  # a matched pack's own name wins
