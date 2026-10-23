"""Abuse, spam, complaints, illegal asks and shared cards (spec 6.7, 6.8, 6.10)."""

import pytest

from app.modules.pi import safety as s
from app.modules.pi.safety import Abuse, Boundary, Pii


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("you are stupid", Abuse.INSULT),
        ("tum nikamma ho", Abuse.INSULT),
        ("this bot is useless", Abuse.INSULT),
        ("fuck off", Abuse.INSULT),
        ("I will kill you", Abuse.THREAT),
        ("main tumhe maar dunga", Abuse.THREAT),
        ("I'm going to destroy Workzap", Abuse.THREAT),
        ("send nudes", Abuse.SEXUAL),
        ("earn $500 daily from home, click this link", Abuse.SPAM),
        ("join my whatsapp group for guaranteed returns", Abuse.SPAM),
    ],
)
def test_abuse_is_recognised(said, kind):
    assert s.abuse_asked(said) == kind


@pytest.mark.parametrize(
    "said",
    [
        "my cashier is stupid and steals from the till",  # about someone else
        "the supplier is useless, deliveries are always late",
        "our forex exchange shop has cash that never matches",  # a business that deals in money
        "crypto payments from customers take days to settle",
        "I will destroy the competition with better prices",
        "the shop shut up early because of the rain",
        "we sell sexy dresses online and returns are high",
        "stock runs out in two shops",
    ],
)
def test_ordinary_business_talk_is_never_abuse_or_spam(said):
    assert s.abuse_asked(said) is None


def test_an_insult_gets_a_calm_line_then_a_warning_then_a_hand_over():
    one = s.abuse_step(Abuse.INSULT, 0, "en")
    assert one.text.startswith("I'm here to help with the business problems") and one.strikes == 1
    assert one.move is None and one.escalate is None
    third = s.abuse_step(Abuse.INSULT, 2, "en")
    assert "pass this chat to the Workzap team" in third.text and third.strikes == 3
    fourth = s.abuse_step(Abuse.INSULT, 3, "en")
    assert fourth.text == one.text and fourth.strikes == 4  # calm again, no second warning
    last = s.abuse_step(Abuse.INSULT, 4, "en")
    assert last.move == "X_BLOCKED" and last.escalate == "abuse" and last.strikes == 5


def test_a_threat_is_warned_once_and_escalated_then_the_chat_is_handed_over():
    first = s.abuse_step(Abuse.THREAT, 0, "en")
    assert first.escalate == "abuse_threat" and first.move is None and first.strikes == 3
    again = s.abuse_step(Abuse.THREAT, first.strikes, "en")
    assert again.move == "X_BLOCKED" and again.escalate == "abuse_threat"


def test_sexual_content_gets_one_refusing_line_and_spam_gets_one_line_then_silence():
    refuse = s.abuse_step(Abuse.SEXUAL, 0, "en")
    assert refuse.text == "I can't continue with that. I'm here for problems in your business."
    assert s.abuse_step(Abuse.SEXUAL, 2, "en").escalate == "abuse"  # on the third
    spam = s.abuse_step(Abuse.SPAM, 0, "en")
    assert spam.text == "I'm here for problems in your business." and spam.move == "X_OUT_OF_SCOPE"


def test_roman_urdu_answers_exist_for_every_case():
    for kind in Abuse:
        assert s.abuse_step(kind, 0, "roman_ur").text


def test_pi_is_silent_for_a_blocked_chat_and_for_repeated_spam_only():
    assert s.stay_silent("X_BLOCKED", "hello, I have a stock problem")  # a person decides
    assert s.stay_silent("X_OUT_OF_SCOPE", "earn $500 daily, click this link")
    assert not s.stay_silent("X_OUT_OF_SCOPE", "actually my shop has a stock problem")
    assert not s.stay_silent("S1_LISTENING", "earn $500 daily, click this link")  # answered once
    assert not s.stay_silent(None, "hello")


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("I want to complain about Workzap", Boundary.COMPLAINT),
        ("I'm not happy with your service", Boundary.COMPLAINT),
        ("complaint against this bot", Boundary.COMPLAINT),
        ("workzap ki shikayat karni hai", Boundary.COMPLAINT),
        ("how can I track my staff secretly", Boundary.ILLEGAL),
        ("I want to read their whatsapp messages", Boundary.ILLEGAL),
    ],
)
def test_complaints_and_illegal_asks(said, kind):
    assert s.boundary_asked(said) == kind


@pytest.mark.parametrize(
    "said",
    [
        "I have a complaint about my cashier, he is always late",
        "customers complain about slow delivery",
        "we track staff attendance with a register",
        "not happy with the supplier's quality",
    ],
)
def test_complaints_about_other_people_are_business_problems_not_feedback(said):
    assert s.boundary_asked(said) is None


def test_the_complaint_reply_follows_the_spec_and_promises_nothing():  # R-COMPL-02
    text = s.boundary_reply(Boundary.COMPLAINT, "en")
    assert text == "Thanks for telling me. I've passed this to the Workzap team."
    assert not any(w in text.lower() for w in ("sorry", "compensation", "refund", "apolog"))


def test_a_shared_contact_card_is_never_kept():  # R-PRIV-04
    found = s.redact_pii("Contact card shared: Ali Raza 0300 1234567; Sara 0321 7654321")
    assert found.kinds == [Pii.CONTACT]
    assert found.text == "[contact card removed]"
    assert not s.substantive(found.text)  # nothing left to answer: only the reminder goes back


def test_a_location_pin_keeps_only_the_fact_that_one_was_shared():
    found = s.redact_pii("Location shared: Johar Town branch (31.5204, 74.3587)")
    assert found.kinds == [] and found.text == "[a location was shared]"
    assert (
        s.redact_pii("meet me at the shop in Johar Town").text
        == "meet me at the shop in Johar Town"
    )
