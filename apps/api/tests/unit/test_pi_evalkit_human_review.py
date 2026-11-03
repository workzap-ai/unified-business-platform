"""The two-reviewer human labelling process and the borderline set (FT-A3, second step).

These check code and files only: blank per-reviewer sheets, the disagreement record, the
adjudication step, the neutral report (numbers and normalised names, never an acceptance verdict),
the structural checks that stop accidents, and the separation of agent-drafted labels. The tool
cannot verify who the reviewers are; no test pretends it can. No model is called, and the
borderline comparison is a finding about the scorer, not something the tests force to agree."""

import json
import tempfile
from pathlib import Path

import pytest

from app.modules.pi.evalkit import access_log, relevance, splits
from app.modules.pi.evalkit import human_review as hr
from app.modules.pi.evalkit import relevance_calibration as cal
from app.modules.pi.evalkit import relevance_report as report

VERDICTS = list(relevance.VERDICTS)
IDS = [s["sample_id"] for s in cal.load_samples() + cal.load_borderline_samples()]
ALL_CASES = cal.load_cases()
HELD_CASE = next(
    c
    for c in ALL_CASES
    if c["kind"] != "borderline_relevance" and splits.split_of(c) == splits.HELD_OUT
)


@pytest.fixture()
def workdir():
    with tempfile.TemporaryDirectory() as tmp:  # pytest's own temp base is not writable here
        yield Path(tmp)


def reviewer(name: str, verdicts: list[str] | None = None, ids: list[str] | None = None) -> dict:
    ids = ids if ids is not None else IDS
    pick = verdicts if verdicts is not None else [VERDICTS[i % 5] for i in range(len(ids))]
    return {"label_source": "human", "reviewer": name, "labels": dict(zip(ids, pick, strict=False))}


def shifted(ids: list[str], by: int = 1) -> list[str]:
    """Verdicts that never equal the agent-drafted label, so a sheet is not an agent copy."""
    agent = cal.agent_labels_all()
    return [VERDICTS[(VERDICTS.index(agent[i]) + by) % 5] for i in ids]


def pair(
    name_a: str = "Ana Reviewer", name_b: str = "Ben Reviewer", ids: list[str] | None = None
) -> tuple[dict, dict]:
    """Two reviewers who disagree on every fifth sample and agree with the agent on none."""
    ids = ids if ids is not None else IDS[:20]
    b_verdicts = [
        v if k % 5 else shifted([i], 2)[0]
        for k, (i, v) in enumerate(zip(ids, shifted(ids), strict=True))
    ]
    return reviewer(name_a, shifted(ids), ids), reviewer(name_b, b_verdicts, ids)


# ------------------------------------------------------------------ the borderline set
def test_there_are_twenty_borderline_samples_all_from_non_held_out_cases() -> None:
    samples = cal.load_borderline_samples()
    assert len(samples) == 20 and len({s["sample_id"] for s in samples}) == 20
    by_id = {c["id"]: c for c in ALL_CASES}
    assert all(by_id[s["case_id"]]["kind"] == "borderline_relevance" for s in samples)
    assert all(splits.split_of(by_id[s["case_id"]]) != splits.HELD_OUT for s in samples)


def test_borderline_labels_are_agent_drafted_in_their_own_file() -> None:
    data = cal.load_borderline_agent_labels()
    assert data["label_source"] == "agent_drafted" and data["human_confirmed"] is False
    cases = [c for c in ALL_CASES if c["kind"] == "borderline_relevance"]
    dev = [c for c in cases if splits.split_of(c) != splits.HELD_OUT]
    held = {c["id"] for c in cases if splits.split_of(c) == splits.HELD_OUT}
    keys = {f"{c['id']}/{x['id']}" for c in dev for x in c["expected"]["candidates"]}
    assert set(data["labels"]) == keys, "Development only: Held-out labels are not committed"
    assert not any(key.split("/")[0] in held for key in {*data["labels"], *data["notes"]})
    assert set(data["labels"].values()) <= set(VERDICTS)
    core = cal.load_agent_labels()["labels"]
    assert set(core).isdisjoint(set(cal.borderline_agent_by_sample())), (
        "two label files, two id sets"
    )


