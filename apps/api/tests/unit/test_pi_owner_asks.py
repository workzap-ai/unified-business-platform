# ruff: noqa: E501
"""Live chat 2026-10-28 (a furniture maker): pi kept asking for what the owner had said they do not
have, answered a request for a plan with one sentence and a question, opened with 'Ji, samajh aaya.
Ye note kar liya hai.', and once handed the lead back ('Aap is ke baare mein aage kya poochna
chahenge?')."""

import pytest

from app.modules.pi import constitution, owner_asks, reply_voice

NO_RECORDS = [
    "Dono wajah se delay hota hai, lekin mujhe exact pata nahi ke kis wajah se zyada hota hai kyun ke hum har order ka proper record nahi rakhte.",
    "Exact number mujhe nahi pata, kyun ke hum pichle mahine ke orders ka proper record nahi rakhte.",
    "Nahi, wood ka proper stock register ya Excel record nahi hai.",
    "I don't know exactly, we never kept records.",
    "Mujhe pata nahi",
]
NOT_UNKNOWN = [
    "Hamare production steps aam tor par ye hain: cutting, assembling, polishing.",
    "Ji haan, mere workers ke paas mobile phones hain.",
    "Main chahta hoon ke system order ka status dikhaye.",
]


@pytest.mark.parametrize("said", NO_RECORDS)
def test_a_fact_the_owner_does_not_have_is_seen(said: str) -> None:
    assert owner_asks.count_unknowns([said]) == 1


@pytest.mark.parametrize("said", NOT_UNKNOWN)
def test_a_plain_answer_is_not_a_missing_fact(said: str) -> None:
    assert owner_asks.count_unknowns([said]) == 0


def test_questions_about_the_past_or_how_often_are_seen() -> None:
    for question in (
        "Pichle mahine ke 20-30 orders mein se kitne late hue the?",
        "Itne orders mein se aam tor par kaun sa stage sab se zyada atakta hai?",
        "Zyada tar kaun si lakri aur kaun sa unit use hota hai?",
        "How often does the delivery slip?",
        "What usually stays pending?",
    ):
        assert owner_asks.asks_for_history(question), question
    for question in (
        "Kya workers ke paas mobile hai jis se woh stage update kar saken?",
        "Kya shuru mein wood ki ginti karna aap ke liye mumkin hoga?",
        "Which part would you like to start with?",
    ):
        assert not owner_asks.asks_for_history(question), question


def test_a_request_to_understand_the_plan_is_seen() -> None:
    for said in (
        "Ab ek simple solution ka overall plan samjha dein",
        "Mujhe practical initial system plan dein, pehle solution samjha dein.",
        "Document banwane se pehle simple alfaaz mein samjha dein ke system kaise kaam karega",
        "Please explain the plan in simple words",
    ):
        assert owner_asks.asks_for_plan(said), said
    assert not owner_asks.asks_for_plan("Ji haan, mere workers ke paas mobile hai")


def test_the_owner_complaining_that_pi_keeps_asking_is_seen() -> None:
    assert owner_asks.complains_of_repeats(
        "Aap baar baar mujh se woh details pooch rahe hain jo mere paas available nahi hain."
    )
    assert not owner_asks.complains_of_repeats("Kya aap baar baar ye karte hain?")


def lint(reply: str, **context):
    base = {"pi_mode": "brain", "latest_customer_message": "Mujhe pata nahi", "history": []}
    return {v.rule for v in constitution.lint(reply, {**base, **context})}


def test_asking_again_for_what_they_lack_breaks_r_ask_09() -> None:
    reply = "Pichle mahine ke 20-30 orders mein se kitne late hue the?"
    assert "R-ASK-09" in lint(reply, owner_unknowns=2)
    assert "R-ASK-09" not in lint(reply)  # no missing fact on record: a normal question
    assert "R-ASK-09" not in lint(
        "Pehle hafte sirf order ki tareekh likhein. Kya aap isse shuru karna chahenge?",
        owner_unknowns=2,
    )


def test_a_complaint_of_repeats_forbids_a_fact_question() -> None:
    assert "R-ASK-09" in lint("Kitne workers hain?", repeat_complaint=True)
    assert "R-ASK-09" not in lint("Kya yahan se shuru karein?", owner_unknowns=0)


def test_the_safe_line_no_longer_hands_the_lead_back() -> None:
    for line in constitution.FALLBACK_OTHER.values():
        assert "poochna" not in line and "ask about" not in line
    assert "theek hota" in constitution.FALLBACK_OTHER["roman_ur"]


def test_ye_note_kar_liya_hai_is_not_sent() -> None:
    reply = "Ji, samajh aaya. Ye note kar liya hai.\n\nAbhi ek waqt mein kitne orders chal rahe hote hain?"
    assert reply_voice.drop_noted(reply) == "Abhi ek waqt mein kitne orders chal rahe hote hain?"
    assert constitution.NOTED_START.match("Ji, samajh aaya. Ye note kar liya hai. Kitne orders?")
