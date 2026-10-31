# ruff: noqa: E501
"""PS-4: causes, reasons, alternatives, data, corrections, links to problem ids and open items."""

from __future__ import annotations

import dataclasses
import re
from types import SimpleNamespace as NS
from typing import Any

import pytest

from app.modules.pi import blueprint_strings as bs
from app.modules.pi.blueprint_build import blueprint_issues, build_blueprint, render_blueprint
from app.modules.pi.blueprint_checks import SECTIONS, check_blueprint, section_report
from app.modules.pi.blueprint_extra import (
    alternatives_from,
    cause_from,
    causes_from,
    parse_corrections,
)
from app.modules.pi.blueprint_types import (
    READY,
    AlternativeRow,
    Blueprint,
    CauseRow,
    DataRow,
    OpenItem,
    OptionIn,
    ProblemRow,
    ReasonRow,
    StepIn,
)

PROBS = [
    {
        "id": "p1",
        "title": "Double bookings",
        "user_words": ["Two teams booked the same court"],
        "of_total": "about 12 clashes",
        "expected_outcome": "fewer than 3 clashes",
    },
    {"id": "p2", "title": "Lost reports", "user_words": ["I forget who told me what"]},
]
REQ: dict[str, Any] = {
    "constraints": [{"kind": "staff", "text": "only two receptionists"}],
    "corrections": [{"wrong": "8", "right": "12", "problem": "p1"}],
    "tried": [{"what": "paper diary", "outcome": "got lost"}],
}
FACTS = [
    "Two teams booked the same court, 8 no 12 clashes, fewer than 3 clashes. I forget who told "
    "me what. only two receptionists. paper diary got lost. the shared diary gets lost"
]


def l2(**over: Any) -> NS:
    base: dict[str, Any] = {
        "id": "O1", "kind": "process_change", "what": "Keep one shared booking sheet",
        "addresses": ("p1", "p2"), "benefit": "Fewer clashes on the sheet", "effort": "small",
        "reversibility": "reversible", "status": "recommended", "limits": (),
        "dependencies": (NS(kind="access", text="The paper diary", blocking=False),), "risks": (),
        "constraint_checks": (NS(constraint="staff", result="ok", why="two people are enough"),),
        "expected_outcome": "", "rejected_because": "",
    }  # fmt: skip
    base.update(over)
    return NS(**base)


def evid(words: tuple[str, ...] = ("diary gets lost",), verified: bool = True) -> NS:
    return NS(msg="m1", words=words, role="owner", verified=verified, seal=None)


CAUSE = NS(text="the shared diary gets lost", status="owner_said", evidence_for=(evid(),))
ALT_HIRE = l2(
    id="O2", what="Hire a booking clerk", status="rejected", rejected_because="owner cannot hire",
    constraint_checks=(NS(constraint="staff", result="violates", why="needs a third person"),),
    dependencies=(),
)  # fmt: skip
ALT_SOFT = l2(
    id="O3", what="Buy booking software", status="alternative",
    constraint_checks=(NS(constraint="budget", result="unknown", why=""),),
    dependencies=(NS(kind="data", text="Export of old bookings", blocking=True),),
)  # fmt: skip
OSET = NS(
    options=(l2(), ALT_HIRE, ALT_SOFT),
    recommended_id="O1",
    none_reason="",
    no_recommendation_reason="",
)


def build(lang: str = "en", causes: Any = None, oset: Any = OSET, **kw: Any) -> Blueprint:
    return build_blueprint(
        oset, kw.get("probs", PROBS), kw.get("req", REQ), kw.get("facts", FACTS), lang, None,
        root_causes={"p1": CAUSE} if causes is None else causes,
    )  # fmt: skip


def issues(bp: Blueprint, causes: Any = None) -> Any:
    return blueprint_issues(
        bp, FACTS, PROBS, REQ, None, {"p1": CAUSE} if causes is None else causes
    )


@pytest.fixture(scope="module")
def bp() -> Blueprint:
    return build()


def test_clean_and_ready(bp: Blueprint) -> None:
    assert bp.status == READY and issues(bp) == ()
    assert blueprint_issues(bp) == ()


def test_problems_keep_ids_and_owner_words(bp: Blueprint) -> None:
    assert bp.problems == (
        ProblemRow("p1", "Double bookings", ("Two teams booked the same court",)),
        ProblemRow("p2", "Lost reports", ("I forget who told me what",)),
    )


