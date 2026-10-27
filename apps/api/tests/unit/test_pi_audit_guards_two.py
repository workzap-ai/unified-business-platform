# ruff: noqa: E501
"""Guards added after the rule-auditor pass over the staff view and the expert steering work."""

import pytest

from app.modules.pi import expert_advisor as ea
from app.modules.pi import hypothesis_reply, solution_ask


@pytest.mark.parametrize(
    "said",
    [
        "We provide solutions to banks and our clients need solutions every month",
        "customers have other options nearby so they leave",
        "kuch bhi kar lete hain magar fee late aati hai",
        "marizon ko ilaj chahiye aur hum clinic chalate hain",
        "billing ke liye solution use karte hain hum",
        "customers don't know how to start using it",
    ],
)
def test_a_sentence_that_only_describes_the_business_is_not_an_ask(said: str) -> None:
    assert not solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize(
    "said", ["solution do", "kuch karo", "ap kya kr skty hain", "what can you do?"]
)
def test_real_asks_still_count(said: str) -> None:
    assert solution_ask.asked_for_ideas(said)


def test_a_long_chinese_story_is_not_an_ask() -> None:
    assert not solution_ask.asked_for_ideas("我们的问题还没解决" * 6)


@pytest.mark.parametrize(
    "reply",
    ["sahi nahi hai", "Right now customers leave after the quote", "yes and no", "haan lekin nahi"],
)
def test_these_are_not_a_yes_to_the_hypothesis(reply: str) -> None:
    assert (
        hypothesis_reply.judge(reply, "customers leave after the quote", put_to_owner=True)
        != "confirm"
    )


def test_a_plain_yes_still_confirms() -> None:
    assert (
        hypothesis_reply.judge("haan bilkul", "customers leave after the quote", put_to_owner=True)
        == "confirm"
    )


def test_customers_come_later_is_an_answer_not_a_deflection() -> None:
    verdict = hypothesis_reply.judge(
        "customers come later in the evening and leave after the quote",
        "customers leave after the quote",
        put_to_owner=True,
    )
    assert verdict != "ignored"


@pytest.mark.parametrize(
    "question",
    [
        "What is your CNIC number?",
        "What is the name of the supplier?",
        "Can you share your bank account number?",
        "What is your WhatsApp number?",
    ],
)
def test_the_expert_question_never_asks_for_identity_contact_or_names(question: str) -> None:
    assert not ea.question_ok(question)


def test_a_cause_question_is_fine() -> None:
    assert ea.question_ok("What reason do late parents usually give?")


def test_the_cached_diagnosis_is_redacted_before_it_is_stored() -> None:
    advice = ea.Advice(
        question="Did the call to 0300 1234567 help?",
        causes=["owner a@b.com says price", "plain cause"],
        problem="Late fees, card 4111 1111 1111 1111",
    )
    stored = ea.remember({}, {"title": "fees", "ref": "P1"}, advice)["expert_diag"]
    text = str(stored)
    assert "a@b.com" not in text and "4111" not in text and "1234567" not in text


def test_a_channel_the_owner_never_named_is_dropped_even_without_the_judge() -> None:
    ordered = [
        ea.Candidate(
            idea="Pin a short video on your page, so new people understand what you offer."
        ),
        ea.Candidate(
            idea="Ask each recent buyer how they first heard of the shop, so you see how people find you."
        ),
    ]
    kept = ea.vet(
        ordered,
        owner_words="I own a car showroom and customers do not come in",
        never_say=[],
        facts=set(),
        ctx=None,
        want=2,
    )
    assert len(kept) == 1 and kept[0].startswith("Ask each recent buyer")