def test_an_implied_limit_is_never_confirmed_and_never_rejects_an_idea() -> None:
    by_id = {c["id"]: c for c in ALL_CASES}
    case = by_id["plan_bl_clinic_implied_budget_en_01"]
    limits = case["input"]["brief"]["problems"][0]["constraints"]
    assert [x["status"] for x in limits] == ["assumed"]
    first = case["expected"]["candidates"][0]["text"]
    assert (
        relevance.score_candidate(case["input"]["brief"], first)["verdict"] != "violates_constraint"
    )


def test_the_borderline_comparison_lists_development_and_only_counts_held_out(workdir) -> None:
    access = cal.Access(workdir / "access.jsonl", "lane E", "borderline comparison")
    found = cal.borderline_comparison(access)
    assert len(found["development"]) == 20
    assert found["held_out_candidates"] > 0
    assert all("text" in r and "agent_drafted" in r and "scorer" in r for r in found["development"])
    listed = {r["case_id"] for r in found["development"]}
    held = {c["id"] for c in ALL_CASES if splits.split_of(c) == splits.HELD_OUT}
    assert listed.isdisjoint(held), "Held-out borderline cases are counted, never listed"


def test_the_report_has_a_borderline_section_and_names_no_held_out_case(workdir) -> None:
    text = report.borderline_section(workdir / "access.jsonl", "lane E", "borderline section")
    assert "not human labels" in text
    held = {c["id"] for c in ALL_CASES if splits.split_of(c) == splits.HELD_OUT}
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
    with pytest.raises(ValueError):
        hr.load_reviewer_sheet(
            write({"label_source": "human", "reviewer": "a", "human_confirmed": True, "rows": rows})
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


# ------------------------------------------------------------------ names
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Ali", "ali"),
        ("Ali", "Ali  "),
        (" ali", "ALI"),
        ("Ali  Khan", "ali khan"),
        ("Ali​", "Ali"),  # zero-width space
        ("Al‍i", "Ali"),  # zero-width joiner
        ("﻿Ali", "Ali"),  # byte order mark
        ("Ａｌｉ", "Ali"),  # fullwidth letters
        ("José", "José"),  # NFC and NFD
        ("Ali.", "Ali"),
        ("Ali-Khan", "Ali Khan"),
        ("Ali_Khan", "ali khan"),
    ],
)
def test_names_that_only_differ_by_form_normalise_to_the_same_skeleton(a: str, b: str) -> None:
    assert cal.norm_name(a) == cal.norm_name(b) != ""


@pytest.mark.parametrize(("a", "b"), [("Ali", "Alia"), ("Ali Khan", "Ali Khalid"), ("Ali", "Ani")])
def test_different_names_stay_different(a: str, b: str) -> None:
    assert cal.norm_name(a) != cal.norm_name(b)


def test_the_docstrings_say_code_cannot_prove_two_names_are_two_people() -> None:
    assert "cannot prove two names are two people" in " ".join(
        (cal.norm_name.__doc__ or "").split()
    )
    assert "NOT verified" in cal.IDENTITY_NOTE and "decision recorded by the owner" in (
        cal.IDENTITY_NOTE
    )


# ------------------------------------------------------------------ structural checks
@pytest.mark.parametrize(
    ("a", "b"),
    [("Ali", "ali"), ("Ali", "Ali  "), ("Ali.", "Ali"), ("Ali-Khan", "Ali Khan"), ("Ali​", "Ali")],
)
def test_the_same_reviewer_under_another_spelling_is_rejected(a: str, b: str) -> None:
    first, second = pair(a, b)
    with pytest.raises(ValueError):
        hr.check_pair(first, second)
    with pytest.raises(ValueError):
        hr.process_report(first, second)
    with pytest.raises(ValueError):
        hr.disagreement_record(first, second)


