"""G56 (platform spec v1.6, Live Audit 6): "bhai mujhay quote do abhi wohi pooch raha hoan" is an
explicit ask for the quote. A vocative before it and "that is what I am asking" after it do not
make it a story, a condition or reported speech; the vetoes still hold."""

import pytest

from app.modules.pi import decisions


@pytest.mark.parametrize(
    "said",
    [
        "bhai mujhay quote do abhi wohi pooch raha hoan",
        "bhai mujhay quote do",
        "Sir mujhe quote chahiye",
    ],
)
def test_the_owners_plain_quote_ask_starts_the_quote(said: str) -> None:
    assert decisions.asks_for_document(said)


@pytest.mark.parametrize(
    "said",
    [
        "sirf quote do jab ready ho",
        "bhai quote do jab ready ho",
        "bhai my customers say send me the quote",
        "bhai kitna kharcha hoga",
        "bhai quote kab milega?",
    ],
)
def test_vetoes_still_hold_after_a_vocative(said: str) -> None:
    assert not decisions.asks_for_document(said)
