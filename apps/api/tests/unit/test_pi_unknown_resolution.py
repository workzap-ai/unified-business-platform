"""PS-5: the unknown-resolution selector (pure; no database, no model).

Golden tests per function, property tests (never asks a stored fact, never repeats, one question
mark, the chosen key maps to at least one unknown decision), a 1000-case fuzz that must never raise,
growth-ratio timing tests, and 200+ multilingual adversarial answers. The gate itself is never
changed: every test that needs verdicts gets them from the real `option_gate.gate_options`.
"""

import ast
import random
import time
from pathlib import Path

import pytest

from app.modules.pi import constraint_check as cc
from app.modules.pi import option_gate as og
from app.modules.pi import unknown_resolution as ur
from app.modules.pi import unknown_resolution_lexicon as lx
from app.modules.pi.requirements_types import (
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
    TriedItem,
)

LANGS = ("en", "roman_ur", "ur", "ar")


def reqs(
    budget: str | None = None,
    staff: str | None = None,
    deadline: str | None = None,
    cannot: tuple[str, ...] = (),
    tried: tuple[tuple[str, str], ...] = (),
    number: int = 1,
    extra: tuple[ProblemRequirements, ...] = (),
) -> Requirements:
    p = ProblemRequirements(
        number=number,
        title="p",
        constraints=Constraints(
            budget=Limit(budget) if budget else None,
            staff=Limit(staff) if staff else None,
            deadline=Limit(deadline) if deadline else None,
            cannot_change=tuple(Limit(c) for c in cannot),
        ),
        tried=tuple(TriedItem(w, o) for w, o in tried),
    )
    return Requirements(problems=(p, *extra))


def gate(options: list[str], r: Requirements, language: str = "en") -> og.GateResult:
    return og.gate_options(options, r, language)


def unknown(rule: str, reason: str) -> cc.Verdict:
    return cc.Verdict("unknown", rule, (), reason)


# ------------------------------------------------------------------- reason classification

REASONS = [
    ("the budget states only a minimum", ur.Code.BUDGET_FLOOR_ONLY),
    ("no figure in the budget text", ur.Code.BUDGET_NO_FIGURE),
    ("the staff limit could not be read as a number of people", ur.Code.STAFF_LIMIT_UNREADABLE),
    (
        "the deadline is not a duration this check can read (a date needs a calendar)",
        ur.Code.DEADLINE_UNREADABLE,
    ),
    ("the option's figure is in another currency than the budget", ur.Code.CURRENCY_MISMATCH),
    (
        "the option's figure covers another period (monthly, yearly) than the budget",
        ur.Code.PERIOD_MISMATCH,
    ),
    (
        "a figure above the budget could not be attributed (cost or income)",
        ur.Code.FIGURE_UNATTRIBUTED,
    ),
    ("the stated limit could not be read (script, wording or too vague)", ur.Code.LIMIT_VAGUE),
    ("the limit's verb is not one this check enforces", ur.Code.VERB_UNENFORCED),
    ("the limit's verb is not known and the option names its object", ur.Code.VERB_UNENFORCED),
    (
        "the limit names only a generic object, so the option cannot be compared",
        ur.Code.GENERIC_OBJECT,
    ),
    (
        "the option shares only part of, or a generic word with, what is ruled out",
        ur.Code.SHARED_PART,
    ),
    ("the option names a place this check does not know", ur.Code.PLACE_UNKNOWN),
    ("the option expands without naming where", ur.Code.OPTION_EXPANDS),
    ("the option needs space and states no size in the limit's unit", ur.Code.SIZE_UNIT_UNKNOWN),
    ("renting may also cost what the owner said they cannot afford", ur.Code.RENT_MAY_COST),
    (
        "an outcome the owner cannot afford is named, with no sign that it is avoided",
        ur.Code.OUTCOME_UNAVOIDED,
    ),
    (
        "the option repeats something the owner tried, and how it went is not clear",
        ur.Code.TRIED_UNCLEAR,
    ),
    ("a thing the owner tried has no words this check can compare", ur.Code.TRIED_NO_WORDS),
    ("a thing the owner tried is not in a script this check can read", ur.Code.TRIED_SCRIPT),
    ("the option overlaps with something that failed", ur.Code.TRIED_OVERLAP),
    ("the option is not in a script this check can read", ur.Code.OPTION_SCRIPT),
    ("the option is too long to be read reliably", ur.Code.OPTION_TOO_LONG),
    ("the option text is empty", ur.Code.OPTION_EMPTY),
    ("the option is not text", ur.Code.OPTION_NOT_TEXT),
    ("the option involves spending and states no cost figure", ur.Code.OPTION_NO_COST),
    ("the option adds people and names no count", ur.Code.OPTION_NO_COUNT),
    ("the option mentions people and its count cannot be read", ur.Code.OPTION_NO_COUNT),
    (
        "the option states no timeframe, so the deadline cannot be compared",
        ur.Code.OPTION_NO_TIMEFRAME,
    ),
    (
        "the option's timeframe is longer than the deadline (2 days); it plainly cannot meet it",
        ur.Code.DEADLINE_EXCEEDED,
    ),
    (
        "part of the option is spaced out letter by letter and cannot be read reliably",
        ur.Code.SPACED_OUT,
    ),
    ("the owner's requirements could not be read from the database", ur.Code.COLUMNS_UNAVAILABLE),
    ("the requirements are not in a form this check reads", ur.Code.REQUIREMENTS_UNREADABLE),
    ("the option or the requirements could not be read", ur.Code.REQUIREMENTS_UNREADABLE),
]


@pytest.mark.parametrize(("reason", "code"), REASONS)
def test_classify_reason_golden(reason: str, code: ur.Code) -> None:
    assert ur.classify_reason(reason) is code


def test_classify_unrecognised_and_junk() -> None:
    assert ur.classify_reason("something new the gate says") is ur.Code.UNRECOGNISED
    assert ur.classify_reason(None) is ur.Code.UNRECOGNISED
    assert ur.classify_reason(42) is ur.Code.UNRECOGNISED
    assert ur.classify_reason("") is ur.Code.UNRECOGNISED


def test_every_reason_the_gate_can_give_is_classified() -> None:
    """Drift guard: every string literal given to `_unknown` / `_unreadable` in constraint_check.py
    classifies to something other than UNRECOGNISED."""
    source = Path(cc.__file__).read_text(encoding="utf-8")
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
            "_unknown",
            "_unreadable",
        }:
            for arg in node.args:
                for sub in ast.walk(arg):
                    if (
                        isinstance(sub, ast.Constant)
                        and isinstance(sub.value, str)
                        and sub.value[:1].isalpha()
                        and len(sub.value) > 15
                    ):
                        found.append(sub.value)
    assert len(found) >= 25
    unclassified = [r for r in found if ur.classify_reason(r) is ur.Code.UNRECOGNISED]
    assert unclassified == []


def test_every_code_has_a_resolution_entry() -> None:
    assert set(ur._CODE_FACT) == set(ur.Code)


def test_every_resolving_fact_exists_and_has_a_template() -> None:
    for resolution, fact in ur._CODE_FACT.values():
        if fact is not None:
            assert resolution is ur.Resolution.ASK_OWNER
            assert fact in ur.FACTS
            assert fact in lx.QUESTIONS


# ------------------------------------------------------------------------- explain_unknowns


def test_explain_golden_vague_budget_english() -> None:
    r = reqs(budget="as little as possible")
    opts = ["Buy a booking tool for the salon", "Ask regulars to rebook before they leave"]
    g = gate(opts, r)
    ex = ur.explain_unknowns(g, r, opts)
    assert [e.code for e in ex] == [ur.Code.BUDGET_NO_FIGURE, ur.Code.BUDGET_NO_FIGURE]
    assert [e.index for e in ex] == [0, 1]
    assert all(e.fact == "budget_ceiling" and e.owner_answerable for e in ex)
    assert ex[0].problems == (1,)
    assert ex[0].rule == cc.RULE_BUDGET


def test_explain_skips_ok_and_violating_options() -> None:
    r = reqs(staff="only 2 people")
    opts = ["Hire 5 new staff", "Use a shared sheet", "Hire 1 new assistant"]
    g = gate(opts, r)
    assert [x.option for x in g.rejected] == ["Hire 5 new staff"]
    ex = ur.explain_unknowns(g, r, opts)
    assert all(e.option != "Hire 5 new staff" for e in ex)


def test_explain_from_aligned_verdict_list() -> None:
    r = reqs(budget="no idea")
    opts = ["Buy a tool", "Call tenants"]
    verdicts = [cc.check_option(o, r) for o in opts]
    ex = ur.explain_unknowns(verdicts, r, opts)
    assert [e.option for e in ex] == [
        o for o, v in zip(opts, verdicts, strict=True) if v.status == "unknown"
    ]