def test_reviewers_must_cover_the_same_samples_and_only_known_ids_count() -> None:
    first = pair(ids=IDS[:20])[0]
    other = pair(ids=IDS[:21])[1]
    with pytest.raises(ValueError, match="same samples"):
        hr.check_pair(first, other)
    unknown = pair(ids=IDS[:20])[1]
    unknown["labels"] = {**unknown["labels"], "zz99": "relevant"}
    with pytest.raises(ValueError):
        hr.check_pair(first, unknown)
    hr.check_pair(*pair(ids=IDS[:20]))


def test_two_reviewers_identical_on_every_shared_sample_are_rejected() -> None:
    ids = IDS[:20]
    first = reviewer("Ana Reviewer", shifted(ids), ids)
    second = reviewer("Ben Reviewer", shifted(ids), ids)
    with pytest.raises(ValueError, match="identical"):
        hr.check_pair(first, second)


def test_a_sheet_that_agrees_with_the_agent_labels_at_ninety_percent_is_refused() -> None:
    ids = IDS[:20]
    agent = cal.agent_labels_all()
    other = shifted(ids)

    def sheet(same: int) -> dict:
        verdicts = [agent[i] if k < same else other[k] for k, i in enumerate(ids)]
        return reviewer("Ana Reviewer", verdicts, ids)

    with pytest.raises(ValueError, match="agent-copy suspected"):
        hr.check_sheet(sheet(20))
    with pytest.raises(ValueError, match="agent-copy suspected"):
        hr.check_sheet(sheet(18))  # exactly 90%
    hr.check_sheet(sheet(17))  # 85% is below the flag
    with pytest.raises(ValueError, match="agent-copy suspected"):
        cal.check_human_labels({"label_source": "human", "labels": sheet(19)["labels"]})


def corrupt_one_field(kind: str) -> tuple[dict, str]:
    """A reviewer sheet with the SAME 20 ids and labels as a valid one, with exactly one field
    corrupted, and the message the loader's checks give for that cause."""
    sheet, _other = pair("Ana Reviewer", "Ben Reviewer")
    labels = dict(sheet["labels"])
    first_id = next(iter(labels))
    if kind == "blank-name":
        return {**sheet, "reviewer": "   "}, "must name its reviewer"
    if kind == "invisible-name":
        return {**sheet, "reviewer": "\u200b."}, "must name its reviewer"
    if kind == "agent-source":
        return {**sheet, "label_source": "agent_drafted"}, "label_source: human"
    if kind == "confirmed":
        return {**sheet, "human_confirmed": True}, "human_confirmed"
    if kind == "bad-verdict":
        return {**sheet, "labels": {**labels, first_id: "good"}}, "not allowed verdicts"
    if kind == "unknown-id":
        swapped = {("zz99" if i == first_id else i): v for i, v in labels.items()}
        return {**sheet, "labels": swapped}, "unknown sample ids"
    if kind == "labels-list":
        return {**sheet, "labels": list(labels)}, "labels mapping"
    raise AssertionError(kind)


CORRUPTIONS = [
    "blank-name",
    "invisible-name",
    "agent-source",
    "confirmed",
    "bad-verdict",
    "unknown-id",
    "labels-list",
]


@pytest.mark.parametrize("kind", CORRUPTIONS)
def test_library_functions_validate_raw_dicts_like_the_loader(kind: str) -> None:
    """The bad sheet has the same 20 ids as the good one, so an id mismatch cannot be the reason
    for the refusal: the message must name the corrupted field."""
    bad, cause = corrupt_one_field(kind)
    good = pair("Ana Reviewer", "Ben Reviewer")[1]
    assert len(good["labels"]) == 20
    if kind not in ("unknown-id", "labels-list"):
        assert set(bad["labels"]) == set(good["labels"]), "same ids, one corrupted field"
    record = {"reviewers": ["Ana Reviewer", "Ben Reviewer"], "adjudicator": "Cy", "items": []}
    for call in (
        lambda: hr.check_pair(bad, good),
        lambda: hr.check_pair(good, bad),
        lambda: hr.process_report(bad, good),
        lambda: hr.process_report(good, bad),
        lambda: hr.disagreement_record(bad, good),
        lambda: hr.adjudicated_labels(bad, good, record),
    ):
        with pytest.raises(ValueError, match=cause):
            call()


