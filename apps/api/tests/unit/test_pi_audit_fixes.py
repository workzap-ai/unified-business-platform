"""Fixes from the full-spec audit: disclosure, buttons, crisis line (spec Parts 1, 5, 6)."""

import pytest

from app.modules.pi import constitution, decisions, safety

BRAIN = {
    "pi_mode": "brain",
    "strict_voice": True,
    "flow": {"state": "S2_CLARIFYING"},
    "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
}


def rules(reply, **over):
    return {v.rule for v in constitution.lint(reply, {**BRAIN, **over})}


@pytest.mark.parametrize(
    "reply",
    [
        "The Workzap team reads this chat. Which shop loses the most?",
        "Someone from the team is reading your messages. Which shop?",
    ],
)
def test_pi_never_says_a_person_reads_the_chat(reply):
    assert "R-DISC-04" in rules(reply)


def test_a_person_may_be_mentioned_once_they_took_over():
    reply = "The Workzap team reads this chat. Which shop loses the most?"
    assert "R-DISC-04" not in rules(reply, flow={"state": "X_HUMAN"})


@pytest.mark.parametrize(
    "reply",
    ["I\u2019m a woman and I know shops.", "I\u2019ve run a shop too. Which one is it?"],
)
def test_human_claims_with_curly_apostrophes_are_caught(reply):
    assert "R-DISC-03" in rules(reply)


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Tabdeeli chahiye", decisions.CHANGES),
        ("طلب تعديلات", decisions.CHANGES),
        ("No thanks", decisions.SAY_NO),
        ("nahi shukriya", decisions.SAY_NO),
    ],
)
def test_button_taps_in_every_language_are_recognised(said, expected):
    assert expected.match(said)


def test_the_crisis_line_in_pakistan_is_1122():
    assert "1122" in safety.emergency_reply(safety.Emergency.SELF_HARM, "PK", "en")
    assert "911" in safety.emergency_reply(safety.Emergency.SELF_HARM, "CA", "en")


def test_repair_leaves_one_question_and_it_comes_last():
    fixed = constitution.repair(
        "Which shop is it? That sounds hard. How often does it happen?", dict(BRAIN)
    )
    assert fixed.count("?") == 1 and fixed.endswith("How often does it happen?")
    moved = constitution.repair("Which shop is it? Noted, thank you.", dict(BRAIN))
    assert moved.endswith("Which shop is it?")


def test_repair_cuts_a_long_reply_down_to_the_limit():
    long = " ".join(f"Sentence number {i} says something useful here." for i in range(20))
    fixed = constitution.repair(f"{long} Which shop is it?", dict(BRAIN))
    assert len(fixed.split()) <= constitution.WORD_CAP + 8 and fixed.endswith("Which shop is it?")
    assert not [v for v in constitution.lint(fixed, dict(BRAIN)) if v.rule == "R-VOICE-02"]


@pytest.mark.parametrize(
    ("said", "stops"),
    [
        ("please stop messaging me", True),
        ("do not contact us again please", True),
        ("mujhe message mat karo", True),
        ("don't message me again", True),
        ("please don't stop the order", False),
        ("he is messaging me about stock", False),
    ],
)
def test_natural_ways_to_say_stop_end_the_follow_ups(said, stops):
    from app.modules.pi_saas.campaigns import OPT_OUT_PHRASE

    assert bool(OPT_OUT_PHRASE.search(said)) is stops


def test_a_canonical_phrase_is_not_used_a_third_time():
    ctx = dict(BRAIN)
    ctx["history"] = [
        {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."},
        {"role": "ai", "text": "That's a real problem. Which shop?"},
        {"role": "customer", "text": "two"},
        {"role": "ai", "text": "That's a real problem. How often?"},
    ]
    assert "R-VOICE-04" in {v.rule for v in constitution.lint("That's a real problem. Why?", ctx)}
    assert "R-VOICE-04" not in {v.rule for v in constitution.lint("Oof. Why?", ctx)}


def test_after_three_clarifying_questions_pi_must_note_what_it_has():
    ctx = {**BRAIN, "clarify_count": 3, "brain_settings": {"max_clarify": 3}}
    assert "R-ASK-02" in {v.rule for v in constitution.lint("Which shop is it?", ctx)}
    ctx["clarify_count"] = 2
    assert "R-ASK-02" not in {v.rule for v in constitution.lint("Which shop is it?", ctx)}
    ctx["clarify_count"] = 3
    assert "R-ASK-02" not in {v.rule for v in constitution.lint("Thanks, noted.", ctx)}
