# ruff: noqa: E501
"""PS-0: the problem-solving case file, the multi-turn scripted replay, the new scorers and the report.

No database, no model. The file checks are fixture invariants (a bad case is a bug in the data);
the scorer checks each carry a negative control (a built case that must fail the scorer)."""

import copy
import hashlib
import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.modules.pi import constitution
from app.modules.pi.brain_docs import MONEY_IN_TEXT
from app.modules.pi.evalkit import access_log, ps_replay, ps_report, ps_scorers, scorers, splits

CASES_DIR = Path(ps_report.CASES).parent
CASES: list[dict[str, Any]] = json.loads(Path(ps_report.CASES).read_text(encoding="utf-8"))
OTHER_IDS = [
    c["id"]
    for name in ("extraction.json", "plan.json")
    for c in json.loads((CASES_DIR / name).read_text(encoding="utf-8"))
]
LANGS = {"en", "roman_ur", "ur", "ar"}
MUST_HAVE = {
    "property_management_and_rentals",
    "e_commerce_and_d2c_brands",
    "sports_clubs_academies_and_turf_court_rentals",
    "wedding_planners_and_event_management",
    "banquet_halls_and_marquees",
    "salons_and_barbers",
    "clinics_and_gp_practices",
    "auto_workshops_and_service_centres",
}
REQUIRED = (
    "problems stated missing constraints tried cause hypothesis_only corrections requirement_change "
    "rejected_solution answered_facts questions candidates blueprint"
).split()


def owner_text(case: dict[str, Any]) -> str:
    return " ".join(t["text"] for t in case["turns"] if t["role"] == "owner")


def ids(split: str) -> list[str]:
    return [c["id"] for c in CASES if splits.split_of(c) == split]


def test_at_least_sixty_cases_with_unique_ids_across_all_case_files() -> None:
    assert len(CASES) >= 60
    everything = [c["id"] for c in CASES] + OTHER_IDS
    assert len(everything) == len(set(everything))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_case_has_the_v2_envelope_and_the_scenario_shape(case: dict[str, Any]) -> None:
    for key in ("id", "case_type", "format_version", "industry", "language", "kind", "regression"):
        assert key in case
    assert case["case_type"] == "conversation" and case["format_version"] == 2
    assert case["synthetic"] is True and case["language"] in LANGS
    assert case["provenance"]["origin"] == "hand_written" and "split" not in case
    roles = [t["role"] for t in case["turns"]]
    assert roles == ["owner", "pi"] * 3 + ["owner"]
    assert [t["text"] for t in case["turns"] if t["role"] == "owner"] == case["messages"]
    assert all(set(REQUIRED) <= set(case["expected"]) for _ in [0])
    exp = case["expected"]
    assert len(exp["problems"]) == 2 and exp["constraints"] and exp["tried"]
    assert exp["hypothesis_only"] and exp["cause"]["status"] == "owner_said"
    fix = exp["corrections"][0]
    assert fix["turn"] == 2 and fix["wrong"] != fix["right"]
    owner = [t["text"] for t in case["turns"] if t["role"] == "owner"]
    assert fix["wrong"] in scorers._NUM.findall(owner[0]) or fix["wrong"] in owner[0]
    assert fix["right"] in owner[2] and fix["wrong"] in owner[2]
    assert exp["requirement_change"]["turn"] == 3 and exp["rejected_solution"]["turn"] == 3
    assert exp["requirement_change"]["text"] in owner[3]
    verdicts = Counter(c["verdict"] for c in exp["candidates"])
    assert verdicts["relevant"] >= 1 and verdicts["violates_constraint"] >= 1
    assert set(verdicts) <= set(ps_scorers.relevance.VERDICTS)
    notes = case["recorded"]["notes_by_turn"]
    assert set(notes) == {"0", "1"} and all(n["category"] for v in notes.values() for n in v)
    assert set(exp["blueprint"]) == set(ps_scorers.BLUEPRINT_KINDS)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_expected_value_is_something_the_owner_said(case: dict[str, Any]) -> None:
    owner = owner_text(case)
    stems = scorers._stems(owner)
    exp = case["expected"]
    for spec in exp["problems"]:
        assert all(scorers._stems(k) <= stems for k in spec["any"]), spec
        assert all(scorers.figure_kept(f, owner) for f in spec["figures"]), spec
    for phrase in exp["stated"]:
        assert phrase in owner, phrase
    for item in exp["constraints"]:
        assert item["status"] == "confirmed" and item["blocks"]
    for item in exp["tried"]:
        assert item["what"] in owner, item
    assert all(w in owner for w in exp["cause"]["evidence_words"])
    for fact in exp["answered_facts"]:
        assert all(w.casefold() in owner.casefold() for w in fact["value_words"]), fact
        assert 0 <= fact["said_in_turn"] <= 3


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_pi_reference_replies_follow_the_rules_and_never_ask_a_known_fact(
    case: dict[str, Any],
) -> None:
    replies = [t["text"] for t in case["turns"] if t["role"] == "pi"]
    for index, reply in enumerate(replies):
        question = ps_scorers.last_question(reply)
        assert question and reply.rstrip().endswith(question)
        assert reply.count("?") + reply.count("؟") == 1
        assert not MONEY_IN_TEXT.search(reply) and not constitution.PROMISE.search(reply)
        slot = next(q["slot"] for q in case["expected"]["questions"] if q["after_turn"] == index)
        assert slot not in ps_scorers.known_slots(case, index), (index, slot)


