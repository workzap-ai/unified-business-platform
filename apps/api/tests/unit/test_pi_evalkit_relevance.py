"""The scripted relevance scorer (FT-A3): its verdicts, hard failures, negative controls, report,
Held-out access log and the calibration helpers. Everything here is a check of code and case files.
No model is called, so none of it measures how well pi solves a problem. Agent-drafted labels and
human labels are separate inputs and are never merged.

Held-out discipline: no test asserts an expected verdict for a Held-out case and none names a
Held-out id in a failure; for Held-out the tests only check that scoring runs and is logged."""

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
HELD_CORE = [c for c in PLAN if splits.split_of(c) == splits.HELD_OUT]
DEV_CORE = [c for c in PLAN if splits.split_of(c) != splits.HELD_OUT]  # Development + Regression
EXTRACTION = replay.load_cases(str(CASES_DIR / "extraction.json"))
HELD_IDS = {c["id"] for c in HELD_CORE}


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
@pytest.mark.parametrize("case", DEV_CORE, ids=lambda c: c["id"])
def test_the_scorer_reproduces_every_expected_verdict_on_development_cases(case) -> None:
    result = relevance.score_case(case)
    wrong = [
        (r["id"], r["expected"], r["got"]) for r in result["results"] if r["expected"] != r["got"]
    ]
    assert wrong == []


def test_held_out_core_cases_are_scored_and_logged_and_no_verdict_is_asserted(workdir) -> None:
    """Held-out is never a tuning target: only that scoring runs and a log line is written."""
    log = workdir / "access.jsonl"
    text, totals = relevance_report.build(HELD_CORE, log, "lane E", "scripted run check")
    assert totals["split:held_out"]["cases"] == len(HELD_CORE)
    assert not any(case_id in text for case_id in HELD_IDS), "Held-out ids are never printed"
    rows = access_log.read(log)
    assert len(rows) == 1 and rows[0]["count"] == len(HELD_CORE)


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


def test_numbers_are_never_truncated_so_a_figure_stays_distinct() -> None:
    assert relevance.stems("20000") != relevance.stems("200000")
    assert relevance.stems("200000") == {"200000"}
    assert relevance.stems("15000 rupees") >= {"15000"}
    constraint = {"kind": "budget", "text": "limit", "blocks": ["200000"], "status": "confirmed"}
    b = brief([constraint])
    assert relevance.score_candidate(b, "Spend 20000 on late orders")["verdict"] != (
        "violates_constraint"
    )
    assert relevance.score_candidate(b, "Spend 200000 on late orders")["verdict"] == (
        "violates_constraint"
    )


def test_numbers_keep_their_separators_whole() -> None:
    assert relevance.tokens("Rs.20000") == ["rs", "20000"]
    assert relevance.tokens("Budget 20,000 only") == ["budget", "20000", "only"]
    assert relevance.tokens("about 1.5 hours") == ["about", "1.5", "hours"]
    assert relevance.stems("20,000") == relevance.stems("20000") == {"20000"}
    assert relevance.stems("1.5") == {"1.5"}
    assert relevance.stems("Rs.20000") == {"20000"}, "'rs' is two letters and is dropped"
    assert relevance.stems("200,000") != relevance.stems("20,000")
    assert relevance.tokens("It started in 2024. Which one") == [
        "it",
        "started",
        "in",
        "2024",
        "which",
        "one",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,00,000", ["100000"]),  # Indian lakh grouping
        ("20,00,000", ["2000000"]),
        ("5,00,000", ["500000"]),
        ("1,00,00,000", ["10000000"]),
        ("20,000", ["20000"]),  # Western grouping
        ("200,000", ["200000"]),
        ("1,200,000", ["1200000"]),
        ("120,000,000", ["120000000"]),
        ("120,150,180", ["120", "150", "180"]),  # a list of 3-digit numbers stays a list
        ("Rs.1,00,000/-", ["rs", "100000"]),
        ("1.5", ["1.5"]),
        ("1,5", ["1.5"]),  # choice: one comma before one or two digits is a decimal comma
        ("12,50", ["12.50"]),
    ],
)
def test_figures_with_separators_become_one_token_and_a_list_stays_a_list(text, expected) -> None:
    assert relevance.tokens(text) == expected


