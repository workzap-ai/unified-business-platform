# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Live chat 6 (owner, clothing brand, pi on Gemini as primary, 21:00-21:08 PKT): the exact replies."""

import pytest

from app.modules.pi import constitution

FIRST = "Hi, main pi hoon, Workzap ka AI. Apne business mein jo masla hai woh batayein."
M2 = "baby aur male clothes ka stock bechna hai"
R2 = "Note kar liya hai: baby aur male clothes ka stock bechna hai. Ye stock warehouse mein parha hai ya outlets mein?"
R3 = "Warehouse aur outlets, dono jagah parha hai. Is stock mein specific broken sizes bache hain ya poore sets hain?"
R4 = "Noted — full sets. Is anything else getting in the way?"


def context(said, earlier, replies):
    history = [{"role": "ai", "text": FIRST}]
    for asked, answered in zip(earlier, replies, strict=False):
        history += [{"role": "customer", "text": asked}, {"role": "ai", "text": answered}]
    return {
        "pi_mode": "brain",
        "flow": {"state": "S3_NOTED"},
        "reply_language": "roman_ur",
        "history": history,
        "latest_customer_message": said,
        "noted_problems": [{"missing": ["where", "impact"]}],
    }


def test_reply_3_a_short_answer_said_back_is_an_echo_and_is_removed():
    ctx = context("warehouse and outlets", [M2], [R2])
    assert "R-ECHO-04" in {v.rule for v in constitution.lint(R3, ctx)}
    fixed = constitution.repair(R3, ctx)
    assert fixed == "Is stock mein specific broken sizes bache hain ya poore sets hain?"


def test_reply_4_english_in_a_roman_urdu_chat_is_never_sent_and_has_no_dash():
    ctx = context("poore sets", [M2, "warehouse and outlets"], [R2, R3])
    fixed = constitution.repair(R4, ctx)
    assert "—" not in fixed and "anything else" not in fixed.lower()
    # spec 17.6: no "Note kar liya" announcement, straight to the one question
    assert not fixed.startswith("Note kar liya") and fixed.endswith("?")
    assert fixed.count("?") == 1
    assert fixed == "Ye har jagah hota hai, ya sirf kuch jagah?"  # the next open slot


def test_english_in_a_roman_urdu_chat_without_anything_noted_gets_the_safe_localised_line():
    ctx = context("poore sets", [M2], [R2])
    ctx["noted_problems"] = []
    fixed = constitution.repair(R4, ctx)
    assert fixed == constitution.safe_fallback(ctx)
    assert fixed.endswith("?") and "anything else" not in fixed.lower()


@pytest.mark.parametrize("dash", ["—", "–"])
def test_a_dash_becomes_a_comma_in_any_reply(dash):
    ctx = context("customers kam hain", [], [])
    fixed = constitution.repair(f"Note kar liya {dash} customers kam hain. Ye kab se hai?", ctx)
    assert dash not in fixed and fixed.startswith("Note kar liya, customers kam hain.")


def test_a_roman_urdu_reply_with_a_few_english_words_is_not_replaced():
    ctx = context("warehouse mein stock hai", [], [])
    reply = "Note kar liya, warehouse mein stock hai. Ye outlets mein bhi hai?"
    assert constitution.repair(reply, ctx) == reply


def test_a_question_that_only_shares_a_word_is_not_an_echo():
    ctx = context("warehouse and outlets", [M2], [R2])
    reply = "Warehouse aur outlets mein kitna stock parha hai?"
    assert "R-ECHO-04" not in {v.rule for v in constitution.lint(reply, ctx)}
    longer = (
        "Warehouse aur outlets mein se kis jagah ka stock sab se purana hai, ye note karna hai."
    )
    # a long sentence is not an echo: it stays (the dead-end rule adds the next question after it)
    assert constitution.repair(longer, ctx).startswith(longer)
