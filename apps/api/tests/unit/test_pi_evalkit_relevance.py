"""The scripted relevance scorer (FT-A3): its verdicts, hard failures, negative controls, report,
Held-out access log and the calibration helpers. Everything here is a check of code and case files.
No model is called, so none of it measures how well pi solves a problem. Agent-drafted labels and
human labels are separate inputs and are never merged."""

import copy
import json
import tempfile
from pathlib import Path

import pytest

from app.modules.pi.evalkit import (
    access_log,
    relevance,
    relevance_report,
    replay,
    scorers,
    splits,
)
from app.modules.pi.evalkit import (
    relevance_calibration as calibration,
)

CASES_DIR = Path(replay.__file__).with_name("cases")
ALL_PLAN = json.loads((CASES_DIR / "plan.json").read_text(encoding="utf-8"))
PLAN = [c for c in ALL_PLAN if c["kind"] != "borderline_relevance"]  # the 30 core cases
EXTRACTION = replay.load_cases(str(CASES_DIR / "extraction.json"))
HELD_IDS = {c["id"] for c in PLAN if splits.split_of(c) == splits.HELD_OUT}


@pytest.fixture()
def workdir():
    with tempfile.TemporaryDirectory() as tmp:  # pytest's own temp base is not writable here
        yield Path(tmp)


def brief(constraints=(), words=("late orders",), facts=("two supervisors",)):
    return {
        "problems": [
            {
                "id": "p1",
                "title": "Orders ship late",
                "figures": [],
                "user_words": list(words),
                "facts": list(facts),
                "constraints": list(constraints),
            }
        ],
        "roles": ["supervisor"],
        "systems": [],
    }


# ------------------------------------------------------------------ the scorer
@pytest.mark.parametrize("case", PLAN, ids=lambda c: c["id"])
def test_the_scorer_reproduces_every_expected_verdict(case) -> None:
    result = relevance.score_case(case)
    wrong = [
        (r["id"], r["expected"], r["got"]) for r in result["results"] if r["expected"] != r["got"]
    ]
    assert wrong == []


def test_a_violated_confirmed_constraint_rejects_the_idea_whatever_its_link_score() -> None:
    constraint = {
        "kind": "cannot_change",
        "text": "cannot stop production",
        "blocks": ["training"],
        "status": "confirmed",
    }
    text = "Run training for the two supervisors on late orders every week"
    out = relevance.score_candidate(brief([constraint]), text)
    assert out["problem_link"] >= 1 and out["verdict"] == "violates_constraint"


def test_an_assumed_constraint_does_not_reject() -> None:
    constraint = {
        "kind": "cannot_change",
        "text": "maybe no training",
        "blocks": ["training"],
        "status": "assumed",
    }
    text = "Run training for the two supervisors on late orders every week"
    assert relevance.score_candidate(brief([constraint]), text)["verdict"] == "relevant"


def test_a_generic_idea_is_never_relevant_and_an_unrelated_one_is_irrelevant() -> None:
    b = brief()
    assert (
        relevance.score_candidate(b, "Use better software to improve your business")["verdict"]
        == "generic"
    )
    assert (
        relevance.score_candidate(b, "Paint the car park a brighter colour")["verdict"]
        == "irrelevant"
    )


def test_an_idea_that_only_repeats_the_owner_is_restates_owner() -> None:
    out = relevance.score_candidate(brief(), "Late orders and two supervisors")
    assert out["verdict"] == "restates_owner"


def test_no_idea_is_a_valid_result_and_is_never_padded_to_a_quota() -> None:
    weak = ["Use better software", "Paint the car park", "Grow your business"]
    assert relevance.pick_ideas(brief(), weak, wanted=3) == []
    assert relevance.pick_ideas(brief(), [], wanted=3) == []
    strong = "Let the supervisor list late orders each morning"
    assert relevance.pick_ideas(brief(), [strong, *weak], wanted=3) == [strong]


def test_the_scorer_is_deterministic() -> None:
    case = PLAN[0]
    assert relevance.score_case(case) == relevance.score_case(copy.deepcopy(case))


def test_layer_b_plan_fields_are_inert() -> None:
    case = copy.deepcopy(PLAN[0])
    before = relevance.score_case(case)
    case["expected"]["plan"] = {
        "steps": [{"id": "s1", "any": ["anything"]}],
        "dependencies": [{"from": "s1", "to": "s2"}],
        "roles": ["x"],
        "next_action": {"any": ["now"]},
    }
    assert relevance.score_case(case) == before