def test_explain_index_follows_position_in_options() -> None:
    r = reqs(budget="no idea")
    opts = ["Call every tenant by phone", "Buy a tool", "Open a new branch"]
    g = gate(opts, r)
    ex = ur.explain_unknowns(g, r, opts)
    for e in ex:
        assert opts[e.index] == e.option


def test_explain_option_side_unknowns_are_not_owner_answerable() -> None:
    r = reqs(budget="50000 PKR per month")
    opts = ["Buy a new oven for the kitchen"]
    g = gate(opts, r)
    ex = ur.explain_unknowns(g, r, opts)
    assert ex[0].code is ur.Code.OPTION_NO_COST
    assert ex[0].resolution is ur.Resolution.REDRAFT_OPTION
    assert not ex[0].owner_answerable


def test_explain_urdu_option_is_unreadable_not_a_question() -> None:
    r = reqs(cannot=("we cannot hire anyone",))
    opts = ["ہر کرایہ دار کو یاد دہانی کا پیغام بھیجیں"]
    g = gate(opts, r, "ur")
    ex = ur.explain_unknowns(g, r, opts)
    assert ex and ex[0].code is ur.Code.OPTION_SCRIPT
    assert ex[0].resolution is ur.Resolution.UNREADABLE
    assert ex[0].fact is None


def test_explain_columns_unavailable() -> None:
    r = Requirements(columns_available=False)
    g = gate(["Do something"], r)
    ex = ur.explain_unknowns(g, r, ["Do something"])
    assert ex[0].code is ur.Code.COLUMNS_UNAVAILABLE and not ex[0].owner_answerable


def test_explain_option_too_long() -> None:
    r = reqs(budget="no idea")
    long = "buy " * 2000
    g = gate([long], r)
    ex = ur.explain_unknowns(g, r, [long])
    assert ex[0].code is ur.Code.OPTION_TOO_LONG
    assert len(ex[0].option) <= ur.MAX_OPTION_CHARS


def test_explain_no_requirements_given() -> None:
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    ex = ur.explain_unknowns(v, None, ["Buy a tool"])
    assert ex[0].code is ur.Code.BUDGET_NO_FIGURE
    assert ex[0].problems == ()


def test_explain_junk_inputs_return_empty() -> None:
    for junk in (None, 5, "abc", b"x", {"a": 1}, object(), [None, 3, "x"], [[]]):
        assert ur.explain_unknowns(junk, None, None) == ()


def test_explain_is_deterministic() -> None:
    r = reqs(budget="no idea", staff="a few")
    opts = ["Buy a tool", "Hire someone", "Ask friends"]
    g = gate(opts, r)
    assert ur.explain_unknowns(g, r, opts) == ur.explain_unknowns(g, r, opts)


# ------------------------------------------------------------------ rank_missing_information


def test_rank_orders_by_options_addressed_then_problems_then_priority() -> None:
    r = reqs(budget="no idea", staff="a few")
    verdicts = [
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
    ]
    opts = ["a", "b", "c"]
    ranked = ur.rank_missing_information(verdicts, r, opts)
    assert [m.key for m in ranked] == ["budget_ceiling", "staff_headcount"]
    assert ranked[0].options == (1, 2) and ranked[1].options == (0,)


def test_rank_tie_break_is_the_fixed_priority() -> None:
    r = reqs(budget="no idea", staff="a few", deadline="soonish")
    verdicts = [
        unknown(cc.RULE_DEADLINE, "the deadline is not a duration this check can read"),
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
    ]
    ranked = ur.rank_missing_information(verdicts, r, ["a", "b", "c"])
    assert [m.key for m in ranked] == ["budget_ceiling", "staff_headcount", "deadline_duration"]


def test_rank_problem_count_is_the_secondary_score() -> None:
    p2 = ProblemRequirements(number=2, constraints=Constraints(budget=Limit("no idea"), staff=None))
    p1 = ProblemRequirements(
        number=1, constraints=Constraints(budget=Limit("no idea"), staff=Limit("a few"))
    )
    r = Requirements(problems=(p1, p2))
    verdicts = [
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
    ]
    ranked = ur.rank_missing_information(verdicts, r, ["a", "b"])
    assert [m.key for m in ranked] == ["budget_ceiling", "staff_headcount"]
    assert ranked[0].problems == (1, 2) and ranked[1].problems == (1,)


def test_rank_skips_stored_fact() -> None:
    r = reqs(budget="50000 PKR per month")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    ranked = ur.rank_missing_information(v, r, ["a"])
    assert [(m.key, m.status) for m in ranked] == [("budget_ceiling", "stored")]
    assert not ranked[0].askable


def test_rank_skips_fact_answered_in_chat() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    ranked = ur.rank_missing_information(v, r, ["a"], owner_messages=["my budget is 40k PKR"])
    assert ranked[0].status == "answered_in_chat"


def test_rank_asked_once_is_exhausted_until_a_non_answer() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    assert (
        ur.rank_missing_information(v, r, ["a"], asked=["budget_ceiling"])[0].status == "exhausted"
    )
    again = ur.rank_missing_information(
        v, r, ["a"], asked=["budget_ceiling"], non_answers={"budget_ceiling": 1}
    )
    assert again[0].askable and again[0].reask
    third = ur.rank_missing_information(
        v, r, ["a"], asked=["budget_ceiling", "budget_ceiling"], non_answers={"budget_ceiling": 2}
    )
    assert third[0].status == "exhausted"


def test_rank_set_of_asked_keys_counts_once() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    out = ur.rank_missing_information(
        v, r, ["a"], asked={"budget_ceiling"}, non_answers={"budget_ceiling": 1}
    )
    assert out[0].askable and out[0].reask


def test_rank_include_zero_lists_every_catalogue_fact() -> None:
    out = ur.rank_missing_information([], reqs(), [], include_zero=True)
    assert {m.key for m in out} == set(ur.FACTS)
    assert all(m.n_options == 0 for m in out)


def test_rank_default_leaves_out_facts_that_address_nothing() -> None:
    assert ur.rank_missing_information([], reqs(), []) == ()


def test_rank_askable_before_skipped_even_with_fewer_options() -> None:
    r = reqs(budget="no idea", staff="a few")
    v = [
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
    ]
    out = ur.rank_missing_information(v, r, ["a", "b", "c"], asked=["budget_ceiling"])
    assert [m.key for m in out] == ["staff_headcount", "budget_ceiling"]


def test_rank_junk_does_not_raise() -> None:
    assert (
        ur.rank_missing_information(None, None, None, owner_messages=5, asked=7, non_answers=[1])
        == ()
    )


# ----------------------------------------------------------------------------- choose_question


def test_choose_golden_english_budget() -> None:
    r = reqs(budget="as little as possible")
    opts = ["Buy a booking tool", "Run a promotion on slow days"]
    g = gate(opts, r)
    q = ur.choose_question(g, r, opts, language="en")
    assert q is not None
    assert q.key == "budget_ceiling"
    assert q.text == "What is the most you could put towards this?"
    assert q.options == (0, 1)
    assert q.field == "budget"
    assert q.why and q.why[0].startswith("Buy a booking tool")
    assert q.target_limits == ("as little as possible",)
    assert not q.reask


@pytest.mark.parametrize("language", LANGS)
@pytest.mark.parametrize("key", sorted(lx.QUESTIONS))
def test_every_template_is_linted(key: str, language: str) -> None:
    text = ur.render_question(key, language)
    assert text
    assert ur.lint_question(text, language) == ()
    reask = ur.render_question(key, language, reask=True)
    assert ur.lint_question(reask, language) == ()
    assert reask.endswith(text)


@pytest.mark.parametrize("language", LANGS)
def test_slot_template_is_linted(language: str) -> None:
    text = ur.render_question("tried_outcome", language, what="the paper register")
    assert "paper register" in text
    assert ur.lint_question(text, language) == ()


def test_slot_with_digits_or_banned_words_is_dropped() -> None:
    plain = ur.render_question("tried_outcome", "en")
    assert ur.render_question("tried_outcome", "en", what="a 50000 discount price") == plain
    assert ur.render_question("tried_outcome", "en", what="special price?") == plain
    assert ur.render_question("tried_outcome", "en", what="x" * 100) == plain
    assert ur.render_question("tried_outcome", "en", what="\ud800") == plain


def test_unknown_key_renders_empty() -> None:
    assert ur.render_question("nope", "en") == ""


