"""A short answer to pi's "What kind of business is it?" names the trade even without "I run"."""

import pytest

from app.modules.pi import industry_packs as packs


@pytest.mark.parametrize(
    ("answer", "key"),
    [
        ("small city hotel", "hotels"),
        ("genset rental business", "generator_sales_rental_and_service"),
        ("joote ki dukaan hai", "footwear_retail"),
        ("ladies parlour", "salons_and_barbers"),
        ("i keep bees and sell honey", "beekeeping_and_honey"),
        ("regional carrier, mostly short routes", "airlines"),
    ],
)
def test_the_answer_to_the_trade_question_picks_the_pack(answer, key):
    assert packs.detect([], answers=[answer]).primary == key


def test_only_a_reply_right_after_the_question_counts():
    said = [
        (False, "hotel"),
        (True, "Thanks. What kind of business is it?"),
        (False, "genset rental business"),
        (True, "Noted. Anything else?"),
        (False, "ladies parlour"),
    ]
    assert packs.trade_answers(said) == ["genset rental business"]


def test_a_long_reply_is_a_story_not_an_answer():
    story = " ".join(["word"] * 40)
    assert packs.trade_answers([(True, "What type of business is it?"), (False, story)]) == []


@pytest.mark.parametrize(
    ("said", "key"),
    [
        ("we're an airline, a few aircraft on domestic routes", "airlines"),
        ("own a car repair shop with a few mechanics", "auto_workshops_and_service_centres"),
        ("i process milk and make dahi and ghee", "dairy_processing"),
    ],
)
def test_everyday_statements_of_the_trade(said, key):
    assert packs.detect([said]).primary == key


@pytest.mark.parametrize("said", ["we keep losing orders", "tender ka kaam hone wala hai"])
def test_loose_wording_is_not_a_statement(said):
    assert packs.detect([said]).industries == []
