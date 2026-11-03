# ruff: noqa: E501
"""Real production chat: an Arabic-script owner asked twice 'پښتو ووایه'. The honest line comes on that very
turn, in Urdu or Persian, one question and nothing else; follow-ups use the owner's script language, never
English by default; a silent owner gets one nudge, never the same line twice."""

import re

import pytest

from app.modules.pi import followup_policy as fp
from app.modules.pi import safety_scope as ss
from app.modules.pi import service_conversation as sc


def gate(text, language="en", history=()):
    ctx = {
        "pi_mode": "brain",
        "latest_customer_message": text,
        "reply_language": language,
        "history": list(history) or [{"role": "ai", "body": "hello"}],
        "flow": {"state": "S1_LISTENING"},
    }
    return sc._brain_gate(ctx, text)


@pytest.mark.parametrize(
    "text",
    [
        "پښتو ووایه",
        "پشتو ووایه",
        "پښتو  ووایه!",
        "pashto mein baat karo",
        "can you speak Pashto?",
        "Reply in Pashto please",
    ],
)
def test_a_pashto_request_gets_the_honest_line_on_that_turn(text):
    turn = gate(text, "ur" if re.search("[\u0600-\u06ff]", text) else "en")
    assert turn is not None
    assert turn.reply.count("؟") + turn.reply.count("?") == 1
    assert turn.reply.rstrip().endswith(("؟", "?"))
    assert "website" not in turn.reply.lower() and "heaviest" not in turn.reply.lower()


def test_the_arabic_script_owner_is_answered_in_urdu_or_persian():
    for lang, expect in (("ur", "اردو"), ("en", "اردو"), ("fa", "فارسی")):
        turn = gate("پښتو ووایه", lang)
        assert expect in turn.reply
        assert not re.search("[A-Za-z]{4,}", turn.reply)
    assert ss.pashto_reply("en", "speak pashto").startswith("I can't write Pashto reliably")


def test_talking_about_pashto_customers_is_not_a_request():
    assert not ss.pashto_asked(
        "my customers are mostly Pashto speakers in Peshawar and they buy a lot of dairy"
    )


@pytest.mark.parametrize("kind", ["silent", "paused", "documents"])
def test_follow_ups_go_in_the_owner_script_language(kind):
    for stored in ("en", None, "ur"):
        lang = fp.owner_language(stored, "پښتو ووایه")
        text = fp.text_for(kind, lang, n=2)
        assert re.search("[\u0600-\u06ff]", text), (kind, stored, text)
        assert "Still here" not in text
    assert "خواستید" in fp.text_for(
        "silent", fp.owner_language("fa", "سلام")
    )  # Persian chat keeps Persian
    assert fp.text_for("silent", fp.owner_language("en", "hello")).startswith("Still here")


def test_a_latin_owner_keeps_the_roman_urdu_line():
    assert fp.text_for("silent", fp.owner_language("roman_ur", "mujhe madad chahiye")).startswith(
        "Jab chahein"
    )
