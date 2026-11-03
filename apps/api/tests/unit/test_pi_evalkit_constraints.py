"""FT-A2: the constraint scorer and its negative controls. A labelled constraint (budget, staff, a
thing that cannot change) is kept when its content words survive in the saved record; a dropped one
lowers the score, an invented one never raises it, and a cause the owner never said stays flagged.
Nothing here changes an earlier score: the previous aggregate numbers are asserted again."""

from app.modules.pi.evalkit import replay, report, scorers, splits

LABELS = ["2 supervisors", "about 300,000 rupees to spend", "cannot stop production for training"]
CASE = {
    "id": "c1",
    "industry": "x",
    "language": "en",
    "messages": [
        "Delivery dates slip on our custom orders. We have only 2 supervisors, about 300,000 "
        "rupees to spend, and we cannot stop production for training."
    ],
    "expected": {
        "problems": [{"id": "p1", "any": ["delivery", "slip"], "figures": []}],
        "corrections": [],
        "hypothesis_only": [],
        "constraints": LABELS,
    },
}
NOTE = {"title": "Delivery dates slip", "user_words": ["Delivery dates slip on our custom orders"]}


def with_constraints(items: list[str], **extra: object) -> list[dict[str, object]]:
    return [{**NOTE, "constraints": items, **extra}]


def test_every_constraint_kept_scores_full() -> None:
    s = scorers.score_case(CASE, with_constraints(LABELS))
    assert s["constraints"] == 3 and s["constraints_kept"] == 3


def test_a_dropped_constraint_lowers_the_score() -> None:
    s = scorers.score_case(CASE, with_constraints(LABELS[:2]))
    assert s["constraints"] == 3 and s["constraints_kept"] == 2
    assert scorers.score_case(CASE, [NOTE])["constraints_kept"] == 0


def test_an_invented_constraint_does_not_raise_the_score() -> None:
    invented = [*LABELS[:2], "must finish before Friday", "only 9 vehicles"]
    s = scorers.score_case(CASE, with_constraints(invented))
    assert s["constraints_kept"] == 2
    assert s["constraints_kept"] <= s["constraints"] == 3


def test_a_constraint_with_the_wrong_number_is_not_kept() -> None:
    wrong = ["5 supervisors", LABELS[1], LABELS[2]]
    assert scorers.score_case(CASE, with_constraints(wrong))["constraints_kept"] == 2


def test_a_constraint_in_the_notes_own_words_counts_as_kept() -> None:
    note = {**NOTE, "user_words": [*NOTE["user_words"], "we cannot stop production for training"]}
    assert scorers.score_case(CASE, [note])["constraints_kept"] == 1


def test_a_script_with_no_word_characters_must_match_as_written() -> None:
    # Devanagari is split by the word pattern at its vowel signs, leaving no content word: such a
    # constraint is kept only when it appears as written, never vacuously
    case = {**CASE, "expected": {**CASE["expected"], "constraints": ["मशीन नहीं बदल सकते"]}}
    assert scorers.score_case(case, with_constraints(["मशीन नहीं बदल सकते"]))["constraints_kept"] == 1
    assert scorers.score_case(case, with_constraints(["कुछ और"]))["constraints_kept"] == 0
    assert scorers.score_case(case, [NOTE])["constraints_kept"] == 0


def test_a_case_without_labels_has_no_constraints_to_keep() -> None:
    plain = {**CASE, "expected": {k: v for k, v in CASE["expected"].items() if k != "constraints"}}
    s = scorers.score_case(plain, with_constraints(LABELS))
    assert s["constraints"] == 0 and s["constraints_kept"] == 0
    assert scorers.aggregate([s] * 3)["constraint_fidelity"] is None


def test_the_aggregate_carries_constraint_fidelity() -> None:
    full = scorers.score_case(CASE, with_constraints(LABELS))
    half = scorers.score_case(CASE, with_constraints(LABELS[:1]))
    assert scorers.aggregate([full, full, full])["constraint_fidelity"] == 1.0
    assert scorers.aggregate([full, half])["constraint_fidelity"] == (3 + 1) / 6


def test_a_cause_the_owner_never_said_stays_flagged_whatever_the_constraints_say() -> None:
    bad = with_constraints(LABELS, cause="a hidden shipping fault", cause_status="confirmed")
    assert scorers.score_case(CASE, bad)["unsupported_causes"] == ["Delivery dates slip"]
    said = with_constraints(LABELS, cause="Delivery dates slip", cause_status="confirmed")
    assert scorers.score_case(CASE, said)["unsupported_causes"] == []


def test_replay_carries_the_recorded_constraints_to_the_record() -> None:
    case = {
        **CASE,
        "recorded": {
            "notes": [
                {
                    **NOTE,
                    "title_local": "Delivery dates slip",
                    "summary": "Delivery dates slip",
                    "category": "orders_fulfilment",
                    "constraints": LABELS,
                }
            ]
        },
    }
    records = replay.replay(case)
    assert records and records[0]["constraints"] == LABELS
    assert scorers.score_case(case, records)["constraints_kept"] == 3


def test_every_case_with_labelled_constraints_keeps_them_in_the_reference_notes() -> None:
    cases = [c for c in replay.load_cases(str(report.CASES)) if c["expected"].get("constraints")]
    assert len(cases) >= 9  # the 4 Held-out and the new Development cases
    for case in cases:
        s = scorers.score_case(case, replay.replay(case))
        assert s["constraints"] == len(case["expected"]["constraints"]) > 0
        assert s["constraints_kept"] == s["constraints"], case["id"]


def test_the_earlier_scores_are_unchanged() -> None:
    cases = replay.load_cases(str(report.CASES))
    for split in (splits.DEVELOPMENT, splits.HELD_OUT, splits.REGRESSION):
        group = [c for c in cases if splits.split_of(c) == split]
        agg = scorers.aggregate([scorers.score_case(c, replay.replay(c)) for c in group])
        assert agg["recall"] == 1.0 and agg["precision"] == 1.0, split
        assert agg["figure_fidelity"] == 1.0 and agg["unsupported_cause_cases"] == 0, split
        assert agg["correction_fidelity"] in (1.0, None), split
    held = [c for c in cases if splits.split_of(c) == splits.HELD_OUT]
    assert len(held) == 60  # Held-out is untouched by this work
