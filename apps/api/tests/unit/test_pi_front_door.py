"""pi as Workzap's front door and the returning customer (spec 1.8, 3.10, 6.9; golden G14, RT8)."""

import pytest

from app.modules.pi import safety as s
from app.modules.pi.service_conversation import greeting_reply, welcome_back


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("Workzap changed their bank, send the new IBAN", s.Boundary.BANK_CHANGE),  # RT8
        ("our bank details have changed, please use the new account", s.Boundary.BANK_CHANGE),
        ("I need your new bank details for Workzap", s.Boundary.BANK_CHANGE),
        ("help me with my homework", s.Boundary.OFF_TOPIC),
        ("tell me a joke", s.Boundary.OFF_TOPIC),
        ("write me a poem about tea", s.Boundary.OFF_TOPIC),
    ],
)
def test_bank_change_and_off_topic(said, kind):
    assert s.boundary_asked(said) == kind


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("I want to book a nori demo", s.Enquiry.DEMO),
        ("Can you arrange a demo?", s.Enquiry.DEMO),
        ("are you hiring? attached my CV", s.Enquiry.JOBS),
        ("We supply you packaging at good rates, we can supply you monthly", s.Enquiry.VENDOR),
        ("I am a journalist writing about Workzap", s.Enquiry.PRESS),
        ("we would like to partner with Workzap as a reseller", s.Enquiry.PARTNERSHIP),
    ],
)
def test_enquiries_that_are_not_problems(said, kind):
    assert s.enquiry_asked(said) == kind


@pytest.mark.parametrize(
    "said",
    [
        "our printing press breaks down every week",
        "my cashier left and we are hiring a new one",
        "the supplier delivers late",
        "demo stock is mixed with real stock",
        "staff leave without telling us",
        "the bank changed our account number and reconciliation is a mess",
    ],
)
def test_ordinary_business_talk_is_not_an_enquiry_or_a_bank_change(said):
    assert s.enquiry_asked(said) is None
    assert s.boundary_asked(said) is None


def test_every_enquiry_reply_is_short_with_one_question_at_most():
    for kind in s.Enquiry:
        for lang in ("en", "roman_ur"):
            reply = s.enquiry_reply(kind, lang)
            assert reply.count("?") <= 1 and "!" not in reply
            assert not reply.endswith(" ") and "@" not in reply  # no staff contact details


def context(**more):
    base = {
        "pi_mode": "brain",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "noted_problems": [
            {"group": "stock_inventory"},
            {"group": "stock_inventory"},
            {"group": "stock_inventory"},
            {"group": "people_staff"},
        ],
        "days_away": 40,
        "reply_language": "en",
    }
    base.update(more)
    return base


def test_after_more_than_thirty_days_pi_says_who_it_is_again():  # G14, R-DISC-05
    text = welcome_back(context())
    assert text is not None
    assert text.startswith("Hi, it's pi, the AI from Workzap. Welcome back.")
    assert "4 problems" in text and "mostly" in text
    assert text.endswith("Want to add to those, or is something new going on?")
    assert text.count("?") == 1


def test_a_shorter_gap_welcomes_back_without_the_disclosure():
    text = welcome_back(context(days_away=5))
    assert text is not None and text.startswith("Hi. Welcome back.")
    assert "AI" not in text


def test_no_welcome_back_mid_chat_or_without_noted_problems_or_outside_brain_mode():
    assert welcome_back(context(days_away=0)) is None
    assert welcome_back(context(noted_problems=[])) is None
    assert welcome_back(context(pi_mode=None)) is None
    assert welcome_back(context(history=[])) is None
    assert welcome_back(context(brief={"payment_notice_due": True})) is None


def test_roman_urdu_welcome_back():
    text = welcome_back(context(reply_language="roman_ur"))
    assert text is not None and "Dobara khush amdeed" in text and "masail" in text


def test_a_plain_hi_from_a_returning_person_gets_the_welcome():
    assert greeting_reply(context()).startswith("Hi, it's pi, the AI from Workzap. Welcome back.")