def test_hindi_and_junk_language_fall_back_to_english() -> None:
    en = ur.render_question("staff_headcount", "en")
    assert ur.render_question("staff_headcount", "hi") == en
    assert ur.render_question("staff_headcount", None) == en
    assert ur.render_question("staff_headcount", 7) == en


def test_choose_returns_none_when_every_unknown_is_option_side() -> None:
    r = reqs(budget="50000 PKR per month")
    opts = ["Buy a new oven for the kitchen"]
    g = gate(opts, r)
    assert ur.choose_question(g, r, opts, language="en") is None
    plan = ur.plan_resolution(g, r, opts, language="en")
    assert plan.question is None and plan.learn_first and plan.unresolvable == 1


def test_choose_returns_none_for_urdu_and_arabic_options() -> None:
    r = reqs(cannot=("we cannot hire anyone",))
    opts = ["ہر کرایہ دار کو پیغام بھیجیں", "أرسل رسالة تذكير لكل مستأجر"]
    g = gate(opts, r, "ur")
    assert ur.choose_question(g, r, opts, language="ur") is None
    assert ur.choose_question(g, r, opts, language="ar") is None


def test_choose_nothing_unknown_gives_none_and_no_learn_first() -> None:
    r = reqs(budget="50000 PKR per month")
    opts = ["Use a shared sheet"]
    g = gate(opts, r)
    plan = ur.plan_resolution(g, r, opts, language="en")
    assert plan.question is None and not plan.learn_first and plan.counts == {}


def test_choose_reask_uses_prefix_and_flag() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    q = ur.choose_question(
        v, r, ["a"], language="en", asked=["budget_ceiling"], non_answers={"budget_ceiling": 1}
    )
    assert q is not None and q.reask
    assert q.text == "A rough answer is fine. What is the most you could put towards this?"


def test_choose_moves_on_to_next_fact_after_non_answers() -> None:
    r = reqs(budget="not much", staff="a few")
    v = [
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
    ]
    opts = ["a", "b", "c"]
    q1 = ur.choose_question(v, r, opts)
    assert q1 is not None and q1.key == "budget_ceiling"
    q2 = ur.choose_question(v, r, opts, asked=["budget_ceiling"], non_answers={"budget_ceiling": 1})
    assert q2 is not None and q2.key == "budget_ceiling" and q2.reask
    q3 = ur.choose_question(
        v, r, opts, asked=["budget_ceiling"] * 2, non_answers={"budget_ceiling": 2}
    )
    assert q3 is not None and q3.key == "staff_headcount"
    q4 = ur.choose_question(
        v,
        r,
        opts,
        asked=["budget_ceiling"] * 2 + ["staff_headcount"] * 2,
        non_answers={"budget_ceiling": 2, "staff_headcount": 2},
    )
    assert q4 is None


def test_choose_tried_outcome_names_what_was_tried() -> None:
    r = reqs(tried=(("a paper register", "got lost"),), cannot=())
    opts = ["Keep a paper register at the desk"]
    g = gate(opts, r)
    ex = ur.explain_unknowns(g, r, opts)
    if ex and ex[0].fact == "tried_outcome":
        q = ur.choose_question(g, r, opts)
        assert q is not None and "paper register" in q.text
    else:  # "got lost" reads as a failure: the gate already knows
        assert all(e.fact != "tried_outcome" for e in ex)


def test_choose_tried_outcome_unclear_outcome() -> None:
    r = reqs(tried=(("a paper register", "hmm"),))
    v = [
        unknown(
            cc.RULE_TRIED,
            "the option repeats something the owner tried, and how it went is not clear",
        )
    ]
    q = ur.choose_question(v, r, ["Keep a paper register"], language="en")
    assert q is not None and q.key == "tried_outcome"
    assert q.text == 'When you tried "a paper register" before, did it help or not?'
    assert q.slot == "a paper register"


