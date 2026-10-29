"""A corrected number is detected, replaced, and the reply must use it (B7.1, B7.3)."""

import pytest

from app.modules.pi import figure_correction as fc


@pytest.mark.parametrize(
    ("latest", "earlier", "expected"),
    [
        ("Sorry, not 10, it was 100 clients.", ["We lost about 10 clients."], ("10", "100")),
        ("Not 10, 100", [], ("10", "100")),
        ("10 nahi, 100", [], ("10", "100")),
        ("Nahi 20 nahi, 12 staff hain.", ["20 staff hain"], ("20", "12")),
        ("Correction, 5,000 subscribers, not 500.", [], ("500", "5000")),
        ("5000, not 500", [], ("500", "5000")),
        ("No wait, it is 15 kg, I checked the bin.", ["We waste about 5 kg of rice."], ("5", "15")),
        ("نہیں 10 نہیں، 100", [], ("10", "100")),
    ],
)
def test_a_numeric_correction_is_found(latest, earlier, expected) -> None:
    assert fc.numeric_correction(latest, earlier) == expected


@pytest.mark.parametrize(
    ("latest", "earlier"),
    [
        ("No, I have 3 shops.", ["We lost about 10 clients."]),  # another fact, not a correction
        ("We have 100 clients.", ["We lost about 10 clients."]),  # no cue
        ("Sorry for the delay.", ["10 clients"]),  # no number
        ("No wait, it is 15 kg and 20 bags.", ["5 kg of rice"]),  # two figures: do not guess
        ("Not 10 or 10.", []),
    ],
)
def test_an_unrelated_number_is_never_treated_as_a_correction(latest, earlier) -> None:
    assert fc.numeric_correction(latest, earlier) is None


def test_replace_figure_only_touches_the_standalone_figure() -> None:
    assert fc.replace_figure("lost 10 clients, 100 others, 10.5 more", "10", "100") == (
        "lost 100 clients, 100 others, 10.5 more"
    )
    assert fc.replace_figure("about 5,000 subscribers", "5000", "9000") == "about 9000 subscribers"
    assert fc.has_figure("lost 10 clients", "10") and not fc.has_figure("lost 100 clients", "10")


def test_the_reply_must_use_the_new_figure_and_not_state_the_old_one() -> None:
    assert fc.reply_problem("Noted: 100 clients, not 10. What caused it?", "10", "100") is None
    assert fc.reply_problem("10 nahi, 100 clients. Kab se?", "10", "100") is None
    assert "must use 100" in (fc.reply_problem("Noted: 10 clients lost. Why?", "10", "100") or "")
    assert fc.reply_problem("100 clients, and 10 of them left early.", "10", "100")


def test_an_old_figure_word_is_superseded_only_for_the_same_thing() -> None:
    new = ["it was 100 clients"]
    assert fc.superseded("We lost about 10 clients last year", new, True)
    assert not fc.superseded("We have 3 shops", new, True)  # unrelated figure
    assert not fc.superseded("We lost about 10 clients last year", new, False)  # not a correction
    assert not fc.superseded("We lost clients", new, True)  # no figure to contradict
