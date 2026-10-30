"""The two-reviewer human labelling process and the borderline set (FT-A3, second step).

These check code and files only: blank per-reviewer sheets, the disagreement record, the
adjudication step, the agreement helper, the refusal to report an 85% human-label result without
two reviewers and twenty samples, and the separation of agent-drafted labels. No model is called,
and the borderline comparison is a finding about the scorer, not something the tests force to
agree."""

import json
import tempfile
from pathlib import Path

import pytest

from app.modules.pi.evalkit import human_review as hr
from app.modules.pi.evalkit import relevance, splits
from app.modules.pi.evalkit import relevance_calibration as cal
from app.modules.pi.evalkit import relevance_report as report

VERDICTS = list(relevance.VERDICTS)
IDS = [s["sample_id"] for s in cal.load_samples() + cal.load_borderline_samples()]


@pytest.fixture()
def workdir():
    with tempfile.TemporaryDirectory() as tmp:  # pytest's own temp base is not writable here
        yield Path(tmp)


def reviewer(name: str, verdicts: list[str] | None = None, ids: list[str] | None = None) -> dict:
    ids = ids if ids is not None else IDS
    pick = verdicts if verdicts is not None else [VERDICTS[i % 5] for i in range(len(ids))]
    return {"label_source": "human", "reviewer": name, "labels": dict(zip(ids, pick, strict=False))}


# ------------------------------------------------------------------ the borderline set
def test_there_are_twenty_borderline_samples_all_from_non_held_out_cases() -> None:
    samples = cal.load_borderline_samples()
    assert len(samples) == 20 and len({s["sample_id"] for s in samples}) == 20
    by_id = {c["id"]: c for c in cal.load_cases()}
    assert all(by_id[s["case_id"]]["kind"] == "borderline_relevance" for s in samples)
    assert all(splits.split_of(by_id[s["case_id"]]) != splits.HELD_OUT for s in samples)


def test_borderline_labels_are_agent_drafted_in_their_own_file() -> None:
    data = cal.load_borderline_agent_labels()
    assert data["label_source"] == "agent_drafted" and data["human_confirmed"] is False
    cases = [c for c in cal.load_cases() if c["kind"] == "borderline_relevance"]
    dev = [c for c in cases if splits.split_of(c) != splits.HELD_OUT]
    held = {c["id"] for c in cases if splits.split_of(c) == splits.HELD_OUT}
    keys = {f"{c['id']}/{x['id']}" for c in dev for x in c["expected"]["candidates"]}
    assert set(data["labels"]) == keys, (
        "Development candidates only: Held-out labels are not committed"
    )
    assert not any(key.split("/")[0] in held for key in {*data["labels"], *data["notes"]})
    assert set(data["labels"].values()) <= set(VERDICTS)
    core = cal.load_agent_labels()["labels"]
    assert set(core).isdisjoint(set(cal.borderline_agent_by_sample())), (
        "two label files, two id sets"
    )


def test_an_implied_limit_is_never_confirmed_and_never_rejects_an_idea() -> None:
    by_id = {c["id"]: c for c in cal.load_cases()}
    case = by_id["plan_bl_clinic_implied_budget_en_01"]
    limits = case["input"]["brief"]["problems"][0]["constraints"]
    assert [x["status"] for x in limits] == ["assumed"]
    first = case["expected"]["candidates"][0]["text"]
    assert (
        relevance.score_candidate(case["input"]["brief"], first)["verdict"] != "violates_constraint"
    )


def test_the_borderline_comparison_lists_development_and_only_counts_held_out() -> None:
    found = cal.borderline_comparison()
    assert len(found["development"]) == 20
    assert found["held_out_candidates"] > 0
    assert all("text" in r and "agent_drafted" in r and "scorer" in r for r in found["development"])
    listed = {r["case_id"] for r in found["development"]}
    held = {c["id"] for c in cal.load_cases() if splits.split_of(c) == splits.HELD_OUT}
    assert listed.isdisjoint(held), "Held-out borderline cases are counted, never listed"


