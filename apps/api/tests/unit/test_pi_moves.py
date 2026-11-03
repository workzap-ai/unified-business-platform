# ruff: noqa: E501
"""The sixteen moves, the choice rules of spec 3.4, the hypothesis ledger (3.5), the plan (3.2)."""

import pytest

from app.modules.pi import dials as dials_mod
from app.modules.pi import moves
from app.modules.pi.dials import Dials, Mode, Pace, Trust
from app.modules.pi.moves import Move, Situation, Turn


def sit(mode: Mode = Mode.LISTEN, recent: list[Turn] | None = None, **flags: object) -> Situation:
    fatigue = bool(flags.pop("fatigue", False))
    trust = flags.pop("trust", Trust.FLAT)
    d = Dials(mode=mode, fatigue=fatigue, trust_trend=trust, pace=Pace.NORMAL)  # type: ignore[arg-type]
    return Situation(dials=d, recent=recent or [], **flags)  # type: ignore[arg-type]


def turn(move: Move, question: bool = True, gave: bool = True, landed: bool | None = None) -> Turn:
    return Turn(move, question, gave, landed)


def test_all_sixteen_moves_and_the_plain_ones_exist() -> None:
    keys = [m.value for m in Move]
    for n in range(1, 17):
        assert any(k.startswith(f"M{n}_") for k in keys), n
    for plain in ("ask", "invite", "give_ideas", "summarise"):
        assert plain in keys
    assert all(m in moves.INFO for m in Move)


def test_several_moves_carry_no_question() -> None:
    free = {m for m in Move if moves.question_free(m)}
    assert {Move.M1, Move.M2, Move.M6, Move.M11, Move.M12, Move.M14, Move.M16} <= free
    assert Move.M4 not in free and Move.M13 not in free and Move.M15 not in free


def test_parse_move_accepts_keys_and_names() -> None:
    assert moves.parse_move("M4_hypothesis") == Move.M4
    assert moves.parse_move("M4") == Move.M4
    assert moves.parse_move("nonsense") is None


def test_choose_by_the_dials_first() -> None:
    assert moves.choose(sit(Mode.LISTEN)).move == Move.M1
    assert moves.choose(sit(Mode.THINK)).move == Move.M3
    assert moves.choose(sit(Mode.FIX)).move == Move.M11  # ideas only when asked for
    assert moves.choose(sit(Mode.FIX, ideas_asked=True)).move == Move.GIVE_IDEAS
    assert moves.choose(sit(Mode.BUY)).move == Move.HONOUR


def test_every_choice_for_a_mode_comes_from_that_modes_pool() -> None:
    pools = {
        Mode.LISTEN: {Move.M1, Move.M16, Move.M8},
        Mode.THINK: {Move.M3, Move.M4, Move.M10, Move.M11, Move.M12},
        Mode.FIX: {Move.M11, Move.M13},
    }
    for mode, pool in pools.items():
        assert moves.choose(sit(mode, has_hypothesis=True, other_problem=True)).move in pool


def test_no_move_more_than_twice_in_the_last_four() -> None:
    recent = [turn(Move.M1), turn(Move.M1, question=False)]
    assert moves.choose(sit(Mode.LISTEN, recent)).move != Move.M1
    # two M1 outside the window of four no longer count
    old = [
        turn(Move.M1),
        turn(Move.M1),
        turn(Move.M16, question=False),
        turn(Move.M16, question=False),
        turn(Move.M11, question=False),
    ]
    assert moves.choose(sit(Mode.LISTEN, old)).move == Move.M1


def test_at_least_one_message_in_three_carries_no_question() -> None:
    recent = [turn(Move.M3), turn(Move.M4)]  # two questions in a row
    c = moves.choose(sit(Mode.THINK, recent, has_hypothesis=True))
    assert c.question_forbidden and not c.question_allowed
    assert moves.question_free(c.move)
    # one question-free message in the last two: a question is allowed again
    recent = [turn(Move.M3, question=False), turn(Move.M4)]
    assert moves.choose(sit(Mode.THINK, recent)).question_allowed


def test_never_two_question_only_messages_in_a_row() -> None:
    only = turn(Move.ASK, question=True, gave=False)
    assert only.question_only
    c = moves.choose(sit(Mode.THINK, [only]))
    assert c.must_give
    assert not moves.choose(sit(Mode.THINK, [turn(Move.M3)])).must_give


