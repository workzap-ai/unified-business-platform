"""Level 1: the owner taking a cause back, in every language, and what is not a withdrawal."""

import pytest

from app.modules.pi import problem_fields as pf


@pytest.mark.parametrize(
    "text",
    [
        "scratch that",
        "ignore what I said",
        "I was mistaken",
        "I take that back",
        "main ne ghalat kaha",
        "woh baat wapas leta hun",
        "\u0645\u06cc\u0631\u06cc \u0628\u0627\u062a \u063a\u0644\u0637 \u062a\u06be\u06cc",
        "\u0623\u0646\u0627 \u0623\u0633\u062d\u0628 \u0643\u0644\u0627\u0645\u064a",
        "\u092e\u0947\u0930\u0940 \u092c\u093e\u0924 \u0917\u0932\u0924 \u0925\u0940",
        "maine galat kaha, wo wajah nahi thi",
    ],
)
def test_these_are_withdrawals(text):
    assert pf.withdrawal_said(text)


@pytest.mark.parametrize(
    "text",
    [
        "my partner says that wasn't the cause",
        "if I take that back...",
        "even if that wasn't the cause...",
        "you said that wasn't the cause but it is",
        "I do not take that back",
        "was that the cause?",
        "our sales are down since March",
    ],
)
def test_these_are_not(text):
    assert not pf.withdrawal_said(text)
