# ruff: noqa: E501
"""The expert advisor inside brain_free_ideas and the diagnosis step (scripted model, no database)."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from test_pi_expert_advisor import (
    GOOD_ONE,
    GOOD_THREE,
    GOOD_TWO,
    NOTED,
    QUESTION,
    SHOWROOM,
    VIDEO_IDEA,
    diag,
    judge_of,
)

from app.modules.pi import expert_advisor
from app.modules.pi.service_conversation import brain_expert_diagnosis, brain_free_ideas

pytestmark = pytest.mark.asyncio

FREE = '{"ideas": ["Ask each recent buyer how they first heard of the showroom, so you see which way people really find you."]}'


class Manager:
    """expert calls by purpose; anything else is the older free-ideas call."""

    def __init__(self, diagnose: str, judge: str = "", free: str = FREE) -> None:
        self.answers = {"pi_expert_diag": diagnose, "pi_expert_judge": judge, "pi_free_ideas": free}
        self.calls: list[str] = []

    async def complete(self, scope: object, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs["purpose"])
        return SimpleNamespace(text=self.answers[kwargs["purpose"]])


def make_turn() -> Any:
    return SimpleNamespace(
        reply="",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
        _free=False,
        _english=False,
        _ideas_rejected=False,
    )


def make_policy(expert: bool = True, judge: bool = True) -> Any:
    brain: dict[str, Any] = {}
    if expert:
        brain["solution_source"] = "expert"
    if not judge:
        brain["expert_judge"] = False
    return SimpleNamespace(response_rules={"pi_mode": "brain", "brain": brain}, ai_config={})


def make_context(**extra: Any) -> dict[str, Any]:
    return {
        "solution_asked_no_ideas": True,
        "latest_customer_message": "give me a solution",
        "noted_problems": [NOTED[0]],
        "reply_language": "en",
        "history": [
            {"role": "customer", "text": SHOWROOM},
            {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. Noted: few walk-ins."},
        ],
        **extra,
    }


async def run(
    manager: Manager, policy: Any, context: dict[str, Any], brief: dict[str, Any] | None = None
):
    conversation = SimpleNamespace(id=None, service_brief=brief if brief is not None else {})
    turn = make_turn()
    await brain_free_ideas(manager, None, conversation, policy, turn, context)  # type: ignore[arg-type]
    return conversation, turn


async def test_the_expert_gives_grounded_ideas_counts_them_and_caches_the_diagnosis() -> None:
    manager = Manager(
        diag([VIDEO_IDEA, GOOD_ONE, GOOD_TWO, GOOD_THREE]),
        judge_of((0, 5), (1, 5), (2, 4), (3, 4), best=[0, 1]),
    )
    conversation, turn = await run(manager, make_policy(), make_context())
    bullets = [line for line in turn.reply.splitlines() if line.startswith("•")]
    assert len(bullets) == 2 and turn._free and turn.awaiting_customer and turn._english
    assert "video" not in turn.reply.lower() and "page" not in turn.reply.lower()
    brief = conversation.service_brief
    assert brief["ideas_given"] == 2
    assert expert_advisor.given_for(brief, NOTED[0]) == 2
    assert brief["expert_diag"]["causes"][0].startswith("people do not know")
    assert "pi_free_ideas" not in manager.calls  # the expert settled it
    assert turn.reply.count("?") == 0  # the offer line is the application's, added later


async def test_judge_off_in_settings_skips_the_judge_call() -> None:
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]))
    _conversation, turn = await run(manager, make_policy(judge=False), make_context())
    assert manager.calls == ["pi_expert_diag"] and turn.reply.count("•") == 2


async def test_when_nothing_survives_pi_asks_the_one_missing_fact_and_gives_no_idea() -> None:
    manager = Manager(diag([VIDEO_IDEA]), "")
    conversation, turn = await run(manager, make_policy(), make_context())
    assert turn.reply.endswith(QUESTION) and turn.reply.count("?") == 1
    assert "•" not in turn.reply and turn._free and turn.awaiting_customer
    assert conversation.service_brief.get("ideas_given", 0) == 0  # not counted as ideas given
    assert conversation.service_brief["expert_diag"]["question"] == QUESTION


async def test_the_second_ask_after_two_ideas_for_one_problem_is_not_answered_with_more() -> None:
    brief = expert_advisor.record_given({"ideas_given": 2}, NOTED[0], 2)
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]))
    conversation, turn = await run(manager, make_policy(), make_context(), brief)
    assert turn.reply == "" and manager.calls == []  # brain_no_ideas says the honest line next
    assert conversation.service_brief["ideas_given"] == 2


async def test_the_business_cap_of_eight_is_respected() -> None:
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]))
    _c, turn = await run(manager, make_policy(), make_context(), {"ideas_given": 8})
    assert turn.reply == "" and manager.calls == []


async def test_a_pipeline_that_returns_nothing_falls_back_to_the_free_ideas() -> None:
    manager = Manager("this is not json")
    conversation, turn = await run(manager, make_policy(), make_context())
    assert manager.calls == ["pi_expert_diag", "pi_free_ideas"]
    assert GOOD_ONE.rstrip(".") in turn.reply and conversation.service_brief["ideas_given"] == 1


async def test_with_the_flag_off_the_expert_is_never_called() -> None:
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]))
    conversation, turn = await run(manager, make_policy(expert=False), make_context())
    assert manager.calls == ["pi_free_ideas"]
    assert (
        "expert_diag" not in conversation.service_brief
        and "expert_given" not in conversation.service_brief
    )
    assert GOOD_ONE.rstrip(".") in turn.reply


async def test_sales_tracking_gets_an_idea_not_no_quick_idea() -> None:
    owner = "My sales team does not update the sheet, I never know who sold what. Please give me a solution"
    tracking = {
        "ref": "t1",
        "title": "Sales are not tracked by the team",
        "user_words": ["team does not update the sheet"],
        "cause": "",
    }
    idea = "Ask each salesperson to say aloud at the end of the day who they sold to, so the sheet and the sales match."
    ideas = json.loads(diag([idea, GOOD_TWO]))
    ideas["problem"] = "the team does not record sales"
    manager = Manager(json.dumps(ideas), judge_of((0, 5), (1, 3), best=[0]))
    context = make_context(
        latest_customer_message=owner,
        noted_problems=[tracking],
        history=[{"role": "customer", "text": owner}, {"role": "ai", "text": "Hi, I'm pi, an AI."}],
    )
    _c, turn = await run(manager, make_policy(), context)
    assert "quick idea" not in turn.reply and "•" in turn.reply


# --- the diagnosis step after the reply -------------------------------------------------------------


async def test_the_diagnosis_step_caches_once_then_waits_for_a_new_fact() -> None:
    manager = Manager(diag([GOOD_ONE]))
    conversation = SimpleNamespace(id=None, service_brief={})
    context = make_context()
    context.pop("solution_asked_no_ideas")
    policy = make_policy()
    turn = make_turn()
    await brain_expert_diagnosis(manager, None, conversation, policy, turn, context)  # type: ignore[arg-type]
    assert manager.calls == ["pi_expert_diag"]
    ask = expert_advisor.question_context(conversation.service_brief, [NOTED[0]])
    assert ask["suggested_next_question"] == QUESTION and ask["main_problem_causes"]
    await brain_expert_diagnosis(manager, None, conversation, policy, make_turn(), context)  # type: ignore[arg-type]
    assert manager.calls == ["pi_expert_diag"]  # cached: not recomputed
    richer = {**NOTED[0], "user_words": ["footfall is low", "a new showroom opened nearby"]}
    await brain_expert_diagnosis(
        manager, None, conversation, policy, make_turn(), {**context, "noted_problems": [richer]}
    )  # type: ignore[arg-type]
    assert manager.calls == ["pi_expert_diag", "pi_expert_diag"]  # a new fact refreshes it


async def test_the_diagnosis_step_is_off_without_the_flag_or_on_a_turn_that_gave_ideas() -> None:
    manager = Manager(diag([GOOD_ONE]))
    conversation = SimpleNamespace(id=None, service_brief={})
    await brain_expert_diagnosis(
        manager, None, conversation, make_policy(expert=False), make_turn(), make_context()
    )  # type: ignore[arg-type]
    free = make_turn()
    free._free = True
    await brain_expert_diagnosis(manager, None, conversation, make_policy(), free, make_context())  # type: ignore[arg-type]
    assert manager.calls == []
