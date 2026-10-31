# ruff: noqa: E501
"""PS-4: the solution blueprint builder, its checks and its renderer (pure, no database, no model).

Golden tests per section, behaviour tests, the adapter contract, property tests over random inputs,
string-table tests, a baseline snapshot of the live BoxDraft, and timing at 1k, 10k and 100k.
The adversarial multilingual set is in test_pi_blueprint_adversarial.py.
"""

from __future__ import annotations

import dataclasses
import random
import re
import time
from types import SimpleNamespace as NS
from typing import Any

import pytest

from app.modules.pi import blueprint_strings as bs
from app.modules.pi.blueprint_build import (
    blueprint_issues,
    build_blueprint,
    option_from,
    recommended_from,
    render_blueprint,
)
from app.modules.pi.blueprint_checks import (
    MASK,
    SECTIONS,
    Issue,
    canon_number,
    check_blueprint,
    clean_text,
    free_texts,
    has_credential,
    has_money,
    has_promise,
    numbers_in,
    section_report,
)
from app.modules.pi.blueprint_types import (
    INSUFFICIENT,
    READY,
    REFUSED,
    ROLES,
    UNKNOWN,
    Blueprint,
    CheckIn,
    ConstraintRow,
    CostLine,
    DepIn,
    Edge,
    Measure,
    Milestone,
    OptionIn,
    RiskIn,
    Step,
    StepIn,
    TimeLine,
)

PROBLEMS = [
    {
        "id": "p1",
        "title": "Double bookings on the same court",
        "of_total": "about 12 clashes",
        "frequency_text": "every month",
        "user_words": ["Two teams booked the same court"],
        "expected_outcome": "fewer than 3 clashes a month",
    }
]
REQ = {
    "constraints": [
        {"kind": "staff", "text": "only two receptionists"},
        {"kind": "budget", "text": "budget 50000"},
    ],
    "tried": [{"what": "paper diary", "outcome": "got lost"}],
}
FACTS = [
    "Two teams booked the same court. About 12 clashes every month, fewer than 3 clashes a "
    "month would be fine. Only two receptionists. Budget 50000. We tried a paper diary and it "
    "got lost."
]
STAFF = {
    "costs": [{"item": "Setup", "amount": 1200, "currency": "PKR", "source": "quote QX"}],
    "durations": [{"text": "4 days", "source": "staff estimate", "step": "S1"}],
}


def option(**over: Any) -> OptionIn:
    base: dict[str, Any] = {
        "id": "O1",
        "kind": "workzap_build",
        "what": "A shared booking sheet that every receptionist updates before confirming a slot.",
        "addresses": ("p1",),
        "steps": (
            StepIn("List every court and slot in one sheet"),
            StepIn("Check the sheet before confirming any booking", role="owner"),
            StepIn("Review double bookings every week", phase=2),
        ),
        "dependencies": (DepIn("access", "The current paper diary", True),),
        "risks": (RiskIn("Receptionists may forget to update the sheet", "medium"),),
        "limits": ("Online booking is not changed",),
    }
    base.update(over)
    return OptionIn(**base)


def build(opt: Any = None, lang: str = "en", staff: Any = STAFF, **kw: Any) -> Blueprint:
    return build_blueprint(
        option() if opt is None else opt,
        kw.get("problems", PROBLEMS),
        kw.get("req", REQ),
        kw.get("facts", FACTS),
        lang,
        staff,
    )


def issues_of(bp: Blueprint, staff: Any = STAFF) -> tuple[Issue, ...]:
    return blueprint_issues(bp, FACTS, PROBLEMS, REQ, staff)


# ---- golden, one section each ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def bp() -> Blueprint:
    return build()


def test_ready_and_clean(bp: Blueprint) -> None:
    assert bp.status == READY and bp.executes_nothing is True
    assert issues_of(bp) == ()
    assert blueprint_issues(bp) == ()  # against the numbers the builder recorded


def test_golden_summary(bp: Blueprint) -> None:
    assert bp.summary is not None
    assert bp.summary.problem_ids == ("p1",) and bp.summary.option_id == "O1"
    assert bp.summary.text == (
        "This plan answers what you told us: Double bookings on the same court. What is "
        "proposed: A shared booking sheet that every receptionist updates before confirming a slot."
    )


def test_golden_architecture(bp: Blueprint) -> None:
    assert [(m.id, m.problems) for m in bp.modules] == [("C1", ("p1",))]
    assert bp.modules[0].name.startswith("A shared booking sheet")
    assert bp.modules[0].not_changed == ("Online booking is not changed",)


def test_golden_workflow(bp: Blueprint) -> None:
    assert [(s.id, s.kind, s.role) for s in bp.steps] == [
        ("A1", "approval", "reviewer"),
        ("G2", "approval", "owner"),
        ("S1", "action", "staff"),
        ("S2", "action", "owner"),
        ("G3", "approval", "owner"),
        ("S3", "action", "staff"),
        ("R1", "review", "owner"),
        ("X1", "rollback", "owner"),
    ]
    assert [s.phase for s in bp.steps] == [1, 2, 2, 2, 3, 3, 3, 3]
    s1 = bp.steps[2]
    assert s1.text == "List every court and slot in one sheet"
    assert s1.done_check == (
        "The owner confirms in chat that this is done: List every court and slot in one sheet"
    )


def test_golden_dependencies(bp: Blueprint) -> None:
    assert {(e.before, e.after) for e in bp.edges} == {
        ("A1", "G2"),
        ("G2", "S1"),
        ("S1", "S2"),
        ("S2", "G3"),
        ("G3", "S3"),
        ("S3", "R1"),
        ("S1", "X1"),
    }


def test_golden_external(bp: Blueprint) -> None:
    assert [(e.id, e.kind, e.text, e.status, e.blocking) for e in bp.external] == [
        ("E1", "access", "The current paper diary", UNKNOWN, True)
    ]
    assert "Needed from the owner: The current paper diary" in bp.unknowns


def test_golden_responsibilities(bp: Blueprint) -> None:
    assert [(r.role, r.steps) for r in bp.responsibilities] == [
        ("owner", ("G2", "S2", "G3", "R1", "X1")),
        ("staff", ("S1", "S3")),
        ("reviewer", ("A1",)),
    ]


def test_golden_costs_staff_only(bp: Blueprint) -> None:
    assert bp.costs == (CostLine("Setup", 1200.0, "PKR", "quote QX", "staff_supplied"),)
    bare = build(staff=None)
    assert bare.costs == (CostLine("plan", None, "", "staff", UNKNOWN),)


def test_golden_timeline(bp: Blueprint) -> None:
    assert bp.timeline == (
        TimeLine("S1", "4 days", "staff estimate", "staff_supplied"),
        TimeLine("S2", "", "", UNKNOWN),
        TimeLine("S3", "", "", UNKNOWN),
        TimeLine("plan", "", "", UNKNOWN),
    )


def test_timeline_owner_deadline_is_owner_sourced() -> None:
    req = {"constraints": [{"kind": "deadline", "text": "before Ramadan"}]}
    out = build(req=req, staff=None)
    assert TimeLine("plan", "before Ramadan", "owner", "owner_stated") in out.timeline
    assert not any(t.item == "plan" and t.status == UNKNOWN for t in out.timeline)