def test_choose_language_texts_differ_and_are_fixed() -> None:
    r = reqs(staff="a few")
    v = [unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people")]
    texts = {lang: ur.choose_question(v, r, ["a"], language=lang).text for lang in LANGS}  # type: ignore[union-attr]
    assert len(set(texts.values())) == 4
    assert texts["ur"].endswith("؟") and texts["ar"].endswith("؟")
    assert texts["en"].endswith("?") and texts["roman_ur"].endswith("?")


# ------------------------------------------------------------------------------ apply_answer


def question_for(key: str, r: Requirements, reason: str, rule: str, n: int = 2) -> ur.Question:
    v = [unknown(rule, reason)] * n
    q = ur.choose_question(v, r, [f"option {i}" for i in range(n)], language="en")
    assert q is not None and q.key == key
    return q


BUDGET_Q = ("budget_ceiling", cc.RULE_BUDGET, "no figure in the budget text")
STAFF_Q = (
    "staff_headcount",
    cc.RULE_STAFF,
    "the staff limit could not be read as a number of people",
)
DEADLINE_Q = (
    "deadline_duration",
    cc.RULE_DEADLINE,
    "the deadline is not a duration this check can read",
)
CANNOT_Q = (
    "cannot_change_detail",
    cc.RULE_CANNOT_CHANGE,
    "the stated limit could not be read (script, wording or too vague)",
)
TRIED_Q = (
    "tried_outcome",
    cc.RULE_TRIED,
    "the option repeats something the owner tried, and how it went is not clear",
)
CURRENCY_Q = (
    "budget_currency_period",
    cc.RULE_BUDGET,
    "the option's figure covers another period (monthly, yearly) than the budget",
)


def test_apply_budget_golden() -> None:
    r = reqs(budget="not much")
    q = (
        question_for(*BUDGET_Q, r=r)
        if False
        else question_for(BUDGET_Q[0], r, BUDGET_Q[2], BUDGET_Q[1])
    )
    p = ur.apply_answer(r, q, "50k PKR per month", "en")
    assert p.status is ur.Status.FILLED and p.key == "budget_ceiling"
    assert len(p.updates) == 1
    u = p.updates[0]
    assert u.field == "budget" and u.problem_number == 1 and u.replaces == "not much"
    assert dict(u.parsed) == {"value": "50000", "currency": "RS", "period": "month"}
    assert cc.parse_ceiling(u.value).value == 50000
    assert p.recheck_indices == (0, 1) and p.recheck_options == ("option 0", "option 1")
    assert p.satisfied is False


def test_apply_staff_golden() -> None:
    r = reqs(staff="a few")
    q = question_for(STAFF_Q[0], r, STAFF_Q[2], STAFF_Q[1])
    p = ur.apply_answer(r, q, "only 2", "en")
    assert p.status is ur.Status.FILLED
    assert dict(p.updates[0].parsed) == {"max_people": "2"}
    assert cc.parse_staff_limit(p.updates[0].value) == 2
    assert p.updates[0].replaces == "a few"


def test_apply_staff_bare_number_and_zero() -> None:
    r = reqs(staff="a few")
    q = question_for(STAFF_Q[0], r, STAFF_Q[2], STAFF_Q[1])
    assert dict(ur.apply_answer(r, q, "3", "en").updates[0].parsed) == {"max_people": "3"}
    assert dict(ur.apply_answer(r, q, "0", "en").updates[0].parsed) == {"max_people": "0"}
    assert dict(ur.apply_answer(r, q, "two", "en").updates[0].parsed) == {"max_people": "2"}
    assert ur.apply_answer(r, q, "we cannot hire anyone", "en").status is ur.Status.FILLED


def test_apply_deadline_golden() -> None:
    r = reqs(deadline="soonish")
    q = question_for(DEADLINE_Q[0], r, DEADLINE_Q[2], DEADLINE_Q[1])
    p = ur.apply_answer(r, q, "within 2 weeks", "en")
    assert p.status is ur.Status.FILLED and dict(p.updates[0].parsed) == {"days": "14"}
    date = ur.apply_answer(r, q, "by 15 November", "en")
    assert date.status is ur.Status.STILL_UNKNOWN and date.reason == "needs_calendar"
    assert date.recheck_indices == ()


def test_apply_cannot_change_golden_and_vague() -> None:
    r = reqs(cannot=("we cannot do that thing",))
    q = question_for(CANNOT_Q[0], r, CANNOT_Q[2], CANNOT_Q[1])
    ok = ur.apply_answer(r, q, "we cannot hire more staff", "en")
    assert ok.status is ur.Status.FILLED and ok.updates[0].field == "cannot_change"
    assert ok.updates[0].replaces == "we cannot do that thing"
    vague = ur.apply_answer(r, q, "that thing, you know", "en")
    assert vague.status is ur.Status.STILL_UNKNOWN and vague.reason in {"too_vague", "not_enforced"}


def test_apply_tried_outcome_golden() -> None:
    r = reqs(tried=(("a paper register", "hmm"),))
    q = question_for(TRIED_Q[0], r, TRIED_Q[2], TRIED_Q[1])
    failed = ur.apply_answer(r, q, "it did not work", "en")
    assert failed.status is ur.Status.FILLED and dict(failed.updates[0].parsed) == {
        "outcome": "failed"
    }
    worked = ur.apply_answer(r, q, "it worked well", "en")
    assert dict(worked.updates[0].parsed) == {"outcome": "worked"}
    both = ur.apply_answer(r, q, "it worked but then it failed", "en")
    assert both.status is ur.Status.STILL_UNKNOWN and both.reason == "ambiguous"
    neither = ur.apply_answer(r, q, "we used it for a while", "en")
    assert neither.status is ur.Status.STILL_UNKNOWN and neither.reason == "no_outcome"


def test_apply_currency_period_golden() -> None:
    r = reqs(budget="50000")
    q = question_for(CURRENCY_Q[0], r, CURRENCY_Q[2], CURRENCY_Q[1])
    p = ur.apply_answer(r, q, "PKR, per month", "en")
    assert p.status is ur.Status.FILLED
    assert dict(p.updates[0].parsed) == {"currency": "RS", "period": "month"}
    c = cc.parse_ceiling(p.updates[0].value)
    assert c.value == 50000 and c.currency == "RS" and c.period == "month"
    one_off = ur.apply_answer(r, q, "PKR, one-off", "en")
    assert dict(one_off.updates[0].parsed) == {"currency": "RS", "period": "one_off"}
    nothing = ur.apply_answer(r, q, "about that much", "en")
    assert nothing.status is ur.Status.STILL_UNKNOWN


def test_apply_contradiction_is_a_correction_candidate() -> None:
    r = reqs(budget="not much")
    q = question_for(BUDGET_Q[0], r, BUDGET_Q[2], BUDGET_Q[1])
    r2 = reqs(budget="100000 PKR")
    p = ur.apply_answer(r2, q, "50k PKR", "en")
    assert p.status is ur.Status.CORRECTION
    assert p.updates[0].is_correction and p.updates[0].replaces == "100000 PKR"
    assert p.recheck_indices == q.options


def test_apply_same_value_as_stored_is_not_a_correction() -> None:
    r = reqs(budget="not much")
    q = question_for(BUDGET_Q[0], r, BUDGET_Q[2], BUDGET_Q[1])
    p = ur.apply_answer(reqs(budget="50000 PKR"), q, "50k PKR", "en")
    assert p.status is ur.Status.FILLED and not p.updates[0].is_correction


def test_apply_staff_contradiction() -> None:
    r = reqs(staff="a few")
    q = question_for(STAFF_Q[0], r, STAFF_Q[2], STAFF_Q[1])
    p = ur.apply_answer(reqs(staff="only 1 person"), q, "only 4", "en")
    assert p.status is ur.Status.CORRECTION


@pytest.mark.parametrize(
    "text",
    [
        "maybe",
        "I don't know",
        "not sure",
        "let me think",
        "hmm",
        "ok",
        "yes",
        "no",
        "dekhte hain",
        "pata nahi",
        "shayad",
        "baad mein",
        "",
        "   ",
        "...",
        "?",
        "پتہ نہیں",
        "شاید",
        "دیکھتے ہیں",
        "لا أعرف",
        "ربما",
        "سنرى",
        "ठीक है",
    ],
)
def test_non_answers_keep_the_item_unknown(text: str) -> None:
    r = reqs(budget="not much")
    q = question_for(BUDGET_Q[0], r, BUDGET_Q[2], BUDGET_Q[1])
    p = ur.apply_answer(r, q, text, "en")
    assert p.status is ur.Status.STILL_UNKNOWN and p.non_answer and p.updates == ()
    assert p.recheck_indices == () and p.recheck_options == ()


def test_state_after_two_non_answers_moves_on() -> None:
    r = reqs(budget="not much", staff="a few")
    v = [
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
    ]
    opts = ["a", "b", "c"]
    state = ur.ResolutionState()
    keys: list[str] = []
    for _ in range(10):
        q = ur.choose_question(v, r, opts, asked=state.asked, non_answers=state.non_answer_map)
        if q is None:
            break
        keys.append(q.key)
        state = ur.record_outcome(state, q, ur.apply_answer(r, q, "maybe", "en"))
    assert keys == ["budget_ceiling", "budget_ceiling", "staff_headcount", "staff_headcount"]


def test_filled_answer_is_not_a_non_answer_and_is_not_asked_again() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    q = ur.choose_question(v, r, ["a"])
    assert q is not None
    state = ur.record_outcome(None, q, ur.apply_answer(r, q, "50k", "en"))
    assert state.asked == ("budget_ceiling",) and state.non_answers == ()
    assert (
        ur.choose_question(v, r, ["a"], asked=state.asked, non_answers=state.non_answer_map) is None
    )


def test_apply_answer_only_lists_affected_options() -> None:
    r = reqs(budget="not much", staff="a few")
    v = [
        unknown(cc.RULE_STAFF, "the staff limit could not be read as a number of people"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
        unknown(cc.RULE_BUDGET, "no figure in the budget text"),
    ]
    q = ur.choose_question(v, r, ["x", "y", "z"])
    assert q is not None and q.key == "budget_ceiling"
    p = ur.apply_answer(r, q, "40000 PKR", "en")
    assert p.recheck_indices == (1, 2) and p.recheck_options == ("y", "z")


def test_proposal_then_real_gate_recheck_decides() -> None:
    """The proposal feeds the real gate; the gate, not this module, says what now passes."""
    r = reqs(budget="not much")
    opts = ["Buy a booking tool for 20000 PKR", "Ask regulars to rebook"]
    g = gate(opts, r)
    q = ur.choose_question(g, r, opts)
    assert q is not None and q.key == "budget_ceiling"
    p = ur.apply_answer(r, q, "50000 PKR", "en")
    assert p.status is ur.Status.FILLED and not p.satisfied
    r2 = reqs(budget=p.updates[0].value)
    again = gate([opts[i] for i in p.recheck_indices], r2)
    assert again.accepted_options == tuple(opts[i] for i in p.recheck_indices)
    # an answer below the option's figure makes the real gate reject: nothing was pre-approved
    p2 = ur.apply_answer(r, q, "5000 PKR", "en")
    again2 = gate([opts[0]], reqs(budget=p2.updates[0].value))
    assert again2.accepted_options == ()


def test_unreadable_answer_text_for_gate_stays_unknown() -> None:
    r = reqs(cannot=("we cannot do that thing",))
    q = question_for(CANNOT_Q[0], r, CANNOT_Q[2], CANNOT_Q[1])
    p = ur.apply_answer(r, q, "ہم مزید لوگ نہیں رکھ سکتے", "ur")
    assert p.status is ur.Status.STILL_UNKNOWN and p.reason == "script_unreadable"


def test_apply_bad_inputs_never_raise() -> None:
    r = reqs(budget="x")
    q = question_for(BUDGET_Q[0], r, BUDGET_Q[2], BUDGET_Q[1])
    for bad_q in (None, 5, "q", object()):
        assert ur.apply_answer(r, bad_q, "50k").status is ur.Status.STILL_UNKNOWN  # type: ignore[arg-type]
    for bad_t in (None, 5, b"50k", ["50k"], object()):
        assert ur.apply_answer(r, q, bad_t).status is ur.Status.STILL_UNKNOWN  # type: ignore[arg-type]
    assert ur.apply_answer(None, q, "50k").status in {ur.Status.FILLED, ur.Status.STILL_UNKNOWN}
    assert ur.apply_answer(r, q, "50k" + " " * 5000).reason == "too_long"
    assert ur.apply_answer("junk", q, "50k").status is ur.Status.STILL_UNKNOWN  # type: ignore[arg-type]


# --------------------------------------------------------------------- answered in messages


def test_answered_in_messages_golden() -> None:
    assert ur.answered_in_messages("budget_ceiling", ["I can spend 50k a month"])
    assert not ur.answered_in_messages("budget_ceiling", ["I have 50 tenants"])
    assert ur.answered_in_messages("staff_headcount", ["I only have one assistant"])
    assert not ur.answered_in_messages("staff_headcount", ["Rent is late"])
    assert ur.answered_in_messages("deadline_duration", ["I need it within 2 weeks"])
    assert not ur.answered_in_messages("deadline_duration", ["It started 2 weeks ago"])
    assert ur.answered_in_messages("budget_currency_period", ["my budget is 40k PKR monthly"])
    assert not ur.answered_in_messages("cannot_change_detail", ["we cannot hire"])
    assert not ur.answered_in_messages("tried_outcome", ["we tried a register"])
    assert not ur.answered_in_messages("budget_ceiling", None)
    assert not ur.answered_in_messages("budget_ceiling", 5)


# ---------------------------------------------------------------------------- property tests


def _random_case(rnd: random.Random) -> tuple[Requirements, list[str], str]:
    budgets = [
        None,
        "not much",
        "50000 PKR per month",
        "at least 5000",
        "10k USD",
        "no idea",
        "bahut kam",
    ]
    staffs = [None, "a few", "only 2 people", "no hiring", "kuch log", "at least 2"]
    deadlines = [None, "soonish", "2 weeks", "by 15 March", "jaldi"]
    cannots = [
        (),
        ("we cannot do that thing",),
        ("cannot hire more staff",),
        ("kuch nahi kar sakte",),
        ("must work on my phone only",),
        ("ہم کچھ نہیں بدل سکتے",),
    ]
    tried = [(), (("a paper register", "got lost"),), (("flyers", "hmm"),), (("ads", ""),)]
    r = reqs(
        rnd.choice(budgets),
        rnd.choice(staffs),
        rnd.choice(deadlines),
        rnd.choice(cannots),
        rnd.choice(tried),
    )
    pool = [
        "Buy a booking tool",
        "Hire two new assistants",
        "Send each tenant a reminder",
        "Phone every flat on the first of the month",
        "Open a second branch in Lahore",
        "Keep a paper register at the desk",
        "Rent a bigger space",
        "Run flyers in the area",
        "Install software for 20000 PKR",
        "ہر کرایہ دار کو پیغام بھیجیں",
        "أرسل تذكيراً لكل مستأجر",
        "Hire a consultant within 3 days",
        "Pay a freelancer 500 USD per month",
        "kiraye daaron ko message bhejein",
    ]
    opts = rnd.sample(pool, rnd.randint(1, len(pool)))
    return r, opts, rnd.choice(LANGS)


def test_property_chosen_question_is_sound() -> None:
    rnd = random.Random(7)
    asked_none = 0
    for _ in range(300):
        r, opts, lang = _random_case(rnd)
        g = gate(opts, r, lang)
        msgs = rnd.sample(
            ["I can spend 30k PKR", "only one assistant", "within 2 weeks", "hello"],
            rnd.randint(0, 3),
        )
        q = ur.choose_question(g, r, opts, language=lang, owner_messages=msgs)
        if q is None:
            asked_none += 1
            continue
        # one question mark, last sentence, linted
        assert ur.lint_question(q.text, lang) == ()
        # it maps to at least one unknown decision
        assert q.options
        unknown_indices = {e.index for e in ur.explain_unknowns(g, r, opts)}
        assert set(q.options) <= unknown_indices
        assert all(opts[i] == t for i, t in zip(q.options, q.option_texts, strict=True))
        # it never asks a stored or already-answered fact
        assert not ur._is_stored(q.key, r)
        assert not ur.answered_in_messages(q.key, msgs)
        # it is owner-answerable
        assert q.owner_answerable
    assert asked_none < 300


def test_property_never_repeats_a_question() -> None:
    rnd = random.Random(11)
    for _ in range(150):
        r, opts, lang = _random_case(rnd)
        g = gate(opts, r, lang)
        state = ur.ResolutionState()
        counts: dict[str, int] = {}
        for _ in range(12):
            q = ur.choose_question(
                g, r, opts, language=lang, asked=state.asked, non_answers=state.non_answer_map
            )
            if q is None:
                break
            counts[q.key] = counts.get(q.key, 0) + 1
            state = ur.record_outcome(
                state, q, ur.apply_answer(r, q, rnd.choice(["maybe", "hmm", "ok"]), lang)
            )
        assert all(n <= 2 for n in counts.values())
        assert sum(counts.values()) <= 2 * len(ur.FACTS)


FIRM = {
    "budget_ceiling": "50000 PKR",
    "budget_currency_period": "PKR per month",
    "staff_headcount": "only 2",
    "deadline_duration": "within 2 weeks",
    "cannot_change_detail": "we cannot hire more staff",
    "tried_outcome": "it did not work",
    "tried_detail": "a register",
    "place_allowed": "Lahore",
}


def test_property_unrepeated_when_answers_are_firm() -> None:
    rnd = random.Random(13)
    for _ in range(100):
        r, opts, lang = _random_case(rnd)
        g = gate(opts, r, lang)
        state = ur.ResolutionState()
        seen: list[str] = []
        for _ in range(12):
            q = ur.choose_question(
                g, r, opts, language=lang, asked=state.asked, non_answers=state.non_answer_map
            )
            if q is None:
                break
            seen.append(q.key)
            state = ur.record_outcome(state, q, ur.apply_answer(r, q, FIRM[q.key], lang))
        assert len(seen) == len(set(seen))


def test_property_proposal_never_satisfies_and_only_rechecks_listed_options() -> None:
    rnd = random.Random(17)
    answers = [
        "50k PKR",
        "only 2",
        "within 3 days",
        "we cannot hire more staff",
        "it failed",
        "maybe",
        "",
        "Lahore",
    ]
    for _ in range(200):
        r, opts, lang = _random_case(rnd)
        g = gate(opts, r, lang)
        q = ur.choose_question(g, r, opts, language=lang)
        if q is None:
            continue
        p = ur.apply_answer(r, q, rnd.choice(answers), lang)
        assert p.satisfied is False
        if p.status is ur.Status.STILL_UNKNOWN:
            assert p.recheck_indices == () and p.updates == ()
        else:
            assert p.recheck_indices == q.options and p.updates


def test_property_updates_round_trip_through_the_gate_readers() -> None:
    """Every value a proposal carries is readable by the same reader the gate uses."""
    rnd = random.Random(19)
    answers = [
        "50k PKR per month",
        "only 2 people",
        "within 2 weeks",
        "we cannot hire more staff",
        "40000 USD",
    ]
    for _ in range(200):
        r, opts, lang = _random_case(rnd)
        g = gate(opts, r, lang)
        q = ur.choose_question(g, r, opts, language=lang)
        if q is None:
            continue
        p = ur.apply_answer(r, q, rnd.choice(answers), lang)
        for u in p.updates:
            if u.field == "budget":
                assert cc.parse_ceiling(u.value).value is not None
            elif u.field == "staff":
                assert cc.parse_staff_limit(u.value) is not None
            elif u.field == "deadline":
                assert cc.parse_days(u.value, need_cue=False) is not None
            elif u.field == "cannot_change":
                assert cc.parse_limit(u.value).kind not in {"unreadable", "unknown_verb"}


# ---------------------------------------------------------------------------------- fuzz


def _junk(rnd: random.Random) -> object:
    pool: list[object] = [
        None,
        0,
        1.5,
        True,
        b"bytes",
        "",
        " ",
        "\ud800",
        "\udfff" * 5,
        "x" * 5000,
        "٠١٢٣" * 50,
        "؟?" * 100,
        ["a", None, 3],
        {"a": 1},
        (1, 2),
        object(),
        "ہ" * 3000,
        "‮\u0000" * 20,
        cc.Verdict("unknown", "budget", (), "no figure in the budget text"),
        cc.Verdict("unknown", None, None, None),  # type: ignore[arg-type]
        Requirements(columns_available=False),
        reqs(budget="\ud800 50k"),
        "50k" * 3000,
        "1" * 5000,
    ]
    return rnd.choice(pool)


def test_fuzz_never_raises_1000() -> None:
    rnd = random.Random(2026)
    r_ok = reqs(
        budget="not much",
        staff="a few",
        deadline="soon",
        cannot=("that thing",),
        tried=(("x", ""),),
    )
    for _ in range(1000):
        a, b, c, d = _junk(rnd), _junk(rnd), _junk(rnd), _junk(rnd)
        ur.explain_unknowns(a, b, c)  # type: ignore[arg-type]
        ur.rank_missing_information(a, b, c, owner_messages=d, asked=d, non_answers=d)  # type: ignore[arg-type]
        ur.choose_question(a, b, c, language=d, owner_messages=d, asked=d, non_answers=d)  # type: ignore[arg-type]
        ur.plan_resolution(a, b, c, language=d, owner_messages=d, asked=d, non_answers=d)  # type: ignore[arg-type]
        ur.answered_in_messages(str(a), d)
        ur.is_non_answer(d)
        ur.render_question(str(a), d, what=d)  # type: ignore[arg-type]
        ur.lint_question(d, d)
        ur.classify_reason(d, d)
        ur.apply_answer(b, a, c, d)  # type: ignore[arg-type]
        q = ur.choose_question(
            [unknown(cc.RULE_BUDGET, "no figure in the budget text")], r_ok, ["o"]
        )
        assert q is not None
        p = ur.apply_answer(r_ok, q, d)  # type: ignore[arg-type]
        assert p.satisfied is False
        ur.record_outcome(d, q, p)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- timing


def _best(fn, repeat: int = 3) -> float:  # type: ignore[no-untyped-def]
    best = 1e9
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return best


def test_linear_in_the_number_of_options() -> None:
    r = reqs(budget="not much", staff="a few")
    v = unknown(cc.RULE_BUDGET, "no figure in the budget text")

    def run(n: int) -> float:
        verdicts = [v] * n
        opts = [f"option {i}" for i in range(n)]
        return _best(lambda: ur.choose_question(verdicts, r, opts))

    small, big = run(200), run(1000)  # inputs are capped at 500: the ratio must stay flat after
    huge = run(5000)
    assert huge < max(small, 0.002) * 12 + 0.05
    assert big < max(small, 0.002) * 12 + 0.05


def test_linear_in_answer_length() -> None:
    r = reqs(budget="not much")
    q = ur.choose_question([unknown(cc.RULE_BUDGET, "no figure in the budget text")], r, ["a"])
    assert q is not None
    t1 = _best(lambda: ur.apply_answer(r, q, "50k PKR " + "word " * 100))
    t10 = _best(lambda: ur.apply_answer(r, q, "50k PKR " + "word " * 1000))
    t100 = _best(lambda: ur.apply_answer(r, q, "50k PKR " + "word " * 100_000))  # over the cap
    assert t100 < max(t1, 0.001) * 50 + 0.05
    assert t10 < max(t1, 0.001) * 30 + 0.05


def test_linear_in_owner_messages() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]

    def run(n: int) -> float:
        msgs = ["hello there, rent is late" * 5] * n
        return _best(lambda: ur.choose_question(v, r, ["a"], owner_messages=msgs))

    a, b, c = run(10), run(100), run(10_000)
    assert c < max(b, 0.002) * 10 + 0.05
    assert b < max(a, 0.002) * 30 + 0.05


def test_pathological_answers_are_fast() -> None:
    r = reqs(budget="not much")
    q = ur.choose_question([unknown(cc.RULE_BUDGET, "no figure in the budget text")], r, ["a"])
    assert q is not None
    start = time.perf_counter()
    for text in ("1 " * 900, "," * 1900, "9" * 1900, "k " * 900, "٠ " * 900, "a" * 1900):
        ur.apply_answer(r, q, text)
    assert time.perf_counter() - start < 3


# --------------------------------------------------------- adversarial multilingual answers

# (key, answer, expected status, expected reason or parsed subset)
F, S, C = ur.Status.FILLED, ur.Status.STILL_UNKNOWN, ur.Status.CORRECTION

BUDGET_CASES = [
    ("50k PKR per month", F, {"value": "50000"}),
    ("50,000 rupees", F, {"value": "50000"}),
    ("Rs 50000", F, {"value": "50000"}),
    ("about 50 thousand rupees", F, {"value": "50000"}),
    ("2 lakh", F, {"value": "200000"}),
    ("5 lakh PKR", F, {"value": "500000"}),
    ("up to 30k", F, {"value": "30000"}),
    ("at most 1000 dollars", F, {"value": "1000"}),
    ("$500", F, {"value": "500"}),
    ("nothing, zero budget", F, {"value": "0"}),
    ("no budget at all", F, {"value": "0"}),
    ("50 hazar rupay", F, {"value": "50000"}),
    ("pachas hazar", F, {"value": "50000"}),
    ("sirf 20 hazar", F, {"value": "20000"}),
    ("٥٠٠٠٠ روپے", F, {"value": "50000"}),
    ("50000 روپے ماہانہ", F, {"value": "50000"}),
    ("٥٠ ألف ريال", F, {"value": "50000"}),
    ("at least 5000", S, "floor_only"),
    ("minimum 10k", S, "floor_only"),
    ("I do not have a number", S, "no_figure"),
    ("a lot", S, "no_figure"),
    ("maybe 50k", S, "hedged"),
    ("50k or 100k", S, "ambiguous"),
    ("50k ya 100k", S, "ambiguous"),
    ("شاید 50 ہزار", S, "hedged"),
    ("ربما 50 ألف", S, "hedged"),
    ("depends", S, "no_figure"),
    ("as little as possible", S, "no_figure"),
    ("bahut kam", S, "no_figure"),
    ("jitna ho sake", S, "no_figure"),
    ("جتنا ہو سکے", S, "no_figure"),
    ("بقدر الإمكان", S, "no_figure"),
    ("?", S, "non_answer"),
    ("i think 40k", S, "hedged"),
    ("not sure, around 40k", S, "hedged"),
    ("50k now and 100k later", S, "ambiguous"),
    ("10 20 30 40 50 60 70 80 90", S, "ambiguous"),
]


@pytest.mark.parametrize(("text", "status", "expect"), BUDGET_CASES)
def test_budget_answers(text: str, status: ur.Status, expect: object) -> None:
    r = reqs(budget="not much")
    q = question_for(BUDGET_Q[0], r, BUDGET_Q[2], BUDGET_Q[1])
    p = ur.apply_answer(r, q, text, "en")
    if status is S:
        assert p.status is S, (p.status, p.updates)
        assert p.reason == expect or (
            expect == "no_figure" and p.reason in {"no_figure", "non_answer"}
        )
        assert p.updates == () and p.recheck_indices == ()
    else:
        assert p.status is status, (p.status, p.reason)
        parsed = dict(p.updates[0].parsed)
        assert {k: parsed.get(k) for k in expect} == expect  # type: ignore[attr-defined]


STAFF_CASES = [
    ("only 2", F, "2"),
    ("just 3 people", F, "3"),
    ("at most 5", F, "5"),
    ("maximum two staff", F, "2"),
    ("one", F, "1"),
    ("1", F, "1"),
    ("0", F, "0"),
    ("none", S, None),
    ("no hiring", S, "no_number"),
    ("we cannot hire anyone", F, "0"),
    ("sirf 2 log", F, "2"),
    ("sirf do", S, None),
    ("sirf ek", F, "1"),
    ("2 ya 3", S, "ambiguous"),
    ("2 or 3 people", S, "ambiguous"),
    ("at least 2", S, "floor_only"),
    ("صرف 2", F, "2"),
    ("فقط 3 أشخاص", F, "3"),
    ("صرف ٢ لوگ", F, "2"),
    ("a few", S, None),
    ("some", S, None),
    ("I don't know", S, "non_answer"),
    ("maybe 2", S, "hedged"),
    ("ربما 2", S, "hedged"),
    ("شاید دو", S, "hedged"),
    ("many", S, None),
    ("2 3 4", S, "ambiguous"),
    ("teen", S, None),
    ("5 log", F, "5"),
]


@pytest.mark.parametrize(("text", "status", "expect"), STAFF_CASES)
def test_staff_answers(text: str, status: ur.Status, expect: str | None) -> None:
    r = reqs(staff="a few")
    q = question_for(STAFF_Q[0], r, STAFF_Q[2], STAFF_Q[1])
    p = ur.apply_answer(r, q, text, "en")
    assert p.status is status, (text, p.status, p.reason, p.updates)
    if status is F:
        assert dict(p.updates[0].parsed)["max_people"] == expect
    else:
        assert p.satisfied is False and p.updates == ()
        if expect:
            assert p.reason == expect


DEADLINE_CASES = [
    ("within 2 weeks", F, "14"),
    ("in 3 days", F, "3"),
    ("next month", F, "30"),
    ("tomorrow", F, "1"),
    ("today", F, "0"),
    ("2 hafte mein", F, "14"),
    ("3 din", F, "3"),
    ("ek mahine mein", F, "30"),
    ("by 15 March", S, "needs_calendar"),
    ("end of the year", S, "needs_calendar"),
    ("15 مارچ تک", S, "needs_calendar"),
    ("جلدی", S, "needs_calendar"),
    ("asap", S, "needs_calendar"),
    ("soon", S, "needs_calendar"),
    ("2 weeks or 3", S, "ambiguous"),
    ("maybe 2 weeks", S, "hedged"),
    ("whenever", S, "needs_calendar"),
    ("dekhte hain", S, "non_answer"),
    ("2 weeks, no rush", F, "14"),
    ("jaldi", S, "needs_calendar"),
    ("المستقبل القريب", S, "needs_calendar"),
]


@pytest.mark.parametrize(("text", "status", "expect"), DEADLINE_CASES)
def test_deadline_answers(text: str, status: ur.Status, expect: str) -> None:
    r = reqs(deadline="soonish")
    q = question_for(DEADLINE_Q[0], r, DEADLINE_Q[2], DEADLINE_Q[1])
    p = ur.apply_answer(r, q, text, "en")
    assert p.status is status, (text, p.status, p.reason)
    if status is F:
        assert dict(p.updates[0].parsed)["days"] == expect
    else:
        assert p.reason == expect and p.updates == ()


CANNOT_CASES = [
    ("we cannot hire more staff", F),
    ("we can't buy new equipment", F),
    ("we cannot afford a website", F),
    ("we must not close on weekends", S),
    ("can't open another branch", F),
    ("only in Lahore", F),
    ("we cannot work outside Karachi", S),
    ("that thing", S),
    ("you know what I mean", S),
    ("it is complicated", S),
    ("hmm", S),
    ("maybe", S),
    ("hum naye log nahi rakh sakte", S),
    ("kuch nahi", S),
    ("ہم مزید لوگ نہیں رکھ سکتے", S),
    ("لا نستطيع توظيف أحد", S),
    ("نہیں پتا", S),
    ("etc", S),
    ("see above", S),
]


@pytest.mark.parametrize(("text", "status"), CANNOT_CASES)
def test_cannot_change_answers_follow_the_gate_reader(text: str, status: ur.Status) -> None:
    r = reqs(cannot=("we cannot do that thing",))
    q = question_for(CANNOT_Q[0], r, CANNOT_Q[2], CANNOT_Q[1])
    p = ur.apply_answer(r, q, text, "en")
    if p.status is F:
        for u in p.updates:
            assert cc.parse_limit(u.value).kind not in {"unreadable", "unknown_verb"}
    else:
        assert p.status is S and p.updates == () and p.recheck_indices == ()
    if status is F:
        assert p.status is F, (text, p.reason)


@pytest.mark.parametrize(
    "text",
    [
        "I don't know",
        "dekhte hain",
        "pata nahi",
        "لا أعرف",
        "پتہ نہیں",
        "maybe",
        "later",
        "baad mein",
        "hmm hmm",
        "let me think",
        "i will tell you later",
        "shayad",
        "ربما",
        "ٹھیک ہے",
        "okay",
        "sure",
        "yes",
        "yes yes",
        "haan",
        "han ji",
        "no",
        "nahi",
        "نعم",
        "لا",
    ],
)
@pytest.mark.parametrize("key_spec", [BUDGET_Q, STAFF_Q, DEADLINE_Q, CANNOT_Q])
def test_non_answers_for_every_key_stay_unknown(text: str, key_spec: tuple[str, str, str]) -> None:
    r = reqs(budget="x", staff="x", deadline="x", cannot=("that thing",))
    q = question_for(key_spec[0], r, key_spec[2], key_spec[1])
    p = ur.apply_answer(r, q, text, "en")
    assert p.status is S and p.satisfied is False and p.updates == ()


NON_ANSWER_TRUE = [
    "maybe",
    "Maybe.",
    "MAYBE!!",
    "  hmm  ",
    "ok",
    "okay.",
    "I don't know",
    "I do not know",
    "not sure",
    "let me think",
    "dekhte hain",
    "Dekhte hain.",
    "pata nahi",
    "shayad",
    "haan",
    "nahi",
    "پتہ نہیں",
    "شاید",
    "دیکھتے ہیں",
    "ہاں",
    "نہیں",
    "لا أعرف",
    "ربما",
    "نعم",
    "لا",
    "",
    "...",
    "ok maybe",
    "hmm ok",
    "haan shayad",
    "yes",
    "no",
    "sure",
    "later",
    "baad mein",
    "ठीक है",
]
NON_ANSWER_FALSE = [
    "50k",
    "only 2",
    "within 2 weeks",
    "we cannot hire",
    "maybe 50k",
    "it did not work",
    "Lahore",
    "no hiring",
    "no budget",
    "nahi hire kar sakte",
    "لا نستطيع",
    "لا ميزانية",
    "ہم نہیں رکھ سکتے",
    "haan 50k",
    "ok 3 days",
]


@pytest.mark.parametrize("text", NON_ANSWER_TRUE)
def test_is_non_answer_true(text: str) -> None:
    assert ur.is_non_answer(text)


@pytest.mark.parametrize("text", NON_ANSWER_FALSE)
def test_is_non_answer_false(text: str) -> None:
    assert not ur.is_non_answer(text)


def test_is_non_answer_junk() -> None:
    assert ur.is_non_answer(None) and ur.is_non_answer(5) and ur.is_non_answer("\ud800")


# --------------------------------------------------------------- lint and templates


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("Tell me more. How much?", None),
        ("What is your budget? And your staff?", "question_marks"),
        ("What is your budget", "question_marks"),
        ("What is your budget? Thanks", "not_last"),
        ("How about 50000 PKR?", "digit"),
        ("What is the price?", "banned_word"),
        ("Can I offer you a package?", "banned_word"),
        ("Do you want to organize it?", "american_spelling"),
        ("Which color do you want?", "american_spelling"),
        ("Can you share your card?", "banned_word"),
        ("ما السعر؟", "banned_word"),
        ("کیا یہ مفت ہے؟", "banned_word"),
        ("کیا آپ ٹھیک ہیں؟ جی؟", "question_marks"),
        ("", "empty"),
    ],
)
def test_lint_catches(text: str, problem: str | None) -> None:
    out = ur.lint_question(text)
    if problem is None:
        assert out == ()
    else:
        assert problem in out


