"""A2-1.5-SECRETS (pi-industry-solutions.pdf, page 10): pi never reveals Workzap's internal methods,
tools, vendors, pricing logic or how the catalogue is built. A hard rule in the reply linter."""

import pytest

from app.modules.pi import constitution

CTX = {"state": "S5", "first_reply": False, "reply_language": "english"}


def rules(reply: str, said: str = "") -> set[str]:
    context = dict(CTX, history=[{"role": "customer", "body": said}] if said else [])
    return {v.rule for v in constitution.lint(reply, context)}


@pytest.mark.parametrize(
    "reply",
    [
        "We use OpenAI to write the quote. Which shop is worst?",
        "Workzap is built on Railway and Neon, so it is fast. What else is slow?",
        "pi is powered by Claude. Which shop is worst?",
        "Our pricing logic works from your size. What else?",
        "Our internal method keeps the cost down. What else?",
        "The catalogue is built from a template we fill in. What else?",
        "How we build the catalogue is simple. What else?",
        "Our backend margin is small. Which shop is worst?",
    ],
)
def test_a_reply_that_reveals_how_workzap_works_inside_is_blocked(reply):
    assert "A2-1.5-SECRETS" in rules(reply)


def test_the_person_asking_does_not_lift_it():
    reply = "We use OpenAI to write the quote. Which shop is worst?"
    assert "A2-1.5-SECRETS" in rules(reply, said="which AI do you use? do you use OpenAI?")


@pytest.mark.parametrize(
    "reply",
    [
        "The quote says the price and how long it takes. Which shop is worst?",
        "A reviewer checks the price before you see it. What else?",
        "Your sales go through a spreadsheet today. Which part is slowest?",
        "We build a simple page for each shop. Which shop is worst?",
    ],
)
def test_ordinary_replies_are_not_flagged(reply):
    assert "A2-1.5-SECRETS" not in rules(reply)