def test_the_cases_cover_the_requested_industries_and_all_four_languages() -> None:
    industries = {c["industry"] for c in CASES}
    assert MUST_HAVE <= industries and len(industries - MUST_HAVE) >= 6
    for industry in industries:
        assert {c["language"] for c in CASES if c["industry"] == industry} == LANGS


def test_the_split_is_the_hash_of_the_id_and_nothing_is_stored() -> None:
    for case in CASES:
        digest = hashlib.sha256(case["id"].encode("utf-8")).digest()[0] % 100
        expected = splits.HELD_OUT if digest < 25 else splits.DEVELOPMENT
        assert splits.split_of(case) == expected and "split" not in case
    total = sum(len(ids(s)) for s in (splits.DEVELOPMENT, splits.HELD_OUT, splits.REGRESSION))
    assert total == len(CASES)
    assert ids(splits.DEVELOPMENT) and ids(splits.HELD_OUT)


def test_no_text_is_shared_between_held_out_and_the_other_cases() -> None:
    held = {t["text"] for c in CASES if c["id"] in ids(splits.HELD_OUT) for t in c["turns"]}
    rest = {t["text"] for c in CASES if c["id"] not in ids(splits.HELD_OUT) for t in c["turns"]}
    assert not held & rest
    extraction = json.loads((CASES_DIR / "extraction.json").read_text(encoding="utf-8"))
    said = {m for c in extraction for m in c["messages"]}
    assert not said & {t["text"] for c in CASES for t in c["turns"]}


def test_no_personal_data_in_any_case() -> None:
    patterns = [
        re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
        re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){9,}\d"),
        re.compile(r"https?://", re.IGNORECASE),
    ]
    for case in CASES:
        blob = json.dumps(case, ensure_ascii=False)
        assert not any(p.search(blob) for p in patterns), case["id"]


def test_the_replay_refuses_a_held_out_case_without_an_access_pass() -> None:
    held = next(c for c in CASES if splits.split_of(c) == splits.HELD_OUT)
    with pytest.raises(PermissionError):
        ps_replay.replay_case(held)
    with pytest.raises(PermissionError):
        ps_replay.replay_case(held, held_out_ok=True)  # type: ignore[arg-type]


def test_the_report_never_replays_or_scores_a_held_out_case(monkeypatch: Any) -> None:
    seen: list[str] = []
    real = ps_replay.replay_case

    def spy(case: dict[str, Any], **kwargs: Any) -> Any:
        seen.append(case["id"])
        return real(case, **kwargs)

    monkeypatch.setattr(ps_replay, "replay_case", spy)
    rows = ps_report.score_all(CASES)
    held = set(ids(splits.HELD_OUT))
    assert seen and not set(seen) & held
    assert not {r["id"] for r in rows} & held
    assert {r["split"] for r in rows} <= {splits.DEVELOPMENT, splits.REGRESSION}


# --- replay ------------------------------------------------------------------------------------