def test_templates_have_one_mark_each_and_no_digits() -> None:
    for key, table in lx.QUESTIONS.items():
        assert set(table) == set(LANGS), key
        for lang, text in table.items():
            assert sum(text.count(q) for q in "?؟") == 1 and not any(c.isdigit() for c in text)
            assert text.endswith("؟" if lang in {"ur", "ar"} else "?")


def test_templates_use_british_spelling_and_no_promise_words() -> None:
    blob = " ".join(t for table in lx.QUESTIONS.values() for t in table.values()).lower()
    for word in ("color", "organize", "center", "program", "guarantee", "promise", "price", "free"):
        assert word not in blob


# ------------------------------------------------------------------ the gate is untouched


def test_module_does_not_call_the_gate_or_import_evalkit() -> None:
    src = Path(ur.__file__).read_text(encoding="utf-8")
    assert "evalkit" not in src
    assert "gate_options(" not in src
    assert "check_option(" not in src
    assert "import anthropic" not in src and "openai" not in src
    lex_src = Path(lx.__file__).read_text(encoding="utf-8")
    assert "evalkit" not in lex_src


def test_proposal_has_no_verdict_field() -> None:
    fields = set(ur.AnswerProposal.__dataclass_fields__)
    assert not ({"verdict", "accepted", "ok"} & fields)
    assert ur.AnswerProposal(ur.Status.FILLED, "k").satisfied is False


