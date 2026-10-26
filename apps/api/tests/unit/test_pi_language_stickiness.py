"""R-LANG-09 (Book 2 10.3, Book 4 5.3): a short or ambiguous message (no, ok, yes, haan, hmm, a
number, an emoji) does not change the conversation language; a substantive message does."""

from types import SimpleNamespace as N

import pytest

from app.modules.pi.service_conversation import AMBIGUOUS_SHORT, reply_language


def msg(body, who="customer", kind="text"):
    return N(body=body, sender_type=who, message_type=kind)


def language_after(chat, latest):
    rows = list(reversed([msg(body, who) for body, who in chat]))  # newest first
    return reply_language(N(), msg(latest), rows).get("reply_language")


ROMAN = [
    ("Mera dhanda nahi chal raha aur meri kuch dukaanain hain defense mein", "customer"),
    ("Samajh liya. Kaunsi cheez ki dukaanain hain?", "ai"),
]
ENGLISH = [
    ("Our shops have no footfall and the staff come late every week", "customer"),
    ("Noted. Which shop is worst?", "ai"),
]


@pytest.mark.parametrize("latest", ["no", "ok", "yes", "haan", "hmm", "5", "👍", "yes please"])
def test_a_short_answer_keeps_a_roman_urdu_chat_in_roman_urdu(latest):
    assert language_after(ROMAN, latest) == "roman_ur"


@pytest.mark.parametrize(
    "latest", ["no", "ok", "haan", "nahi", "theek hai", "hmm", "5", "👍", "thanks"]
)
def test_a_short_answer_keeps_an_english_chat_in_english_even_in_urdu_words(latest):
    assert language_after(ENGLISH, latest) == "en"


def test_a_substantive_message_does_switch_the_language():
    assert language_after(ENGLISH, "Mujhe samajh nahi aaya yeh sab kya hai") == "roman_ur"
    assert language_after(ROMAN, "Our biggest problem is that the staff come late") == "en"


def test_the_ambiguous_set_is_only_short_acknowledgements():
    for text in ("no", "Haan", "theek hai", "yes please", "OK!", "hmm...", "haan ji"):
        assert AMBIGUOUS_SHORT.match(text), text
    for text in ("stock khatam ho jata hai", "late deliveries", "yes the staff are late", ""):
        assert not AMBIGUOUS_SHORT.match(text), text