@pytest.mark.parametrize("kind", ["blank-name", "agent-source", "confirmed", "bad-verdict"])
def test_the_refusals_above_depend_on_the_sheet_check_and_not_on_something_else(
    kind: str, monkeypatch
) -> None:
    """Mutation check: with check_sheet removed, check_pair no longer raises for the intended
    cause, so the test above would fail. The sheets have the same ids and differ in labels."""
    bad, cause = corrupt_one_field(kind)
    good = pair("Ana Reviewer", "Ben Reviewer")[1]
    monkeypatch.setattr(hr, "check_sheet", lambda sheet: sheet)
    try:
        hr.check_pair(bad, good)
    except ValueError as exc:
        assert cause not in str(exc), "another check catches this cause, so the test is weak"


def test_the_loader_and_the_library_share_the_agent_label_guard() -> None:
    ids = IDS
    agent = cal.agent_labels_all()
    copied = reviewer("Ana Reviewer", [agent[i] for i in ids], ids)
    with pytest.raises(ValueError):
        hr.check_sheet(copied)
    with pytest.raises(ValueError):
        hr.process_report(copied, pair(ids=ids)[1])


# ------------------------------------------------------------------ disagreements and adjudication
def test_the_disagreement_record_lists_only_the_differences_with_blank_fields() -> None:
    first, second = pair("rev_a", "rev_b")
    record = hr.disagreement_record(first, second)
    assert record["label_source"] == "human_disagreements" and record["adjudicator"] == ""
    differing = [i for i in first["labels"] if first["labels"][i] != second["labels"][i]]
    assert [i["sample_id"] for i in record["items"]] == sorted(differing) and differing
    item = record["items"][0]
    assert item["adjudicated"] == "" and item["rationale"] == ""
    assert item["rev_a"] != item["rev_b"]


def filled(first: dict, second: dict, adjudicator: str = "rev_c") -> dict:
    record = hr.disagreement_record(first, second)
    record["adjudicator"] = adjudicator
    for item in record["items"]:
        item["adjudicated"] = item[first["reviewer"]]
    return record


def test_adjudication_needs_a_named_third_person_and_every_disagreement_resolved() -> None:
    first, second = pair("rev_a", "rev_b")
    record = hr.disagreement_record(first, second)
    with pytest.raises(ValueError):
        hr.adjudicated_labels(first, second, record)  # no adjudicator
    record["adjudicator"] = "rev_c"
    with pytest.raises(ValueError):
        hr.adjudicated_labels(first, second, record)  # disagreements not resolved
    record["items"][0]["adjudicated"] = "not_a_verdict"
    with pytest.raises(ValueError):
        hr.adjudicated_labels(first, second, record)
    done = filled(first, second)
    labels = hr.adjudicated_labels(first, second, done)
    assert set(labels) == set(first["labels"]), "exactly the reviewers' common ids"


@pytest.mark.parametrize("name", ["REV_A", " rev_a ", "Rev-A", "rev_b.", "rev​_b"])
def test_the_adjudicator_must_differ_from_both_reviewers_after_normalisation(name: str) -> None:
    first, second = pair("rev a", "rev b")
    record = filled(first, second, adjudicator=name)
    with pytest.raises(ValueError):
        hr.adjudicated_labels(first, second, record)


def test_the_record_must_name_the_same_two_reviewers_as_the_sheets() -> None:
    first, second = pair("rev_a", "rev_b")
    record = filled(first, second)
    record["reviewers"] = ["rev_a", "someone_else"]
    with pytest.raises(ValueError, match="same two reviewers"):
        hr.adjudicated_labels(first, second, record)
    with pytest.raises(ValueError):
        hr.process_report(first, second, {"rev_a": "relevant"})  # a bare dict is not trusted