def test_unreadable_unknown_stays_unknown_in_the_real_gate_after_a_vague_answer() -> None:
    r = reqs(cannot=("we cannot do that thing",))
    opts = ["Hire two more staff"]
    g = gate(opts, r)
    assert g.unknown
    q = ur.choose_question(g, r, opts)
    assert q is not None
    p = ur.apply_answer(r, q, "that thing, you know", "en")
    assert p.status is S
    assert gate(opts, r).accepted_options == ()  # nothing changed, nothing passes


def _bare_question(key: str) -> ur.Question:
    return ur.Question(
        key=key,
        fact=key,
        field="",
        text=ur.render_question(key),
        language="en",
        why=(),
        options=(0,),
        option_texts=("Open a branch",),
        problems=(),
        codes=(),
    )


# ------------------------------------------------- tests added after the mutation pass


def test_why_is_capped_and_clipped() -> None:
    r = reqs(budget="not much")
    opts = [f"option number {i} " + "x" * 300 for i in range(9)]
    q = ur.choose_question([unknown(cc.RULE_BUDGET, "no figure in the budget text")] * 9, r, opts)
    assert q is not None
    assert len(q.why) == ur.MAX_WHY == 3
    assert all(len(w) <= ur.MAX_WHY_CHARS for w in q.why)
    assert len(q.options) == 9