def test_golden_risks_and_unknowns(bp: Blueprint) -> None:
    assert [(r.text, r.level, r.source) for r in bp.risks] == [
        (
            "Work cannot start until this is supplied: The current paper diary",
            "high",
            "missing_fact",
        ),
        ("Receptionists may forget to update the sheet", "medium", "option"),
    ]
    assert bp.unknowns == (
        "Steps without a stated role follow the kind of option. Staff confirm who does them.",
        "Needed from the owner: The current paper diary",
        "The owner has not stated a deadline.",
    )


def test_missing_facts_become_risks_and_unknowns() -> None:
    probs = [{"id": "p1", "title": "Late rent", "user_words": ["rent is late"]}]
    out = build(problems=probs, req={}, facts=["rent is late"], staff=None)
    texts = [r.text for r in out.risks]
    assert (
        "The starting figure for Late rent is not known, so progress cannot be measured until it is recorded."
        in texts
    )
    assert "The result the owner wants for Late rent is not stated." in texts
    assert "The owner has not stated a budget limit." in out.unknowns
    assert "The owner has not said who can help on their side." in out.unknowns


def test_golden_milestones(bp: Blueprint) -> None:
    assert [(m.id, m.steps) for m in bp.milestones] == [
        ("M1", ("A1",)),
        ("M2", ("G2", "S1", "S2")),
        ("M3", ("G3", "S3")),
        ("M4", ("R1", "X1")),
    ]
    assert all(m.check and m.name for m in bp.milestones)


def test_golden_acceptance(bp: Blueprint) -> None:
    assert [(c.id, c.steps, c.problems) for c in bp.acceptance] == [
        ("AC1", ("R1",), ("p1",)),
        ("AC2", ("R1",), ("p1",)),
        ("AC3", ("S1", "S2", "S3"), ("p1",)),
    ]
    assert bp.acceptance[0].text.endswith("fewer than 3 clashes a month")
    assert bp.acceptance[1].text == (
        "Double bookings on the same court: the count in the same period as the starting "
        "figure is at or below 3."
    )


def test_acceptance_at_or_below_only_from_the_owner_and_only_with_a_reduce_cue() -> None:
    probs = [dict(PROBLEMS[0], expected_outcome="we want a calm month with 3 clashes")]
    out = build(problems=probs, facts=["we want a calm month with 3 clashes"])
    assert not any("at or below" in c.text for c in out.acceptance)
    probs = [dict(PROBLEMS[0], expected_outcome="a better diary")]
    out = build(problems=probs, facts=["a better diary"])
    assert not any("at or below" in c.text for c in out.acceptance)
    assert out.success[0].target == "" and out.success[0].target_source == ""


def test_no_outcome_gives_a_measurement_not_a_target() -> None:
    probs = [{"id": "p1", "title": "Late rent", "user_words": ["rent is late"]}]
    out = build(problems=probs, req={}, facts=["rent is late"], staff=None)
    m = out.success[0]
    assert (m.baseline, m.baseline_source, m.target, m.target_source) == ("", "step B1", "", "")
    assert [s.id for s in out.steps if s.kind == "measure"] == ["B1"]
    assert "step B1" in m.baseline_source
    assert any("has not said what result" in c.text for c in out.acceptance)
    assert issues_of_probs(out, probs) == ()


def issues_of_probs(bp: Blueprint, probs: Any) -> tuple[Issue, ...]:
    return blueprint_issues(bp, ["rent is late"], probs, {}, None)


def test_golden_success_measures(bp: Blueprint) -> None:
    assert bp.success == (
        Measure(
            "SM1",
            "p1",
            "Count of: Double bookings on the same court",
            "about 12 clashes every month",
            "owner",
            "fewer than 3 clashes a month",
            "owner",
        ),
    )


def test_golden_rollback_and_approvals(bp: Blueprint) -> None:
    x1 = [s for s in bp.steps if s.kind == "rollback"]
    assert len(x1) == 1 and x1[0].role == "owner" and x1[0].done_check
    gates = [s for s in bp.steps if s.kind == "approval"]
    assert [(g.id, g.role) for g in gates] == [("A1", "reviewer"), ("G2", "owner"), ("G3", "owner")]


def test_golden_constraint_table(bp: Blueprint) -> None:
    assert [(c.label, c.kind, c.result) for c in bp.constraints] == [
        ("staff", "staff", "unknown"),
        ("budget", "budget", "unknown"),
        ("tried#1", "tried", "unknown"),
    ]
    assert bp.constraints[1].text == "The owner gave a budget limit. Staff read the exact words."
    assert all(c.reason == "Not checked against this option yet." for c in bp.constraints)


def test_constraints_ok_only_with_a_check_and_never_by_default() -> None:
    opt = option(
        checks=(
            CheckIn("staff", "ok", "two people can keep one sheet"),
            CheckIn("budget", "unknown"),
        )
    )
    out = build(opt)
    rows = {c.label: c for c in out.constraints}
    assert rows["staff"].result == "ok" and rows["staff"].reason == "two people can keep one sheet"
    assert rows["budget"].result == "unknown"
    assert rows["tried#1"].result == "unknown"


def test_a_check_with_ok_and_no_reason_gets_the_fixed_reason() -> None:
    out = build(option(checks=(CheckIn("staff", "ok", ""),)))
    assert {c.label: c for c in out.constraints}[
        "staff"
    ].reason == "The option check found no conflict."


def test_violated_hard_constraint_refuses_via_option_check() -> None:
    out = build(option(checks=(CheckIn("staff", "violates", "needs four people"),)))
    assert out.status == REFUSED and out.steps == ()
    assert out.refusal == (
        "Not built: the option breaks something the owner said: only two receptionists. needs four people",
    )
    assert [c.result for c in out.constraints] == ["violates", "unknown", "unknown"]
    assert check_blueprint(out, out.known_numbers) == ()


def test_blocks_phrase_refuses_on_whole_words_only() -> None:
    req = {"constraints": [{"kind": "cannot_change", "text": "no new app", "blocks": ["app"]}]}
    ok = build(req=req)  # "application" is not "app"
    assert ok.status == READY
    opt = option(steps=(StepIn("Install the app on every phone"),))
    out = build(opt, req=req)
    assert out.status == REFUSED
    assert out.constraints[0].reason == "The option contains: app"


def test_soft_constraint_violation_does_not_refuse() -> None:
    req = {
        "constraints": [
            {"kind": "other", "text": "prefers blue", "hard": False, "blocks": ["sheet"]}
        ]
    }
    out = build(req=req)
    assert out.status == READY and out.constraints[0].result == "violates"
    assert any(i.code == "BP-CONSTR" for i in issues_of(out)) is False  # hard False is not an issue


def test_tried_repeat_is_flagged_for_a_person_not_refused() -> None:
    probs = PROBLEMS
    req = {"tried": [{"what": "shared booking sheet every receptionist", "outcome": "ignored"}]}
    out = build(req=req, problems=probs)
    row = out.constraints[0]
    assert out.status == READY and row.result == "unknown"
    assert row.reason == "This may repeat something already tried. A person should check."


