"""Confirming the summary, and what the summary shows (spec 3.7, 4.8, R-OFFER-01)."""

import pytest

from app.modules.pi import decisions, problems


@pytest.mark.parametrize("said", ["ok", "theek hai", "looks right", "yes", "sab theek"])
def test_a_plain_acknowledgement_confirms_the_summary(said):
    assert decisions.summary_ok(said)


@pytest.mark.parametrize(
    "said",
    [
        "ok but P2 is wrong",
        "theek hai lekin staff missing",
        "yes, however the second one is different",
        "ok? what about cash",
    ],
)
def test_an_acknowledgement_with_a_correction_does_not(said):
    assert not decisions.summary_ok(said)


def test_the_summary_uses_the_persons_own_words_and_group_names():
    items = [
        {"category": "stock_inventory", "title": "Stock runs out", "title_local": "Maal khatam"},
        {"category": "stock_inventory", "title": "Dead stock", "group_name": "Godown"},
    ]
    english = problems.summary_message(items, "en")
    assert "*Godown*" in english and "Stock runs out" in english
    roman = problems.summary_message(items, "roman_ur")
    assert "Maal khatam" in roman and "Dead stock" in roman  # no local title: English stays


def test_two_quiet_replies_bring_the_summary_once_something_is_unsummarised():
    # spec v1.6 19.7: quiet replies no longer bring a summary; a checkpoint does (part19)
    assert problems.summary_due("ok", 3, 1, 7, quiet_replies=2) is None
    assert problems.summary_due("ok", 3, 1, 7, quiet_replies=1) is None
    assert problems.summary_due("ok", 3, 0, 7, quiet_replies=2) is None  # nothing new to show


def test_the_reading_grade_check_tells_plain_text_from_dense_text():
    from app.modules.pi import brain_docs

    plain = " ".join(["A stock check tells each shop when a best seller is low."] * 6)
    dense = " ".join(
        [
            "Comprehensive reconciliation infrastructure would substantially accelerate "
            "organisational decision-making across heterogeneous distribution environments."
        ]
        * 3
    )
    assert brain_docs.reading_grade(plain) < brain_docs.MAX_READING_GRADE
    assert brain_docs.reading_grade(dense) > brain_docs.MAX_READING_GRADE