def test_stored_facts_are_detected_per_key() -> None:
    r = reqs(
        budget="50000 PKR per month",
        staff="only 2 people",
        deadline="within 2 weeks",
        cannot=("only in Lahore",),
        tried=(("a paper register", "it failed"),),
    )
    for key in (
        "budget_ceiling",
        "budget_currency_period",
        "staff_headcount",
        "deadline_duration",
        "tried_outcome",
        "tried_detail",
        "place_allowed",
    ):
        assert ur._is_stored(key, r), key
    assert not ur._is_stored("cannot_change_detail", r)
    assert not ur._is_stored("tools_resources", r)
    assert not ur._is_stored("expected_outcome", r)
    empty = reqs()
    for key in ur.FACTS:
        assert not ur._is_stored(key, empty), key


def test_expected_outcome_stored_when_a_problem_has_one() -> None:
    p = ProblemRequirements(number=1, expected_outcome="fewer late payers")
    assert ur._is_stored("expected_outcome", Requirements(problems=(p,)))


def test_unreadable_stored_facts_are_not_stored() -> None:
    r = reqs(
        budget="at least 5000",
        staff="a few",
        deadline="soonish",
        tried=(("a register", "hmm"),),
    )
    assert not ur._is_stored("budget_ceiling", r)
    assert not ur._is_stored("staff_headcount", r)
    assert not ur._is_stored("deadline_duration", r)
    assert not ur._is_stored("tried_outcome", r)
    assert not ur._is_stored("budget_currency_period", reqs(budget="50000"))
    assert not ur._is_stored("budget_currency_period", reqs(budget="50000 PKR"))
    assert ur._is_stored("budget_currency_period", reqs(budget="50000 PKR in total"))


