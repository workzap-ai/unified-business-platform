"""L2-2: the scripted root-cause scorer (measure M1) and its labelled cases.

No model, no database, no network. A scripted run tests the code and the cases, never the model's
quality. The cases are agent-drafted and unreviewed; none is Held-out and no Held-out text is in
Git. Nothing here asserts or prints an acceptance decision: the tool prints numbers only.
"""

import csv
import hashlib
import json
import re
import tempfile
from pathlib import Path

import pytest

from app.modules.pi.evalkit import root_cause, splits

CASES = root_cause.load_cases()
INDUSTRY_CSV = (
    Path(__file__).resolve().parents[4] / "docs" / "pi-saas" / "pi-211-industry-check.csv"
)
LANGUAGES = {"en", "roman_ur", "ur", "ar", "hi"}
KINDS = {
    "owner_cause",
    "wrong_cause",
    "corrected_cause",
    "several_causes",
    "no_cause",
    "unsupported_plausible",
}
PII = [
    re.compile(r"\+?\d[\d\s-]{8,}\d"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
]
# wording that would imply a computed acceptance or a verdict: none of it may appear in any output
BANNED_PHRASES = (
    "meets",
    "does not meet",
    "eligible",
    "proposed 85% test",
    "acceptance test",
    "not evaluated",
    "85% agreement test",
    "85%",
)
BANNED_WORDS = re.compile(
    r"\b(pass|passes|passed|passing|fail|fails|failed|failing|failure|failures|accepted|verdict)\b"
)


def owner_case(**changes):
    """A small hand-made case for scorer unit tests."""
    case = {
        "id": "x_unit",
        "industry": "bakeries_mithai_and_confectionery",
        "language": "en",
        "kind": "owner_cause",
        "regression": False,
        "input": {"messages": ["Orders go out late because we have one oven shared with bread."]},
        "expected": {
            "outcome": "cause_stated",
            "cause_any": ["oven"],
            "forbidden_cause_any": [],
            "both_sides": False,
            "factors": [],
        },
    }
    case.update(changes)
    return case


def stated(text="One oven shared with bread", words=("we have one oven shared with bread",)):
    return {
        "text": text,
        "status": "owner_said",
        "evidence": {"words": list(words)},
        "shown_as": "fact",
    }


# ------------------------------------------------------------------ the cases


def test_there_are_enough_cases_across_industries_and_languages() -> None:
    assert len(CASES) >= 24
    known = {row["industry_id"] for row in csv.DictReader(INDUSTRY_CSV.open(encoding="utf-8"))}
    industries = {c["industry"] for c in CASES}
    assert industries <= known and len(industries) >= 12
    assert {c["language"] for c in CASES} == LANGUAGES
    assert {c["kind"] for c in CASES} == KINDS, "every trap and situation kind is present"
    assert len({c["id"] for c in CASES}) == len(CASES)


def test_no_case_is_held_out_and_the_split_is_the_hash_of_the_id() -> None:
    for case in CASES:
        digest = hashlib.sha256(case["id"].encode("utf-8")).digest()
        assert digest[0] % 100 >= splits.HELD_OUT_PERCENT, case["id"]
        assert splits.split_of(case) == splits.DEVELOPMENT
        assert case["regression"] is False


def test_cases_say_they_are_agent_drafted_and_unreviewed() -> None:
    for case in CASES:
        assert case["synthetic"] is True and case["case_type"] == "root_cause"
        provenance = case["provenance"]
        assert provenance["origin"] == "agent_drafted" and provenance["reviewer"] is None
        assert provenance["human_confirmed"] is False


def test_cases_hold_no_personal_data() -> None:
    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for key, value in node.items():
                if key != "created":
                    yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)

    for case in CASES:
        for text in strings(case):
            assert not any(p.search(text) for p in PII), f"{case['id']}: {text!r}"


def test_loading_refuses_a_held_out_case() -> None:
    for n in range(200):
        candidate = {"id": f"probe_{n}", "regression": False}
        if splits.split_of(candidate) == splits.HELD_OUT:
            break
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "cases.json"
        path.write_text(json.dumps([owner_case(id=candidate["id"])]), encoding="utf-8")
        with pytest.raises(ValueError, match="Held-out"):
            root_cause.load_cases(path)


def test_every_reference_record_scores_with_all_checks_true() -> None:
    for case in CASES:
        out = root_cause.score_case(case)
        assert out["hard_flags"] == [], (case["id"], out)
        assert out["checks_all_true"] is True, (case["id"], out)


# ------------------------------------------------------------------ the checks