# ------------------------------------------------------------------ the neutral report
VERDICT_WORDS = (
    "meets",
    "does not meet",
    "eligible",
    "passes",
    "accepted",
    "proposed 85% test",
    "acceptance test",
    "not evaluated",
)


def test_the_report_with_too_few_samples_shows_no_agreement() -> None:
    first, second = pair("rev_a", "rev_b", ids=IDS[:10])
    text = hr.process_report(first, second)
    assert "Too few samples, no agreement shown" in text and "have 10" in text
    assert "agreement on" not in text and "kappa" not in text
    assert cal.IDENTITY_NOTE in text


def test_the_report_is_neutral_names_numbers_and_the_identity_note_only() -> None:
    first, second = pair("Ana  Reviewer", "BEN reviewer")
    text = hr.process_report(first, second)
    assert "'ana reviewer'" in text and "'ben reviewer'" in text, "normalised names are shown"
    assert "reviewer vs reviewer" in text and "agreement on 20 samples" in text and "kappa" in text
    assert text.rstrip().endswith(cal.IDENTITY_NOTE)
    assert not any(word in text.casefold() for word in VERDICT_WORDS)


def test_the_report_builds_adjudicated_labels_itself_and_shows_scorer_and_grader_separately() -> (
    None
):
    first, second = pair("rev_a", "rev_b")
    record = filled(first, second)
    grader = {i: "relevant" for i in first["labels"]}
    text = hr.process_report(first, second, record, grader)
    assert "adjudicated vs scorer" in text and "adjudicated vs grader" in text
    assert not any(word in text.casefold() for word in VERDICT_WORDS)
    no_grader = hr.process_report(first, second, record)
    assert "adjudicated vs scorer" in no_grader and "adjudicated vs grader" not in no_grader


@pytest.mark.parametrize(
    "grader",
    [
        "garbage",
        5,
        [],
        {},
        {"results": []},
        {"results": "x"},
        {"s01": "good"},
        {"s01": 3},
        [{"a": 1}],
    ],
)
def test_an_invalid_grader_file_is_reported_and_never_crashes(grader) -> None:
    first, second = pair("rev_a", "rev_b")
    text = hr.process_report(first, second, filled(first, second), grader)
    assert "invalid grader file" in text
    assert "adjudicated vs scorer" in text and "adjudicated vs grader" not in text
    assert "None" not in text
    compared = cal.compare(grader)
    assert "invalid grader file" in compared and "scorer vs agent_drafted" in compared


def test_a_grader_file_with_no_matching_ids_reports_no_overlap_and_never_crashes() -> None:
    first, second = pair("rev_a", "rev_b")
    text = hr.process_report(first, second, filled(first, second), {"nothing": "relevant"})
    assert "no overlap" in text.casefold() and "None" not in text


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


# ------------------------------------------------------------------ Held-out entry points
@pytest.fixture()
def held_samples(monkeypatch):
    """Make the core sample list point at a Held-out case, as a mistake or an attack would."""
    samples = [{"sample_id": "h01", "case_id": HELD_CASE["id"], "candidate_id": "c1"}]
    monkeypatch.setattr(cal, "load_samples", lambda: samples)
    return samples


def access_for(path: Path) -> cal.Access:
    return cal.Access(path, "lane E", "refusal test")


def test_scorer_labels_and_blind_sheet_refuse_a_held_out_case_without_an_access_log(
    workdir, held_samples
) -> None:
    with pytest.raises(PermissionError):
        cal.scorer_labels(ALL_CASES, held_samples)
    with pytest.raises(PermissionError):
        cal.blind_sheet(ALL_CASES, held_samples)
    log = workdir / "access.jsonl"
    assert cal.scorer_labels(ALL_CASES, held_samples, access_for(log))
    assert cal.blind_sheet(ALL_CASES, held_samples, access=access_for(log))
    rows = access_log.read(log)
    assert len(rows) == 2 and all(r["split"] == splits.HELD_OUT and r["count"] == 1 for r in rows)


