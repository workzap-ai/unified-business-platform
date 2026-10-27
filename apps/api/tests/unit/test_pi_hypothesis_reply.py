# ruff: noqa: E501
"""What the owner's reply does to pi's last question: the hypothesis ledger verdicts and the
`landed` input of the variety rule (Book 5, Part 3.5). Pure functions, no model, no database."""

import pytest

from app.modules.pi import hypothesis_reply as hr
from app.modules.pi import moves, think_prompt

HYPOTHESIS = "parents forget the due date because nobody reminds them"
PUT = "Meri ek soch hai, galat bhi ho sakti hai: parents due date bhool jate hain kyunke koi yaad nahi dilata. Kya yehi wajah hai?"


@pytest.mark.parametrize(
    "said",
    [
        "ok",
        "hmm",
        "theek hai",
        "ji",
        "pata nahi",
        "I don't know",
        "baad mein",
        "solution do",
        "kuch karo",
        "",
    ],
)
def test_a_deflection_does_not_land(said: str) -> None:
    assert hr.deflected(said)
    assert hr.landed(PUT, said) is (False if said else None)


@pytest.mark.parametrize(
    "said", ["cash", "haan wo bhool jate hain", "nahi, paison ki wajah se", "mahine ke aakhir mein"]
)
def test_an_answer_lands(said: str) -> None:
    assert hr.landed(PUT, said) is True


def test_nothing_asked_means_nothing_to_land() -> None:
    assert hr.landed("Yeh sab fee ka masla hai.", "cash") is None


def test_an_explicit_yes_to_the_hypothesis_question_confirms() -> None:
    assert hr.judge("haan bilkul", HYPOTHESIS, put_to_owner=True) == "confirm"
    assert hr.judge("yes exactly", HYPOTHESIS, put_to_owner=True) == "confirm"
    assert hr.judge("ji haan", HYPOTHESIS, put_to_owner=True) == "confirm"


def test_a_yes_never_confirms_a_hypothesis_that_was_not_put_to_the_owner() -> None:
    assert hr.judge("haan", HYPOTHESIS, put_to_owner=False) == "none"


def test_a_yes_with_a_but_is_not_a_confirmation() -> None:
    assert hr.judge("haan lekin sirf kuch parents", HYPOTHESIS, put_to_owner=True) != "confirm"


def test_an_answer_that_supports_the_cause_adds_evidence_and_never_confirms() -> None:
    said = "parents due date bhool jate hain, koi unko reminder nahi bhejta"
    assert hr.judge(said, HYPOTHESIS, put_to_owner=False) == "for"
    assert hr.judge(said, HYPOTHESIS, put_to_owner=True) == "for"


def test_an_answer_that_contradicts_the_cause_adds_evidence_against() -> None:
    assert hr.judge("nahi, ye wajah nahi hai", HYPOTHESIS, put_to_owner=True) == "against"
    assert hr.judge("galat, paise nahi hote unke paas", HYPOTHESIS, put_to_owner=True) == "against"
    said = "no, parents never forget the due date, nobody reminds them is not the reason"
    assert hr.judge(said, HYPOTHESIS, put_to_owner=False) == "against"


def test_an_unanswered_hypothesis_question_is_ignored() -> None:
    assert hr.judge("ok", HYPOTHESIS, put_to_owner=True) == "ignored"
    assert hr.judge("pata nahi", HYPOTHESIS, put_to_owner=True) == "ignored"
    assert hr.judge("solution do", HYPOTHESIS, put_to_owner=True) == "ignored"
    assert hr.judge("kitna kharcha aayega?", HYPOTHESIS, put_to_owner=True) == "ignored"


def test_a_reply_about_something_else_leaves_a_hypothesis_that_was_not_asked_alone() -> None:
    assert hr.judge("ok", HYPOTHESIS, put_to_owner=False) == "none"
    assert hr.judge("teachers bhi chhod jate hain", HYPOTHESIS, put_to_owner=False) == "none"


# --- landed into the thinking prompt -------------------------------------------------------------


def ctx(replies: list[tuple[str, str]], latest: str) -> dict:
    history: list[dict] = []
    for ai, owner in replies:
        history.append({"role": "ai", "text": ai, "move": "M4_hypothesis"})
        history.append({"role": "customer", "text": owner})
    history.append({"role": "ai", "text": PUT, "move": "M4_hypothesis"})
    return {"history": history, "latest_customer_message": latest, "thinking": True}


def test_the_last_move_lands_when_the_owner_answers_and_not_when_they_deflect() -> None:
    answered = think_prompt.recent_turns(ctx([], "haan bilkul, wo bhool jate hain"))
    assert answered[-1].landed is True
    ignored = think_prompt.recent_turns(ctx([], "ok"))
    assert ignored[-1].landed is False


def test_earlier_moves_get_the_next_owner_message_as_their_answer() -> None:
    context = ctx([(PUT, "hmm"), (PUT, "cash")], "ok")
    turns = think_prompt.recent_turns(context)
    assert [t.landed for t in turns] == [False, True, False]


def test_a_hypothesis_that_did_not_land_is_not_repeated_and_the_prompt_says_so() -> None:
    context = ctx([], "pata nahi")
    note = think_prompt.situation_note(context)
    assert "did not land" in note and "M4_hypothesis" in note
    choice = think_prompt.suggested(context)
    assert choice is not None and choice.move != moves.Move.M4  # a number or a fork instead
    landed = think_prompt.situation_note(ctx([], "haan wo bhool jate hain"))
    assert "did not land" not in landed
