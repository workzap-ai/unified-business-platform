"""alreadyAnswered at fact level (spec v1.5, 18.5): a question about a count, a duration or a
frequency that the owner already stated is blocked, in English and Roman Urdu. Narrow on purpose:
no stated fact, or a different thing asked, and the question may go."""

import pytest

from app.modules.pi import reply_gates


@pytest.mark.parametrize(
    ("said", "reply"),
    [
        ("I have 4 shops and stock runs out", "Noted. How many shops do you have?"),
        ("we run three branches", "Got it. How many branches is that?"),
        ("meri 5 dukaan hain", "Theek hai. Aap ki kitni dukaan hain?"),
        ("it started since March", "Since when has this been happening?"),
        ("this happens for 3 months now", "How long has it been going on?"),
        ("ye 2 mahine se ho raha hai", "Ye kab se ho raha hai?"),
        ("it happens every day", "How often does it happen?"),
        ("ye har roz hota hai", "Ye kitni baar hota hai?"),
    ],
)
def test_a_question_the_owner_already_answered_is_blocked(said: str, reply: str) -> None:
    reason = reply_gates.fact_already_given(reply, [said])
    assert reason and "already said" in reason


@pytest.mark.parametrize(
    ("said", "reply"),
    [
        ("I have 4 shops and stock runs out", "How many staff work in each shop?"),
        ("stock runs out", "How many shops do you have?"),
        ("we run three branches", "How many people work there?"),
        ("it started since March", "How often does it happen?"),
        ("it happens every day", "Since when has this been happening?"),
        ("the cashier is late", "Which day is it worst?"),
        ("we share the shop with my brother", "How often does it happen?"),
        ("always happy to help", "Since when has this been happening?"),
        ("I have 4 shops", "That is a lot to look after. What hurts most?"),
    ],
)
def test_a_different_or_unstated_thing_may_still_be_asked(said: str, reply: str) -> None:
    assert reply_gates.fact_already_given(reply, [said]) is None


def test_the_fact_can_come_from_an_earlier_message() -> None:
    said = ["hello", "I have 4 shops", "stock runs out often"]
    assert reply_gates.fact_already_given("How many shops do you have?", said)


def test_the_reason_quotes_the_owners_words() -> None:
    reason = reply_gates.fact_already_given("How many shops?", ["I have 4 shops"])
    assert reason and "4 shops" in reason


def test_a_reply_with_no_question_is_not_touched() -> None:
    assert reply_gates.fact_already_given("Noted, 4 shops.", ["I have 4 shops"]) is None


def test_the_gate_source_has_no_stray_control_characters() -> None:
    import inspect

    source = inspect.getsource(reply_gates)
    allowed = {"\n", "\r", "\t"}
    assert not [c for c in source if ord(c) < 32 and c not in allowed]  # a typed backspace


def test_since_when_alone_is_not_a_stated_duration() -> None:
    assert reply_gates.fact_already_given("Since when?", ["since when does it matter"]) is None


def _context(**extra: object) -> dict:
    history = [
        {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."},
        {"role": "customer", "text": "I have 4 shops and stock runs out"},
    ]
    return {"history": history, "latest_customer_message": "yes", "noted_problems": [{}]} | extra


def test_the_live_check_blocks_the_repeat_only_when_the_workspace_turned_it_on() -> None:
    from app.modules.pi.service_conversation import part18_problem

    reply = "Stock running out in 4 shops is hard. How many shops do you have?"
    assert part18_problem(reply, _context()) is None  # off by default
    on = part18_problem(reply, _context(fact_ask=True))
    assert on and "already said" in on
