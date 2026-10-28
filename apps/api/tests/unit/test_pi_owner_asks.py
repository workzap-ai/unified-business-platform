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


NO_QUESTION_ASKS = [
    "Maine kaha tha ke abhi mujh se aur sawal na karein. Aap khud best practical approach recommend karein.",
    "abhi mujh se aur sawal na karein",
    "Please, no more questions right now",
    "Don't ask me any more questions, just recommend",
    "bas sawal mat karein",
]


@pytest.mark.parametrize("said", NO_QUESTION_ASKS)
def test_an_owner_asking_for_no_questions_is_seen(said: str) -> None:
    assert owner_asks.asked_no_questions(said)


def test_a_normal_message_is_not_a_request_for_no_questions() -> None:
    assert not owner_asks.asked_no_questions("Mere paas ek sawal hai ke ye kaise chalega")


def test_the_questions_are_taken_out_of_the_reply() -> None:
    reply = (
        "Pehle order tracking, phir wood ki ginti. Aap ko mobile par stage nazar aayega.\n\n"
        "In mein se kaun sa shuru karna aap ke liye sab se aasaan rahega?"
    )
    out = owner_asks.without_questions(reply)
    assert "?" not in out and out.startswith("Pehle order tracking")


def test_an_offer_is_taken_out_with_its_you_can_say_no() -> None:
    reply = (
        "Ye shuru ke liye kaafi hai.\n\nKya aap chahte hain ke main solution document aur quote "
        "banwa doon? Aap mana bhi kar sakte hain."
    )
    out = owner_asks.without_questions(reply)
    assert out == "Ye shuru ke liye kaafi hai." or out.startswith("Ye shuru ke liye kaafi hai")
    assert "mana" not in out and "?" not in out


def test_a_reply_that_is_only_a_question_is_left_for_the_guards() -> None:
    assert owner_asks.without_questions("Kaun si dukaan?") == "Kaun si dukaan?"


def test_a_recall_question_is_not_a_how_to() -> None:
    from app.modules.pi import solution_ask

    said = (
        "Mujhe yaad nahi hum ne kya decide kiya tha, pehle kaunsa system banana tha, "
        "aur wood stock tracking ko baad mein kyun rakhna tha?"
    )
    assert owner_asks.asks_for_recall(said)
    assert not solution_ask.asked_howto(said)
    assert solution_ask.asked_howto("Ye sab kaise hoga step by step? Kaunsa software?")


def test_asks_to_suggest_and_to_explain_the_alert() -> None:
    assert owner_asks.asks_to_suggest(
        "Aap delay ki common wajahon ki ek practical list khud suggest karein."
    )
    assert owner_asks.asks_for_plan(
        "Batayein ke agar worker order ka stage update karna bhool jaye to system mujhe kaise alert karega."
    )
    assert not owner_asks.asks_to_suggest("Mere workers ke paas mobile hai")