# ---- insufficient information ----------------------------------------------------------------------


def test_no_problem_asks_the_one_targeted_question_last() -> None:
    out = build_blueprint(option(), [], REQ, FACTS, "en")
    assert out.status == INSUFFICIENT and out.steps == ()
    assert [m.code for m in out.missing] == ["problem"]
    assert out.next_question == "What is the main thing going wrong in your business right now?"
    text = render_blueprint(out)
    assert text.splitlines()[-1] == out.next_question
    assert qmarks(text) == 1


def test_no_option_is_listed_without_inventing_a_question() -> None:
    out = build_blueprint(None, PROBLEMS, REQ, FACTS, "en")
    assert [m.code for m in out.missing] == ["option"] and out.next_question == ""
    assert qmarks(render_blueprint(out)) == 0


def test_option_that_answers_no_stated_problem_asks_which_matters() -> None:
    out = build(option(addresses=("p9",)))
    assert out.status == INSUFFICIENT
    assert [m.code for m in out.missing] == ["option_not_tied"]
    assert out.next_question == "Which of the problems you mentioned matters most to solve first?"
    out2 = build(option(addresses=()))
    assert out2.status == INSUFFICIENT


def test_rejected_or_empty_option_builds_nothing() -> None:
    assert build(option(status="rejected")).status == INSUFFICIENT
    assert build(option(what="   ")).status == INSUFFICIENT
    assert build(option(what="Guaranteed 100% fix. Trust me.")).status == INSUFFICIENT


def test_everything_missing_lists_everything_and_asks_about_the_problem() -> None:
    out = build_blueprint(None, None, None, None, "ar")
    assert [m.code for m in out.missing] == ["problem", "option"]
    assert out.next_question == bs.AR["q_problem"]


def test_problem_with_no_words_and_no_title_is_not_a_stated_problem() -> None:
    out = build(problems=[{"id": "p1"}])
    assert out.status == INSUFFICIENT and out.missing[0].code == "problem"


# ---- cleaning: nothing invented gets in ------------------------------------------------------------


def test_an_untraceable_number_is_masked_and_listed() -> None:
    opt = option(steps=(StepIn("Call 40 tenants before the due date"),))
    out = build(opt)
    step = [s for s in out.steps if s.kind == "action"][0]
    assert step.text == f"Call {MASK} tenants before the due date"
    assert (
        "A figure the owner did not give was removed from the text. Staff confirm it."
        in out.unknowns
    )
    assert issues_of(out) == ()


def test_a_number_the_owner_gave_is_kept() -> None:
    opt = option(steps=(StepIn("Limit the sheet to 12 clashes at first"),))
    step = [s for s in build(opt).steps if s.kind == "action"][0]
    assert step.text == "Limit the sheet to 12 clashes at first"


def test_money_in_option_text_is_masked_never_priced() -> None:
    opt = option(steps=(StepIn("Set up the sheet for Rs 5,000"),))
    out = build(opt)
    step = [s for s in out.steps if s.kind == "action"][0]
    assert "5,000" not in step.text and MASK in step.text
    assert "An amount in the option text was removed. Only staff give costs." in out.unknowns


def test_promise_sentence_is_removed_the_rest_stays() -> None:
    opt = option(steps=(StepIn("Use one sheet. This guarantees zero clashes."),))
    step = [s for s in build(opt).steps if s.kind == "action"][0]
    assert step.text == "Use one sheet."
    assert (
        "A sentence that made a claim about results was removed from the option text."
        in build(opt).unknowns
    )


def test_a_denied_guarantee_is_not_a_promise() -> None:
    assert not has_promise("We cannot guarantee anything here")
    assert has_promise("We cannot guarantee anything, but this will double your bookings")
    assert not has_promise("guarantee nahi de sakta")
    assert not has_promise("لا نضمن شيئا")


def test_credential_sentence_is_removed() -> None:
    opt = option(steps=(StepIn("Ask the owner for the OTP. Update the sheet."),))
    out = build(opt)
    step = [s for s in out.steps if s.kind == "action"][0]
    assert step.text == "Update the sheet."
    assert "A sentence asking for private details was removed from the option text." in out.unknowns


def test_budget_words_are_never_repeated() -> None:
    out = build()
    assert "50000" not in render_blueprint(out)
    assert "50000" in out.known_numbers  # it is the owner's number, only not repeated


def test_staff_input_without_a_source_or_a_valid_amount_is_dropped() -> None:
    staff = {
        "costs": [
            {"item": "Setup", "amount": 1200, "source": ""},
            {"item": "Run", "amount": "many", "source": "x"},
            {"item": "Neg", "amount": -5, "source": "x"},
            {"item": "Inf", "amount": float("inf"), "source": "x"},
            {"item": "Bool", "amount": True, "source": "x"},
            {"item": "Ok", "amount": "2,500", "currency": "PKR", "source": "quote 7"},
        ],
        "durations": [{"text": "3 days", "source": ""}],
    }
    out = build(staff=staff)
    assert out.costs == (CostLine("Ok", 2500.0, "PKR", "quote 7", "staff_supplied"),)
    assert "A staff input was ignored because it had no source or no valid amount." in out.unknowns
    assert not any(t.duration == "3 days" for t in out.timeline)


def test_staff_duration_for_a_missing_step_moves_to_the_plan() -> None:
    staff = {"durations": [{"text": "5 days", "source": "staff", "step": "S9"}]}
    out = build(staff=staff, facts=[*FACTS, "5 days"])
    assert TimeLine("plan", "5 days", "staff", "staff_supplied") in out.timeline
    assert (
        "A staff duration named a step that does not exist. It is shown for the whole plan."
        in out.unknowns
    )


def test_staff_can_set_a_step_role_but_only_a_real_role() -> None:
    staff = {"roles": [{"step": "S1", "role": "pi"}, {"step": "S3", "role": "janitor"}]}
    out = build(staff=staff)
    roles = {s.id: s.role for s in out.steps}
    assert roles["S1"] == "pi" and roles["S3"] == "staff"


def test_declared_order_after_is_used_and_forward_references_fall_back() -> None:
    steps = (
        StepIn("List slots", id="a"),
        StepIn("Check the sheet", id="b", after=("a",)),
        StepIn("Review weekly", id="c", after=("b", "a")),
        StepIn("Close the loop", id="d", after=("zzz",)),
    )
    out = build(option(steps=steps))
    pairs = {(e.before, e.after) for e in out.edges}
    assert {("S1", "S2"), ("S2", "S3"), ("S1", "S3")} <= pairs
    assert ("S3", "S4") in pairs and ("S1", "S4") not in pairs  # bad ref: list order
    assert "The order of some steps was unclear. They follow the order of the list." in out.unknowns
    assert issues_of(out) == ()


def test_option_with_no_steps_is_one_step_and_says_so() -> None:
    out = build(option(steps=()))
    assert [s.id for s in out.steps if s.kind == "action"] == ["S1"]
    assert (
        "The option gave no detailed steps. Staff break it down before work starts." in out.unknowns
    )