def test_facts_are_the_owners_words_and_the_correction_is_shown(bp: Blueprint) -> None:
    kinds = [(f.problem, f.kind, f.text) for f in bp.facts]
    assert ("p1", "said", "Two teams booked the same court") in kinds
    assert ("p1", "figure", "about 12 clashes") in kinds
    assert ("p1", "outcome", "fewer than 3 clashes") in kinds
    assert ("", "constraint", "only two receptionists") in kinds
    assert ("", "tried", "paper diary - got lost") in kinds
    corr = [f for f in bp.facts if f.kind == "correction"]
    assert [(f.problem, f.was, f.text) for f in corr] == [("p1", "8", "12")]


def test_a_correction_the_owner_never_said_is_dropped() -> None:
    assert parse_corrections([{"wrong": "8", "right": "99"}], "8 no 12") == ()
    assert parse_corrections([{"wrong": "8", "right": "12"}], "8 no 12") == (("8", "12", ""),)
    assert parse_corrections("junk", "x") == () and parse_corrections([5, None], "x") == ()
    req = dict(REQ, corrections=[{"wrong": "7", "right": "77", "problem": "p1"}])
    out = build(req=req)
    assert not [f for f in out.facts if f.kind == "correction"]


def test_cause_status_is_labelled_and_evidence_kept(bp: Blueprint) -> None:
    assert bp.causes[0] == CauseRow(
        "p1", "the shared diary gets lost", "owner_said", ("diary gets lost",)
    )
    assert bp.causes[1].problem == "p2" and bp.causes[1].status == "unknown"
    text = render_blueprint(bp)
    assert "p1: the shared diary gets lost (said by the owner)" in text
    assert "  Owner's words: diary gets lost" in text


def test_a_guess_is_labelled_as_pi_guess_and_is_an_open_decision() -> None:
    guess = NS(text="the staff are careless", status="pi_inferred", evidence_for=())
    out = build(causes={"p1": guess})
    assert out.causes[0].status == "pi_inferred"
    assert "p1: the staff are careless (pi's guess, not confirmed)" in render_blueprint(out)
    assert any(
        o.text == "Confirm this cause with the owner: the staff are careless"
        for o in out.open_items
    )
    assert issues(out, {"p1": guess}) == ()


def test_an_owner_status_without_the_owners_words_reads_as_a_guess() -> None:
    forged = NS(text="the shared diary gets lost", status="confirmed", evidence_for=())
    assert cause_from(forged).status == "pi_inferred"  # type: ignore[union-attr]
    out = build(causes={"p1": forged})
    assert out.causes[0].status == "pi_inferred"


def test_a_confirmed_cause_is_not_an_open_decision() -> None:
    ok = NS(text="the shared diary gets lost", status="confirmed", evidence_for=(evid(),))
    out = build(causes={"p1": ok})
    assert out.causes[0].status == "confirmed"
    assert not any(o.text.startswith("Confirm this cause") for o in out.open_items)


def test_cause_inputs_in_every_shape() -> None:
    assert cause_from(None) is None and cause_from("x") is None and cause_from(NS(text=" ")) is None
    stored = {"text": "t", "status": "owner_said", "evidence": {"words": ["w"]}}
    assert cause_from(stored).evidence == ("w",)  # type: ignore[union-attr]
    assert len(causes_from([CAUSE, CAUSE])) == 2
    assert causes_from({"p1": [CAUSE, "junk"], "p2": CAUSE})[1].problem == "p2"
    assert causes_from(stored)[0].problem == ""
    one = build_blueprint(l2(addresses=("p1",)), PROBS[:1], REQ, FACTS, "en", root_causes=CAUSE)
    assert one.causes[0].status == "owner_said"  # a single cause with no id fits a single problem


def test_the_recommendation_has_reasons_from_code_facts(bp: Blueprint) -> None:
    texts = [r.text for r in bp.reasons]
    assert texts == [
        "It answers: Double bookings; Lost reports.",
        "Limit staff: the option check found no conflict.",
        "It needs nothing from the owner before it can start.",
        "Effort: small. Can it be undone: reversible.",
        "Fewer clashes on the sheet",
    ]
    assert all(r.problems == ("p1", "p2") for r in bp.reasons)


