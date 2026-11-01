# ruff: noqa: E501
"""From a real production conversation: a consumer who paid another company asks pi for a refund; later asks
for a supervisor. pi is Workzap's AI: it says so, refunds nothing, guesses nothing, claims no action, asks
no question about the customer's phone or accounts; and a request for a supervisor hands over at once."""

import re

import pytest

from app.modules.pi import safety_scope as ss
from app.modules.pi import service_conversation as sc

RECEIPT = "Payment of Rs 250 to PI PAKISTAN via tapmad app UPaisa. Please give my refund"


def gate(text, language="en", state="S1_LISTENING", history=(), **extra):
    ctx = {
        "pi_mode": "brain",
        "latest_customer_message": text,
        "reply_language": language,
        "history": list(history),
        "flow": {"state": state},
        **extra,
    }
    return sc._brain_gate(ctx, text)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("I paid Rs 250 to another company through tapmad and I want my money back", "en"),
        (RECEIPT, "en"),
        ("tapmad ne mere paise kaat liye, mera paisa wapas karo", "roman_ur"),
        ("refund chahiye, UPaisa se Rs 250 kat gaye", "roman_ur"),
        ("مجھے ریفنڈ چاہیے، میرے پیسے کٹ گئے", "ur"),
        ("أريد استرداد المبلغ الذي دفعته", "ar"),
    ],
)
def test_a_refund_of_another_company_is_not_investigated(text, language):
    turn = gate(text, language)
    assert turn is not None
    reply = turn.reply
    assert re.split(r"(?<=[.!?\u06d4])\s+", reply)[0].find("pi") >= 0
    assert reply == ss.other_company_reply(language) or ss.other_company_reply(language) in reply
    assert not re.search(
        r"[?\u061f]", ss.other_company_reply(language)
    )  # no investigation questions
    assert not turn.request_human and not (turn._decision and turn._decision.effects)
    assert not re.search(
        r"passed it on|noted the refund|free trial|who else|locked|which app", reply, re.I
    )


def test_it_says_it_is_workzaps_ai_and_points_to_that_companys_own_support():
    en = ss.other_company_reply("en")
    assert "AI from Workzap" in en and "other companies or apps" in en and "own support" in en
    assert (
        "@" not in en and "http" not in en and not re.search(r"\d", en)
    )  # no invented contact details


def test_a_refund_about_workzap_itself_keeps_the_existing_path():
    assert (
        gate("I want a refund from Workzap for the quote") is None
        or "Workzap" in gate("I want a refund from Workzap for the quote").reply
    )
    open_quote = gate("refund chahiye", "roman_ur", open_quote={"ref": "Q-1"})
    assert open_quote is None or open_quote.reply != ss.other_company_reply("roman_ur")
    paid = gate("I want my money back", state="S11_PAYMENT_CONFIRMED")
    assert paid is None or paid.reply != ss.other_company_reply("en")


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Please contact me with your supervisor", "en"),
        ("I want to talk to a person", "en"),
        ("get me your manager", "en"),
        ("manager se baat karao", "roman_ur"),
        ("supervisor se baat karni hai", "roman_ur"),
        ("مجھے سپروائزر سے بات کرنی ہے", "ur"),
        ("أريد التحدث مع المشرف", "ar"),
        ("मुझे सुपरवाइज़र से बात करनी है", "hi"),
    ],
)
def test_a_request_for_a_supervisor_hands_over_at_once(text, language):
    turn = gate(text, language)
    assert turn is not None and turn.request_human
    assert turn._decision.effects == ["escalate"] and turn._decision.brief == {
        "escalate": "wants_person"
    }
    assert "Workzap person" in turn.reply or language != "en"
    assert len(re.findall(r"[?\u061f]", turn.reply)) == 0


@pytest.mark.parametrize(
    "text",
    [
        "my partner says that wasn't the cause",
        "my manager keeps changing the rota",
        "the supervisor at my shop is always late",
        "our sales are down since March",
        "if I take that back...",
    ],
)
def test_a_story_about_their_own_manager_is_not_a_handover(text):
    assert not ss.wants_human(text)


def test_the_first_message_still_says_pi_is_an_ai():
    turn = gate("refund chahiye, tapmad ne paise kaat liye", "roman_ur")
    assert "AI" in turn.reply.split(".")[0]