def test_phases_get_one_owner_gate_each_and_cap_at_four() -> None:
    steps = tuple(StepIn(f"Do thing {chr(97 + i)}", phase=i + 1) for i in range(6))
    out = build(option(steps=steps))
    phases = sorted({s.phase for s in out.steps if s.kind == "action"})
    assert phases == [2, 3, 4]
    assert [s.id for s in out.steps if s.id.startswith("G")] == ["G2", "G3", "G4"]
    assert issues_of(out) == ()


def test_no_known_dependency_is_stated_not_invented() -> None:
    out = build(option(dependencies=()))
    assert [e.id for e in out.external] == ["E1"]
    assert out.external[0].text.startswith("Nothing else is known to be needed")


def test_baseline_step_per_problem_without_a_figure_by_pi() -> None:
    probs = [
        {"id": "p1", "title": "Late rent", "user_words": ["late"]},
        {"id": "p2", "title": "Lost reports", "user_words": ["lost"], "of_total": "many"},
        {"id": "p3", "title": "Noise", "user_words": ["noise"]},
    ]
    out = build(
        option(addresses=("p1", "p2", "p3")), problems=probs, req={}, facts=["late lost noise many"]
    )
    b = [s for s in out.steps if s.kind == "measure"]
    assert [(s.id, s.role, s.problems) for s in b] == [("B1", "pi", ("p1",)), ("B2", "pi", ("p3",))]
    assert [m.baseline_source for m in out.success] == ["step B1", "owner", "step B2"]
    assert all(s.done_check for s in b)


# ---- the adapter ----------------------------------------------------------------------------------


def l2_option(**over: Any) -> NS:
    """A stand-in with the attribute names of `blueprint_models.Option` (L2-3)."""
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "Keep one shared sheet for all bookings",
        "addresses": ("p1",),
        "benefit": "Fewer clashes on the sheet",
        "effort": "small",
        "reversibility": "reversible",
        "status": "recommended",
        "works_on": (),
        "catalogue_key": None,
        "fit": NS(problem_link=("p1",), facts_reused=(), generic=False),
        "limits": ("Online booking is not changed",),
        "trade_offs": ("Needs daily habit",),
        "dependencies": (NS(kind="access", text="The paper diary", blocking=True),),
        "risks": (NS(text="Staff forget", level="medium"),),
        "constraint_checks": (NS(constraint="staff", result="ok", why="two people are enough"),),
        "expected_outcome": "fewer than 3 clashes a month",
        "evidence": (),
        "rejected_because": "",
        "cost": NS(source="staff", amount=None),
    }
    base.update(over)
    return NS(**base)


def test_adapter_reads_l2_option_attributes_by_name() -> None:
    o = option_from(l2_option())
    assert o is not None
    assert (o.id, o.kind, o.what, o.addresses, o.status) == (
        "O1",
        "process_change",
        "Keep one shared sheet for all bookings",
        ("p1",),
        "recommended",
    )
    assert o.dependencies == (DepIn("access", "The paper diary", True),)
    assert o.risks == (RiskIn("Staff forget", "medium"),)
    assert o.checks == (CheckIn("staff", "ok", "two people are enough"),)
    assert o.limits == ("Online booking is not changed",)
    assert o.expected_outcome == "fewer than 3 clashes a month"
    assert o.steps == () and o.modules == ()  # not in L2-3 today


def test_adapter_never_reads_a_cost() -> None:
    assert not hasattr(option_from(l2_option()), "cost")


def test_adapter_accepts_mappings_and_junk() -> None:
    assert option_from({"id": "x", "what": "a sheet", "addresses": ["p1"]}) is not None
    for junk in (None, "text", 5, 1.5, True, [], ()):
        assert option_from(junk) is None
    weird = option_from(NS(what=["not", "text"], addresses="p1", dependencies="x", risks=5))
    assert weird is not None and weird.what == "" and weird.addresses == ()


def test_recommended_from_an_option_set() -> None:
    o1, o2 = l2_option(id="O1"), l2_option(id="O2", what="Other")
    opts = NS(options=(o1, o2), recommended_id="O2", none_reason="", no_recommendation_reason="")
    got, why = recommended_from(opts)
    assert got is not None and got.id == "O2" and why == ""
    none = NS(options=(o1,), recommended_id=None, none_reason="no fit", no_recommendation_reason="")
    assert recommended_from(none) == (None, "no fit")
    again = NS(
        options=(), recommended_id=None, none_reason="", no_recommendation_reason="not sure yet"
    )
    assert recommended_from(again) == (None, "not sure yet")


def test_build_accepts_l2_option_and_option_set_directly() -> None:
    out = build(l2_option())
    assert out.status == READY and out.summary is not None and out.summary.option_id == "O1"
    rows = {c.label: c.result for c in out.constraints}
    assert rows["staff"] == "ok"
    opts = NS(
        options=(l2_option(),), recommended_id="O1", none_reason="", no_recommendation_reason=""
    )
    assert build(opts).status == READY
    assert (
        build(
            NS(options=(), recommended_id=None, none_reason="", no_recommendation_reason="")
        ).status
        == INSUFFICIENT
    )


def test_l2_unknown_dependency_kind_reads_as_other() -> None:
    o = option_from(l2_option(dependencies=(NS(kind="weird", text="x", blocking="yes"),)))
    assert o is not None and o.dependencies == (DepIn("other", "x", False),)


# ---- never raises, linear caps ---------------------------------------------------------------------

JUNK = [
    None, 0, 1.5, True, "", "text", b"bytes", [], [None], [[]], {}, {"a": 1}, (1, 2), {1, 2}, object(),
    [object()], {"id": None}, [{"id": []}], NS(), lambda: 1, float("nan"), "\x00\x01", "𝔘𝔫𝔦", 10**100,
]  # fmt: skip


@pytest.mark.parametrize("junk", range(len(JUNK)))
def test_junk_in_every_position_never_raises(junk: int) -> None:
    j = JUNK[junk]
    for args in (
        (j, PROBLEMS, REQ, FACTS, "en", STAFF),
        (option(), j, REQ, FACTS, "en", STAFF),
        (option(), PROBLEMS, j, FACTS, "en", STAFF),
        (option(), PROBLEMS, REQ, j, "en", STAFF),
        (option(), PROBLEMS, REQ, FACTS, j, STAFF),
        (option(), PROBLEMS, REQ, FACTS, "en", j),
    ):
        out = build_blueprint(*args)
        assert isinstance(out, Blueprint) and out.status in (READY, INSUFFICIENT, REFUSED)
        render_blueprint(out, "ar")
        blueprint_issues(out)
    for fn in (render_blueprint, blueprint_issues):
        assert fn(j) is not None  # type: ignore[operator]


def test_a_raising_property_on_an_input_never_escapes() -> None:
    class Bad:
        @property
        def what(self) -> str:
            raise RuntimeError("boom")

        def __getattr__(self, name: str) -> Any:
            raise RuntimeError(name)

    out = build_blueprint(Bad(), PROBLEMS, REQ, FACTS, "en")
    assert out.status == INSUFFICIENT