def test_the_report_has_a_borderline_section_and_names_no_held_out_case(workdir) -> None:
    text = report.borderline_section(workdir / "access.jsonl", "lane E", "borderline section")
    assert "not human labels" in text
    held = {c["id"] for c in cal.load_cases() if splits.split_of(c) == splits.HELD_OUT}
    assert not any(case_id in text for case_id in held)


# ------------------------------------------------------------------ blank sheets per reviewer
def test_each_reviewer_gets_a_blank_sheet_in_its_own_order(workdir) -> None:
    written = hr.write_reviewer_sheets(workdir)
    assert {p.name for p in written} == {
        "human_review_reviewer_1.json",
        "human_review_reviewer_1.csv",
        "human_review_reviewer_2.json",
        "human_review_reviewer_2.csv",
    }
    one, two = (
        json.loads((workdir / f"human_review_reviewer_{n}.json").read_text(encoding="utf-8"))
        for n in (1, 2)
    )
    for sheet in (one, two):
        assert sheet["label_source"] == "human" and sheet["reviewer"] == ""
        assert len(sheet["rows"]) == 40
        assert all(r["verdict"] == "" and r["notes"] == "" for r in sheet["rows"])
        assert {r["block"] for r in sheet["rows"]} == {"core", "borderline"}
        assert not ({"label", "reason", "scorer"} & {k for r in sheet["rows"] for k in r})
    assert [r["sample_id"] for r in one["rows"]] != [r["sample_id"] for r in two["rows"]]
    assert "verdict" in (workdir / "human_review_reviewer_1.csv").read_text(encoding="utf-8-sig")


def test_a_reviewer_sheet_must_name_the_reviewer_and_use_allowed_verdicts(workdir) -> None:
    rows = [{"sample_id": "s01", "verdict": "relevant"}, {"sample_id": "s02", "verdict": "generic"}]
    path = workdir / "sheet.json"

    def write(data: dict) -> Path:
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    with pytest.raises(ValueError):
        hr.load_reviewer_sheet(write({"label_source": "human", "reviewer": "", "rows": rows}))
    with pytest.raises(ValueError):
        hr.load_reviewer_sheet(
            write({"label_source": "agent_drafted", "reviewer": "a", "rows": rows})
        )
    bad = [{"sample_id": "s01", "verdict": "good"}]
    with pytest.raises(ValueError):
        hr.load_reviewer_sheet(write({"label_source": "human", "reviewer": "a", "rows": bad}))
    blank = [*rows, {"sample_id": "s03", "verdict": ""}]
    with pytest.raises(ValueError):
        hr.load_reviewer_sheet(write({"label_source": "human", "reviewer": "a", "rows": blank}))
    ok = hr.load_reviewer_sheet(
        write({"label_source": "human", "reviewer": "a", "rows": blank}), require_complete=False
    )
    assert ok["labels"] == {"s01": "relevant", "s02": "generic"}


# ------------------------------------------------------------------ disagreements and adjudication
def test_the_disagreement_record_lists_only_the_differences_with_blank_fields() -> None:
    a = reviewer("rev_a", ["relevant", "generic", "irrelevant"], ["s01", "s02", "s03"])
    b = reviewer("rev_b", ["relevant", "irrelevant", "irrelevant"], ["s01", "s02", "s03"])
    record = hr.disagreement_record(a, b)
    assert record["label_source"] == "human_disagreements" and record["adjudicator"] == ""
    assert [i["sample_id"] for i in record["items"]] == ["s02"]
    item = record["items"][0]
    assert item["rev_a"] == "generic" and item["rev_b"] == "irrelevant"
    assert item["adjudicated"] == "" and item["rationale"] == ""


def test_adjudication_needs_a_named_third_person_and_every_disagreement_resolved() -> None:
    a = reviewer("rev_a", ["relevant", "generic"], ["s01", "s02"])
    b = reviewer("rev_b", ["relevant", "irrelevant"], ["s01", "s02"])
    record = hr.disagreement_record(a, b)
    with pytest.raises(ValueError):
        hr.adjudicated_labels(a, b, record)  # no adjudicator
    record["adjudicator"] = "rev_a"
    with pytest.raises(ValueError):
        hr.adjudicated_labels(a, b, record)  # one of the two reviewers
    record["adjudicator"] = "rev_c"
    with pytest.raises(ValueError):
        hr.adjudicated_labels(a, b, record)  # disagreement not resolved
    record["items"][0]["adjudicated"] = "not_a_verdict"
    with pytest.raises(ValueError):
        hr.adjudicated_labels(a, b, record)
    record["items"][0]["adjudicated"] = "irrelevant"
    assert hr.adjudicated_labels(a, b, record) == {"s01": "relevant", "s02": "irrelevant"}


