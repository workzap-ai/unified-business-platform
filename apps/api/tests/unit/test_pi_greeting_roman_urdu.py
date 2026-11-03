"""A returning customer's greeting stays in Roman Urdu in a Roman Urdu chat."""

import re

from app.modules.pi.service_conversation import greeting_reply

HISTORY = [{"role": "ai", "text": "Hi"}]


def roman(**over):
    return {
        "pi_mode": "brain",
        "history": HISTORY,
        "reply_language": "roman_ur",
        "customer_profile": {"name": "Ali Raza"},
        **over,
    }


def test_the_plain_return_keeps_the_usual_hi() -> None:
    text = greeting_reply(roman())
    assert text.startswith("Hi Ali.") and "Bataiye" in text and text.count("?") <= 1


def test_an_open_project_is_offered_in_roman_urdu() -> None:
    text = greeting_reply(
        roman(brief={"projects": [{"title": "stock register", "status": "collecting"}]})
    )
    assert text == "Hi Ali. Kya hum stock register par aage barhein?"


def test_an_active_deal_update_is_offered_in_roman_urdu() -> None:
    one = greeting_reply(roman(project_deals=[{"project": "gaam ka app", "stage": "won"}]))
    assert one == "Hi Ali. Kya aap gaam ka app ka update chahte hain, ya koi nayi baat hai?"
    many = greeting_reply(
        roman(project_deals=[{"project": "a", "stage": "won"}, {"project": "b", "stage": "won"}])
    )
    assert "apne projects ka update" in many


def test_no_english_words_remain_in_the_roman_urdu_lines() -> None:
    english = re.compile(r"\b(?:would|you|your|shall|carry|help|today|update on)\b", re.IGNORECASE)
    for ctx in (
        roman(),
        roman(brief={"projects": [{"title": "x", "status": "collecting"}]}),
        roman(project_deals=[{"project": "x", "stage": "won"}]),
    ):
        assert not english.search(greeting_reply(ctx))


def test_english_chats_are_unchanged() -> None:
    ctx = {"pi_mode": "brain", "history": HISTORY, "customer_profile": {"name": "Ali Raza"}}
    assert greeting_reply(ctx) == "Hi Ali. How can I help you today?"
