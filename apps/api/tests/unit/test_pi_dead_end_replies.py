"""No dead-end replies (owner rule, memory pi-journey-never-blocked): in brain mode a reply never
ends without a next step. Each test reproduces one path that used to send a statement alone:
the rejected-draft acknowledgement, the "document|quote" exemption of the progress rule, a progress
rule with no next-slot question left, and a pi-written problem label ("P2") that the digit check
mistook for a price and so rejected the map-edit question (fixed by letting exactly those lines
through, never by loosening the price guard)."""

import pytest

from app.modules.pi import constitution, flow, map_edit, runtime
from app.modules.pi.language import (
    BRAIN_ACK_NOTICES,
    TEAM_CHECK_NOTICES,
    TECH_DOWN_NOTICES,
    TOOL_FAIL_NOTICES,
    notice_in,
)
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


BANNED = ("quote", "document", "price", "pay", "offer", "box", "rs ", "solution")


def pool(language, group):
    return constitution.ACK_QUESTIONS[language][group]


def test_every_safe_question_is_clean_and_every_group_has_variants():
    assert set(constitution.ACK_QUESTIONS) == set(LANGUAGES)
    for language, groups in constitution.ACK_QUESTIONS.items():
        for group, questions in groups.items():
            assert len(set(questions)) >= 2, (language, group)
            for question in questions:
                assert question.endswith(QUESTION_MARKS) and marks(question) == 1
                assert not any(ch.isdigit() for ch in question)
                assert not any(word in question.lower() for word in BANNED), question


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_listening_chat_gets_the_listening_question_and_other_states_the_other_group(language):
    ack = notice_in(BRAIN_ACK_NOTICES, language)
    listening = constitution.ack_with_question(ack, context("S1_LISTENING", language), language)
    other = constitution.ack_with_question(ack, context("S5_READINESS", language), language)
    assert listening == f"{ack} {pool(language, 'listening')[0]}"
    assert other == f"{ack} {pool(language, 'other')[0]}"


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("state", ["S1_LISTENING", "S6_PREPARING"])
def test_a_question_asked_before_is_never_asked_again(language, state):
    ack = notice_in(BRAIN_ACK_NOTICES, language)
    replies = []
    seen = set()
    total = len(pool(language, "listening")) + len(pool(language, "other"))
    for _ in range(total):
        text = constitution.ack_with_question(
            ack, context(state, language, replies=replies), language
        )
        question = text[len(ack) :].strip()
        assert question not in seen, (language, state, question)
        assert text.rstrip().endswith(QUESTION_MARKS) and marks(text) == 1
        seen.add(question)
        replies.append(text)
    assert len(seen) == total
    # everything asked once: still one question, last, and the one asked longest ago
    again = constitution.ack_with_question(ack, context(state, language, replies=replies), language)
    assert marks(again) == 1 and again.rstrip().endswith(QUESTION_MARKS)
    assert again[len(ack) :].strip() == replies[0][len(ack) :].strip()


def test_the_language_of_the_chat_is_used_when_none_is_given():
    text = constitution.ack_with_question("Shukriya.", context(language="roman_ur"), None)
    assert text == f"Shukriya. {pool('roman_ur', 'listening')[0]}"


BRAIN = {"pi_mode": "brain", "flow": {"state": "S1_LISTENING"}, "history": []}


@pytest.mark.parametrize("reason", ["low_confidence", "reply_rejected"])
def test_in_brain_mode_a_rejected_or_unsure_draft_gets_the_ack_and_a_question(reason):
    text = runtime.soft_notice(reason, BRAIN, "hello there", "en")
    assert text == f"{BRAIN_ACK_NOTICES['en']} {pool('en', 'listening')[0]}"


def test_in_brain_mode_a_failure_keeps_its_own_notice_untouched():
    assert (
        runtime.soft_notice("provider_failure", BRAIN, "hello there", "en")
        == (TECH_DOWN_NOTICES["en"])
    )
    assert (
        runtime.soft_notice("tool_failure", BRAIN, "hello there", "en") == TOOL_FAIL_NOTICES["en"]
    )


@pytest.mark.parametrize("mode", [None, "", "legacy"])
@pytest.mark.parametrize("reason", ["low_confidence", "reply_rejected", "provider_failure"])
def test_outside_brain_mode_the_old_team_check_notice_is_untouched(mode, reason):
    context_ = {"pi_mode": mode, "flow": {"state": "S1_LISTENING"}}
    assert runtime.soft_notice(reason, context_, "hello there", "en") == TEAM_CHECK_NOTICES["en"]
    assert runtime.soft_notice(reason, None, "hello there", "en") == TEAM_CHECK_NOTICES["en"]


@pytest.mark.parametrize("mode", ["quote", "hidden", "ask_team"])
def test_the_map_edit_label_lines_pass_when_they_are_the_exempt_lines(mode):
    assert map_edit.LABEL_LINES
    for language in ("en", "roman_ur", "ar", "fr", "fa", "es"):
        for key in ("which_problem", "which_link"):
            line = map_edit.LINES[key][language]
            assert validate_service_reply(line, 4000, mode, list(map_edit.LABEL_LINES)) == line


PROBES = [
    "It would cost P2000.",
    "It is Rs 500.",
    "Which problem, P2 at 500 rupees?",
    "P2k",
    "P5k",
    "P2K",
    "P12k",
    "P99k",
    "P2m",
    "P2L",
    "P50",
    "P99",
    "P0",
    "P2%",
    "P2x",
    "Rs P2",
    "PKR P2",
    "Rs. P12",
    "P٢k",
    "P2 five hundred",
    "P2 grand",
    "P2 per month",
    "P2 پانچ سو",
]


@pytest.mark.parametrize("mode", ["quote", "hidden", "ask_team"])
@pytest.mark.parametrize("probe", PROBES)
def test_price_figures_next_to_a_label_stay_blocked(mode, probe):
    with pytest.raises(ReplyRejected):
        validate_service_reply(probe, 4000, mode, list(map_edit.LABEL_LINES))


def test_a_label_line_with_a_price_added_is_still_blocked():
    line = map_edit.LINES["which_problem"]["en"]
    for extra in (" It costs P2k.", " Rs 500."):
        with pytest.raises(ReplyRejected):
            validate_service_reply(line + extra, 4000, "quote", list(map_edit.LABEL_LINES))
