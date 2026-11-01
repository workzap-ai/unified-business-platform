# ruff: noqa: E501
"""G54 (spec 17.5 EO3, v1.6 19.3): a question about pi is answered in sentence one; no ideas without a
problem; the unchecked-ideas caveat follows the ideas; no filler; a repeated question is not answered twice
the same way. From a real production transcript (voice note)."""

import re

import pytest

from app.modules.pi import constitution, safety
from app.modules.pi import option_voice as ov
from app.modules.pi import service_conversation as sc

VOICE = (
    "Can you tell me are you chatbot or any other? I'm considering you are a chatbot... "
    "just tell me about yourself"
)
SECOND = "Just tell me what then that can you do for me?"
BUL = "\u2022 "


def gate(text, history=(), language="en"):
    ctx = {
        "pi_mode": "brain",
        "latest_customer_message": text,
        "reply_language": language,
        "history": list(history),
        "flow": {"state": "S1_LISTENING"},
    }
    turn = sc._brain_gate(ctx, text)
    return turn


@pytest.mark.parametrize(
    "text",
    [VOICE, SECOND, "what can you do for me", "tell me about yourself", "are you a chatbot?"],
)
def test_a_question_about_pi_is_recognised(text):
    assert safety.identity_asked(text, constitution.ASKS_IF_AI) in (
        safety.Identity.ABOUT,
        safety.Identity.PERSON,
    )


def test_what_can_you_do_about_it_is_a_request_for_a_fix_not_a_question_about_pi():
    assert safety.identity_asked("What can you do about it?", constitution.ASKS_IF_AI) is None


def test_sentence_one_says_pi_is_an_ai_then_one_short_line_then_one_question():
    turn = gate(VOICE, history=[{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}])
    assert turn is not None
    first = re.split(r"(?<=[.!?])\s+", turn.reply.strip())[0]
    assert "AI" in first and "pi" in first
    assert turn.reply.count("?") == 1 and turn.reply.rstrip().endswith("?")
    assert not re.search(r"\b(?:price|cost|quote|rs\.?|pkr|offer)\b", turn.reply, re.I)
    assert "ideas marked" not in turn.reply and "Sorry about the wait" not in turn.reply


def test_the_same_question_again_gets_a_shorter_answer_and_the_one_question():
    first = gate(VOICE, history=[{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}])
    again = gate(SECOND, history=[{"role": "ai", "text": first.reply}])
    assert again is not None and again.reply != first.reply
    assert len(again.reply) < len(first.reply)
    assert again.reply.count("?") == 1 and again.reply.rstrip().endswith("?")


@pytest.mark.parametrize("language", ["en", "roman_ur", "ur", "ar"])
def test_every_language_answers_in_sentence_one_and_asks_one_question(language):
    text = safety.identity_reply(safety.Identity.ABOUT, language)
    assert len(re.findall(r"[?\u061f]", text)) == 1 and re.search(r"[?\u061f]\s*$", text)
    assert "pi" in text.split(".")[0].split("\u06d4")[0]
    shorter = safety.identity_reply(safety.Identity.ABOUT_AGAIN, language)
    assert len(shorter) < len(text)


def test_the_unchecked_caveat_follows_the_ideas_never_leads():
    reply = f"Here are two ideas:\n{BUL}Message each buyer when their order is late.\n{BUL}Ask each buyer for a note."
    from app.modules.pi.requirements_types import (
        Constraints,
        Limit,
        ProblemRequirements,
        Requirements,
    )

    vague = Requirements(
        problems=(ProblemRequirements(constraints=Constraints(budget=Limit("tight budget"))),)
    )
    problems = [{"title": "Late orders upset customers", "user_words": ["orders are late"]}]
    v = ov.voice(reply, vague, "en", problems)
    assert ov.T["en"]["unknown"] not in v.block and v.after == ov.T["en"]["unknown"]
    text = sc.put_option_voice(v.reply, v.block, v.question, v.after)
    assert text.index(ov.T["en"]["unknown"]) > text.index("Message each buyer")
    none = ov.voice("Hello there. What is going wrong?", vague, "en", problems)
    assert none.after == ""  # no ideas shown: no caveat


def test_no_problem_noted_means_no_ideas_at_all_only_the_one_question():
    ideas = f"Sorry about the wait. Here are two ideas:\n{BUL}Notice which task you keep putting off.\n{BUL}Write down the three things that worry you."
    turn = sc.ServiceTurn(reply=ideas)
    ctx = {
        "pi_mode": "brain",
        "latest_customer_message": SECOND,
        "reply_language": "en",
        "noted_problems": [],
        "history": [{"role": "ai", "text": "Hi"}],
    }
    sc.brain_option_voice(turn, ctx)
    assert BUL not in turn.reply and "ideas" not in turn.reply.lower()
    assert turn.reply.count("?") == 1 and turn.reply.rstrip().endswith("?")