def test_a_blocking_dependency_removes_the_no_block_reason() -> None:
    blocked = l2(dependencies=(NS(kind="data", text="Old bookings", blocking=True),))
    out = build(
        oset=NS(
            options=(blocked,), recommended_id="O1", none_reason="", no_recommendation_reason=""
        )
    )
    assert not any("needs nothing" in r.text for r in out.reasons)


def test_alternatives_say_why_not(bp: Blueprint) -> None:
    by = {a.id: a for a in bp.alternatives}
    assert set(by) == {"O2", "O3"} and "O1" not in by
    assert by["O2"].status == "rejected"
    assert by["O2"].why_not.split("\n") == [
        "Rejected: owner cannot hire",
        "It breaks a limit: staff. needs a third person",
    ]
    assert by["O3"].why_not.split("\n") == [
        "Could not check against: budget.",
        "It is blocked by: Export of old bookings.",
    ]
    assert any(
        o.text == "Options with an unchecked limit need a person to look: O3" for o in bp.open_items
    )


def test_an_alternative_with_no_recorded_reason_says_so() -> None:
    bare = l2(id="O4", what="Do nothing", constraint_checks=(), dependencies=())
    out = build(
        oset=NS(
            options=(l2(), bare), recommended_id="O1", none_reason="", no_recommendation_reason=""
        )
    )
    assert (
        out.alternatives[0].why_not
        == "Not recommended. No reason was recorded, so staff confirm why."
    )


def test_no_alternatives_is_stated_not_invented() -> None:
    out = build_blueprint(l2(), PROBS, REQ, FACTS, "en", root_causes={"p1": CAUSE})
    assert out.alternatives == (
        AlternativeRow("", "No other option was compared yet.", "none", "", ("p1", "p2")),
    )
    assert section_report(out)["alternatives"] == (True, False)


def test_alternatives_from_reads_an_option_set_and_junk() -> None:
    got = alternatives_from(OSET)
    assert [a.id for a in got] == ["O2", "O3"] and got[0].violated == (
        "staff: needs a third person",
    )
    assert got[1].unknown == ("budget",) and got[1].blocked_by == ("Export of old bookings",)
    assert alternatives_from(None) == () and alternatives_from(NS(options="x")) == ()


def test_options_keyword_gives_alternatives_for_an_option_in() -> None:
    opt = OptionIn(id="O1", kind="x", what="Keep a sheet", addresses=("p1",))
    out = build_blueprint(opt, PROBS, REQ, FACTS, "en", options=OSET)
    assert [a.id for a in out.alternatives] == ["O2", "O3"]


def test_data_records_and_connections_only_if_the_option_names_them() -> None:
    none = build()
    assert none.data == (
        DataRow(
            "none",
            "The option names no data records or connections yet. Staff confirm what is needed.",
            "unknown",
            ("p1", "p2"),
        ),
    )
    named = build(
        oset=NS(
            options=(l2(entities=("Booking",), integrations=("WhatsApp",)),),
            recommended_id="O1",
            none_reason="",
            no_recommendation_reason="",
        )
    )
    assert [(d.kind, d.name) for d in named.data] == [
        ("entity", "Booking"),
        ("integration", "WhatsApp"),
    ]
    text = render_blueprint(named)
    assert "Data record: Booking" in text
    assert (
        "Connection to WhatsApp: account and access details are not known until the owner supplies them."
        in text
    )


def test_permissions_are_the_options_or_not_stated() -> None:
    opt = l2(permissions=({"role": "owner", "what": "approve each phase"},))
    out = build(
        oset=NS(options=(opt,), recommended_id="O1", none_reason="", no_recommendation_reason="")
    )
    perms = {r.role: r.permissions for r in out.responsibilities}
    assert perms["owner"] == ("approve each phase",) and perms["staff"] == ()
    text = render_blueprint(out)
    assert "  Permissions: approve each phase" in text
    assert (
        "  Permissions: Permissions are not stated. Staff define them before work starts." in text
    )


def test_open_items_collect_missing_and_decisions(bp: Blueprint) -> None:
    texts = [o.text for o in bp.open_items]
    assert "No cause is recorded for this problem yet." in texts
    assert (
        "Costs: requires staff confirmation." in texts
        and "Timeline: requires staff confirmation." in texts
    )
    assert texts[-1] == "Owner decides: approve each checkpoint before work starts."
    assert any(o.kind == "missing" for o in bp.open_items) and any(
        o.kind == "decision" for o in bp.open_items
    )
    assert all(o.problems for o in bp.open_items)


