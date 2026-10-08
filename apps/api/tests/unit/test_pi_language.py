"""pi answers in the language of the customer's latest words."""

import pytest

from app.modules.pi.language import (
    HANDOFF_NOTICES,
    clearly_other,
    detect_language,
    notice_in,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Can you tell me your team performance?", "en"),
        ("And 2nd software development of Cloud system for my company", "en"),
        ("I need a website for my bakery, can you help?", "en"),
        ("Mujhe automation chahiye of flight booking", "roman_ur"),
        ("website design chahiye", "roman_ur"),
        ("Aap ka rate kya hai?", "roman_ur"),
        ("Assalamualaikum bhai", "roman_ur"),
        ("مجھے ویب سائٹ چاہیے", "roman_ur"),
        ("मुझे वेबसाइट चाहिए", "roman_ur"),
        ("أريد موقعا إلكترونيا", "ar"),
        ("ok", None),
        ("👍", None),
        ("", None),
        ("Website", None),
    ],
)
def test_detects_the_customers_language(text: str, expected: str | None) -> None:
    assert detect_language(text) == expected


def test_a_reply_in_the_other_language_is_caught_but_borrowed_words_are_not() -> None:
    assert clearly_other("Aap ka business kis type ka hai?", "en") == "roman_ur"
    assert clearly_other("What kind of business do you have?", "roman_ur") == "en"
    # Roman Urdu with English product words is still Roman Urdu.
    assert clearly_other("Ji, aap ki website aur app dono ka design ho jayega.", "roman_ur") is None
    assert clearly_other("Thanks! What is the website for?", "en") is None
    assert clearly_other("Anything", "ar") is None


def test_fixed_notices_follow_the_language() -> None:
    assert notice_in(HANDOFF_NOTICES, "roman_ur").startswith("Aap ke message")
    assert notice_in(HANDOFF_NOTICES, "en").startswith("Thanks for your message")
    assert notice_in(HANDOFF_NOTICES, "fr") == HANDOFF_NOTICES["en"]
    assert notice_in(HANDOFF_NOTICES, None) == HANDOFF_NOTICES["en"]