def test_a_lakh_figure_cannot_link_to_another_through_a_run_of_zeros() -> None:
    for text in ("1,00,000", "20,00,000", "5,00,000", "120,000,000"):
        assert not any(t.strip("0") == "" for t in relevance.tokens(text)), text
    assert relevance.stems("5,00,000") & relevance.stems("20,00,000") == set()
    assert relevance.stems("1,5") & relevance.stems("1,50,000") == set()
    assert relevance.stems("1,5") == {"1.5"}, "a decimal comma never becomes two single digits"


def test_digits_inside_a_word_stay_in_the_word_and_only_standalone_numbers_split_out() -> None:
    assert relevance.tokens("B2B Q3 A4 24x7 order_1234") == [
        "b2b",
        "q3",
        "a4",
        "24x7",
        "order_1234",
    ]
    assert relevance.stems("B2B Q3 A4 24x7 order_1234") == {
        "b2b",
        "q3",
        "a4",
        "24x7",
        "order_1234",
    }
    assert relevance.tokens("6pm and 5th") == ["6pm", "and", "5th"]
    assert relevance.tokens("order 1234 was late") == ["order", "1234", "was", "late"]
    assert "1234" not in relevance.stems("order_1234") and "2" not in relevance.stems("b2b")


def test_scoring_a_held_out_case_directly_is_refused_at_runtime() -> None:
    assert HELD_CORE
    with pytest.raises(PermissionError):
        relevance.score_case(HELD_CORE[0])


