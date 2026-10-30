"""The evaluation data keeps its promises: Held-out has at least 60 cases, nothing is shared between
the splits, every case is complete, and the existing cases never move. These check the data, not the
model, and none of them touches a scorer or a threshold."""

import json
from collections import Counter
from pathlib import Path

import pytest

from app.modules.pi import taxonomy
from app.modules.pi.evalkit import replay, scorers, splits

PATH = Path(replay.__file__).with_name("cases") / "extraction.json"
CASES = replay.load_cases(str(PATH))
HELD = [c for c in CASES if splits.split_of(c) == splits.HELD_OUT]
DEV = [c for c in CASES if splits.split_of(c) == splits.DEVELOPMENT]
CATEGORIES = {c.key for c in taxonomy.CATEGORIES}
NEW_HELD_OUT_FLOOR = 60  # proposal S7: never fewer than 60 in total


def test_held_out_has_at_least_the_proposed_floor() -> None:
    assert len(HELD) >= NEW_HELD_OUT_FLOOR


def test_case_ids_are_unique() -> None:
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_no_message_is_shared_between_held_out_and_development_or_regression() -> None:
    held = {m for c in HELD for m in c["messages"]}
    others = {m for c in CASES if splits.split_of(c) != splits.HELD_OUT for m in c["messages"]}
    assert held & others == set()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_case_is_complete(case) -> None:
    assert case["messages"] and all(m.strip() for m in case["messages"])
    assert case["expected"]["problems"], "a case with no expected problem measures nothing"
    notes = case["recorded"]["notes"]
    assert notes and all(n["category"] in CATEGORIES for n in notes)
    assert all(n["user_words"] for n in notes), "a note without the owner's words cannot be scored"
    for fix in case["expected"]["corrections"]:
        assert fix["wrong"] != fix["right"]


def test_held_out_covers_every_language_and_the_main_case_kinds() -> None:
    languages = Counter(c["language"] for c in HELD)
    assert set(languages) >= {"en", "roman_ur", "ur", "ar"}
    kinds = {c["kind"] for c in HELD}
    assert kinds >= {"single", "list", "correction", "constraints", "mixed", "multi_turn", "rant"}


def test_held_out_has_multi_problem_cases_corrections_and_figures() -> None:
    multi = [c for c in HELD if len(c["expected"]["problems"]) >= 2]
    corrections = sum(len(c["expected"]["corrections"]) for c in HELD)
    figures = sum(len(p["figures"]) for c in HELD for p in c["expected"]["problems"])
    assert len(multi) >= 20 and corrections >= 8 and figures >= 40


def test_a_group_below_its_minimum_is_still_not_measured() -> None:
    one = [scorers.score_case(HELD[0], replay.replay(HELD[0]))]
    assert scorers.aggregate(one)["measured"] is False


def test_the_split_is_still_the_hash_of_the_id_and_the_cases_file_is_valid_json() -> None:
    json.loads(PATH.read_text(encoding="utf-8"))
    assert all(splits.split_of({"id": c["id"]}) == splits.HELD_OUT for c in HELD)
    assert len(DEV) >= 39  # Development never shrinks below what the first round had


DEV_FLOOR = 63


def test_development_has_grown_to_its_floor_and_covers_the_languages() -> None:
    assert len(DEV) >= DEV_FLOOR
    languages = Counter(c["language"] for c in DEV)
    # Hindi is data only: pi understands Devanagari but does not write it
    assert languages["ar"] >= 8 and languages["hi"] >= 8 and languages["ur"] >= 8
    assert languages["en"] >= 1 and languages["roman_ur"] >= 1
    kinds = {c["kind"] for c in DEV}
    assert kinds >= {"single", "list", "correction", "constraints", "mixed", "multi_turn", "rant"}


def test_development_constraint_cases_are_labelled() -> None:
    labelled = [c for c in DEV if c["kind"] == "constraints"]
    assert len(labelled) >= 4
    assert all(c["expected"]["constraints"] for c in labelled)


def test_development_shares_nothing_with_held_out_and_one_pair_with_regression() -> None:
    dev = {m for c in DEV for m in c["messages"]}
    held = {m for c in HELD for m in c["messages"]}
    regression = {
        m for c in CASES if splits.split_of(c) == splits.REGRESSION for m in c["messages"]
    }
    assert dev & held == set()
    # reg_correction_figure is, on purpose, a copy of the acc_correction_en conversation
    assert dev & regression == {
        "Sorry, not 10, it was 100 clients.",
        "We lost about 10 clients last year because reports came late.",
    }