def test_a_stated_cause_needs_the_owners_own_words_as_evidence() -> None:
    case = owner_case()
    good = {"causes": [stated()]}
    assert root_cause.score_case(case, good)["hard_flags"] == []
    invented = {"causes": [stated(words=("the staff are careless",))]}
    assert "unsupported_confirmed" in root_cause.score_case(case, invented)["hard_flags"]
    none = {"causes": [{"text": "One oven", "status": "confirmed", "evidence": {"words": []}}]}
    assert "unsupported_confirmed" in root_cause.score_case(case, none)["hard_flags"]


def test_evidence_must_be_a_whole_phrase_in_the_owners_message() -> None:
    case = owner_case()
    partial = {"causes": [stated(words=("oven shar",))]}
    assert "unsupported_confirmed" in root_cause.score_case(case, partial)["hard_flags"]


def test_evidence_that_does_not_belong_to_the_cause_text_is_unsupported() -> None:
    case = owner_case()
    ungrounded = {"causes": [stated(text="Careless staff", words=("shared with bread",))]}
    assert "unsupported_confirmed" in root_cause.score_case(case, ungrounded)["hard_flags"]


def test_a_guess_is_never_shown_as_a_fact() -> None:
    case = owner_case()
    guess = {"text": "Staff are slow", "status": "pi_inferred", "evidence": {}, "shown_as": "guess"}
    as_fact = {**guess, "shown_as": "fact"}
    ok = root_cause.score_case(case, {"causes": [stated(), guess]})
    assert ok["hard_flags"] == [] and ok["hypotheses"] == 1
    bad = root_cause.score_case(case, {"causes": [stated(), as_fact]})
    assert "inferred_shown_as_fact" in bad["hard_flags"]


def test_an_unknown_status_is_flagged() -> None:
    out = root_cause.score_case(owner_case(), {"causes": [{"text": "x", "status": "sure"}]})
    assert "unknown_status" in out["hard_flags"]


def test_a_superseded_or_trap_cause_is_not_stated() -> None:
    case = owner_case(
        expected={
            "outcome": "cause_stated",
            "cause_any": ["oven"],
            "forbidden_cause_any": ["bread"],
            "both_sides": False,
            "factors": [],
        }
    )
    out = root_cause.score_case(case, {"causes": [stated("Bread line takes the oven")]})
    assert "trap_cause_stated" in out["hard_flags"]


def test_both_sides_and_factors_are_checked_only_when_expected() -> None:
    case = owner_case(
        expected={
            "outcome": "cause_stated",
            "cause_any": ["oven"],
            "forbidden_cause_any": [],
            "both_sides": True,
            "factors": [["oven"], ["bread"]],
        }
    )
    full = {
        "causes": [stated()],
        "evidence_for": ["one oven shared with bread"],
        "evidence_against": ["orders go out late"],
        "factors": ["the shared oven", "bread line"],
    }
    out = root_cause.score_case(case, full)
    assert out["both_sides"] is True and out["factors_named"] == 2 == out["factors_expected"]
    thin = {**full, "evidence_against": [], "factors": ["the shared oven"]}
    out = root_cause.score_case(case, thin)
    assert out["both_sides"] is False and out["factors_named"] == 1
    assert out["checks_all_true"] is False
    plain = root_cause.score_case(owner_case(), {"causes": [stated()]})
    assert plain["both_sides"] is None and plain["factors_expected"] == 0


def test_evidence_for_and_against_must_come_from_the_owner() -> None:
    case = owner_case(
        expected={
            "outcome": "cause_stated",
            "cause_any": ["oven"],
            "forbidden_cause_any": [],
            "both_sides": True,
            "factors": [],
        }
    )
    record = {
        "causes": [stated()],
        "evidence_for": ["one oven shared with bread"],
        "evidence_against": ["a rival opened next door"],
    }
    assert "evidence_not_from_owner" in root_cause.score_case(case, record)["hard_flags"]


def insufficient_case():
    return owner_case(
        input={"messages": ["Weekday bookings are falling. I do not know why."]},
        expected={
            "outcome": "insufficient_evidence",
            "cause_any": [],
            "forbidden_cause_any": ["price"],
            "both_sides": False,
            "factors": [],
        },
    )


def test_insufficient_evidence_means_one_question_and_no_cause() -> None:
    case = insufficient_case()
    right = root_cause.score_case(case, {"causes": [], "question": "What changed on weekdays?"})
    assert right["hard_flags"] == [] and right["insufficient_ok"] is True
    assert right["question_ok"] is True and right["checks_all_true"] is True
    invented = {"causes": [{"text": "Prices", "status": "pi_inferred", "shown_as": "guess"}]}
    out = root_cause.score_case(case, {**invented, "question": "Why?"})
    assert "cause_invented_without_facts" in out["hard_flags"]
    assert out["insufficient_ok"] is False
    for question in ("", "What changed? And when?", "No question mark here"):
        out = root_cause.score_case(case, {"causes": [], "question": question})
        assert out["question_ok"] is False and out["checks_all_true"] is False


