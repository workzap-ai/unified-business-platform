"""Matching the person and mending a reply that did not land (pi Brain spec 8.4.1, 8.4.2)."""

from types import SimpleNamespace

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import style
from app.modules.pi.service_conversation import matching_the_person


def test_a_short_writer_gets_a_short_answer_but_never_too_short_to_hold_a_note():
    found = style.profile(["yaar maal nahi bikta", "stock khatam", "kal bhi"])
    assert found["median_words"] == 2 and found["writes_short"] is True
    assert found["reply_up_to_words"] == style.MIN_REPLY_WORDS  # 1.5 x 2 is under the floor
    assert found["formality"] == "casual"


def test_a_long_writer_may_get_a_longer_answer_inside_the_cap():
    said = " ".join(["word"] * 24)
    found = style.profile([said, said, said])
    assert found["reply_up_to_words"] == 36 and found["writes_short"] is False
    huge = style.profile([" ".join(["word"] * 200)])
    assert huge["reply_up_to_words"] == style.MAX_REPLY_WORDS


@pytest.mark.parametrize(
    ("said", "formality"),
    [
        ("Good morning sir, please note our cashiers are late", "formal"),
        ("aap ka shukriya, assalam o alaikum", "formal"),
        ("bhai ye batao yaar", "casual"),
        ("stock runs out", "neutral"),
    ],
)
def test_formality_is_read_from_how_they_address_pi(said, formality):
    assert style.profile([said])["formality"] == formality


def test_emoji_and_voice_notes():
    assert style.profile(["maal khatam 😭"])["uses_emoji"] is True
    assert style.profile(["maal khatam"])["uses_emoji"] is False
    assert style.profile(["a", "b", "c", "d"], voice_notes=2, total=4)["voice_notes"] is True
    assert style.profile(["a", "b", "c", "d"], voice_notes=1, total=10)["voice_notes"] is False
    assert style.profile([]) == {}


@pytest.mark.parametrize(
    "said",
    [
        "what?",
        "?",
        "??",
        "samajh nahi aaya",
        "I don't understand",
        "kya matlab",
        "what do you mean by that",
    ],
)
def test_a_lost_person_is_noticed(said):
    assert style.confused(said)


@pytest.mark.parametrize(
    "said",
    ["Stock runs out in two shops", "ok what is the price?", "yes", "what time do you open?"],
)
def test_a_normal_message_is_not_confusion(said):
    assert not style.confused(said)


def test_each_repeat_moves_one_strategy_further_and_a_clear_reply_resets():
    step = 0
    seen = []
    for _ in range(7):
        step = style.repair_step(step, "samajh nahi aaya")
        seen.append(step)
    assert seen == [1, 2, 3, 4, 5, 5, 5]
    assert style.repair_step(4, "ok, stock runs out") == 0
    assert [style.REPAIR[n].split(":")[0].split(" ")[0] for n in (1, 2, 3, 4, 5)] == [
        "Rephrase", "Give", "Give", "Offer", "Drop",
    ]  # fmt: skip


def chat(brief=None):
    return SimpleNamespace(service_brief=brief or {})


def message(body, kind="text", sender="customer"):
    return SimpleNamespace(body=body, message_type=kind, sender_type=sender)


def test_the_context_carries_the_style_and_the_repair_step():
    conversation = chat()
    rows = [message("Noted. Which shop?", sender="ai"), message("main road wali")]
    found = matching_the_person(conversation, message("samajh nahi aaya"), rows)
    assert found["style"]["writes_short"] is True
    assert found["repair"]["step"] == 1 and "Rephrase" in found["repair"]["do"]
    assert conversation.service_brief["repair_step"] == 1
    again = matching_the_person(conversation, message("kya matlab"), rows)
    assert again["repair"]["step"] == 2
    clear = matching_the_person(conversation, message("the main road shop"), rows)
    assert "repair" not in clear and conversation.service_brief["repair_step"] == 0


def test_voice_notes_are_counted():
    rows = [message("", "audio"), message("", "audio"), message("ok")]
    found = matching_the_person(chat(), message("main road", "audio"), rows)
    assert found["style"]["voice_notes"] is True


def ctx(**style_fields):
    return {
        "latest_customer_message": "stock khatam",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "style": {"reply_up_to_words": 15, **style_fields},
    }


def test_the_linter_keeps_a_reply_near_a_short_writers_length():
    twenty = "Thanks for telling me. " + " ".join(["more"] * 18) + ". Which shop is it?"
    short = "Noted: stock runs out. Which shop is it?"
    assert any(v.rule == "R-VOICE-01" and "write short" in v.message for v in c.lint(twenty, ctx()))
    assert not any(v.rule == "R-VOICE-01" for v in c.lint(short, ctx()))
    # With no style (or a long writer) the general 60-word cap is the only limit.
    plain = {**ctx(), "style": {}}
    assert not any(v.rule == "R-VOICE-01" for v in c.lint(twenty, plain))
    # A summary or a document message keeps its own, larger cap.
    summary = "\n".join(["• " + " ".join(["a"] * 15)] * 3)
    assert not any(v.rule == "R-VOICE-01" for v in c.lint(summary, ctx()))