def test_inputs_are_capped_and_work_is_bounded() -> None:
    probs = [
        {"id": f"p{i}", "title": f"Problem {i}", "user_words": [f"word {i}"]} for i in range(1000)
    ]
    steps = tuple(StepIn(f"Step number {i}") for i in range(1000))
    opt = option(addresses=tuple(p["id"] for p in probs), steps=steps)
    out = build_blueprint(opt, probs, REQ, ["x " * 100000] * 1000, "en", STAFF)
    assert out.status == READY
    assert len([s for s in out.steps if s.kind == "action"]) == 12
    assert len(out.success) == 8 and len(out.problem_ids) == 8
    assert all(len(t) < 2000 for _, t in free_texts(out))


# ---- the checks catch a bad blueprint --------------------------------------------------------------


def codes(bp_: Blueprint, known: Any = None) -> set[str]:
    k = bp_.known_numbers if known is None else known
    return {i.code for i in check_blueprint(bp_, k)}


def replace_step(bp_: Blueprint, sid: str, **kw: Any) -> Blueprint:
    steps = tuple(dataclasses.replace(s, **kw) if s.id == sid else s for s in bp_.steps)
    return dataclasses.replace(bp_, steps=steps)


def test_check_flags_every_defect(bp: Blueprint) -> None:
    assert codes(bp) == set()
    assert "BP-STEP-DONE" in codes(replace_step(bp, "S1", done_check=" "))
    assert "BP-STEP-ROLE" in codes(replace_step(bp, "S1", role="Acme Ltd"))
    assert "BP-STEP-ROLE" in codes(replace_step(bp, "S1", role=""))
    assert "BP-STEP-TEXT" in codes(replace_step(bp, "S1", text=""))
    assert "BP-STEP-KIND" in codes(replace_step(bp, "S1", kind="deploy"))
    dup = dataclasses.replace(bp, steps=(*bp.steps, bp.steps[0]))
    assert "BP-STEP-ID" in codes(dup)
    ghost = dataclasses.replace(bp, edges=(*bp.edges, Edge("S1", "S77")))
    assert "BP-DEP-MISSING" in codes(ghost)
    loop = dataclasses.replace(bp, edges=(*bp.edges, Edge("S3", "G2")))
    assert "BP-DEP-CYCLE" in codes(loop)
    ungated = dataclasses.replace(bp, edges=tuple(e for e in bp.edges if e.before != "G3"))
    assert "BP-GATE" in codes(ungated)
    reviewer_only = replace_step(bp, "G2", role="staff")
    assert "BP-GATE" in codes(reviewer_only)
    no_rb = dataclasses.replace(bp, steps=tuple(s for s in bp.steps if s.kind != "rollback"))
    assert "BP-ROLLBACK" in codes(no_rb)


def test_check_flags_dishonest_text(bp: Blueprint) -> None:
    n = replace_step(bp, "S1", text="Call 77 tenants")
    assert "BP-NUM" in codes(n)
    assert "BP-MONEY" in codes(replace_step(bp, "S1", text="Pay Rs 400 for it"))
    assert "BP-PROMISE" in codes(replace_step(bp, "S1", text="This guarantees success"))
    assert "BP-CRED" in codes(replace_step(bp, "S1", text="Send the password"))
    assert "BP-NUM" in codes(replace_step(bp, "S1", text="٧٧ tenants"))  # Arabic-Indic digits


def test_check_flags_cost_and_time_defects(bp: Blueprint) -> None:
    c1 = dataclasses.replace(bp, costs=(CostLine("x", 1200.0, "PKR", "", "staff_supplied"),))
    assert "BP-COST" in codes(c1)
    c2 = dataclasses.replace(bp, costs=(CostLine("x", 999.0, "PKR", "staff", "staff_supplied"),))
    assert "BP-COST" in codes(c2)
    c3 = dataclasses.replace(bp, costs=(CostLine("x", 1200.0, "PKR", "pi", "staff_supplied"),))
    assert "BP-COST" in codes(c3)
    c4 = dataclasses.replace(bp, costs=(CostLine("x", None, "", "staff", "staff_supplied"),))
    assert "BP-COST" in codes(c4)
    t1 = dataclasses.replace(bp, timeline=(TimeLine("plan", "4 days", "", "staff_supplied"),))
    assert "BP-TIME" in codes(t1)


def test_check_flags_structure_defects(bp: Blueprint) -> None:
    assert "BP-SEC-SUMMARY" in codes(dataclasses.replace(bp, summary=None))
    assert "BP-SEC-COSTS" in codes(dataclasses.replace(bp, costs=()))
    assert "BP-SEC-MILESTONES" in codes(dataclasses.replace(bp, milestones=()))
    assert "BP-SEC-CONSTRAINTS" in codes(dataclasses.replace(bp, constraints=()))
    assert "BP-SEC-ACCEPTANCE" in codes(dataclasses.replace(bp, acceptance=()))
    assert "BP-SEC-SUCCESS" in codes(dataclasses.replace(bp, success=()))
    assert "BP-MILE" in codes(
        dataclasses.replace(bp, milestones=(Milestone("M9", "x", ("S99",), "c"),))
    )
    assert "BP-MILE" in codes(dataclasses.replace(bp, milestones=(Milestone("M9", "x", (), "c"),)))
    assert "BP-PROB" in codes(dataclasses.replace(bp, problem_ids=("zz",)))
    assert "BP-EXEC" in codes(dataclasses.replace(bp, executes_nothing=False))
    assert "BP-STATUS" in codes(dataclasses.replace(bp, status="done"))
    rows = (ConstraintRow("budget", "budget", "t", "violates", "r", True),)
    assert "BP-CONSTR" in codes(dataclasses.replace(bp, constraints=rows))
    rows = (ConstraintRow("budget", "budget", "t", "ok", "", True),)
    assert "BP-CONSTR" in codes(dataclasses.replace(bp, constraints=rows))
    rows = (ConstraintRow("budget", "budget", "t", "satisfied", "r", True),)
    assert "BP-CONSTR" in codes(dataclasses.replace(bp, constraints=rows))
    resp = (dataclasses.replace(bp.responsibilities[0], role="Acme"),)
    assert "BP-ROLE" in codes(dataclasses.replace(bp, responsibilities=resp))
    resp = (dataclasses.replace(bp.responsibilities[0], steps=("S99",)),)
    assert "BP-RESP-STEP" in codes(dataclasses.replace(bp, responsibilities=resp))


def test_check_flags_success_measure_defects(bp: Blueprint) -> None:
    m = bp.success[0]

    def with_measure(**kw: Any) -> Blueprint:
        return dataclasses.replace(bp, success=(dataclasses.replace(m, **kw),))

    assert "BP-SUCC" in codes(with_measure(target_source=""))
    assert "BP-SUCC" in codes(with_measure(baseline_source="pi"))
    assert "BP-SUCC" in codes(with_measure(baseline="", baseline_source="owner"))
    assert "BP-SUCC" in codes(with_measure(baseline="", baseline_source="step B9"))
    assert "BP-SUCC" not in codes(with_measure(baseline="", baseline_source="step R1"))


