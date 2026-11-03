# ruff: noqa: E501
"""Fixes from the car-showroom chat of 2026-10-27: ideas that assumed videos and a page the owner never
had, a typo in the ask, and new ideas given in answer to a question about an earlier idea."""

import pytest

from app.modules.pi import constitution, idea_filter, solution_ask, solution_free

OWNER = (
    "I own a car showroom, but customers don't come in. It has been a year since I opened the "
    "showroom, and so far I have only managed to sell two cars. customer nh arahi showroom mai "
    "Ghulshan mai"
)


@pytest.mark.parametrize(
    "idea",
    [
        "Put the price and contact in the first line of each video caption, so viewers can reach you.",
        "Pin a short video on your page that shows how to buy a car, so new people understand.",
        "Run a small ad for the showroom, so people nearby see it.",
        "Post the new arrivals on Instagram, so people see them.",
    ],
)
def test_an_idea_that_assumes_a_channel_the_owner_never_named_is_dropped(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER) == "G2"
    assert solution_free.vetted([idea], OWNER, [], None) == []


@pytest.mark.parametrize(
    "idea",
    [
        "Ask each of your last two buyers how they first heard of the showroom, so you see which way people find you.",
        "Ask your manager to note how each enquirer heard of the showroom, so you see which source brings visits.",
        "Look at the showroom the way a stranger does when they search for it nearby, so you see what puts them off.",
    ],
)
def test_an_idea_that_asks_looks_or_counts_passes(idea: str) -> None:
    assert idea_filter.invented_context(idea, OWNER) is None


def test_a_channel_the_owner_named_may_be_used() -> None:
    owner = OWNER + " I post reels on instagram"
    assert (
        idea_filter.invented_context(
            "Put the rate in each reel caption, so viewers can act.", owner
        )
        is None
    )
    assert (
        idea_filter.invented_context(
            "Post the new arrivals on Instagram, so people see them.", owner
        )
        is None
    )


@pytest.mark.parametrize("said", ["soluton dw", "solutin do", "solushan dein", "Solution do"])
def test_a_typed_ask_for_a_solution_is_understood(said: str) -> None:
    assert solution_ask.asked_for_ideas(said)


@pytest.mark.parametrize(
    "said", ["this is a solid plan", "hello there", "customer nh arahi showroom mai"]
)
def test_ordinary_words_are_not_mistaken_for_the_ask(said: str) -> None:
    assert solution_ask.fix_typos(said) == said
    assert not solution_ask.asked_for_ideas(said)


BRAIN = {
    "pi_mode": "brain",
    "flow": {"state": "S2_CLARIFYING"},
    "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
}
TWO_IDEAS = "Ye do ideas hain:\n• Pehli baat yahan.\n• Doosri baat yahan."


def test_a_question_about_an_earlier_idea_is_not_answered_with_new_ideas() -> None:
    context = {**BRAIN, "ideas_given": 2, "latest_customer_message": "but page khn pr banana hain?"}
    assert "R-VAL-07" in {v.rule for v in constitution.lint(TWO_IDEAS, context)}


def test_new_ideas_are_fine_when_they_were_asked_for_or_none_were_given_yet() -> None:
    asked = {
        **BRAIN,
        "ideas_given": 2,
        "solution_asked": True,
        "latest_customer_message": "aur idea",
    }
    assert "R-VAL-07" not in {v.rule for v in constitution.lint(TWO_IDEAS, asked)}
    first = {**BRAIN, "ideas_given": 0, "latest_customer_message": "ap kya kr skty hain"}
    assert "R-VAL-07" not in {v.rule for v in constitution.lint(TWO_IDEAS, first)}