def test_fatigue_wins_over_method_and_gives_value_or_a_fork() -> None:
    c = moves.choose(sit(Mode.LISTEN, fatigue=True))
    assert c.move == Move.M13 and "fatigue" in c.reason
    assert (
        moves.choose(sit(Mode.THINK, fatigue=True, has_hypothesis=True)).move in moves.FATIGUE_POOL
    )
    # even a heavy mode pool gives way to fatigue, but a Buy request is honoured
    assert moves.choose(sit(Mode.BUY, fatigue=True)).move == Move.HONOUR


def test_a_move_that_did_not_land_is_not_repeated() -> None:
    c = moves.choose(sit(Mode.THINK, [turn(Move.M3, landed=False)]))
    assert c.move != Move.M3


def test_if_a_hypothesis_was_ignored_try_a_number_or_a_fork() -> None:
    ignored = [turn(Move.M4, landed=False)]
    assert moves.choose(sit(Mode.THINK, ignored, has_number=True)).move == Move.M2
    assert moves.choose(sit(Mode.THINK, ignored, has_number=False)).move == Move.M13


def test_gentle_challenge_never_when_upset_corrected_or_trust_falling() -> None:
    used = [turn(Move.M3, question=False), turn(Move.M3, question=False)]
    assert moves.choose(sit(Mode.THINK, used)).move == Move.M10
    for flag in ({"upset": True}, {"corrected": True}, {"trust": Trust.FALLING}):
        assert moves.choose(sit(Mode.THINK, used, **flag)).move != Move.M10, flag


def test_noticing_what_is_missing_at_most_once_in_three_messages() -> None:
    assert (
        moves.choose(sit(Mode.THINK, absence_to_notice=True)).move == Move.M3
    )  # not in the pool, so not chosen by default
    s = sit(Mode.THINK, [turn(Move.M9)], absence_to_notice=True)
    assert not moves._eligible(Move.M9, s)
    assert moves._eligible(Move.M9, sit(Mode.THINK, [turn(Move.M3)] * 3, absence_to_notice=True))


def test_numbers_and_links_need_something_to_work_with() -> None:
    assert not moves._eligible(Move.M2, sit())
    assert moves._eligible(Move.M2, sit(has_number=True))
    assert not moves._eligible(Move.M8, sit())
    assert moves._eligible(Move.M8, sit(other_problem=True))


# --- the worked examples of spec 3.10 and 8.1 ---------------------------------------------------


def test_restaurant_reading_then_a_testable_hypothesis() -> None:
    # "Khana kabhi achha kabhi kharab": M1 plus M3 plus a question; then M4 with a testable question.
    first = moves.choose(sit(Mode.THINK))
    assert first.move == Move.M3 and first.question_allowed
    second = moves.choose(sit(Mode.THINK, [turn(first.move)], has_hypothesis=True))
    assert second.move == Move.M4


def test_clinic_front_desk_reflects_meaning_before_asking() -> None:
    # "Patients appointment par nahi aate": a reflection (M1) with one question.
    c = moves.choose(sit(Mode.LISTEN))
    assert c.move == Move.M1 and c.question_allowed


def test_logistics_consequence_carries_no_question_by_itself() -> None:
    # "Delivery late hoti hai": the consequence (M6) is question-free; the question is added after.
    assert Move.M6 in moves.FALLBACK_POOL and moves.question_free(Move.M6)


def test_chat3_solution_dein_gives_ideas_and_may_end_with_a_sharpening_question() -> None:
    d = dials_mod.estimate(
        ["Hi", "6crore ka stock bechna hai", "30% sale lagayi thi, solution dein ap"]
    )
    assert d.mode == Mode.FIX
    c = moves.choose(Situation(dials=d, ideas_asked=True))
    assert c.move == Move.GIVE_IDEAS and c.question_allowed


def test_chat3_working_the_number_when_they_give_a_fraction() -> None:
    # "haan taqreeban aadha pichle saal ka hai": M2 work the number, then a contrast question.
    d = Dials(mode=Mode.FIX, openness=2)
    c = moves.choose(Situation(dials=d, has_number=True, fresh_number=True))
    assert c.move == Move.M2


def test_chat3_a_sensitive_disclosure_holds_space_even_in_fix_mode() -> None:
    d = Dials(mode=Mode.FIX, openness=3)
    c = moves.choose(Situation(dials=d, heavy=True, other_problem=True))
    assert c.move == Move.M16 and not c.question_forbidden


def test_chat3_four_problems_and_a_ready_map_show_the_map() -> None:
    d = Dials(mode=Mode.LISTEN, openness=3)
    c = moves.choose(Situation(dials=d, map_ready=True, other_problem=True))
    assert c.move == Move.M15