def mini_case(**over: Any) -> dict[str, Any]:
    """A small synthetic case used to build negative controls."""
    case = copy.deepcopy(next(c for c in CASES if c["id"] == "ps_restaurant_en"))
    case.update(over)
    return case


def dev_case(case_id: str) -> dict[str, Any]:
    case = next(c for c in CASES if c["id"] == case_id)
    assert splits.split_of(case) == splits.DEVELOPMENT
    return case


def test_live_records_drop_what_the_extractor_shape_cannot_carry_and_reference_keeps_it() -> None:
    case = dev_case("ps_restaurant_en")
    run = ps_replay.replay_case(case)
    assert len(run["live"]) == 2 and len(run["reference"]) == 2
    assert all(
        "constraints" not in r and "cause" not in r and "tried" not in r for r in run["live"]
    )
    assert any(r.get("tried") for r in run["reference"])


def test_a_correction_is_found_by_the_live_finder_and_applied_to_the_records() -> None:
    run = ps_replay.replay_case(dev_case("ps_restaurant_en"))
    assert run["corrections"] == [{"turn": 2, "wrong": "7", "right": "70"}]
    assert "70" in " ".join(run["live"][0]["user_words"])
    assert "About 7 " not in " ".join(run["live"][0]["user_words"])


def test_an_untouched_wrong_figure_fails_the_correction_scorer() -> None:
    case = dev_case("ps_restaurant_en")
    run = ps_replay.replay_case(case)
    stale = [
        {**r, "user_words": ["About 7 customers"], "summary": "7 customers"} for r in run["live"]
    ]
    got = ps_scorers.extraction_scores(case, stale, "")
    assert got["correction_applied"]["num"] == 0 and got["correction_applied"]["den"] == 1


def test_a_roman_urdu_figure_correction_is_detected_by_the_live_finder() -> None:
    assert ps_replay.fc.numeric_correction("10 nahi 100 hain", ["about 10 clients"]) == (
        "10",
        "100",
    )


# --- scorers: negative controls ------------------------------------------------------------------


def test_repeated_question_scorer_flags_a_known_fact_asked_again() -> None:
    case = mini_case()
    known = [f for f in case["expected"]["answered_facts"] if f["said_in_turn"] == 0]
    assert known
    slot = known[0]["slot"]
    cue = {
        "count": "How many are there?",
        "since": "Since when is this happening?",
        "how_often": "How often does this happen?",
        "where": "Where does it happen?",
        "money": "How much does it cost you?",
        "who": "Who handles it?",
        "tried": "What have you tried?",
        "cause": "Why do you think it happens?",
    }.get(slot)
    if cue is None:
        pytest.skip("slot has no english cue in this fixture")
    pis = [t for t in case["turns"] if t["role"] == "pi"]
    pis[0]["text"] = f"Thanks. {cue}"
    assert ps_scorers.question_scores(case)["repeated_question"]["num"] >= 1


def test_the_same_question_twice_is_a_repeat_even_without_a_known_slot() -> None:
    case = mini_case()
    pis = [t for t in case["turns"] if t["role"] == "pi"]
    pis[1]["text"] = pis[0]["text"]
    assert ps_scorers.question_scores(case)["repeated_question"]["num"] >= 1


def test_a_question_with_no_recognised_slot_is_unclassified_not_fine() -> None:
    case = mini_case()
    pis = [t for t in case["turns"] if t["role"] == "pi"]
    pis[0]["text"] = "Interesting. Does the colour blue matter to you?"
    got = ps_scorers.question_scores(case)
    assert got["unclassified_question"]["num"] >= 1 and got["repeated_question"]["num"] == 0


def test_slot_classification_in_four_languages() -> None:
    assert ps_scorers.classify_slot("Since when has it been like this?") == "since"
    assert ps_scorers.classify_slot("Yeh kab se ho raha hai?") == "since"
    assert ps_scorers.classify_slot("منذ متى يحدث هذا؟") == "since"
    assert ps_scorers.classify_slot("یہ کب سے ہو رہا ہے؟") == "since"
    assert ps_scorers.classify_slot("How many staff do you have?") == "count"