def test_question_marks_of_every_script_count() -> None:
    case = insufficient_case()
    for question in ("ما الذي تغير؟", "کیا بدلا؟", "क्या बदला?"):
        assert root_cause.score_case(case, {"causes": [], "question": question})["question_ok"]
    two = root_cause.score_case(case, {"causes": [], "question": "ما الذي تغير؟ ومتى؟"})
    assert two["question_ok"] is False


def test_matching_is_by_whole_tokens_in_every_script() -> None:
    owner = ["सिर्फ़ एक गाड़ी है और वह सुबह दो चक्कर लगाती है।"]
    assert root_cause.in_owner_text("सिर्फ़ एक गाड़ी है", owner)
    assert not root_cause.in_owner_text("गाड़ी है और वह सुबह तीन", owner)
    assert root_cause.in_owner_text("ایک ہی بس", ["نہیں، ایک ہی بس تین راستوں پر چلتی ہے۔"])
    assert not root_cause.in_owner_text("ایک بس", ["نہیں، ایک ہی بس تین راستوں پر چلتی ہے۔"])


# ------------------------------------------------------------------ negative controls


def test_every_seeded_defect_is_caught_by_the_scorer() -> None:
    out = root_cause.controls(CASES)
    assert out["tried"] >= 100
    assert out["caught"] == out["tried"], out["missed"]
    assert set(out["by_defect"]) >= {
        "fake_confirmed_cause",
        "guess_shown_as_fact",
        "fabricated_evidence",
        "dropped_evidence_against",
        "dropped_factors",
        "invented_cause_without_facts",
        "dropped_question",
        "dropped_cause",
        "trap_cause_stated",
    }


def test_a_scorer_that_always_says_supported_is_caught_by_the_controls() -> None:
    def always_supported(case, record=None):
        return {
            "hard_flags": [],
            "checks_all_true": True,
            "both_sides": None,
            "factors_expected": 0,
            "factors_named": 0,
        }

    out = root_cause.controls(CASES, score_fn=always_supported)
    assert out["caught"] == 0 and out["tried"] > 0


def test_a_scorer_that_flags_everything_is_caught_by_the_clean_references() -> None:
    def flags_everything(case, record=None):
        return {"hard_flags": ["x"], "checks_all_true": False}

    assert root_cause.reference_true(CASES, score_fn=flags_everything) == 0
    assert root_cause.reference_true(CASES) == len(CASES)


# ------------------------------------------------------------------ the report


def test_each_language_reports_n_and_below_the_minimum_is_not_yet_measured() -> None:
    report = root_cause.build(CASES)
    for language in LANGUAGES:
        group = report["language"][language]
        assert group["cases"] == sum(1 for c in CASES if c["language"] == language)
        assert group["measured"] is (group["cases"] >= root_cause.MIN_CASES)
    few = root_cause.build(CASES[:1])
    only = next(iter(few["language"].values()))
    assert only["measured"] is False
    text = root_cause.render(few)
    assert "not yet measured" in text


def test_the_report_has_numbers_by_language_split_industry_and_kind() -> None:
    report = root_cause.build(CASES)
    assert set(report) >= {"total", "language", "split", "industry", "kind", "controls"}
    assert report["total"]["cases"] == len(CASES)
    assert set(report["split"]) == {"development"}
    assert report["total"]["hard_flag_cases"] == 0, "the references carry no hard flag"


def test_no_output_implies_a_computed_acceptance() -> None:
    report = root_cause.build(CASES)
    texts = [
        root_cause.render(report),
        root_cause.render(root_cause.build(CASES[:1])),
        root_cause.render(root_cause.build([])),
        root_cause.__doc__ or "",
        Path(root_cause.__file__).read_text(encoding="utf-8"),
    ]
    for text in texts:
        folded = " ".join(text.casefold().split())
        for phrase in BANNED_PHRASES:
            assert phrase not in folded, f"{phrase!r} implies a computed acceptance"
        assert not BANNED_WORDS.search(folded), BANNED_WORDS.search(folded)
    assert "decision on any threshold is the owner's; this tool only prints numbers" in texts[0]
    assert "scripted" in texts[0] and "not a measure of model quality" in texts[0]


def test_the_command_line_prints_the_report(capsys) -> None:
    assert root_cause.main([]) == 0
    printed = capsys.readouterr().out
    assert "root-cause" in printed and "language" in printed