def test_not_ready_blueprints_are_checked_for_honesty_only() -> None:
    out = build_blueprint(None, [], {}, [], "en")
    assert check_blueprint(out, ()) == ()
    assert "BP-MISSING" in codes(dataclasses.replace(out, missing=()))
    ref = build(option(checks=(CheckIn("staff", "violates", "no"),)))
    assert check_blueprint(ref, ref.known_numbers) == ()
    assert "BP-REFUSAL" in codes(dataclasses.replace(ref, refusal=()))
    assert "BP-EMPTY" in codes(
        dataclasses.replace(out, steps=(Step("S1", "action", "x", "owner", "d", 1),))
    )
    lying = dataclasses.replace(out, next_question="Pay Rs 5000 now?")
    assert "BP-MONEY" in codes(lying)


def test_check_with_independent_sources_is_stricter_than_recorded_numbers() -> None:
    forged = dataclasses.replace(build(), known_numbers=(*build().known_numbers, "999"))
    forged = replace_step(forged, "S1", text="Call 999 tenants")
    assert blueprint_issues(forged) == ()  # trusts its own record
    assert any(i.code == "BP-NUM" for i in blueprint_issues(forged, FACTS, PROBLEMS, REQ, STAFF))


def test_check_never_raises_on_a_malformed_record() -> None:
    assert check_blueprint(None, ())[0].code == "BP-MALFORMED"  # type: ignore[arg-type]
    bad = dataclasses.replace(build(), steps=(None,))  # type: ignore[arg-type]
    assert check_blueprint(bad, ())[0].code == "BP-MALFORMED"
    assert blueprint_issues(build(), object(), object(), object(), object()) is not None


def test_section_report_separates_present_from_grounded(bp: Blueprint) -> None:
    rep = section_report(bp)
    assert set(rep) == set(SECTIONS) and len(SECTIONS) == 15
    assert all(present for present, _ in rep.values())
    assert rep["costs"] == (True, True) and rep["timeline"] == (True, True)
    bare = section_report(build(staff=None))
    assert bare["costs"] == (True, False) and bare["timeline"] == (True, False)
    assert bare["constraints"] == (True, False)  # nothing was checked
    assert section_report(build_blueprint(None, [], {}, [], "en"))["workflow"] == (False, False)


# ---- text hygiene ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("80 tenants", ["80"]),
        ("٨٠ کرایہ دار", ["80"]),
        ("۸۰ flats", ["80"]),
        ("８０ flats", ["80"]),
        ("1,000 and 1000.0", ["1000", "1000"]),
        ("S1 and p2 and G3", []),
        ("two shops, teen dukaan", ["2", "3"]),
        ("007", ["7"]),
        ("0.50", ["0.5"]),
        ("", []),
        (None, []),
        (5, []),
    ],
)
def test_numbers_in(text: Any, expected: list[str]) -> None:
    assert numbers_in(text) == expected


def test_canon_number() -> None:
    assert [canon_number(x) for x in ("1,000", "1000.00", "00", "0", "٠٥", "3.10")] == [
        "1000", "1000", "0", "0", "5", "3.1",
    ]  # fmt: skip


MONEY_SAMPLES = [
    "Rs 5000", "PKR 300", "5,000", "450,000.50", "3 lakh", "2k", "5 million", "cost 5000",
    "price: 2500", "$40", "€5", "£9", "₹20", "10 crore", "fee of 3000", "budget around 90000",
    "paying 1200", "5 hazaar", "ten thousand rupees", "aed 12", "dirhams", "روپے", "ریال", "درهم",
]  # fmt: skip


@pytest.mark.parametrize("text", MONEY_SAMPLES)
def test_has_money_is_a_superset_of_the_live_pattern(text: str) -> None:
    from app.modules.pi.brain_docs import MONEY_IN_TEXT

    if MONEY_IN_TEXT.search(text):
        assert has_money(text)
    if text in ("5 hazaar", "روپے", "ریال", "درهم", "ten thousand rupees"):
        assert has_money(text)


def test_has_money_does_not_flag_counts_or_years() -> None:
    for text in ("4 shops", "12 clashes", "in 2026", "about 80 tenants", "3 days"):
        assert not has_money(text)


def test_clean_text_cuts_and_reports() -> None:
    known = frozenset({"12"})
    text, notes = clean_text(
        "Count 12 now. It is guaranteed. Enter your password. Pay Rs 99. Add 7.", known
    )
    assert text == f"Count 12 now. Pay {MASK}. Add {MASK}."
    assert notes == ("promise", "credential", "money", "number") or set(notes) == {
        "promise", "credential", "money", "number",
    }  # fmt: skip
    assert clean_text("x" * 5000, frozenset())[0] == "x" * 300
    assert clean_text(None, frozenset()) == ("", ())
    assert clean_text("a" * 10 + "\x00\x07" + "b", frozenset())[0] == "a" * 10 + " b"


def test_clean_text_never_lengthens_digits_or_leaks_an_untraced_number() -> None:
    text, _ = clean_text("Call ٤٠ tenants, ٤٠ times, forty-five minutes, 4O", frozenset())
    assert not [n for n in numbers_in(text) if n != "0"]


def test_has_credential() -> None:
    for t in ("password", "Send your OTP", "card number", "CNIC", "پاس ورڈ", "كلمة المرور"):
        assert has_credential(t)
    assert not has_credential("the receptionist updates the sheet")


# ---- strings --------------------------------------------------------------------------------------


def test_every_language_has_the_same_keys_and_placeholders() -> None:
    ph = lambda s: sorted(re.findall(r"{(\w+)}", s))  # noqa: E731
    for lang, table in bs.TABLES.items():
        assert set(table) == set(bs.EN), lang
        for key, value in table.items():
            assert ph(value) == ph(bs.EN[key]), (lang, key)


def test_no_fixed_phrase_carries_money_a_promise_a_credential_or_a_digit() -> None:
    for lang, table in bs.TABLES.items():
        for key, value in table.items():
            assert not has_money(value), (lang, key)
            assert not has_promise(value), (lang, key)
            assert not has_credential(value), (lang, key)
            assert not re.search(r"\d", value), (lang, key)
            assert not re.search(r"[|*#`~]", value), (lang, key)
            assert "?" not in value or key.startswith("q_"), (lang, key)


def test_english_uses_british_spelling_and_no_will() -> None:
    joined = " ".join(bs.EN.values()).lower()
    assert not re.search(r"\bwill\b", joined)
    for american in ("color", "organize", "center", "license", "program "):
        assert american not in joined
    assert "workzap" in joined and "workzap" not in " ".join(bs.EN[k] for k in ("title",)).lower()


def test_language_names_normalise() -> None:
    assert [bs.norm_language(x) for x in ("en", "EN", " roman_ur ", "Roman Urdu", "urdu", "AR", "arabic", "xx", None, 5)] == [
        "en", "en", "roman_ur", "roman_ur", "ur", "ar", "ar", "en", "en", "en",
    ]  # fmt: skip
    assert bs.tr("en", "no_such_key") == "no_such_key"
    assert bs.tr("zz", "title") == "Solution blueprint"
    assert bs.tr("en", "summary") == bs.EN["summary"]  # a missing placeholder never raises