def test_negative_controls_fail_when_a_label_is_wrong() -> None:
    case = copy.deepcopy(PLAN[0])
    for candidate in case["expected"]["candidates"]:
        candidate["verdict"] = "relevant" if candidate["verdict"] != "relevant" else "generic"
    result = relevance.score_case(case)
    assert result["agree"] < result["candidates"]
    flipped = copy.deepcopy(PLAN[0])
    for candidate in flipped["expected"]["candidates"]:
        if candidate["verdict"] == "violates_constraint":
            candidate["verdict"] = "relevant"
    result = relevance.score_case(flipped)
    assert result["missed_relevant"] >= 1 and result["agree"] < result["candidates"]


def test_every_existing_extraction_score_is_unchanged() -> None:
    scores = [scorers.score_case(c, replay.replay(c)) for c in EXTRACTION]
    total = scorers.aggregate(scores)
    assert total["cases"] == 132 and total["unsupported_cause_cases"] == 0
    for key in (
        "recall",
        "precision",
        "figure_fidelity",
        "correction_fidelity",
        "constraint_fidelity",
    ):
        assert total[key] == 1.0


def test_a_group_below_three_cases_is_not_yet_measured() -> None:
    two = [relevance.score_case(c) for c in PLAN[:2]]
    assert relevance.aggregate(two)["measured"] is False
    many = [relevance.score_case(c) for c in PLAN[:5]]
    assert relevance.aggregate(many)["measured"] is True


# ------------------------------------------------------------------ the report
def test_the_report_is_headed_as_a_code_path_check_and_never_claims_ai_quality() -> None:
    text, totals = relevance_report.build(PLAN)
    assert "scripted code-path check" in text.casefold()
    assert "ai quality" not in text.casefold()
    assert "not yet measured" in text
    assert any(key.startswith("split:") for key in totals)


def test_the_report_prints_held_out_as_totals_only() -> None:
    text, _ = relevance_report.build(PLAN)
    assert HELD_IDS and not any(case_id in text for case_id in HELD_IDS)


def test_the_report_groups_by_language_industry_and_kind() -> None:
    text, totals = relevance_report.build(PLAN)
    for key in ("language:en", "language:hi", "kind:constraint_violation"):
        assert key in totals
    assert "poultry_farms" in text


# ------------------------------------------------------------------ Held-out access log
def test_the_access_log_is_append_only_and_records_who_why_and_when(workdir) -> None:
    path = workdir / "access.jsonl"
    access_log.append(path, who="lane E", why="first run", run_id="r1", split="held_out", count=7)
    access_log.append(path, who="reviewer", why="read", run_id="r2", split="held_out", count=7)
    rows = access_log.read(path)
    assert [r["who"] for r in rows] == ["lane E", "reviewer"]
    assert {"who", "why", "when", "run_id", "split", "count"} <= set(rows[0])
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_a_report_that_reads_held_out_writes_one_log_entry_and_none_without_a_path(workdir) -> None:
    path = workdir / "access.jsonl"
    relevance_report.build(PLAN)
    assert not path.exists()
    relevance_report.build(PLAN, access_log_path=path, who="lane E", why="scripted check")
    rows = access_log.read(path)
    assert len(rows) == 1 and rows[0]["count"] == len(HELD_IDS)


def test_a_log_path_without_who_and_why_is_refused(workdir) -> None:
    with pytest.raises(ValueError):
        relevance_report.build(PLAN, access_log_path=workdir / "a.jsonl", who="", why="")


# ------------------------------------------------------------------ calibration
SAMPLES = calibration.load_samples()
AGENT = calibration.load_agent_labels()


def test_there_are_twenty_samples_spread_across_verdicts_and_languages() -> None:
    assert len(SAMPLES) == 20 and len({s["sample_id"] for s in SAMPLES}) == 20
    by_case = {c["id"]: c for c in PLAN}
    verdicts = set()
    languages = set()
    for s in SAMPLES:
        case = by_case[s["case_id"]]
        languages.add(case["language"])
        verdicts.add(AGENT["labels"][s["sample_id"]])
    assert verdicts == {
        "relevant",
        "irrelevant",
        "generic",
        "violates_constraint",
        "restates_owner",
    }
    assert languages == {"en", "roman_ur", "ur", "ar", "hi"}


def test_agent_drafted_labels_are_a_separate_file_and_say_so() -> None:
    assert AGENT["label_source"] == "agent_drafted" and AGENT["human_confirmed"] is False
    assert set(AGENT["labels"]) == {s["sample_id"] for s in SAMPLES}
    assert all(not ({"label", "verdict"} & set(s)) for s in SAMPLES), "samples carry no labels"


