import dataclasses

from app.modules.pi import option_voice as ov
from app.modules.pi import resolution_flow as rf
from app.modules.pi import unknown_resolution as ur
from app.modules.pi.requirements_types import Constraints, Limit, ProblemRequirements, Requirements

BUL = "\u2022 "
PROBLEMS = [{"title": "Late orders upset customers", "user_words": ["orders are late"]}]
VAGUE = Requirements(
    problems=(ProblemRequirements(constraints=Constraints(budget=Limit("tight budget"))),)
)


def question():
    return ur.Question(
        key="budget_ceiling",
        fact="budget ceiling",
        field="budget",
        text="What is the most you can spend on this, in one figure?",
        language="en",
        why=("x",),
        options=(0,),
        option_texts=("Buy a new tracking system for orders.",),
        problems=(),
        codes=(),
    )


def test_a_stored_question_round_trips():
    stored = dataclasses.asdict(question())
    back = rf.question_from(stored)
    assert back is not None and back.key == "budget_ceiling" and back.options == (0,)
    assert rf.question_from({"nope": 1}) is None and rf.question_from("x") is None


def test_an_answer_becomes_a_note_with_the_owners_own_words_only():
    proposal = ur.apply_answer(VAGUE, question(), "my budget is 50,000 rupees a month", "en")
    assert proposal.status is ur.Status.FILLED and proposal.satisfied is False
    note = rf.note_for(proposal.updates[0])
    assert note.budget and "50" in note.budget


def test_a_non_answer_or_a_hedge_fills_nothing():
    for text in ("I don't know", "maybe around 50,000 or so"):
        assert ur.apply_answer(VAGUE, question(), text, "en").status is ur.Status.STILL_UNKNOWN


def test_voice_asks_one_question_from_ps5_and_keeps_it_for_the_answer():
    reply = f"Ideas:\n{BUL}Send each buyer a message when their order is late."
    r = ov.voice(reply, VAGUE, "en", PROBLEMS)
    # the vague budget makes the idea unknown: one owner-answerable question, kept for the answer
    assert r.unknown == 1 and r.accepted == 0
    assert r.pending and r.question == r.pending["text"] and r.question.count("?") == 1
    assert rf.question_from(r.pending) is not None
