"""The price policy must not mistake counts or money words for an amount (golden G2, G6)."""

import pytest

from app.modules.pi import price_policy as p


@pytest.mark.parametrize(
    "text",
    [
        "Thanks. I've noted three things:\n• Stock running out\n• Cash not matching at one branch\n"
        "Which of these costs you the most?",
        "Two shops run out of stock. How much does that cost you each week?",
        "Shukriya. Note kar liya: udhaar ke paise wapas nahi aate, hisaab register mein.",
        "Is the money coming in late from credit customers?",
    ],
)
def test_counts_and_money_words_without_a_number_are_not_an_amount(text):
    assert p.disclosures(text) == []
    assert p.check(text, "hidden") is None


@pytest.mark.parametrize(
    "text",
    [
        "It costs three thousand",
        "The price is two lakh",
        "That would be 5000 rupees",
        "It is only $50 a month",
        "paise 500 lagenge",
        "about five rupees",
        "total 1 lakh",
    ],
)
def test_real_amounts_are_still_blocked(text):
    assert p.disclosures(text)
    assert p.check(text, "hidden") == "PRICE_POLICY_BLOCKED"
