"""Ideas read as plain sentences (no dots), other scripts keep their own language, and short
Roman Urdu asks and dislikes are understood."""

import pytest

from app.modules.pi import solution_ask, solution_score
from app.modules.pi.language import in_script, other_script
from app.modules.pi.solution_rules import count_ideas, idea_lines

CHINESE = "Chinese (Simplified)"


def test_idea_lines_are_prose_not_bullets() -> None:
    text = idea_lines(
        [
            "Count the till together at shift change, so a gap is placed.",
            "Log each order in one book, so none is missed.",
        ]
    )
    assert text.splitlines()[0].startswith("First, count the till")
    assert text.splitlines()[1].startswith("Second, log each order")
    assert "•" not in text
    assert count_ideas(text) == 2


def test_one_idea_is_one_sentence() -> None:
    assert (
        idea_lines(["Write the order down, so it is not missed"])
        == "Write the order down, so it is not missed."
    )


@pytest.mark.parametrize(
    "text",
    [
        "你好，我经营一家小型制造工厂。我们每天生产几百件产品。",
        "我们有三个仓库和五十名员工。我还希望系统能够预测需求",
    ],
)
def test_chinese_is_its_own_language(text: str) -> None:
    assert other_script(text) == CHINESE
    assert in_script(text, CHINESE)


def test_latin_and_arabic_are_not_other_scripts() -> None:
    assert other_script("Hello, I own a shop") is None
    assert other_script("مرحبا، لدي شركة توصيل طلبات") is None
    assert not in_script("I have noted the three points", CHINESE)


@pytest.mark.parametrize(
    "text",
    [
        "Idea psnd NH aiya mujhe",
        "idea pasand nahi aya",
        "ye idea acha nahi hai",
        "I don't like these ideas",
    ],
)
def test_disliked_ideas_ask_for_a_different_kind(text: str) -> None:
    reaction = solution_score.classify(text)
    assert reaction is not None and reaction.signal == "idea_generic"


@pytest.mark.parametrize(
    "text", ["Aur idea dw", "aur idea chahiye", "or idea do", "idea dena", "mazeed suggestions"]
)
def test_more_ideas_in_roman_urdu_is_an_ask(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)