def test_facts_without_a_gate_unknown_have_no_problems_behind_them() -> None:
    ranked = ur.rank_missing_information([], reqs(budget="x"), [], include_zero=True)
    out = {m.key: m for m in ranked}
    assert out["tools_resources"].problems == () and out["expected_outcome"].problems == ()


def test_deadline_priority_beats_alphabet_on_a_tie() -> None:
    r = reqs(deadline="soonish", cannot=("that thing",))
    v = [
        unknown(cc.RULE_DEADLINE, "the deadline is not a duration this check can read"),
        unknown(
            cc.RULE_CANNOT_CHANGE,
            "the stated limit could not be read (script, wording or too vague)",
        ),
    ]
    ranked = ur.rank_missing_information(v, r, ["a", "b"])
    assert [m.key for m in ranked] == ["deadline_duration", "cannot_change_detail"]


def test_asked_and_messages_mappings_are_not_collections_of_keys() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    out = ur.rank_missing_information(
        v, r, ["a"], asked={"budget_ceiling": 5}, owner_messages={"my budget is 40k PKR": 1}
    )
    assert out[0].askable and not out[0].reask
    assert ur.rank_missing_information(v, r, ["a"], asked=b"budget_ceiling")[0].askable
    assert ur.rank_missing_information(v, r, ["a"], owner_messages=b"my budget is 40k")[0].askable


def test_non_answers_mapping_ignores_bad_counts() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")]
    for bad in ({"budget_ceiling": True}, {"budget_ceiling": "1"}, {1: 1}, [("budget_ceiling", 1)]):
        out = ur.rank_missing_information(
            v,
            r,
            ["a"],
            asked=["budget_ceiling"],
            non_answers=bad,  # type: ignore[arg-type]
        )
        assert out[0].status == "exhausted"


def test_a_template_that_fails_the_lint_is_never_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = {lang: "What is the price? Or the cost?" for lang in LANGS}
    monkeypatch.setitem(lx.QUESTIONS, "budget_ceiling", bad)
    r = reqs(budget="not much")
    assert (
        ur.choose_question([unknown(cc.RULE_BUDGET, "no figure in the budget text")], r, ["a"])
        is None
    )


def test_answered_in_messages_cues() -> None:
    assert ur.answered_in_messages("budget_ceiling", ["budget 50000"])
    assert ur.answered_in_messages("budget_ceiling", ["بجٹ 50000"])
    assert not ur.answered_in_messages("budget_ceiling", ["we have 50000 customers"])
    assert ur.answered_in_messages("deadline_duration", ["it must be done within 2 weeks"])
    assert not ur.answered_in_messages("deadline_duration", ["we waited 2 weeks"])
    assert not ur.answered_in_messages("expected_outcome", ["anything"])


def test_currency_period_reads_each_half_alone() -> None:
    r = reqs(budget="50000 PKR")
    q = question_for(CURRENCY_Q[0], r, CURRENCY_Q[2], CURRENCY_Q[1])
    monthly = ur.apply_answer(r, q, "monthly", "en")
    assert monthly.status is F
    assert dict(monthly.updates[0].parsed) == {"currency": "RS", "period": "month"}
    once = ur.apply_answer(r, q, "once", "en")
    assert once.status is F and dict(once.updates[0].parsed)["period"] == "one_off"
    r2 = reqs(budget="50000")
    q2 = question_for(CURRENCY_Q[0], r2, CURRENCY_Q[2], CURRENCY_Q[1])
    only_cur = ur.apply_answer(r2, q2, "USD", "en")
    assert only_cur.status is S and only_cur.reason == "no_period"
    only_per = ur.apply_answer(r2, q2, "monthly", "en")
    assert only_per.status is S and only_per.reason == "no_currency"
    assert ur.apply_answer(r2, q2, "xyz", "en").reason == "no_currency_or_period"
    both = ur.apply_answer(r2, q2, "monthly, once", "en")
    assert both.status is S and both.reason == "ambiguous"


def test_currency_and_period_contradictions() -> None:
    r = reqs(budget="50000 USD per month")
    q = _bare_question("budget_currency_period")
    cur = ur.apply_answer(r, q, "PKR, per month", "en")
    assert cur.status is C and cur.updates[0].is_correction
    per = ur.apply_answer(r, q, "USD, per year", "en")
    assert per.status is C
    same = ur.apply_answer(r, q, "USD, per month", "en")
    assert same.status is F and not same.updates[0].is_correction


def test_deadline_and_staff_contradictions_use_their_own_stored_limit() -> None:
    r = reqs(deadline="soonish")
    q = question_for(DEADLINE_Q[0], r, DEADLINE_Q[2], DEADLINE_Q[1])
    changed = ur.apply_answer(reqs(deadline="within 2 weeks"), q, "within 3 days", "en")
    assert changed.status is C and changed.updates[0].replaces == "within 2 weeks"
    same = ur.apply_answer(reqs(deadline="within 2 weeks"), q, "in 14 days", "en")
    assert same.status is F
    # a stored budget or staff limit is not the deadline's stored value
    other = ur.apply_answer(
        reqs(budget="100000 PKR", staff="only 1 person"), q, "within 3 days", "en"
    )
    assert other.status is F and other.updates[0].replaces is None
    rs = reqs(staff="a few")
    qs = question_for(STAFF_Q[0], rs, STAFF_Q[2], STAFF_Q[1])
    other_s = ur.apply_answer(
        reqs(budget="100000 PKR", deadline="within 2 weeks"), qs, "only 2", "en"
    )
    assert other_s.status is F and other_s.updates[0].replaces is None
    rb = reqs(budget="not much")
    qb = question_for(BUDGET_Q[0], rb, BUDGET_Q[2], BUDGET_Q[1])
    other_b = ur.apply_answer(
        reqs(staff="only 1 person", deadline="within 2 weeks"), qb, "50k PKR", "en"
    )
    assert other_b.status is F and other_b.updates[0].replaces is None


def test_tried_outcome_proposal_targets_one_item() -> None:
    r = reqs(tried=(("a paper register", "hmm"), ("flyers", "ok")))
    v = [
        unknown(
            cc.RULE_TRIED,
            "the option repeats something the owner tried, and how it went is not clear",
        )
    ]
    q = ur.choose_question(v, r, ["Keep a register"])
    assert q is not None and len(q.target_limits) == 2
    p = ur.apply_answer(r, q, "it did not work", "en")
    assert len(p.updates) == 1 and p.updates[0].replaces == "a paper register"


def test_place_answer_is_read_by_the_gate_place_reader() -> None:
    q = _bare_question("place_allowed")
    ok = ur.apply_answer(reqs(), q, "Lahore", "en")
    assert ok.status is F and ok.updates[0].value.lower().startswith("only in")
    unreadable = ur.apply_answer(reqs(), q, "لاہور", "ur")
    assert unreadable.status is S and unreadable.reason == "script_unreadable"
    assert ur.apply_answer(reqs(), q, "xqzv", "en").status is S


def test_tools_resources_has_no_reading_and_stays_unknown() -> None:
    p = ur.apply_answer(reqs(), _bare_question("tools_resources"), "a laptop and a phone", "en")
    assert p.status is S and p.reason == "not_enforced_by_gate"


def test_why_options_never_repeat_and_follow_option_order() -> None:
    r = reqs(budget="not much")
    v = [unknown(cc.RULE_BUDGET, "no figure in the budget text")] * 3
    q = ur.choose_question(v, r, ["third", "first", "second"])
    assert q is not None and q.option_texts == ("third", "first", "second")
    assert q.options == (0, 1, 2)
