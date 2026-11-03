"""Live test 7: "solution glt hai again den" (the ideas were wrong, give again) is a rejection that
asks for different ideas, never silence and never "those are all the ideas I have"."""

import pytest

from app.modules.pi import solution_ask, solution_score
from app.modules.pi.service_conversation import ideas_opener, roman_ideas_opener


@pytest.mark.parametrize(
    "said",
    [
        "solution glt hai again den",
        "ye nahi, wrong",
        "not what I asked",
        "kaam ka nahi",
        "yeh solution galat hai",
        "again den",
    ],
)
def test_a_rejection_is_recognised_and_asks_for_different_ideas(said: str) -> None:
    assert solution_ask.rejects_ideas(said), said
    assert solution_score.classify(said).signal == "idea_generic"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "said", ["ye nahi ho sakta", "aur ideas dein", "theek hai", "solution dein ap"]
)
def test_other_messages_are_not_rejections(said: str) -> None:
    assert not solution_ask.rejects_ideas(said), said


def test_the_opener_after_a_rejection_acknowledges_once_in_one_clause() -> None:
    context = {
        "solution_rejected_fit": True,
        "solution_ideas": ["a"],
        "latest_customer_message": "solution glt hai again den",
    }
    assert ideas_opener(context).startswith("Sorry, those did not fit your problem.")
    roman = roman_ideas_opener("Sorry.\n• Ek.\n• Do.", {**context, "solution_asked": True})
    assert (
        roman.splitlines()[0]
        == "Maazrat, wo aap ke masle se mel nahi khate. Ye do naye ideas hain:"
    )
