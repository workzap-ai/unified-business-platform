"""No dead-end replies (owner rule, memory pi-journey-never-blocked): in brain mode a reply never
ends without a next step. Each test reproduces one path that used to send a statement alone:
the rejected-draft acknowledgement, the "document|quote" exemption of the progress rule, a progress
rule with no next-slot question left, and a pi-written problem label ("P2") that the digit check
mistook for a price and so rejected the map-edit question."""

import pytest

from app.modules.pi import constitution, flow
from app.modules.pi.language import BRAIN_ACK_NOTICES, notice_in
from app.modules.pi.service_conversation import ReplyRejected, validate_service_reply

QUESTION_MARKS = ("?", "؟")
LANGUAGES = ["en", "roman_ur", "ur", "ar", "fr", "es", "fa"]


def context(state="S2_CLARIFYING", language="en", said="the cashiers are always late", replies=()):
    history = [
        {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What does your business do?"}
    ]
    for reply in replies:
        history += [{"role": "customer", "text": "x"}, {"role": "ai", "text": reply}]
    return {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": language,
        "history": history,
        "latest_customer_message": said,
        "noted_problems": [{"missing": ["where", "impact", "since"]}],
    }


def marks(text):
    return sum(text.count(m) for m in QUESTION_MARKS)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_rejected_draft_acknowledgement_carries_the_next_question(language):
    ack = notice_in(BRAIN_ACK_NOTICES, language)
    text = constitution.ack_with_question(ack, context(language=language), language)
    assert text.startswith(ack)
    assert text.rstrip().endswith(QUESTION_MARKS), text
    assert marks(text) == 1, text  # one question, and it is the last sentence


@pytest.mark.parametrize("state", ["S1_LISTENING", "S5_READINESS", "S5B_DECLINED", "S6_PREPARING"])
def test_the_acknowledgement_asks_in_every_state_and_never_offers_or_prices(state):
    ack = BRAIN_ACK_NOTICES["en"]
    text = constitution.ack_with_question(ack, context(state=state), "en")
    assert text.rstrip().endswith("?") and marks(text) == 1
    lowered = text.lower()
    assert not any(word in lowered for word in ("quote", "document", "price", "pay", "rs "))


def test_the_acknowledgement_does_not_repeat_a_question_already_asked():
    first = constitution.FALLBACK_LISTENING["en"]
    text = constitution.ack_with_question(BRAIN_ACK_NOTICES["en"], context(replies=[first]), "en")
    assert first not in text and text.rstrip().endswith("?")


def test_an_acknowledgement_that_already_asks_is_left_alone():
    asked = "Thanks. Which shop first?"
    assert constitution.ack_with_question(asked, context(), "en") == asked


def test_the_document_or_quote_word_is_not_a_way_out_of_the_next_question():
    # Nothing is offered here (S2, listening): a statement about a document is still a dead end.
    reply = "Noted, the cashiers are late. A document comes later."
    out = constitution._ensure_next_step(reply, context())
    assert out != reply and out.rstrip().endswith("?") and marks(out) == 1
    assert out.startswith(reply)


def test_a_reply_that_already_asks_about_a_document_is_unchanged():
    reply = "Noted. Would you like a document for these later?"
    assert constitution._ensure_next_step(reply, context()) == reply


def test_a_chat_with_no_next_slot_question_still_gets_a_question():
    # Arabic has no slot seeds (_next_question is empty): the safe listening question is used.
    reply = "تمام، سجلت ذلك."
    ctx = context(language="ar")
    assert constitution._next_question(ctx, reply) == ""
    out = constitution._ensure_next_step(reply, ctx)
    assert out.startswith(reply) and out.rstrip().endswith(QUESTION_MARKS) and marks(out) == 1


def test_the_states_that_own_their_question_are_untouched():
    offer = "Shall I write all of this into one Solution Box and have Workzap prepare a quote?"
    at_the_offer = context(state="S5_READINESS")
    assert flow.parse("S5_READINESS") not in constitution.PROGRESS_STATES
    assert constitution._ensure_next_step(offer, at_the_offer) == offer


@pytest.mark.parametrize("mode", ["hidden", "quote", "ask_team", "starting", "exact"])
def test_a_problem_label_in_a_pi_written_question_is_not_a_price(mode):
    reply = "I want to change the right one. Which problem do you mean, for example P2?"
    assert validate_service_reply(reply, 4000, mode, []) == reply


@pytest.mark.parametrize(
    "reply", ["It would cost P2000.", "It is Rs 500.", "Which problem, P2 at 500 rupees?"]
)
def test_a_real_figure_next_to_a_label_is_still_blocked(reply):
    with pytest.raises(ReplyRejected):
        validate_service_reply(reply, 4000, "quote", [])
