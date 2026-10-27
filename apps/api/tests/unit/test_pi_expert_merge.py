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
