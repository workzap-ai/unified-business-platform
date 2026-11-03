"""What owners say about pi's ideas, in real Roman Urdu, and the candidate lesson text made from it
(learning_feedback.py). The classifier missed "ye kam nahi aya" and "already kar raha hoon", so the
idea leaderboards and the nightly miner never saw them."""

import pytest

from app.modules.pi import learning_bank, learning_feedback, learning_lessons, solution_score


@pytest.mark.parametrize(
    ("said", "signal"),
    [
        ("ye kam nahi aya", "idea_no_help"),
        ("kaam nahi aaya", "idea_no_help"),
        ("nahi chala", "idea_no_help"),
        ("koi result nahi aya", "idea_no_help"),
        ("farq nahi pada", "idea_no_help"),
        ("already kar raha hoon", "idea_already_doing"),
        ("pehle hi kar raha hoon", "idea_already_doing"),
        ("we already do this", "idea_already_doing"),
        ("ye to sab ko pata hai", "idea_generic"),
        ("it worked for me", "idea_worked"),
    ],
)
def test_the_classifier_reads_real_roman_urdu_reactions(said, signal):
    reaction = solution_score.classify(said)
    assert reaction is not None and reaction.signal == signal, said


@pytest.mark.parametrize("said", ["sirf raqam", "ok", "price kitna hai", "ye idea acha hai"])
def test_a_plain_answer_is_not_a_reaction_to_the_ideas(said):
    reaction = solution_score.classify(said)
    assert reaction is None or reaction.signal not in learning_feedback.SAYS


def test_the_idea_lines_of_a_reply():
    reply = (
        "Ji, ye do ideas abhi aazma sakte hain:\n\n"
        "• Chhoti video banayein.\n"
        "• Purane customers ko message karein.\n\n"
        "Kya aap in sab ke liye solution document aur quote chahenge?"
    )
    assert learning_feedback.ideas_of(reply) == [
        "Chhoti video banayein.",
        "Purane customers ko message karein.",
    ]
    assert learning_feedback.ideas_of("1. Pehla idea\n2) Doosra idea") == [
        "Pehla idea",
        "Doosra idea",
    ]
    assert learning_feedback.ideas_of("Note kar liya. Kab se hai?") == []


def test_the_candidate_text_is_a_lesson_of_the_right_size_and_passes_the_gates():
    for signal in learning_feedback.SAYS:
        text = learning_feedback.lesson_text(signal, ["Chhoti video banayein.", "Message karein."])
        assert learning_lessons.MIN_LENGTH <= len(text) <= learning_lessons.MAX_LENGTH, signal
        assert learning_bank.redaction_confidence(text) >= learning_feedback.REDACTION_BAR, text


def test_a_long_idea_is_cut_to_fit_and_a_worked_idea_is_offered_first():
    long_idea = "Apne purane customers ko roz ek chhota message bhejein " * 10
    text = learning_feedback.lesson_text("idea_no_help", [long_idea])
    assert len(text) <= learning_lessons.MAX_LENGTH and "…" in text
    assert "offer it first" in learning_feedback.lesson_text("idea_worked", ["x y z"]).lower() or (
        "good one to offer first" in learning_feedback.lesson_text("idea_worked", ["x y z"])
    )


def test_an_idea_with_personal_data_is_below_the_redaction_bar():
    text = learning_feedback.lesson_text("idea_no_help", ["Call Ahmed on 0300 1234567 today."])
    assert learning_bank.redaction_confidence(text) < learning_feedback.REDACTION_BAR
