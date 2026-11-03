"""B6 root cause 3: the separate extractor can carry what the owner said about when it began, what
it costs, how many and how often, so the noted problem is not listed as missing those facts and pi
does not ask for them again. Before the fix the extractor's note had no such fields."""

import pytest

from app.modules.pi.problem_extract import SYSTEM, SimpleNote

FACTS = {
    "title": "Cash does not match at day end",
    "user_words": ["since March, it costs us 4,000 rupees a day, every day, in 2 of our 4 shops"],
    "category": "cash_collections",
    "where": ["2 of our 4 shops"],
    "frequency": "daily",
    "since_text": "since March",
    "money_text": "4,000 rupees a day",
    "of_total": "2 of 4 shops",
    "frequency_text": "every day",
    "impact_types": ["lost_money"],
}


def test_the_extractor_note_keeps_since_money_count_frequency_and_impact() -> None:
    note = SimpleNote(**FACTS).to_note()
    assert note.since_text == "since March"
    assert note.money_text == "4,000 rupees a day"
    assert note.of_total == "2 of 4 shops"
    assert note.frequency_text == "every day"
    assert note.impact_types == ["lost_money"]


def test_a_note_without_those_facts_still_works_as_before() -> None:
    note = SimpleNote(
        title="Staff come late", user_words=["staff come late"], category="people_staff"
    )
    converted = note.to_note()
    assert (
        converted.since_text == "" and converted.money_text == "" and converted.impact_types == []
    )


@pytest.mark.parametrize("field", ["since_text", "money_text", "of_total", "impact_types"])
def test_the_extractor_is_asked_for_each_of_them_only_when_said(field: str) -> None:
    flat = " ".join(SYSTEM.split()).lower()  # the prompt wraps its lines
    assert field in flat
    assert "only what they said" in flat and "never a guess" in flat
