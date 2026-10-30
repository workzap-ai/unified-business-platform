# ruff: noqa: E501
"""The cached diagnosis steers every next question while the problem is open (scripted model, no
database): no drift to an adjacent process (R-ASK-08), no repeated question, a cheap refresh when an
answer adds a fact and never two diagnosis calls in one turn; the idea caps per business and per
problem across chats; a different problem is not held back by the first one's cap."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from test_pi_expert_advisor import GOOD_ONE, GOOD_TWO, NOTED, diag, judge_of
from test_pi_expert_wiring import Manager, make_context, make_policy, make_turn, run

from app.modules.pi import constitution, expert_advisor, solution_context
from app.modules.pi.service_conversation import (
    brain_expert_diagnosis,
    brain_no_ideas,
    noted_with_turn,
)

pytestmark = pytest.mark.asyncio

FEE = {
    "ref": "p-fee",
    "title": "Parents pay the school fee late",
    "user_words": ["parents pay fee late every month"],
    "cause": "",
}
OTHER = {
    "ref": "p-staff",
    "title": "Teachers leave in the middle of the year",
    "user_words": ["teachers leave mid year"],
    "cause": "",
}
DRIFT = "Parents fee kaise jama karwate hain, challan, cash ya online?"
ON_THE_PROBLEM = "Wo kya wajah batate hain?"
SUGGESTED = "What reason do parents give when the fee comes late?"


def lint_context(**extra: Any) -> dict[str, Any]:
    return {
        "pi_mode": "brain",
        "expert_on": True,
        "flow": {"state": "S2_CLARIFYING"},
        "reply_language": "roman_ur",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "latest_customer_message": "cash",
        "main_problem": FEE["title"],
        "main_problem_words": FEE["user_words"][0],
        "main_problem_causes": ["no reminder before due date", "parents run short of money"],
        "suggested_next_question": SUGGESTED,
        **extra,
    }


def rules_of(reply: str, context: dict[str, Any]) -> set[str]:
    return {v.rule for v in constitution.lint(reply, context)}


# --- R-ASK-08 with a cached diagnosis ----------------------------------------------------------


async def test_r_ask_08_fires_on_how_parents_pay_when_the_diagnosis_is_about_late_fees() -> None:
    assert "R-ASK-08" in rules_of(DRIFT, lint_context())


async def test_r_ask_08_names_the_cached_question_for_the_rewrite() -> None:
    found = [v for v in constitution.lint(DRIFT, lint_context()) if v.rule == "R-ASK-08"]
    assert found and SUGGESTED[:40] in found[0].message


async def test_r_ask_08_is_quiet_on_a_question_that_looks_for_the_reason() -> None:
    assert "R-ASK-08" not in rules_of(ON_THE_PROBLEM, lint_context())
    assert "R-ASK-08" not in rules_of(
        "Fee kab late hoti hai, mahine ke shuru mein ya aakhir mein?", lint_context()
    )


async def test_r_ask_08_is_quiet_when_the_listed_cause_is_about_that_process() -> None:
    context = lint_context(main_problem_causes=["parents pay cash and forget the challan"])
    assert "R-ASK-08" not in rules_of(DRIFT, context)


async def test_the_adjacent_check_needs_the_expert_and_a_diagnosis() -> None:
    off = lint_context(expert_on=False)
    assert not constitution._adjacent_when_diagnosed(DRIFT, off)
    bare = lint_context(main_problem_causes=[], suggested_next_question="")
    assert not constitution._adjacent_when_diagnosed(DRIFT, bare)


# --- the question context ----------------------------------------------------------------------


def stored_diag(**extra: Any) -> dict[str, Any]:
    advice = expert_advisor.Advice(
        question=SUGGESTED, causes=["no reminder before due date"], problem="fee comes late"
    )
    return expert_advisor.remember({}, FEE, advice, 2) | extra


async def test_the_context_carries_the_causes_the_questions_asked_and_the_answers_since() -> None:
    brief = stored_diag()
    ask = expert_advisor.question_context(
        brief,
        [FEE],
        asked=["Fee kab late hoti hai?"],
        owner_messages=["parents fee late dete hain", "dosri tarikh ko", "cash"],
        owner_turns=3,
    )
    assert ask["suggested_next_question"] == SUGGESTED
    assert ask["main_problem_causes"] == ["no reminder before due date"]
    assert ask["questions_already_asked"] == ["Fee kab late hoti hai?"]
    assert ask["owner_answers_since"] == ["cash"]


async def test_a_question_pi_has_asked_is_not_offered_again() -> None:
    again = expert_advisor.question_context(stored_diag(), [FEE], asked=[SUGGESTED.upper()])
    assert "suggested_next_question" not in again
    spent = expert_advisor.mark_consumed(stored_diag(), "Wo kya wajah batate hain?")
    assert "suggested_next_question" not in expert_advisor.question_context(spent, [FEE])
    unchanged = expert_advisor.mark_consumed(stored_diag(), "That is all for today.")
    assert not unchanged["expert_diag"].get("consumed")


async def test_questions_in_takes_the_last_question_of_each_message() -> None:
    texts = ["Hi. Fee kab late hoti hai? Batayein.", "Sirf bayan.", "Kitne parents? Aur kab?"]
    assert expert_advisor.questions_in(texts) == ["Fee kab late hoti hai?", "Aur kab?"]
    assert expert_advisor.questions_in(["Fee kab late hoti hai?"]) == ["Fee kab late hoti hai?"]
    assert expert_advisor.same_question(
        "Why do parents pay the fee late?", "Why do parents pay late?"
    )
    assert not expert_advisor.same_question("Why do parents pay late?", "Which system tracks dues?")


async def test_owner_turns_are_counted_once_per_message() -> None:
    brief = expert_advisor.count_owner_turn({}, "m1", 3)
    assert brief["owner_n"] == 4
    assert expert_advisor.count_owner_turn(brief, "m1", 3)["owner_n"] == 4
    assert expert_advisor.count_owner_turn(brief, "m2", 3)["owner_n"] == 5


# --- the cheap refresh and no duplicate call ---------------------------------------------------


class Recorder(Manager):
    def __init__(self, diagnose: str) -> None:
        super().__init__(diagnose)
        self.payloads: list[dict[str, Any]] = []
        self.systems: list[str] = []
        self.tokens: list[int] = []

    async def complete(self, scope: object, **kwargs: Any) -> SimpleNamespace:
        if kwargs["purpose"] == "pi_expert_diag":
            self.systems.append(kwargs["messages"][0].text())
            self.payloads.append(json.loads(kwargs["messages"][-1].text()))
            self.tokens.append(kwargs["max_tokens"])
        return await super().complete(scope, **kwargs)


def light_answer(question: str = "Which month does the fee come latest?") -> str:
    return json.dumps(
        {
            "problem": "fee comes late",
            "causes": [{"cause": "no reminder before due date"}, {"cause": "money runs short"}],
            "missing_fact": "when it is latest",
            "question": question,
        }
    )


def fee_context(said: str, **extra: Any) -> dict[str, Any]:
    return make_context(
        noted_problems=[FEE],
        latest_customer_message=said,
        history=[
            {"role": "customer", "text": "Fee parents late dete hain"},
            {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. Wo kya wajah batate hain?"},
        ],
        **extra,
    ) | {"solution_asked_no_ideas": False}


async def test_an_answer_that_adds_a_fact_refreshes_the_diagnosis_cheaply_with_the_steering() -> (
    None
):
    manager = Recorder(light_answer())
    conversation = SimpleNamespace(id=None, service_brief=stored_diag() | {"owner_n": 3})
    turn = make_turn()
    turn.reply = "Samajh gaya. Wo kab tak de dete hain?"
    await brain_expert_diagnosis(
        manager, None, conversation, make_policy(), turn, fee_context("cash")
    )  # type: ignore[arg-type]
    assert manager.calls == ["pi_expert_diag"]
    payload = manager.payloads[0]
    assert '"ideas"' not in manager.systems[0]  # the light schema: no ideas
    assert manager.tokens[0] < 4000  # and a smaller call
    assert payload["facts_owner_already_answered"][-1] == "cash"
    assert any("wajah" in q for q in payload["questions_pi_already_asked"])
    assert payload["previous_diagnosis"]["causes"] == ["no reminder before due date"]
    assert any("Wo kab tak" in said for said in payload["pi_already_said_do_not_repeat_or_reword"])
    stored = conversation.service_brief["expert_diag"]
    assert stored["owner_turns"] == 3 and stored["question"].startswith("Which month")


async def test_an_ok_does_not_refresh_and_pi_asking_marks_the_cached_question_spent() -> None:
    manager = Recorder(light_answer())
    conversation = SimpleNamespace(id=None, service_brief=stored_diag() | {"owner_n": 3})
    turn = make_turn()
    turn.reply = "Fee kab late hoti hai?"
    await brain_expert_diagnosis(
        manager, None, conversation, make_policy(), turn, fee_context("ok")
    )  # type: ignore[arg-type]
    assert manager.calls == []
    assert conversation.service_brief["expert_diag"]["consumed"] is True


async def test_the_diagnosis_is_never_called_twice_in_one_turn() -> None:
    manager = Recorder(light_answer())
    conversation = SimpleNamespace(id=None, service_brief={})
    turn = make_turn()
    turn._expert_tried = True  # the ideas pipeline already ran (and failed) this turn
    await brain_expert_diagnosis(
        manager, None, conversation, make_policy(), turn, fee_context("cash")
    )  # type: ignore[arg-type]
    assert manager.calls == []
    fresh = make_turn()
    await brain_expert_diagnosis(
        manager, None, conversation, make_policy(), fresh, fee_context("cash")
    )  # type: ignore[arg-type]
    assert manager.calls == ["pi_expert_diag"] and fresh._expert_tried is True


async def test_a_repeated_question_from_the_model_is_dropped_not_asked() -> None:
    first = "What reason do parents give when the fee comes late?"
    manager = Recorder(light_answer(first))
    conversation = SimpleNamespace(id=None, service_brief={"owner_n": 2})
    turn = make_turn()
    turn.reply = first  # pi is asking exactly this now
    context = fee_context("cash")
    await brain_expert_diagnosis(manager, None, conversation, make_policy(), turn, context)  # type: ignore[arg-type]
    assert conversation.service_brief["expert_diag"]["question"] == ""


# --- the idea caps across chats and per problem --------------------------------------------------


async def test_the_business_cap_counts_the_other_chats() -> None:
    assert solution_context.allowance({"ideas_elsewhere": 6}, 1) == 1
    assert solution_context.allowance({"ideas_elsewhere": 6}, 2) == 0
    assert solution_context.allowance({}, 2) == 6  # one chat: as before
    declined = {"declines": 1, "ideas_at_decline": 2, "ideas_elsewhere": 6}
    assert solution_context.allowance(declined, 3) == 1  # after a decline only this chat counts


async def test_a_new_chat_of_a_business_that_had_eight_gets_no_more_ideas() -> None:
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]))
    brief = {"ideas_elsewhere": 8}
    conversation, turn = await run(manager, make_policy(), make_context(), brief)
    assert turn.reply == "" and manager.calls == []
    assert "ideas_given" not in conversation.service_brief  # nothing was given here


async def test_the_room_left_in_the_business_limits_the_ideas_given() -> None:
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]), judge_of((0, 5), (1, 5), best=[0, 1]))
    conversation, turn = await run(manager, make_policy(), make_context(), {"ideas_elsewhere": 7})
    assert turn.reply.count("•") == 1
    assert conversation.service_brief["ideas_given"] == 1


async def test_two_ideas_for_a_problem_in_another_chat_close_it_here() -> None:
    brief = {"expert_given_elsewhere": {"showroom-ref": 1, NOTED[0]["title"]: 1}}
    assert expert_advisor.given_for(brief, NOTED[0]) == 1
    both = {
        "expert_given_elsewhere": {NOTED[0]["title"]: 1},
        "expert_given": {NOTED[0]["title"]: 1},
    }
    assert expert_advisor.given_for(both, NOTED[0]) == 2
    manager = Manager(diag([GOOD_ONE, GOOD_TWO]))
    _c, turn = await run(manager, make_policy(), make_context(), both)
    assert turn.reply == "" and manager.calls == []


async def test_the_given_count_reads_the_problem_by_ref_or_by_title() -> None:
    brief = {"expert_given": {"p-fee": 1, FEE["title"]: 1}}
    assert expert_advisor.given_for(brief, FEE) == 2
    assert (
        expert_advisor.given_for(brief, {"title": FEE["title"]}) == 1
    )  # noted this turn: no ref yet


async def test_a_different_problem_is_not_blocked_by_the_cap_of_the_first() -> None:
    capped = expert_advisor.record_given({"ideas_given": 2}, FEE, 2)
    assert expert_advisor.main_problem([FEE, OTHER], capped) is OTHER  # FEE is closed for ideas
    assert expert_advisor.main_problem([FEE, OTHER]) is OTHER  # no brief: the latest, as before
    ranked = [{**FEE, "rank": 1}, {**OTHER, "rank": 2}]
    assert expert_advisor.main_problem(ranked) is ranked[0]
    assert expert_advisor.main_problem(ranked, capped) is ranked[1]
    assert expert_advisor.main_problem([FEE], capped) is FEE  # nothing else open: the first stays
    only_ranked = expert_advisor.main_problem(ranked, {})
    assert only_ranked is ranked[0]


async def test_ideas_for_the_new_problem_after_the_first_was_capped() -> None:
    ideas = "Ask each teacher who leaves what finally made them decide, so you see the real reason before the next one goes."
    manager = Manager(diag([ideas, GOOD_TWO]), judge_of((0, 5), (1, 5), best=[0, 1]))
    capped = expert_advisor.record_given({"ideas_given": 2}, FEE, 2)
    context = make_context(
        noted_problems=[FEE],
        latest_customer_message="teachers bhi chhod jate hain, solution do",
        history=[
            {"role": "customer", "text": "Fee parents late dete hain"},
            {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. Wo kya wajah batate hain?"},
        ],
    )
    from app.modules.pi.problems import ProblemNote

    note = ProblemNote(title=OTHER["title"], user_words=["teachers leave mid year"])
    turn = make_turn()
    turn.problem_ops = [SimpleNamespace(op="create", note=note)]
    conversation = SimpleNamespace(id=None, service_brief=capped)
    from app.modules.pi.service_conversation import brain_free_ideas

    await brain_free_ideas(manager, None, conversation, make_policy(), turn, context)  # type: ignore[arg-type]
    assert manager.calls[0] == "pi_expert_diag"
    assert (
        turn.reply.count("•") == 2
    )  # the new problem got its two, in spite of the first one's cap
    brief = conversation.service_brief
    assert expert_advisor.given_for(brief, {"title": OTHER["title"]}) == 2
    assert expert_advisor.given_for(brief, FEE) == 2 and brief["ideas_given"] == 4


async def test_noted_with_turn_adds_the_problem_this_message_creates() -> None:
    from app.modules.pi.problems import ProblemNote

    turn = make_turn()
    turn.problem_ops = [SimpleNamespace(op="create", note=ProblemNote(title="Stock is stuck"))]
    noted, fresh = noted_with_turn({"noted_problems": [FEE]}, turn)
    assert [p["title"] for p in noted] == [FEE["title"], "Stock is stuck"]
    assert fresh is noted[-1]
    assert noted_with_turn({"noted_problems": [FEE]}, make_turn())[1] is None


# --- "no more ideas here" is per problem ---------------------------------------------------------


def no_idea_context(**extra: Any) -> dict[str, Any]:
    return {
        "expert_on": True,
        "solution_asked_no_ideas": True,
        "latest_customer_message": "solution do",
        "flow": {"state": "S3_NOTED"},
        "reply_language": "en",
        "ideas_given": 2,
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        **extra,
    }


async def test_the_no_more_ideas_line_is_for_a_capped_problem_not_for_a_new_one() -> None:
    new_problem = make_turn()
    brain_no_ideas(new_problem, no_idea_context())
    assert "quick idea" in new_problem.reply  # ideas went to another problem: this one has none yet
    capped = make_turn()
    capped._problem_capped = True
    brain_no_ideas(capped, no_idea_context())
    assert "did not help" in capped.reply  # spec v1.6 19.6: ask what they tried, never "no more ideas"
    assert capped.reply.count("?") == 1


async def test_without_the_expert_the_chat_wide_line_is_unchanged() -> None:
    turn = make_turn()
    brain_no_ideas(turn, no_idea_context(expert_on=False))
    assert "did not help" in turn.reply


async def test_the_linter_counts_the_ideas_of_the_other_chats() -> None:
    from test_pi_value_line_gaps import WITH_LINE

    context = {
        "pi_mode": "brain",
        "flow": {"state": "S5_READINESS"},
        "reply_language": "en",
        "ideas_given": 0,
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "latest_customer_message": "stock keeps running out",
    }
    two = (
        "1. Give each ad a code, to see which works.\n2. Ask who sent them, to learn why."
        + WITH_LINE
    )
    assert "R-VAL-02" in rules_of(two, {**context, "ideas_given": 3, "ideas_elsewhere": 4})
    assert "R-VAL-02" not in rules_of(two, {**context, "ideas_given": 3})
    assert "R-VAL-02" not in rules_of(two, {**context, "ideas_given": 3, "ideas_elsewhere": 3})
