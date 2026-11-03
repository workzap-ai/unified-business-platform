"""B6 root cause 4: a short question asked again is caught. Before the fix a question with fewer
than three content words ("Which shop is it?") was never the same as itself, so when the model
named no slot, the repeat was never stopped."""

import pytest

from app.modules.pi import slots


@pytest.mark.parametrize(
    "question",
    [
        "Which shop is it?",
        "How many shops do you have?",
        "Since when has this been happening?",
        "Kaun si shop mein hota hai?",
    ],
)
def test_a_short_question_is_the_same_as_itself(question: str) -> None:
    assert slots.same_question(question, question)


def test_case_spacing_and_punctuation_do_not_make_it_a_different_question() -> None:
    assert slots.same_question("Which shop is it?", "which  shop is it ?")
    assert slots.same_question("Which shop is it?", "Which shop is it?!")


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Which shop is it?", "Which day is it?"),
        ("How many shops do you have?", "How many staff do you have?"),
        ("Since when has this been happening?", "How often has this been happening?"),
        ("Kaun si shop mein hota hai?", "Kaun sa din hota hai?"),
    ],
)
def test_two_different_short_questions_stay_different(one: str, other: str) -> None:
    assert not slots.same_question(one, other)


def test_a_repeated_short_question_is_caught_without_a_named_slot() -> None:
    closed = [{"slot": "", "q": "Which shop is it?"}]
    assert slots.asked_again("", "Which shop is it?", closed) == "Which shop is it?"
    assert slots.asked_again("", "Which day is it?", closed) is None


def test_the_same_short_question_is_not_added_to_the_closed_list_twice() -> None:
    previous = {"closed_slots": [], "last_question": {"slot": "", "q": "Which shop is it?"}}
    once, _ = slots.advance(previous, "the second one", "Anything?", "")
    again, _ = slots.advance(
        {"closed_slots": once, "last_question": {"slot": "", "q": "Which shop is it?"}},
        "the second one",
        "Anything?",
        "",
    )
    assert len(once) == 1 and len(again) == 1