def test_human_labels_are_a_separate_input_and_agent_labels_are_refused_as_human(workdir) -> None:
    path = workdir / "human.json"
    path.write_text(json.dumps({"label_source": "agent_drafted", "labels": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        calibration.load_human_labels(path)
    path.write_text(
        json.dumps(
            {"label_source": "human", "reviewers": ["a", "b"], "labels": {"s01": "generic"}}
        ),
        encoding="utf-8",
    )
    assert calibration.load_human_labels(path)["labels"] == {"s01": "generic"}


def test_the_blind_sheet_has_no_label_score_or_hint() -> None:
    sheet = calibration.blind_sheet(PLAN, SAMPLES)
    assert len(sheet) == 20
    allowed = {
        "sample_id",
        "industry",
        "language",
        "owner_problem",
        "facts",
        "constraints",
        "candidate_idea",
        "allowed_verdicts",
    }
    by_case = {c["id"]: c for c in PLAN}
    for row in sheet:
        assert set(row) <= allowed
        assert row["allowed_verdicts"] == list(relevance.VERDICTS)
        for constraint in row["constraints"]:
            assert set(constraint) == {"kind", "text"}, "the blocking keywords are a hint"
    texts = {c["text"] for case in by_case.values() for c in case["expected"]["candidates"]}
    assert all(row["candidate_idea"] in texts for row in sheet)
    for row in sheet:  # the only place a verdict word may appear is the list of allowed verdicts
        rest = {k: v for k, v in row.items() if k != "allowed_verdicts"}
        assert not any(v in json.dumps(rest["constraints"]) for v in ("relevant", "generic"))
    assert "reason" not in {key for row in sheet for key in row}


def test_the_human_sheet_is_empty_to_fill_in_and_written_as_json_csv_and_markdown(workdir) -> None:
    calibration.write_sheets(workdir)
    names = {p.name for p in workdir.iterdir()}
    assert {
        "blind_samples.json",
        "human_review_sheet.json",
        "human_review_sheet.csv",
        "human_review_sheet.md",
    } <= names
    rows = json.loads((workdir / "human_review_sheet.json").read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 40 and all(r["verdict"] == "" and r["notes"] == "" for r in rows)
    assert {r["block"] for r in rows} == {"core", "borderline"}
    assert (workdir / "blind_samples_borderline.json").exists()
    markdown = (workdir / "human_review_sheet.md").read_text(encoding="utf-8")
    assert "Block 1: core samples" in markdown and "Block 2: borderline samples" in markdown
    for verdict in relevance.VERDICTS:
        assert verdict in markdown
    assert "relevant" in (workdir / "human_review_sheet.csv").read_text(encoding="utf-8")


def test_agreement_percent_and_kappa_on_known_vectors() -> None:
    langs = {"a": "en", "b": "en", "c": "ur", "d": "ur"}
    perfect = calibration.agreement(
        {"a": "x", "b": "y", "c": "x", "d": "y"}, {"a": "x", "b": "y", "c": "x", "d": "y"}, langs
    )
    assert perfect["percent"] == 100.0 and perfect["kappa"] == 1.0
    half = calibration.agreement(
        {"a": "x", "b": "x", "c": "y", "d": "y"}, {"a": "x", "b": "y", "c": "y", "d": "x"}, langs
    )
    assert half["percent"] == 50.0 and half["kappa"] == 0.0
    assert half["per_language"]["en"]["n"] == 2 and "x" in half["per_verdict"]


def test_compare_reports_three_ways_and_refuses_to_claim_the_human_test_without_human_labels() -> (
    None
):
    grader = dict(AGENT["labels"])
    text = calibration.compare(grader)
    assert "scorer vs grader" in text and "scorer vs agent_drafted" in text
    assert "grader vs agent_drafted" in text
    assert "no human labels" in text.casefold()
    assert "hand-labelled" not in text.casefold() and "hand labelled" not in text.casefold()


def test_compare_adds_the_human_comparisons_only_when_a_human_file_is_given() -> None:
    grader = dict(AGENT["labels"])
    human = {"label_source": "human", "reviewers": ["a", "b"], "labels": dict(AGENT["labels"])}
    text = calibration.compare(grader, human)
    assert (
        "scorer vs human" in text and "grader vs human" in text and "agent_drafted vs human" in text
    )