def test_language_scorer_flags_an_english_reply_in_an_urdu_case() -> None:
    case = mini_case(language="ur")
    got = ps_scorers.language_scores(case)
    assert got["language_match"]["num"] == 0 and got["language_match"]["den"] == 3


def test_hypothesis_stays_hypothesis_through_merge_cause() -> None:
    got = ps_scorers.hypothesis_scores(mini_case())
    assert got["hypothesis_stays_hypothesis"]["den"] >= 2
    assert got["hypothesis_stays_hypothesis"]["num"] == got["hypothesis_stays_hypothesis"]["den"]


def test_blueprint_scorer_catches_missing_elements_bad_order_price_and_promise() -> None:
    case = dev_case("ps_restaurant_en")
    plan = copy.deepcopy(case["expected"]["blueprint"])
    assert ps_scorers.blueprint_scores(case, plan)["blueprint_elements_present"]["num"] == 4
    thin = {**plan, "dependencies": [], "success_criteria": []}
    assert ps_scorers.blueprint_scores(case, thin)["blueprint_elements_present"]["num"] == 2
    ids_ = [s["id"] for s in plan["steps"]]
    backwards = {
        **plan,
        "dependencies": [{"from": ids_[-1], "to": ids_[0]}, {"from": "x", "to": "y"}],
    }
    assert ps_scorers.blueprint_scores(case, backwards)["blueprint_dependencies_valid"]["num"] == 0
    priced = copy.deepcopy(plan)
    priced["steps"][0]["text"] = "Buy the tool for Rs 5000 and it will definitely fix everything"
    assert ps_scorers.blueprint_scores(case, priced)["blueprint_price_or_promise"]["num"] >= 1
    unrelated = copy.deepcopy(plan)
    unrelated["steps"][0]["text"] = "Repaint the lobby"
    assert (
        ps_scorers.blueprint_scores(case, unrelated)["blueprint_tied_to_owner_words"]["num"]
        < ps_scorers.blueprint_scores(case, plan)["blueprint_tied_to_owner_words"]["num"]
    )


def test_live_blueprint_support_reads_the_schema_for_all_four_elements() -> None:
    support = ps_scorers.live_blueprint_support()
    assert set(support) == set(ps_scorers.BLUEPRINT_KINDS)


def test_aggregate_needs_cases_and_items_before_a_cell_is_measured() -> None:
    def row(num: int, den: int) -> dict[str, Any]:
        return {"metrics": {"m": ps_scorers.rate(num, den)}}

    few_cases = ps_scorers.aggregate([row(5, 20), row(5, 20)])["m"]
    few_items = ps_scorers.aggregate([row(1, 3), row(1, 3), row(1, 3)])["m"]
    enough = ps_scorers.aggregate([row(1, 4)] * 3)["m"]
    assert not few_cases["measured"] and not few_items["measured"] and enough["measured"]
    assert (enough["num"], enough["den"], enough["cases"]) == (3, 12, 3)
    assert ps_scorers.MIN_CASES == scorers.MIN_CASES == 3 and ps_scorers.MIN_ITEMS == 10


def test_a_cell_below_the_minimum_prints_not_yet_measured_with_its_n() -> None:
    low = ps_report.cell({"num": 2, "den": 4, "cases": 4, "measured": False})
    assert low.startswith("not yet measured") and "2/4" in low
    assert ps_report.cell({"num": 0, "den": 0, "cases": 0, "measured": False}) == "no items"
    assert "50%" in ps_report.cell({"num": 5, "den": 10, "cases": 3, "measured": True})


def test_the_relevance_scorer_and_the_live_filter_both_run_on_every_development_case() -> None:
    for case in CASES:
        if splits.split_of(case) != splits.DEVELOPMENT:
            continue
        got = ps_scorers.idea_scores(case)
        assert got["relevance_agreement"]["den"] == len(case["expected"]["candidates"])


def test_the_access_pass_lets_a_held_out_case_replay() -> None:
    held = next(c for c in CASES if splits.split_of(c) == splits.HELD_OUT)
    with tempfile.TemporaryDirectory() as folder:
        log = Path(folder) / "log.jsonl"
        ticket = access_log.grant(log, "test", "unit test of the guard", "t", "held_out", 1)
        assert ps_replay.replay_case(held, held_out_ok=ticket)["gate"]
