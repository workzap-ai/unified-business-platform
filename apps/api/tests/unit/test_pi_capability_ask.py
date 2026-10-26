# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Live chats of 2026-10-26: a capability ask is answered with ideas (not "Aap chahen to ...?"), a bare
"g" is not a yes, the heavy Roman Urdu solution asks are read as asks, and a Roman Urdu reply does not
open with an English filler (R-LANG-02)."""

import pytest

from app.modules.pi import constitution, decisions, solution_ask

H = [{"role": "ai", "text": "x"}]


def rules(
    reply: str, said: str = "", state: str = "S3_NOTED", language: str = "roman_ur"
) -> set[str]:
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": language,
        "history": H,
        "latest_customer_message": said,
    }
    return {v.rule for v in constitution.lint(reply, context)}


@pytest.mark.parametrize(
    "said",
    ["ap kya kr skty hain wo btyn", "kya kar sakte hain aap?", "what can you do?", "any ideas?"],
)
def test_a_permission_question_to_a_capability_ask_is_sent_back(said):
    for reply in (
        "Aap chahen to main abhi solution ideas bataun?",
        "Kya main abhi do ideas bataun?",
        "Would you like me to share two ideas?",
    ):
        assert "R-ANS-01" in rules(reply, said), (said, reply)


def test_the_offer_after_ideas_is_not_a_permission_question():
    reply = (
        "Ji, ye do ideas abhi aazma sakte hain:\n\n• Chhoti video banayein.\n• Purane customers ko "
        "message karein.\n\nKya aap in sab ke liye solution document aur quote chahenge? Aap mana bhi "
        "kar sakte hain."
    )
    assert "R-ANS-01" not in rules(reply, "ap kya kr skty hain wo btyn", "S5_READINESS")
    english = (
        "Here are two ideas to try now:\n\n• Film a short video.\n• Message old customers.\n\n"
        "Would you like me to prepare a solution document and a quote? You can say no."
    )
    assert "R-ANS-01" not in rules(english, "what can you do?", "S5_READINESS", "en")


@pytest.mark.parametrize("said", ["g", "G", "g haan", "ok g", "hmm"])
def test_a_bare_g_is_not_an_explicit_yes(said):
    answer, _ = decisions.classify(said)
    assert answer is not decisions.Answer.YES, said


def test_ji_and_haan_still_are_a_yes():
    assert decisions.classify("ji")[0] is decisions.Answer.YES
    assert decisions.classify("haan")[0] is decisions.Answer.YES


@pytest.mark.parametrize(
    "said",
    ["solution ap dw", "solution dw", "solution dy", "ap kya kr skty hain wo btyn", "hal btyn"],
)
def test_the_heavy_roman_urdu_solution_asks_are_asks(said):
    assert solution_ask.asked_for_ideas(said), said


@pytest.mark.parametrize("filler", ["Thanks", "Thank you", "Sure", "Okay", "Alright", "Great"])
def test_a_roman_urdu_reply_does_not_open_with_an_english_filler(filler):
    reply = f"{filler}, note kar liya hai. Ye kab se ho raha hai?"
    assert "R-LANG-02" in rules(reply, "customers kam hain")
    assert "R-LANG-02" not in rules(reply, "customers are few", language="en")


def test_the_roman_urdu_openers_the_owner_approved_are_fine():
    for reply in (
        "Note kar liya, customers kam hain. Ye kab se ho raha hai?",
        "Ji, ab Roman Urdu mein baat karte hain. Sales shuru karne mein abhi sab se bari rukawat kya hai?",
        "Shukriya, note kar liya. Ye kab se ho raha hai?",
    ):
        assert "R-LANG-02" not in rules(reply, "customers kam hain"), reply