def test_chat3_replayed_with_the_rules_never_breaks_the_variety_rules() -> None:
    recent: list[Turn] = []
    d = Dials(mode=Mode.LISTEN, openness=2)
    for i in range(12):
        c = moves.choose(
            Situation(dials=d, recent=recent, other_problem=i % 2 == 0, has_number=True)
        )
        window = recent[-3:]
        assert sum(1 for t in window + [turn(c.move)] if t.move == c.move) <= 2 or len(window) < 3
        recent.append(
            Turn(c.move, question=c.question_allowed and not moves.question_free(c.move), gave=True)
        )
        # never three question-ending messages in a row
        assert not all(t.question for t in recent[-3:]) or len(recent) < 3


# --- the hypothesis ledger ----------------------------------------------------------------------


def test_only_the_owner_confirms_a_hypothesis() -> None:
    ledger = moves.HypothesisLedger()
    h = ledger.add(
        "Qeemat aur design dono rok rahe hain", evidence_for=["qeemat zyada", "design purane"]
    )
    assert h.status == moves.Status.OPEN and not ledger.may_state_as_fact(h)
    for who in ("pi", "model", "pack", ""):
        with pytest.raises(PermissionError):
            ledger.confirm(h, by=who)
    assert h.status == moves.Status.OPEN
    ledger.confirm(h, by="owner")
    assert h.status == moves.Status.CONFIRMED and ledger.may_state_as_fact(h)


def test_an_unconfirmed_hypothesis_is_labelled_in_the_solution_box() -> None:
    ledger = moves.HypothesisLedger()
    h = ledger.add("Staff trained badly")
    assert ledger.solution_label(h) is not None
    ledger.confirm(h, by="owner")
    assert ledger.solution_label(h) is None


def test_evidence_against_lowers_confidence_then_drops() -> None:
    ledger = moves.HypothesisLedger()
    h = ledger.add("Price", confidence=moves.Confidence.MEDIUM)
    ledger.against(h, "30% sale barely helped")
    assert h.confidence == moves.Confidence.LOW and h.status == moves.Status.OPEN
    ledger.against(h, "no one asked about price")
    assert h.status == moves.Status.DROPPED and ledger.open() == []


def test_the_leading_hypothesis_is_the_most_confident_open_one() -> None:
    ledger = moves.HypothesisLedger()
    ledger.add("A", confidence=moves.Confidence.LOW)
    b = ledger.add("B", confidence=moves.Confidence.MEDIUM)
    assert ledger.leading() is b
    b.ignored = True
    assert ledger.leading() is not b
    assert ledger.add("a").text == "A" and len(ledger.items) == 2  # the same text is one hypothesis


# --- the plan object ----------------------------------------------------------------------------

PLAN = {
    "dials": {"openness": 1, "pace": "fast", "mode": "fix", "trust_trend": "flat"},
    "known": ["goal: sell 6 crore of stock"],
    "unknown": ["cost or selling price"],
    "hypotheses": [
        {
            "text": "price and design hold it",
            "confidence": "medium",
            "test": "which outlet sells better",
        }
    ],
    "map_updates": [
        {
            "op": "add_node",
            "node": "stock to sell",
            "evidence": "6crore ka stock bechna hai",
            "message_id": "m2",
        }
    ],
    "move": "M4_hypothesis",
    "one_line_reason": "think mode, hypothesis ready",
    "ask": {"rung": "contrast", "slot": "better_outlet", "text": "Kahan behtar bikta hai?"},
}


def test_the_plan_round_trips_the_spec_shape() -> None:
    plan = moves.Plan.from_dict(PLAN)
    assert plan.to_dict() == PLAN
    assert moves.check_plan(plan) == []


def test_a_plan_with_an_unknown_move_or_untraceable_map_update_is_rejected() -> None:
    bad = {
        **PLAN,
        "move": "M99",
        "map_updates": [{"op": "add_node", "node": "x", "evidence": "", "message_id": None}],
    }
    problems = moves.check_plan(moves.Plan.from_dict(bad))
    assert any("unknown move" in p for p in problems)
    assert any("no evidence" in p for p in problems)


def test_a_plan_may_not_ask_when_the_variety_rules_forbid_a_question() -> None:
    plan = moves.Plan.from_dict(PLAN)
    choice = moves.choose(sit(Mode.THINK, [turn(Move.M3), turn(Move.M4)]))
    assert any("not allowed" in p for p in moves.check_plan(plan, choice))
    plan.ask = None
    assert moves.check_plan(plan, choice) == []


def test_a_model_plan_with_the_wrong_shapes_parses_to_empty_not_an_error() -> None:
    plan = moves.Plan.from_dict(
        {"known": "nope", "hypotheses": [1, "x"], "ask": "text", "dials": []}
    )
    assert plan.known == [] and plan.hypotheses == [] and plan.ask is None and plan.dials == {}