def test_every_item_links_to_a_stated_problem(bp: Blueprint) -> None:
    ids = set(bp.problem_ids)
    for group in (
        bp.steps,
        bp.modules,
        bp.risks,
        bp.external,
        bp.acceptance,
        bp.reasons,
        bp.alternatives,
        bp.data,
        bp.open_items,
    ):
        for item in group:
            assert item.problems and set(item.problems) <= ids
    assert all(m.problem in ids for m in bp.success)


def test_a_step_that_answers_no_stated_problem_is_not_built() -> None:
    steps = (
        StepIn("Fix the roof", problems=("p9",)),
        StepIn("Keep one sheet", problems=("p2",)),
        StepIn("Check weekly"),
    )
    opt = OptionIn(
        id="O1", kind="process_change", what="Keep one sheet", addresses=("p1", "p2"), steps=steps
    )
    out = build_blueprint(opt, PROBS, REQ, FACTS, "en")
    acts = [(s.text, s.problems) for s in out.steps if s.kind == "action"]
    assert acts == [("Keep one sheet", ("p2",)), ("Check weekly", ("p1", "p2"))]
    assert "A step that answers none of the stated problems was removed." in out.unknowns
    assert blueprint_issues(out, FACTS, PROBS, REQ) == ()


def test_check_flags_unlinked_items_and_bad_causes(bp: Blueprint) -> None:
    def codes(x: Blueprint) -> set[str]:
        return {i.code for i in check_blueprint(x, bp.known_numbers)}

    assert codes(bp) == set()
    assert "BP-UNLINKED" in codes(
        dataclasses.replace(
            bp, steps=(dataclasses.replace(bp.steps[0], problems=()), *bp.steps[1:])
        )
    )
    assert "BP-UNLINKED" in codes(dataclasses.replace(bp, reasons=(ReasonRow("x", ()),)))
    assert "BP-UNLINKED" in codes(
        dataclasses.replace(bp, open_items=(OpenItem("missing", "x", ("p9",)),))
    )
    assert "BP-UNLINKED" in codes(
        dataclasses.replace(bp, causes=(CauseRow("p9", "x", "pi_inferred"),))
    )
    assert "BP-CAUSE" in codes(dataclasses.replace(bp, causes=(CauseRow("p1", "x", "confirmed"),)))
    assert "BP-CAUSE" in codes(dataclasses.replace(bp, causes=(CauseRow("p1", "x", "sure"),)))
    assert "BP-SEC-CAUSES" in codes(dataclasses.replace(bp, causes=()))
    assert "BP-SEC-FACTS" in codes(dataclasses.replace(bp, facts=()))
    assert "BP-SEC-OPEN" in codes(dataclasses.replace(bp, open_items=()))
    assert "BP-NUM" in codes(
        dataclasses.replace(bp, reasons=(ReasonRow("saves 77 hours", ("p1",)),))
    )
    assert "BP-PROMISE" in codes(
        dataclasses.replace(
            bp, alternatives=(AlternativeRow("O9", "guaranteed fix", "alternative", "", ("p1",)),)
        )
    )


def test_section_report_has_all_22_sections(bp: Blueprint) -> None:
    rep = section_report(bp)
    assert set(rep) == set(SECTIONS) and len(SECTIONS) == 22
    assert all(p for p, _ in rep.values())
    assert rep["causes"] == (True, True) and rep["costs"] == (True, False)


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar"])
def test_new_sections_render_in_every_language_in_order(lang: str) -> None:
    out = build(lang=lang)
    lines = render_blueprint(out).splitlines()
    t = bs.TABLES[lang]
    keys = [
        "sec_summary",
        "sec_problems",
        "sec_facts",
        "sec_causes",
        "sec_reasons",
        "sec_alternatives",
        "sec_architecture",
        "sec_workflow",
        "sec_external",
        "sec_data",
        "sec_responsibilities",
        "sec_risks",
        "sec_open",
        "sec_milestones",
        "sec_constraints",
    ]
    at = [lines.index(t[k]) for k in keys]
    assert at == sorted(at)
    assert not re.search(r"[|*#`~]", "\n".join(lines))
    assert t["cause_owner_said"] in "\n".join(lines)


def test_unreviewed_translations_have_no_untranslated_placeholders() -> None:
    for lang, table in bs.TABLES.items():
        for key, value in table.items():
            assert value.count("{") == value.count("}"), (lang, key)