# ---- render ---------------------------------------------------------------------------------------

HEADERS = ["sec_summary", "sec_architecture", "sec_workflow", "sec_dependencies", "sec_external",
           "sec_responsibilities", "sec_costs", "sec_timeline", "sec_risks", "sec_milestones",
           "sec_acceptance", "sec_success", "sec_rollback", "sec_approvals", "sec_constraints"]  # fmt: skip


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
def test_render_has_every_section_in_order_in_every_language(bp: Blueprint, lang: str) -> None:
    text = render_blueprint(bp, lang)
    lines = text.splitlines()
    at = [lines.index(bs.TABLES[lang][h]) for h in HEADERS]
    assert at == sorted(at) and lines[0] == bs.TABLES[lang]["title"]
    assert not re.search(r"[|*#`~]", text) and qmarks(text) == 0
    assert "\t" not in text


def test_render_golden_english_costs_timeline_and_gates(bp: Blueprint) -> None:
    lines = render_blueprint(bp).splitlines()
    assert "Setup: 1200 PKR (staff: quote QX)" in lines
    assert "S1: 4 days (from: staff estimate)" in lines
    assert "S2: To be estimated by staff." in lines
    assert "plan: To be estimated by staff." in lines
    assert (
        "G3: Owner checkpoint: nothing in the next phase starts until the owner says yes in chat."
        in lines
    )
    assert "S2: Comes after S1" in lines and "G3: Comes after S2" in lines
    assert (
        "  Who: owner. Done when: The owner confirms in chat that this is done: Check the sheet before confirming any booking"
        in lines
    )
    assert "  Starting figure: about 12 clashes every month" in lines
    assert "  Target: fewer than 3 clashes a month" in lines
    assert "staff: only two receptionists. not known. Not checked against this option yet." in lines
    assert (
        "E1: The current paper diary (Not known until the owner supplies it). Blocks the start."
        in lines
    )
    assert (
        "Costs" in lines
        and "Nothing starts until the owner says yes at each checkpoint. Costs and dates come only from staff."
        in lines
    )


def test_render_unknown_cost_and_target_say_so() -> None:
    probs = [{"id": "p1", "title": "Late rent", "user_words": ["late"]}]
    out = build(problems=probs, req={}, facts=["late"], staff=None)
    lines = render_blueprint(out).splitlines()
    assert "plan: To be quoted by staff." in lines
    assert "  Target: To be agreed with the owner." in lines
    assert "  Starting figure: Not known yet. Recorded first in B1." in lines


def test_render_keeps_the_owners_words_in_every_language() -> None:
    probs = [
        {
            "id": "p1",
            "title": "کرایہ دیر سے آتا ہے",
            "user_words": ["کرایہ"],
            "of_total": "٨٠ کرایہ دار",
        }
    ]
    out = build(problems=probs, req={}, facts=["کرایہ ٨٠ کرایہ دار"], staff=None)
    for lang in ("en", "ur", "ar", "roman_ur"):
        assert "کرایہ دیر سے آتا ہے" in render_blueprint(out, lang)
        assert "٨٠ کرایہ دار" in render_blueprint(out, lang)


def test_render_neutralises_markdown_in_owner_words() -> None:
    probs = [{"id": "p1", "title": "| a | **bold** | # head `code`", "user_words": ["x"]}]
    out = build(problems=probs, req={}, facts=["x"], staff=None)
    assert not re.search(r"[|*#`]", render_blueprint(out))


def test_render_defaults_to_the_build_language_and_survives_junk_language() -> None:
    out = build(lang="ur")
    assert render_blueprint(out).splitlines()[0] == bs.UR["title"]
    assert render_blueprint(out, 12345).splitlines()[0] == bs.EN["title"]


def test_refused_render_names_the_constraint_and_has_no_question() -> None:
    out = build(option(checks=(CheckIn("staff", "violates", "needs four"),)))
    text = render_blueprint(out)
    assert bs.EN["sec_refusal"] in text.splitlines() and qmarks(text) == 0
    assert "only two receptionists" in text


# ---- property tests: random inputs ----------------------------------------------------------------

WORDS = {
    "en": "late rent tenant court booking sheet owner staff diary stock order driver shift".split(),
    "roman_ur": "kiraya late kirayedar phone register shikayat flat hafta list reminder".split(),
    "ur": "کرایہ دیر شکایت فلیٹ ہفتہ فہرست فون رجسٹر یاد".split(),
    "ar": "إيجار متأخر مستأجر هاتف سجل شكوى شقة أسبوع قائمة تذكير".split(),
}
RISKY = [
    "This guarantees results.", "Pay Rs 5000 first.", "Send your password.", "It will double sales.",
    "ضمان النتيجة", "پاس ورڈ دیں", "ہو جائے گا", "رقم 5000 روپے", "zaroor ho jayega", "100% pakka",
]  # fmt: skip


def random_case(seed: int) -> dict[str, Any]:
    r = random.Random(seed)
    lang = r.choice(list(WORDS))
    w = WORDS[lang]

    def sentence() -> str:
        s = " ".join(r.choice(w) for _ in range(r.randint(1, 6)))
        if r.random() < 0.3:
            s += f" {r.choice(['2', '15', '٣٠', '۴۰', '200', 'two', 'teen'])}"
        if r.random() < 0.2:
            s += ". " + r.choice(RISKY)
        return s

    n_p = r.randint(0, 4)
    probs = []
    facts = []
    for i in range(n_p):
        title = sentence()
        facts.append(title)
        probs.append(
            {
                "id": f"p{i + 1}",
                "title": title,
                "user_words": [title] if r.random() < 0.7 else [],
                "of_total": sentence() if r.random() < 0.5 else "",
                "expected_outcome": sentence() if r.random() < 0.5 else "",
            }
        )
    facts += [sentence() for _ in range(r.randint(0, 4))]
    steps = tuple(
        StepIn(
            sentence(),
            role=r.choice(["", "owner", "staff", "pi", "reviewer", "Acme", "OWNER"]),
            done_check=r.choice(["", "", sentence()]),
            after=tuple(f"S{r.randint(1, 8)}" for _ in range(r.randint(0, 2))),
            phase=r.randint(0, 5),
            id=f"S{i + 1}" if r.random() < 0.7 else "",
        )
        for i in range(r.randint(0, 8))
    )
    opt = OptionIn(
        id="O1",
        kind=r.choice(["owner_action", "workzap_build", "process_change", "learn_first", ""]),
        what=sentence() if r.random() < 0.95 else "",
        addresses=tuple(
            f"p{r.randint(1, max(1, n_p) + (1 if r.random() < 0.1 else 0))}"
            for _ in range(r.randint(1, 3))
        )
        if r.random() < 0.95
        else (),
        steps=steps,
        dependencies=tuple(
            DepIn(r.choice(["access", "data", "person", "weird"]), sentence(), r.random() < 0.5)
            for _ in range(r.randint(0, 3))
        ),
        risks=tuple(
            RiskIn(sentence(), r.choice(["low", "medium", "high", "x"]))
            for _ in range(r.randint(0, 3))
        ),
        limits=tuple(sentence() for _ in range(r.randint(0, 2))),
        checks=tuple(
            CheckIn(
                r.choice(["staff", "budget", "cannot_change#1", "tried#1"]),
                r.choice(["ok", "unknown", "violates"]),
                sentence(),
            )
            for _ in range(r.randint(0, 2))
            if r.random() < 0.15
        ),
    )
    req = {
        "constraints": [
            {
                "kind": r.choice(["budget", "staff", "deadline", "cannot_change", "x"]),
                "text": sentence(),
                "blocks": [r.choice(w)] if r.random() < 0.1 else [],
            }
            for _ in range(r.randint(0, 3))
        ],
        "tried": [{"what": sentence(), "outcome": sentence()} for _ in range(r.randint(0, 2))],
        "expected_outcome": sentence() if r.random() < 0.3 else "",
    }
    staff = None
    if r.random() < 0.6:
        staff = {
            "costs": [
                {
                    "item": sentence(),
                    "amount": r.choice([100, 2500.5, "7,000", -1, "x"]),
                    "currency": "PKR",
                    "source": r.choice(["", "quote 1", "staff"]),
                }
                for _ in range(r.randint(0, 2))
            ],
            "durations": [
                {
                    "text": r.choice(["3 days", "two weeks", ""]),
                    "source": r.choice(["", "staff"]),
                    "step": r.choice(["", "S1", "S99"]),
                }
                for _ in range(r.randint(0, 2))
            ],
            "roles": [
                {"step": f"S{r.randint(1, 8)}", "role": r.choice(ROLES + ("zzz",))}
                for _ in range(r.randint(0, 2))
            ],
        }
    return {"opt": opt, "probs": probs, "req": req, "facts": facts, "lang": lang, "staff": staff}


