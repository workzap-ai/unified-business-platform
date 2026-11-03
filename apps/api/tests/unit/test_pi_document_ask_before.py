# ruff: noqa: E501
"""Live chat 2026-10-28 (wholesale owner): "Quote banane se pehle mujhe samjhayen ..." is a wish to
understand first. It was read as "make the quote" and pi sent the document and quote at once."""

import pytest

from app.modules.pi import decisions

NOT_A_REQUEST = [
    "Quote banane se pehle mujhe simple alfaaz mein samjhayen ke system kaam kaise karega, workers "
    "kya enter karenge, aur mujhe kaise pata chalega ke stock ya cash mein discrepancy kahan aa rahi hai.",
    "Quote banane se pehle batayen ke ye kaise kaam karega",
    "Before you make the quote, explain how it works",
    "Please explain the document first",
    "document bhejne ke baad kya hoga",
]
REQUESTS = [
    "solution document bhej do",
    "Haan, quote bana dein",
    "send me the quote",
    "Please send the solution document and quote",
    "mujhe document chahiye",
]


@pytest.mark.parametrize("said", NOT_A_REQUEST)
def test_a_wish_to_understand_first_is_not_a_document_request(said: str) -> None:
    assert not decisions.asks_for_document(said)


@pytest.mark.parametrize("said", REQUESTS)
def test_a_direct_request_still_is_one(said: str) -> None:
    assert decisions.asks_for_document(said)


def test_the_fixed_decision_lines_no_longer_open_with_thanks() -> None:
    for key in ("preparing", "approved", "payment_claimed"):
        for language in ("en", "roman_ur"):
            line = decisions.TEXT[key][language]
            assert not line.lstrip().lower().startswith(("thanks", "shukriya")), (key, language)