# ------------------------------------------------------------------ the report and the 85% refusal
def test_few_samples_or_one_reviewer_refuse_an_85_percent_result() -> None:
    a = reviewer("rev_a", ids=IDS[:10])
    b = reviewer("rev_b", ids=IDS[:10])
    text = hr.process_report(a, b)
    assert "No 85% human-label result" in text and "have 10" in text
    same = hr.process_report(reviewer("rev_a"), reviewer("rev_a"))
    assert "No 85% human-label result" in same, "two sheets from one person are not two reviewers"


def test_twenty_samples_from_two_reviewers_make_the_result_eligible_but_not_automatic() -> None:
    a = reviewer("rev_a", ids=IDS[:20])
    b = reviewer("rev_b", ids=IDS[:20])
    eligible, count = hr.eligible_for_acceptance(a, b)
    assert eligible and count == 20
    text = hr.process_report(a, b)
    assert "No 85% human-label result" not in text
    assert "evaluated only with adjudicated labels and a grader file" in text


def test_the_report_gives_reviewer_agreement_then_adjudicated_against_scorer_and_grader() -> None:
    ids = IDS[:20]
    a = reviewer("rev_a", ids=ids)
    b = reviewer("rev_b", [VERDICTS[(i + (1 if i % 4 == 0 else 0)) % 5] for i in range(20)], ids)
    record = hr.disagreement_record(a, b)
    record["adjudicator"] = "rev_c"
    for item in record["items"]:
        item["adjudicated"] = item["rev_a"]
    adjudicated = hr.adjudicated_labels(a, b, record)
    grader = {i: "relevant" for i in ids}
    text = hr.process_report(a, b, adjudicated, grader)
    assert "reviewer vs reviewer" in text and "kappa" in text
    assert "adjudicated vs scorer" in text and "adjudicated vs grader" in text
    assert "Proposed 85% test (the owner has not approved it as a gate)" in text
    without_grader = hr.process_report(a, b, adjudicated)
    assert (
        "adjudicated vs scorer" in without_grader and "adjudicated vs grader" not in without_grader
    )


def test_reviewer_agreement_and_kappa_on_known_vectors() -> None:
    langs = {i: "en" for i in "abcd"}
    r = cal.agreement(
        {"a": "x", "b": "y", "c": "x", "d": "y"}, {"a": "x", "b": "y", "c": "x", "d": "y"}, langs
    )
    assert r["percent"] == 100.0 and r["kappa"] == 1.0
    half = cal.agreement(
        {"a": "x", "b": "x", "c": "y", "d": "y"}, {"a": "x", "b": "y", "c": "y", "d": "x"}, langs
    )
    assert half["percent"] == 50.0 and half["kappa"] == 0.0


def test_agent_drafted_labels_are_never_an_input_of_the_human_process() -> None:
    with pytest.raises(ValueError):
        cal.load_human_labels(cal.AGENT_PATH)
    with pytest.raises(ValueError):
        hr.load_reviewer_sheet(cal.AGENT_PATH)


# ------------------------------------------------------------------ the guard cannot be bypassed
def shifted(ids: list[str]) -> list[str]:
    """Verdicts that differ from the agent-drafted labels, so a sheet is never a copy of them."""
    agent = cal.agent_labels_all()
    return [VERDICTS[(VERDICTS.index(agent[i]) + 1) % 5] for i in ids]


def human(name: str, ids: list[str] | None = None) -> dict:
    ids = ids if ids is not None else IDS[:20]
    return reviewer(name, shifted(ids), ids)