def test_write_sheets_and_all_rows_refuse_before_writing_anything(workdir, held_samples) -> None:
    target = workdir / "sheets"
    with pytest.raises(PermissionError):
        cal.write_sheets(target)
    assert not target.exists()
    with pytest.raises(PermissionError):
        cal.all_rows()
    cal.write_sheets(target, access_for(workdir / "access.jsonl"))
    assert (target / "human_review_sheet.json").exists()
    assert access_log.read(workdir / "access.jsonl")


def test_compare_refuses_a_held_out_sample_without_an_access_log(workdir, held_samples) -> None:
    with pytest.raises(PermissionError):
        cal.compare({"x": "relevant"})
    text = cal.compare({"x": "relevant"}, access=access_for(workdir / "access.jsonl"))
    assert "scorer vs agent_drafted" in text
    assert access_log.read(workdir / "access.jsonl")


def test_the_reviewer_sheet_writer_and_the_scorer_helper_refuse_too(workdir, held_samples) -> None:
    target = workdir / "reviewer"
    with pytest.raises(PermissionError):
        hr.write_reviewer_sheets(target)
    assert not target.exists()
    with pytest.raises(PermissionError):
        hr._languages_and_scorer()
    log = workdir / "access.jsonl"
    hr.write_reviewer_sheets(target, access=access_for(log))
    languages, scorer = hr._languages_and_scorer(access_for(log))
    assert languages and scorer
    assert len(access_log.read(log)) >= 2


def test_the_borderline_comparison_requires_the_access_log_and_writes_the_line(workdir) -> None:
    with pytest.raises(TypeError):
        cal.borderline_comparison()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        cal.borderline_comparison(cal.Access("", "lane E", "no path"))
    with pytest.raises(ValueError):
        cal.borderline_comparison(cal.Access(workdir / "a.jsonl", "", ""))
    assert not (workdir / "a.jsonl").exists()
    cal.borderline_comparison(cal.Access(workdir / "a.jsonl", "lane E", "borderline"))
    rows = access_log.read(workdir / "a.jsonl")
    assert len(rows) == 1 and rows[0]["count"] > 0


def test_a_development_only_sample_set_never_needs_an_access_log() -> None:
    assert cal.scorer_labels(ALL_CASES, cal.load_samples())
    assert cal.blind_sheet(ALL_CASES, cal.load_borderline_samples())


# ------------------------------------------------------------------ the 19-versus-20 boundary
def test_nineteen_samples_show_no_agreement_and_twenty_do() -> None:
    nineteen = hr.process_report(*pair("rev_a", "rev_b", ids=IDS[:19]))
    assert "Too few samples, no agreement shown" in nineteen and "have 19" in nineteen
    assert "agreement on" not in nineteen and "kappa" not in nineteen
    twenty = hr.process_report(*pair("rev_a", "rev_b", ids=IDS[:20]))
    assert "Too few samples" not in twenty and "agreement on 20 samples" in twenty


def human_labels_of(n: int) -> dict:
    agent = cal.agent_labels_all()
    ids = sorted(agent)[:n]
    labels = {i: VERDICTS[(VERDICTS.index(agent[i]) + 1) % 5] for i in ids}
    return {
        "label_source": "human",
        "reviewers": ["Ana Reviewer", "Ben Reviewer"],
        "labels": labels,
    }


def test_the_human_comparison_in_compare_needs_exactly_twenty_labelled_samples() -> None:
    grader = dict(cal.load_agent_labels()["labels"])
    assert "at least 20 labelled samples" in cal.human_labels_problem(human_labels_of(19))
    assert cal.human_labels_problem(human_labels_of(20)) == ""
    assert "human comparison is not valid" in cal.compare(grader, human_labels_of(19))
    assert "scorer vs human" in cal.compare(grader, human_labels_of(20))
