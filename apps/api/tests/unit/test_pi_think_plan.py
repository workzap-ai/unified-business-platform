# ruff: noqa: E501
"""The plan on the wire (Book 5, spec 3.2): schema, validation, rewrite instruction, fallback, the
moves fed back from history, and the ideas cap of decision 5."""

from types import SimpleNamespace
from typing import Any

from app.modules.pi import moves, solution_context, think_lint, think_plan, think_prompt, value_line
from app.modules.pi.service_conversation import ServiceTurn, ThinkingServiceTurn

OWNER = "Meri dukan mein maal purana hai aur gahak kam aa rahe hain"
ASKING = "Kaun si cheez sab se pehle theek karni hai, maal ya gahak?"
GIVING = "Purana maal paisa roke rakhta hai, aur wahi paisa naye maal ke liye chahiye hota hai."


def ctx(
    history: list[dict[str, Any]] | None = None, latest: str = OWNER, **extra: Any
) -> dict[str, Any]:
    return {"history": history or [], "latest_customer_message": latest, "thinking": True, **extra}


def plan(**kw: Any) -> think_plan.MovePlan:
    base: dict[str, Any] = {
        "move": "M1_reflect",
        "reason": "they just opened up",
        "asks_question": False,
    }
    base.update(kw)
    return think_plan.MovePlan(**base)


def test_the_schema_is_only_on_the_thinking_turn() -> None:
    assert "move_plan" not in ServiceTurn.model_fields
    assert "move_plan" in ThinkingServiceTurn.model_fields
    turn = ThinkingServiceTurn(reply="Theek hai.", language="en")
    assert turn.move_plan.move == "" and turn.move_plan.hypothesis.action == "none"


def test_a_malformed_plan_never_fails_the_parse() -> None:
    turn = ThinkingServiceTurn.model_validate(
        {"reply": "ok", "language": "en", "move_plan": "nonsense"}
    )
    assert turn.move_plan.move == ""
    turn = ThinkingServiceTurn.model_validate(
        {
            "reply": "ok",
            "language": "en",
            "move_plan": {
                "move": "M1_reflect",
                "reason": "x" * 900,
                "hypothesis": {"action": "confirm"},
            },
        }
    )
    assert len(turn.move_plan.reason) == 300 and turn.move_plan.hypothesis.action == "none"


def test_a_valid_plan_passes() -> None:
    assert think_plan.problems(plan(), GIVING, ctx()) == []
    assert think_plan.check_turn(SimpleNamespace(move_plan=plan(), reply=GIVING), ctx()) == ""


def test_an_unknown_move_and_a_missing_reason_are_refused() -> None:
    found = think_plan.problems(plan(move="M99_magic", reason=""), GIVING, ctx())
    assert any("unknown move" in f for f in found) and any("no reason" in f for f in found)


def test_asks_question_must_match_the_reply() -> None:
    assert any(
        "asks_question" in f for f in think_plan.problems(plan(asks_question=True), GIVING, ctx())
    )
    assert any(
        "asks_question" in f for f in think_plan.problems(plan(asks_question=False), ASKING, ctx())
    )
    assert think_plan.problems(plan(move="M13_fork", asks_question=True), ASKING, ctx()) == []


def test_a_question_free_move_cannot_carry_a_question() -> None:
    quiet = next(m for m in moves.Move if moves.question_free(m))
    found = think_plan.problems(plan(move=quiet.value, asks_question=True), ASKING, ctx())
    assert any("carries no question" in f for f in found)


def test_one_in_three_without_a_question_is_enforced_from_the_moves_in_history() -> None:
    history = [
        {"role": "customer", "text": "kya karun"},
        {"role": "ai", "text": ASKING, "move": "M13_fork"},
        {"role": "customer", "text": "pata nahi"},
        {
            "role": "ai",
            "text": "Kya aap ko lagta hai ke ye bara masla hai?",
            "move": "M11_prioritise",
        },
    ]
    found = think_plan.problems(plan(move="M13_fork", asks_question=True), ASKING, ctx(history))
    assert any("not allowed" in f for f in found)


def test_a_hypothesis_update_needs_a_text() -> None:
    bad = plan(hypothesis=think_plan.HypothesisUpdate(action="add"))
    assert any("names no hypothesis" in f for f in think_plan.problems(bad, GIVING, ctx()))


def test_the_instruction_is_clear_and_lists_the_moves() -> None:
    text = think_plan.instruction(["unknown move 'x'"])
    assert (
        text.startswith("your move_plan is not valid") and "M1_reflect" in text and "reason" in text
    )


def test_a_plan_still_bad_becomes_the_code_fallback_never_the_models() -> None:
    bad = plan(move="M99_magic", reason="")
    turn = SimpleNamespace(move_plan=bad, reply=GIVING)
    context = ctx()
    think_plan.settle_turn(turn, context)
    assert moves.parse_move(turn.move_plan.move) is not None
    assert (
        turn.move_plan.reason.startswith("code fallback") and turn.move_plan.asks_question is False
    )
    assert context["plan"] == {"move": turn.move_plan.move}


def test_a_valid_plan_is_kept_and_feeds_the_repeat_check() -> None:
    turn = SimpleNamespace(move_plan=plan(), reply=GIVING)
    context = ctx(
        [
            {"role": "ai", "text": GIVING, "move": "M1_reflect"},
            {"role": "ai", "text": GIVING + " Haan.", "move": "M1_reflect"},
        ]
    )
    think_plan.settle_turn(turn, context)
    assert turn.move_plan.reason == "they just opened up"
    # two earlier M1 plus this one: T-REPEAT now fires in production, from stored moves
    assert {f.rule for f in think_lint.think_flags(GIVING, context)} >= {"T-REPEAT-01"}


def test_history_moves_reach_the_prompt_and_the_choice() -> None:
    history = [
        {"role": "ai", "text": ASKING, "move": "M13_fork"},
        {"role": "ai", "text": ASKING, "move": "M11_prioritise"},
        {"role": "ai", "text": "Theek hai"},  # no stored move: skipped
    ]
    context = ctx(history)
    assert [t.move for t in think_prompt.recent_turns(context)] == [moves.Move.M13, moves.Move.M11]
    text = think_prompt.block(context)
    assert "move_plan" in text and "Your last moves, oldest first: M13_fork, M11_prioritise" in text
    assert think_prompt.block({"history": [], "latest_customer_message": OWNER}) == ""


def test_the_move_of_a_reply_the_application_wrote_is_not_the_models() -> None:
    summary = SimpleNamespace(move_plan=plan(), _summary=True, _decision=None)
    assert think_plan.move_of_sent(summary).move == moves.Move.SUMMARISE.value
    gate = SimpleNamespace(
        move_plan=plan(), _summary=False, _decision=SimpleNamespace(reply="fixed")
    )
    assert think_plan.move_of_sent(gate).move == moves.Move.HONOUR.value
    assert think_plan.move_of_sent(SimpleNamespace(_summary=False)) is None  # thinking off: no plan


# --- decision 5: the free ideas cap ---------------------------------------------------------


def test_free_ideas_are_two_per_problem_up_to_eight_per_business() -> None:
    assert value_line.IDEAS_PER_PROBLEM == 2 and value_line.IDEAS_PER_MESSAGE == 2
    assert value_line.IDEAS_BEFORE_OFFER == 8
    assert solution_context.allowance({}, 0) == 8
    assert solution_context.allowance({}, 7) == 1
    assert solution_context.allowance({}, 8) == 0
    # after a declined offer the old rule stands: two more, for a new problem only
    assert solution_context.allowance({"declines": 1, "ideas_at_decline": 8}, 8) == 2
