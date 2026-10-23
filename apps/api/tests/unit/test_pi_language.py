"""pi answers in the language of the customer's latest words."""

import pytest

from app.modules.pi.language import (
    HANDOFF_NOTICES,
    clearly_other,
    detect_language,
    english_greeting,
    notice_in,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Can you tell me your team performance?", "en"),
        ("And 2nd software development of Cloud system for my company", "en"),
        ("I need a website for my bakery, can you help?", "en"),
        ("Hi", "en"),
        ("HELLO!", "en"),
        ("Hey there 👋", "en"),
        ("Good morning", "en"),
        ("ye hi chahiye", "roman_ur"),
        ("Mujhe automation chahiye of flight booking", "roman_ur"),
        ("website design chahiye", "roman_ur"),
        ("Aap ka rate kya hai?", "roman_ur"),
        ("Assalamualaikum bhai", "roman_ur"),
        ("مجھے ویب سائٹ چاہیے", "roman_ur"),
        ("मुझे वेबसाइट चाहिए", "roman_ur"),
        ("أريد موقعا إلكترونيا", "ar"),
        ("ok", None),
        ("no", None),  # Roman Urdu speakers answer "no" too: the chat keeps its language
        ("Yes please", None),
        ("nahi", "roman_ur"),
        ("no, I don't", "en"),
        ("👍", None),
        ("", None),
        ("Website", None),
    ],
)
def test_detects_the_customers_language(text: str, expected: str | None) -> None:
    assert detect_language(text) == expected


@pytest.mark.parametrize(
    "text",
    ["Hi, I need a website", "hi mujhe website chahiye", "ye hi", "Hi مجھے مدد چاہیے", ""],
)
def test_a_greeting_with_a_request_is_not_just_a_greeting(text: str) -> None:
    assert not english_greeting(text)


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


def test_a_bare_no_after_voice_notes_keeps_their_language() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import reply_language

    def said(body: str, kind: str = "text") -> SimpleNamespace:
        return SimpleNamespace(sender_type="customer", message_type=kind, body=body)

    rows = [said("Hum Facebook ad chalate hain, footfall nahi aata", "audio"), said("hello")]
    found = reply_language(SimpleNamespace(), said("no"), rows)  # type: ignore[arg-type]
    assert found["reply_language"] == "roman_ur"