def qmarks(text: str) -> int:
    return text.count("?") + text.count("؟")


def acyclic(bp_: Blueprint) -> bool:
    ids = [s.id for s in bp_.steps]
    pos = {sid: i for i, sid in enumerate(ids)}
    return all(
        e.before in pos and e.after in pos and pos[e.before] < pos[e.after] for e in bp_.edges
    )


@pytest.mark.parametrize("seed", range(300))
def test_property_ready_blueprints_are_complete_and_honest(seed: int) -> None:
    c = random_case(seed)
    out = build_blueprint(c["opt"], c["probs"], c["req"], c["facts"], c["lang"], c["staff"])
    assert out.status in (READY, INSUFFICIENT, REFUSED) and out.executes_nothing
    found = blueprint_issues(out, c["facts"], c["probs"], c["req"], c["staff"])
    assert found == (), found
    text = render_blueprint(out)
    assert not re.search(r"[|*#`~]", text)
    if out.status != READY:
        assert out.steps == ()
        if out.status == INSUFFICIENT:
            assert out.missing
            assert qmarks(text) == (1 if out.next_question else 0)
            if out.next_question:
                assert text.splitlines()[-1] == out.next_question
        else:
            assert out.refusal and any(k.result == "violates" for k in out.constraints)
        return
    assert qmarks(text) == 0
    known = set(out.known_numbers)
    # no untraceable number anywhere, in data or in the rendered text
    for _, t in free_texts(out):
        assert set(numbers_in(t)) <= known
    assert set(numbers_in(text)) <= known | {n for n in numbers_in(text) if False}
    for s in out.steps:
        assert s.role in ROLES and s.done_check.strip() and s.text.strip()
    assert acyclic(out)
    ids = {s.id for s in out.steps}
    assert all(e.before in ids and e.after in ids for e in out.edges)
    for s in out.steps:
        if s.kind == "action":
            gates = {g.id for g in out.steps if g.kind == "approval" and g.role == "owner"}
            assert gates & _ancestors(out, s.id)
    assert any(s.kind == "rollback" for s in out.steps)
    assert all(k.result != "ok" or k.reason for k in out.constraints)
    assert all(c_.amount is None or c_.source for c_ in out.costs)
    assert not any(has_money(t) for _, t in free_texts(out) if not t.startswith("Setup"))
    assert all(set(m.steps) <= ids and m.steps for m in out.milestones)
    for s in out.success:
        assert (s.baseline and s.baseline_source == "owner") or s.baseline_source.startswith(
            "step "
        )
        assert not s.target or s.target_source == "owner"
    # the same input twice gives the same blueprint
    again = build_blueprint(c["opt"], c["probs"], c["req"], c["facts"], c["lang"], c["staff"])
    assert again == out


def _ancestors(bp_: Blueprint, sid: str) -> set[str]:
    prev: dict[str, list[str]] = {}
    for e in bp_.edges:
        prev.setdefault(e.after, []).append(e.before)
    seen: set[str] = set()
    stack = list(prev.get(sid, ()))
    while stack:
        cur = stack.pop()
        if cur not in seen:
            seen.add(cur)
            stack.extend(prev.get(cur, ()))
    return seen


# ---- baseline snapshot of the live BoxDraft (read-only) --------------------------------------------


def test_live_boxdraft_has_phase_names_and_needs_but_no_blueprint_elements() -> None:
    """The PS-0 baseline: the live draft carries phases as names only and needs, with no dependencies,
    no success criteria, no roles, no costs or timeline. If this fails because BoxDraft grew fields,
    update the wiring note: the gap closed."""
    from app.modules.pi.brain_docs import BoxDraft, Line

    fields = set(BoxDraft.model_fields)
    assert {"phases", "needs", "components"} <= fields
    assert set(Line.model_fields) == {"text", "local", "refs"}  # a phase is a line of text: a name
    for absent in ("dependencies", "success", "acceptance", "roles", "costs", "timeline", "risks",
                   "milestones", "rollback", "approvals", "constraints"):  # fmt: skip
        assert not any(absent in f for f in fields), absent


# ---- timing ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", [1_000, 10_000, 100_000])
def test_timing_is_bounded_by_the_caps(size: int) -> None:
    probs = [{"id": f"p{i}", "title": f"Problem {i}", "user_words": ["w"]} for i in range(size)]
    steps = tuple(StepIn(f"Step {i}") for i in range(size))
    facts = ["fact " * 50] * size
    opt = option(addresses=("p0", "p1"), steps=steps)
    t0 = time.perf_counter()
    out = build_blueprint(opt, probs, REQ, facts, "en", STAFF)
    render_blueprint(out)
    blueprint_issues(out)
    elapsed = time.perf_counter() - t0
    assert out.status == READY
    assert elapsed < 1.0, elapsed


@pytest.mark.parametrize("size", [1_000, 10_000, 100_000])
def test_timing_long_text_is_cut_before_it_is_scanned(size: int) -> None:
    long_text = ("2 tenants and Rs 5 " * (size // 10)) + "x" * size
    t0 = time.perf_counter()
    for _ in range(20):
        clean_text(long_text, frozenset())
        has_promise(long_text[:5000])
    assert time.perf_counter() - t0 < 2.0
    assert len(clean_text(long_text, frozenset())[0]) <= 300
