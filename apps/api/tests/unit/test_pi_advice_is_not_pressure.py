# ruff: noqa: E501
"""An idea bullet is advice to the owner about the owner's own business: their discounts, offers,
tools, deadlines and a day or a week to do something. It is not pi pressing someone, offering a
discount, naming its own insides or promising a time. The same words in pi's own sentences, and
claims about Workzap, the document or the quote, are still refused (industry quick ideas: 96 of
2,104 pairs broke a hard rule before this)."""

import pytest

from app.modules.pi import constitution

H = [{"role": "ai", "text": "x"}]
OFFER = "Shall I get a solution document and a quote made for you? You can say no."


def hard(reply: str, *, ideas: bool = True) -> dict[str, str]:
    context = {
        "pi_mode": "brain",
        "flow": {"state": "S5_READINESS"},
        "reply_language": "en",
        "history": H,
        "solution_asked": ideas,
    }
    return {v.rule: v.message for v in constitution.lint(reply, context) if v.hard}


def ideas(first: str, second: str = "Review it with your team once.") -> str:
    return f"Here are two ideas you can try now:\n\n• {first}\n• {second}\n\n{OFFER}"


@pytest.mark.parametrize(
    "idea",
    [
        "Name who may give a discount, so there is one rule.",
        "Agree who approves discounts, so exceptions are controlled.",
        "Put current offers with start and end dates in one shared list.",
        "Send each customer a progress update on a set day this week, so none are left waiting.",
        "Note the machine counter at open and close for one week, because it shows the gap.",
        "List everything expiring in the next two months, so renewals are not missed.",
        "Reply to every enquiry the same day, even if only to say when the quote will come.",
        "Count a day's WhatsApp orders and how many were delivered, because it shows the leak.",
        "Make sure the night shift can search the stock list on a phone, so they don't wait for morning.",
        "Review the sales pipeline weekly, so stuck deals show.",
        "Sign tools out and back in by crew, so each has a holder.",
        "List every recurring tool and cloud cost once with its owner.",
        "Invite repeat customers to order direct on WhatsApp where your app terms allow.",
        "Raise returns before it is too late by moving near-expiry stock to the front.",
    ],
)
def test_an_idea_about_the_owners_own_business_breaks_no_hard_rule(idea):
    assert hard(ideas(idea)) == {}, idea


@pytest.mark.parametrize(
    ("reply", "rule"),
    [
        ("I can give you a 10% discount if you decide today.", "R-SELL-03"),
        ("Act now: this is a limited-time offer.", "R-SELL-03"),
        ("Don't wait, the price will go up.", "R-SELL-03"),
        ("Our learning pipeline will pick this up.", "R-VOICE-06"),
        ("Workzap will have it ready in 3 days.", "R-HONEST-01"),
        ("The quote will be with you next week.", "R-HONEST-01"),
    ],
)
def test_pi_pressing_or_promising_in_its_own_sentence_is_still_refused(reply, rule):
    assert rule in hard(reply, ideas=False), reply
    assert rule in hard(f"{reply}\n\n• Count the slips.\n• Review them once."), reply


def test_a_bullet_that_names_workzap_and_a_time_is_still_refused():
    assert "R-HONEST-01" in hard(ideas("Workzap will deliver the first version in two weeks."))


def test_without_ideas_the_same_bullet_words_are_judged_as_before():
    reply = "• Name who may give a discount, so there is one rule.\n\nWhat else is slow?"
    assert "R-SELL-03" in hard(reply, ideas=False)