@pytest.mark.parametrize(
    ("a", "b"),
    [("Ali", "ali"), ("Ali", "Ali  "), (" ali", "ALI"), ("Ali  Khan", "ali khan")],
)
def test_the_same_reviewer_under_another_spelling_is_not_two_reviewers(a: str, b: str) -> None:
    first, second = human(a), human(b)
    assert hr.eligible_for_acceptance(first, second)[0] is False
    assert "same reviewer" in hr.acceptance_problem(first, second)
    assert "No 85% human-label result" in hr.process_report(first, second)
    with pytest.raises(ValueError):
        hr.disagreement_record(first, second)


def test_the_adjudicator_must_differ_from_both_reviewers_after_normalisation() -> None:
    a, b = human("Ana Reviewer"), reviewer("Ben Reviewer", shifted(IDS[:20])[::-1], IDS[:20])
    record = hr.disagreement_record(a, b)
    for name in ("ana reviewer", "ANA  REVIEWER", "Ben Reviewer ", "  ben reviewer"):
        record["adjudicator"] = name
        with pytest.raises(ValueError):
            hr.adjudicated_labels(a, b, record)


def test_reviewers_must_cover_the_same_samples_and_only_known_ids_count() -> None:
    first = human("Ana Reviewer", IDS[:20])
    other = human("Ben Reviewer", IDS[:21])
    assert hr.eligible_for_acceptance(first, other)[0] is False
    assert "same samples" in hr.acceptance_problem(first, other)
    unknown = {**human("Ben Reviewer", IDS[:20])}
    unknown["labels"] = {**unknown["labels"], "zz99": "relevant"}
    with pytest.raises(ValueError):
        hr.eligible_for_acceptance(first, unknown)
    eligible, count = hr.eligible_for_acceptance(first, human("Ben Reviewer", IDS[:20]))
    assert eligible and count == 20


@pytest.mark.parametrize(
    "bad",
    [
        {"label_source": "human", "reviewer": "", "labels": {"s01": "generic"}},
        {"label_source": "human", "reviewer": "   ", "labels": {"s01": "generic"}},
        {"label_source": "agent_drafted", "reviewer": "a", "labels": {"s01": "generic"}},
        {
            "label_source": "human",
            "reviewer": "a",
            "labels": {"s01": "generic"},
            "human_confirmed": 1,
        },
        {"label_source": "human", "reviewer": "a", "labels": {"zz99": "generic"}},
        {"label_source": "human", "reviewer": "a", "labels": {"s01": "good"}},
        {"label_source": "human", "reviewer": "a", "labels": ["s01"]},
    ],
    ids=["no-name", "blank-name", "agent-source", "confirmed", "unknown-id", "bad-verdict", "list"],
)
def test_library_functions_validate_raw_dicts_like_the_loader(bad: dict) -> None:
    good = human("Ben Reviewer")
    for call in (
        lambda: hr.eligible_for_acceptance(bad, good),
        lambda: hr.eligible_for_acceptance(good, bad),
        lambda: hr.process_report(bad, good),
        lambda: hr.disagreement_record(bad, good),
        lambda: hr.adjudicated_labels(bad, good, {"adjudicator": "Cy", "items": []}),
    ):
        with pytest.raises(ValueError):
            call()


def test_a_sheet_that_copies_the_agent_labels_is_rejected() -> None:
    ids = IDS
    agent = cal.agent_labels_all()
    copied = reviewer("Ana Reviewer", [agent[i] for i in ids], ids)
    with pytest.raises(ValueError):
        hr.check_sheet(copied)
    with pytest.raises(ValueError):
        hr.eligible_for_acceptance(copied, human("Ben Reviewer", ids))


def test_a_grader_file_with_no_matching_ids_reports_no_overlap_and_never_crashes() -> None:
    ids = IDS[:20]
    a, b = human("Ana Reviewer", ids), human("Ben Reviewer", ids)
    adjudicated = {i: a["labels"][i] for i in ids}
    text = hr.process_report(a, b, adjudicated, {"nothing": "relevant"})
    assert "no overlap" in text.casefold()
    assert "None" not in text and "Proposed 85% test" not in text
    assert "No 85% comparison" in text