def test_a_plain_true_no_longer_unlocks_a_held_out_case_only_a_minted_pass_does(workdir) -> None:
    with pytest.raises(PermissionError):
        relevance.score_case(HELD_CORE[0], held_out_ok=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        access_log.Pass({})  # a Pass cannot be built by hand
    log = workdir / "access.jsonl"
    ticket = access_log.grant(log, "lane E", "pass check", "r1", splits.HELD_OUT, 1)
    assert isinstance(ticket, access_log.Pass)
    assert relevance.score_case(HELD_CORE[0], held_out_ok=ticket)["candidates"] > 0
    assert len(access_log.read(log)) == 1, "the line was written when the pass was granted"


def test_the_disclaimer_is_in_the_module_docstring_and_in_the_report(workdir) -> None:
    assert " ".join(relevance.DISCLAIMER.split()) in " ".join((relevance.__doc__ or "").split())
    assert relevance.DISCLAIMER.startswith("Not a quality gate and not a learning reward.")
    assert (
        "Scorer agreed 55% with an independent grader on the borderline set" in relevance.DISCLAIMER
    )
    text, _ = relevance_report.build(DEV_CORE, workdir / "a.jsonl", "lane E", "disclaimer check")
    assert relevance.DISCLAIMER in text
    assert "agent-drafted labels (not a score)" in text


def test_the_scorer_is_deterministic() -> None:
    case = DEV_CORE[0]
    assert relevance.score_case(case) == relevance.score_case(copy.deepcopy(case))


def test_layer_b_plan_fields_are_inert() -> None:
    case = copy.deepcopy(DEV_CORE[0])
    before = relevance.score_case(case)
    case["expected"]["plan"] = {
        "steps": [{"id": "s1", "any": ["anything"]}],
        "dependencies": [{"from": "s1", "to": "s2"}],
        "roles": ["x"],
        "next_action": {"any": ["now"]},
    }
    assert relevance.score_case(case) == before


def test_negative_controls_fail_when_a_label_is_wrong() -> None:
    case = copy.deepcopy(DEV_CORE[0])
    for candidate in case["expected"]["candidates"]:
        candidate["verdict"] = "relevant" if candidate["verdict"] != "relevant" else "generic"
    result = relevance.score_case(case)
    assert result["agree"] < result["candidates"]
    flipped = copy.deepcopy(DEV_CORE[0])
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
    two = [relevance.score_case(c) for c in DEV_CORE[:2]]
    assert relevance.aggregate(two)["measured"] is False
    many = [relevance.score_case(c) for c in DEV_CORE[:5]]
    assert relevance.aggregate(many)["measured"] is True


# ------------------------------------------------------------------ the report
def test_the_report_is_headed_as_a_code_path_check_and_never_claims_ai_quality(workdir) -> None:
    text, totals = relevance_report.build(PLAN, workdir / "a.jsonl", "lane E", "header check")
    assert "scripted code-path check" in text.casefold()
    assert "ai quality" not in text.casefold()
    assert "not yet measured" in text
    assert any(key.startswith("split:") for key in totals)


def test_the_report_prints_held_out_as_totals_only(workdir) -> None:
    text, _ = relevance_report.build(PLAN, workdir / "a.jsonl", "lane E", "totals check")
    assert HELD_IDS and not any(case_id in text for case_id in HELD_IDS)


def test_the_report_groups_by_language_industry_and_kind(workdir) -> None:
    text, totals = relevance_report.build(PLAN, workdir / "a.jsonl", "lane E", "groups check")
    for key in ("language:en", "language:hi", "kind:constraint_violation"):
        assert key in totals
    assert "banquet_halls_and_marquees" in text


def test_only_the_split_table_shows_held_out_so_its_share_cannot_be_subtracted(workdir) -> None:
    text, totals = relevance_report.build(PLAN, workdir / "a.jsonl", "lane E", "tables check")
    for key in ("language", "kind", "industry"):
        cases = sum(v["cases"] for k, v in totals.items() if k.startswith(f"{key}:"))
        assert cases == len(DEV_CORE), f"the {key} table leaves Held-out out"
    held_only = {c["industry"] for c in HELD_CORE} - {c["industry"] for c in DEV_CORE}
    assert held_only, "the fixture has an industry that only Held-out cases use"
    assert not any(f"industry:{name}" in totals for name in held_only)
    assert not any(name in text for name in held_only)
    assert totals["split:held_out"]["cases"] == len(HELD_CORE)
    assert text.count("(Development and Regression only)") == 3


# ------------------------------------------------------------------ Held-out access log
def test_the_access_log_is_append_only_and_records_who_why_and_when(workdir) -> None:
    path = workdir / "access.jsonl"
    access_log.append(path, who="lane E", why="first run", run_id="r1", split="held_out", count=7)
    access_log.append(path, who="reviewer", why="read", run_id="r2", split="held_out", count=7)
    rows = access_log.read(path)
    assert [r["who"] for r in rows] == ["lane E", "reviewer"]
    assert {"who", "why", "when", "run_id", "split", "count"} <= set(rows[0])
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_the_report_fails_closed_without_a_log_path_who_and_why(workdir) -> None:
    path = workdir / "access.jsonl"
    with pytest.raises(ValueError):
        relevance_report.build(PLAN, None, "lane E", "no log path")
    with pytest.raises(ValueError):
        relevance_report.build(PLAN, path, "", "")
    with pytest.raises(ValueError):
        relevance_report.borderline_section(None, "lane E", "no log path")
    with pytest.raises(ValueError):
        relevance_report.borderline_section(path, "lane E", "")
    assert not path.exists(), "nothing is read, so nothing is logged"


def test_a_report_that_reads_held_out_writes_one_log_entry(workdir) -> None:
    path = workdir / "access.jsonl"
    relevance_report.build(PLAN, path, "lane E", "scripted check")
    rows = access_log.read(path)
    assert len(rows) == 1 and rows[0]["count"] == len(HELD_IDS)
    assert rows[0]["who"] == "lane E" and rows[0]["split"] == splits.HELD_OUT


def test_the_report_cannot_return_when_the_log_cannot_be_written(workdir) -> None:
    blocked = workdir / "folder"
    blocked.mkdir()  # a directory cannot be opened as the log file
    with pytest.raises(OSError):
        relevance_report.build(PLAN, blocked, "lane E", "log failure")


def test_the_borderline_section_logs_the_held_out_candidates_it_counts(workdir) -> None:
    path = workdir / "access.jsonl"
    text = relevance_report.borderline_section(path, "lane E", "borderline count")
    assert "not human labels" in text
    rows = access_log.read(path)
    assert len(rows) == 1 and rows[0]["count"] > 0


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


def test_the_core_calibration_samples_contain_no_held_out_case() -> None:
    by_case = {c["id"]: c for c in ALL_PLAN}
    assert all(splits.split_of(by_case[s["case_id"]]) != splits.HELD_OUT for s in SAMPLES)


def test_agent_drafted_labels_are_a_separate_file_and_say_so() -> None:
    assert AGENT["label_source"] == "agent_drafted" and AGENT["human_confirmed"] is False
    assert set(AGENT["labels"]) == {s["sample_id"] for s in SAMPLES}
    assert all(not ({"label", "verdict"} & set(s)) for s in SAMPLES), "samples carry no labels"


# wording that would imply a computed acceptance or a verdict: none of it may appear in any output
BANNED_WORDING = (
    "meets",
    "does not meet",
    "eligible",
    "proposed 85% test",
    "acceptance test",
    "not evaluated",
    "85% agreement test",
)


def test_no_output_of_the_calibration_tool_implies_a_computed_acceptance(workdir) -> None:
    grader = dict(AGENT["labels"])
    outputs = [
        calibration.compare(grader),
        calibration.compare(grader, valid_human()),
        calibration.compare("garbage"),
        calibration.compare(grader, {"label_source": "human", "reviewers": ["a"], "labels": {}}),
        calibration.__doc__ or "",
    ]
    for text in outputs:
        folded = " ".join(text.casefold().split())
        for word in BANNED_WORDING:
            assert word not in folded, f"{word!r} implies a computed acceptance"
    no_human = calibration.compare(grader)
    assert "acceptance is the owner's decision; this tool only prints numbers" in no_human


def write_human(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def valid_human(reviewers=("Ana Reviewer", "Ben Reviewer"), n: int = 20) -> dict:
    """A human labels dict that differs from the agent-drafted labels on every sample."""
    agent = calibration.agent_labels_all()
    order = list(relevance.VERDICTS)
    ids = sorted(agent)[:n]
    labels = {i: order[(order.index(agent[i]) + 1) % len(order)] for i in ids}
    return {"label_source": "human", "reviewers": list(reviewers), "labels": labels}


def test_human_labels_need_two_distinct_normalised_reviewers_and_known_ids(workdir) -> None:
    path = workdir / "human.json"
    ok = valid_human()
    assert calibration.load_human_labels(write_human(path, ok))["reviewers"] == ok["reviewers"]
    for reviewers in (["a", "a"], [""], ["a"], ["Ali", "ali  "], [" Ali", "ALI"], [], None):
        bad = {**ok, "reviewers": reviewers}
        with pytest.raises(ValueError):
            calibration.load_human_labels(write_human(path, bad))
    with pytest.raises(ValueError):
        calibration.load_human_labels(write_human(path, {**ok, "label_source": "agent_drafted"}))
    with pytest.raises(ValueError):
        calibration.load_human_labels(write_human(path, {**ok, "human_confirmed": True}))
    unknown = {**ok, "labels": {**ok["labels"], "zz99": "relevant"}}
    with pytest.raises(ValueError):
        calibration.load_human_labels(write_human(path, unknown))
    copy_of_agent = {**ok, "labels": dict(calibration.agent_labels_all())}
    with pytest.raises(ValueError):
        calibration.load_human_labels(write_human(path, copy_of_agent))


def test_the_blind_sheet_has_no_label_score_or_hint() -> None:
    blocked = [
        *relevance.VERDICTS,
        "verdict",
        "label",
        "reason",
        "blocks",
        "scorer",
        "agent_drafted",
        "human_confirmed",
        "expected",
    ]
    allowed_keys = {
        "sample_id",
        "industry",
        "language",
        "owner_problem",
        "facts",
        "constraints",
        "candidate_idea",
        "allowed_verdicts",
    }
    for sheet in (
        calibration.blind_sheet(PLAN, SAMPLES),
        calibration.blind_sheet(ALL_PLAN, calibration.load_borderline_samples()),
    ):
        assert len(sheet) == 20
        for row in sheet:
            assert set(row) <= allowed_keys
            assert row["allowed_verdicts"] == list(relevance.VERDICTS)
            for constraint in row["constraints"]:
                assert set(constraint) == {"kind", "text"}
        # the allowed list names the verdicts by design; nothing else in the sheet may
        stripped = [{k: v for k, v in row.items() if k != "allowed_verdicts"} for row in sheet]
        blob = json.dumps(stripped, ensure_ascii=False).casefold()
        for word in blocked:
            assert word.casefold() not in blob, f"hint {word!r} appears in the blind sheet"


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


def test_agreement_with_no_overlap_has_no_percent_and_formats_without_crashing() -> None:
    nothing = calibration.agreement({"a": "x"}, {"b": "y"}, {})
    assert nothing["n"] == 0 and nothing["percent"] is None and nothing["kappa"] is None
    assert "n/a" in calibration._fmt("empty", nothing)[0]


def test_compare_reports_three_ways_and_refuses_to_claim_the_human_test_without_human_labels() -> (
    None
):
    grader = dict(AGENT["labels"])
    text = calibration.compare(grader)
    assert "scorer vs grader" in text and "scorer vs agent_drafted" in text
    assert "grader vs agent_drafted" in text
    assert "no human labels" in text.casefold()
    assert "hand-labelled" not in text.casefold() and "hand labelled" not in text.casefold()


def test_compare_prints_human_lines_only_for_a_valid_human_file() -> None:
    grader = dict(AGENT["labels"])
    text = calibration.compare(grader, valid_human())
    assert "scorer vs human" in text and "grader vs human" in text
    assert "agent_drafted vs human" in text
    assert "not valid" not in text
    assert calibration.IDENTITY_NOTE in text, "the tool never claims to verify who reviewed"
    assert "ana reviewer" in text and "ben reviewer" in text
    for word in BANNED_WORDING:
        assert word not in text.casefold()


def mostly_agent(human: dict, same: int) -> dict:
    """The same sheet, but `same` of its labels are replaced by the agent-drafted label."""
    agent = calibration.agent_labels_all()
    labels = {i: (agent[i] if k < same else v) for k, (i, v) in enumerate(human["labels"].items())}
    return {**human, "labels": labels}


def test_compare_flags_an_agent_copy_at_ninety_percent_but_not_below() -> None:
    grader = dict(AGENT["labels"])
    flagged = calibration.compare(grader, mostly_agent(valid_human(), 18))
    assert "agent-copy suspected" in flagged and "scorer vs human" not in flagged
    below = calibration.compare(grader, mostly_agent(valid_human(), 17))
    assert "agent-copy suspected" not in below and "scorer vs human" in below


@pytest.mark.parametrize(
    "mutate",
    [
        lambda h: {**h, "reviewers": ["​", "Ben Reviewer"]},
        lambda h: {**h, "reviewers": ["...", "Ben Reviewer"]},
        lambda h: {**h, "reviewers": ["Ali​", "ali."]},
        lambda h: {**h, "reviewers": ["a", "a"]},
        lambda h: {**h, "reviewers": [""]},
        lambda h: {**h, "reviewers": ["a"]},
        lambda h: {**h, "reviewers": ["Ali", "ali "]},
        lambda h: {**h, "labels": dict(list(h["labels"].items())[:5])},
        lambda h: {**h, "label_source": "agent_drafted"},
        lambda h: {**h, "human_confirmed": True},
        lambda h: {**h, "labels": {**h["labels"], "zz99": "relevant"}},
        lambda h: {**h, "labels": dict(calibration.agent_labels_all())},
    ],
    ids=[
        "invisible-name",
        "punctuation-name",
        "normalised-twin",
        "same-name",
        "blank-name",
        "one-name",
        "case-and-space",
        "too-few-samples",
        "agent-source",
        "human-confirmed-set",
        "unknown-id",
        "copy-of-agent-labels",
    ],
)
def test_compare_refuses_every_human_comparison_for_an_invalid_human_file(mutate) -> None:
    grader = dict(AGENT["labels"])
    text = calibration.compare(grader, mutate(valid_human()))
    assert "human comparison is not valid" in text
    assert "scorer vs human" not in text and "grader vs human" not in text
    assert "agent_drafted vs human" not in text
