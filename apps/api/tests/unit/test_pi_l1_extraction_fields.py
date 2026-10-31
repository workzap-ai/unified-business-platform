"""L1-2: the extractor's note carries the B2a fields; the scripted replay saves them through the
real save logic; an invented cause never becomes the owner's."""

import json
from pathlib import Path

from app.modules.pi.evalkit import replay, scorers
from app.modules.pi.problem_extract import SimpleNote

MESSAGE = (
    "Sales fell since March because the competitor is cheaper. We tried Facebook ads, they brought "
    "nobody. Budget is 50,000 rupees, we cannot close the second shop."
)


def case(note):
    return {
        "id": "l1",
        "messages": [MESSAGE],
        "expected": {"problems": [{"id": "p1", "any": ["sales"]}]},
        "recorded": {"notes": [note]},
    }


BASE = {
    "title": "Sales fell",
    "category": "sales_revenue",
    "user_words": ["Sales fell since March"],
    "summary": "Sales fell",
}


def test_the_simple_note_maps_the_b2a_fields_into_the_problem_note():
    note = SimpleNote(
        title="Sales fell",
        budget="50,000 rupees",
        cannot_change=["close the second shop"],
        tried=[{"what": "Facebook ads", "outcome": "brought nobody"}],
        cause_text="the competitor is cheaper",
        cause_said=True,
        cause_words=["competitor", "cheaper"],
        expected_outcome="sales back",
    ).to_note()
    assert note.budget == "50,000 rupees" and note.cannot_change == ["close the second shop"]
    assert note.tried[0]["what"] == "Facebook ads"
    assert (note.cause_text, note.cause_said) == ("the competitor is cheaper", True)
    assert note.expected_outcome == "sales back"


def test_an_empty_note_stays_empty_nothing_is_invented():
    note = SimpleNote(title="Sales fell").to_note()
    assert not (note.budget or note.cannot_change or note.tried or note.cause_text)


def test_replay_scores_constraints_tried_and_an_owner_said_cause():
    (record,) = replay.replay(
        case(
            {
                **BASE,
                "budget": "50,000 rupees",
                "cannot_change": ["close the second shop"],
                "tried": [{"what": "Facebook ads", "outcome": "brought nobody"}],
                "cause_text": "the competitor is cheaper",
                "cause_said": True,
                "cause_words": ["competitor", "cheaper"],
            }
        )
    )
    assert record["constraints"] == ["50,000 rupees", "close the second shop"]
    assert record["tried"][0]["what"] == "Facebook ads"
    assert record["cause_status"] == "owner_said"


def test_negative_control_an_invented_cause_stays_a_hypothesis_and_is_not_unsupported():
    note = {
        **BASE,
        "cause_text": "the supplier ships late",
        "cause_said": True,
        "cause_words": ["supplier", "ships", "late"],
    }
    (record,) = replay.replay(case(note))
    assert record["cause_status"] == "hypothesis"  # the words are not the owner's
    assert scorers.score_case(case(note), [record])["unsupported_causes"] == []
    # the scorer itself still catches a record that claims owner_said without the words
    lie = {**record, "cause_status": "owner_said"}
    assert scorers.score_case(case(note), [lie])["unsupported_causes"] == ["Sales fell"]


def test_no_split_has_an_unsupported_cause():
    folder = Path(replay.__file__).parent / "cases"
    for name in ("extraction.json",):
        for c in json.loads((folder / name).read_text(encoding="utf-8")):
            records = replay.replay(c)
            assert scorers.score_case(c, records)["unsupported_causes"] == [], c["id"]
