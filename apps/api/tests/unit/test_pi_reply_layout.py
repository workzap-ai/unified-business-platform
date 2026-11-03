# ruff: noqa: E501
"""Reply layout for expert workspaces: same words, set out for a phone."""

import pytest

from app.modules.pi.reply_layout import tidy

BULLET = "•"


def test_the_question_that_ends_a_paragraph_stands_alone() -> None:
    reply = "Fee late hone ka masla note kar liya hai. Jin parents ki fee late hoti hai, wo kya wajah batate hain?"
    assert tidy(reply) == (
        "Fee late hone ka masla note kar liya hai.\n\n"
        "Jin parents ki fee late hoti hai, wo kya wajah batate hain?"
    )


def test_a_list_is_set_apart_from_the_text_around_it() -> None:
    reply = f"Ji, ye do ideas abhi aazma sakte hain:\n{BULLET} Pehla idea.\n{BULLET} Doosra idea.\nKya main document banwa doon?"
    assert tidy(reply) == (
        f"Ji, ye do ideas abhi aazma sakte hain:\n\n{BULLET} Pehla idea.\n{BULLET} Doosra idea.\n\n"
        "Kya main document banwa doon?"
    )


def test_dash_bullets_become_bullets_and_headings_go() -> None:
    assert tidy("# Plan\n- ek\n- do") == f"Plan\n\n{BULLET} ek\n{BULLET} do"


@pytest.mark.parametrize(
    "reply",
    [
        "Hi, I'm pi, an AI from Workzap. Tell me what's going wrong in your business and I'll start on it.",
        "Aap ka koi bhi sawal?",
        "Ek jumla. Doosra jumla.",
    ],
)
def test_short_or_questionless_text_is_left_as_it_is(reply: str) -> None:
    assert tidy(reply) == reply


def test_the_words_never_change_and_running_it_twice_is_safe() -> None:
    reply = "Samajh gaya.\n- ek\n- do\nAap ka kya khayal hai, aur kab se hai ye masla?"
    once = tidy(reply)
    assert tidy(once) == once
    assert [w for w in once.split() if w != BULLET] == [
        w for w in reply.replace("- ", "").split() if w
    ]
