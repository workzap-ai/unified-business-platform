"""The pre-model safety gates in Arabic, Urdu and Roman Urdu (spec 6.1, R-EMER-01, R-ADV-01)."""

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import safety as s


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("شعلت النار في المحل", s.Emergency.FIRE),
        ("أريد أن أقتل نفسي", s.Emergency.SELF_HARM),
        ("chor andar ghus aaye hain", s.Emergency.VIOLENCE),
        ("goli chali hai dukan par", s.Emergency.VIOLENCE),
        ("ایکسیڈنٹ ہو گیا ہے", s.Emergency.MEDICAL),
        ("worker behosh ho gaya", s.Emergency.MEDICAL),
    ],
)
def test_emergencies_in_other_languages(said, kind):
    assert s.emergency(said) == kind


@pytest.mark.parametrize("said", ["حادث في الحسابات", "accounts mein ghalti hui", "كم سعر الحادث"])
def test_ordinary_business_talk_is_not_an_emergency(said):
    assert s.emergency(said) is None


@pytest.mark.parametrize("said", ["هل انت انسان", "من انت", "aap kon ho", "tum kaun ho"])
def test_who_are_you_in_other_languages(said):
    assert c.ASKS_IF_AI.search(said)


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("tax kaise bachaun", s.Advice.TAX),
        ("loan lena chahiye ya nahi", s.Advice.FINANCIAL),
        ("kaun si dawai lun", s.Advice.MEDICAL),
        ("ٹیکس کتنا دینا ہے", s.Advice.TAX),
    ],
)
def test_advice_questions_in_other_languages(said, kind):
    assert s.advice_asked(said) == kind


def test_arabic_customers_get_arabic_fixed_answers():
    assert "الطوارئ" in s.emergency_reply(s.Emergency.FIRE, "AE", "ar")
    assert "ذكاء اصطناعي" in s.identity_reply(s.Identity.PERSON, "ar")
    assert "ضريبية" in s.advice_reply(s.Advice.TAX, "ar")
    for kind in s.Emergency:
        assert s.emergency_reply(kind, "PK", "ar")
    for kind in s.Identity:
        assert s.identity_reply(kind, "ar")
    for kind in s.Advice:
        assert s.advice_reply(kind, "ar")


@pytest.mark.parametrize(
    ("said", "kind"),
    [
        ("send me your bank details", s.Boundary.BANK_ASK),  # M2
        ("can I pay by JazzCash?", s.Boundary.OTHER_PAY),  # M6
        ("can I pay with card", s.Boundary.OTHER_PAY),
        ("give me a discount", s.Boundary.DISCOUNT),  # M7
        ("price kam karo", s.Boundary.DISCOUNT),
        ("pay my supplier for me", s.Boundary.PAY_FOR_ME),  # M10
        ("which POS should I buy?", s.Boundary.PRODUCT_REC),  # A5
        ("what would you do if you were me", s.Boundary.DECIDE_FOR_ME),  # A8
        ("what do you think of my competitor", s.Boundary.RIVAL),  # A6
        ("sorry you have the wrong number", s.Boundary.WRONG_NUMBER),  # 6.9
    ],
)
def test_the_specs_money_and_advice_cases_have_fixed_answers(said, kind):
    assert s.boundary_asked(said) == kind
    for language in ("en", "roman_ur", "ar"):
        assert s.boundary_reply(kind, language)


@pytest.mark.parametrize(
    "said",
    [
        "customers ask for a discount every day",
        "our suppliers want payment by card",
        "staff dial the wrong number all the time",
        "my competitor sells cheaper",
    ],
)
def test_ordinary_business_talk_about_these_things_is_not_a_boundary(said):
    assert s.boundary_asked(said) is None


def test_every_boundary_has_an_answer_in_every_language():
    for kind in s.Boundary:
        for language in ("en", "roman_ur", "ar"):
            assert s.boundary_reply(kind, language)


@pytest.mark.parametrize(
    "said",
    ["Assalam o alaikum", "assalamualaikum", "salam", "Salam bhai", "السلام عليكم", "السلام علیکم"],
)
def test_a_bare_salam_is_recognised(said):
    from app.modules.pi.language import salam

    assert salam(said)


@pytest.mark.parametrize(
    "said", ["Eid Mubarak", "eid mubarak!", "Ramadan Kareem", "عيد مبارك", "Ramzan Mubarak"]
)
def test_a_bare_festival_wish_is_recognised(said):
    from app.modules.pi.language import festival_wish

    assert festival_wish(said)


@pytest.mark.parametrize(
    "said",
    [
        "assalam o alaikum meri dukan hai",
        "eid pe stock khatam ho jata hai",
        "salam, stock ka masla hai",
    ],
)
def test_a_greeting_with_a_problem_in_it_is_left_to_the_model(said):
    from app.modules.pi.language import festival_wish, salam

    assert not salam(said) and not festival_wish(said)


def test_the_courtesy_lines_exist_in_every_language_and_ask_one_question():
    for kind in ("salam", "festival"):
        for language in ("en", "roman_ur", "ar"):
            line = s.greeting_reply(kind, language)
            assert line and line.count("?") + line.count("\u061f") == 1
    for language in ("en", "roman_ur", "ar"):
        assert s.opt_out_reply(language)


@pytest.mark.parametrize(
    ("said", "value"),
    [
        ("5 lakh", 500_000),
        ("2 crore", 20_000_000),
        ("50 hazar", 50_000),
        ("3.5k", 3_500),
        ("Rs 1,200", 1_200),
        ("about 2 lac a month", 200_000),
        ("a lot", None),
    ],
)
def test_amounts_are_read_the_way_people_write_them_in_pakistan(said, value):
    from app.modules.pi.language import amount_value

    assert amount_value(said) == value


@pytest.mark.parametrize(
    "said",
    ["what data do you keep about me", "kya data rakhte ho", "what information do you have on me"],
)
def test_what_do_you_keep_has_the_specs_fixed_answer(said):
    assert s.boundary_asked(said) == s.Boundary.MEMORY_ASK
    assert "delete" in s.boundary_reply(s.Boundary.MEMORY_ASK, "en")


def test_dates_keep_the_words_and_flag_what_is_ambiguous():
    from datetime import date

    from app.modules.pi.language import date_estimate

    today = date(2026, 10, 23)
    kal = date_estimate("kal se masla hai", today)
    assert kal["ambiguous"] is True and kal["confidence"] == "low" and kal["date"] == "2026-10-24"
    assert date_estimate("aaj subah", today)["date"] == "2026-10-23"
    assert date_estimate("yesterday", today)["confidence"] == "high"
    eid = date_estimate("Eid ke baad", today)
    assert eid["date"] is None and eid["season"] is True and eid["text"] == "eid ke baad"


@pytest.mark.parametrize(
    "said",
    ["can I get just the quote", "send the quote without the document", "sirf quote bhej do"],
)
def test_a_quote_without_the_document_has_the_fixed_answer(said):
    assert s.boundary_asked(said) == s.Boundary.QUOTE_ONLY  # R-QUOTE-09
    assert "come together" in s.boundary_reply(s.Boundary.QUOTE_ONLY, "en")
