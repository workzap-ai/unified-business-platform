"""L2-3: "without a fee" as the owner's limit is not a price claim, "it is free" is, and a phrase
that could be either is flagged MONEY_AMBIGUOUS (fail closed), never passed."""

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import blueprint_text as bt

P = {"P1", "P2"}


def option(**over) -> bm.Option:
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
        "evidence": (bm.mark_verified(bm.Evidence("m1", ("count", "stock"))),),
    }
    base.update(over)
    return bm.Option(**base)


def codes(issues) -> list[str]:
    return [i.code for i in issues]


LIMITS = [
    # Urdu
    "بغیر فیس والے",
    "صرف بغیر فیس والے حل چاہیے",
    # English
    "Only options without a fee",
    "The owner needs no fee for the first month",
    "We want solutions with no charges",
    # Roman Urdu
    "sirf bina fees wale options",
    "fees ke bina wale options chahiye",
    # Hindi
    "बिना फीस वाले विकल्प",
    "सिर्फ फीस के बिना वाले",
    # Arabic
    "نريد خيارات بدون رسوم",
    "فقط حلول بدون رسوم",
]

AMBIGUOUS = [
    "بدون رسوم",
    "بغیر فیس",
    "bina fees",
    "fees ke bina",
    "बिना फीस",
    "no fee for the first month",
    "لا توجد اي رسوم",
    "no charge",
    "We want a quick start, no fee for the first month",
]

CLAIMS = [
    "it will be free",
    "free of charge",
    "مفت",
    "muft",
    "at no cost",
    "मुफ़्त",
    "zero cost",
    "مجاني",
    "Only options without a fee, and it will be free",
    "بغیر فیس والے اور مفت",
]


@pytest.mark.parametrize("text", LIMITS)
def test_an_absence_of_fee_used_as_the_owners_limit_is_not_money(text):
    assert bt.money_state(text) == "clean", text
    assert not bt.money_in(text), text
    issues = br.option_issues(option(what=text), P)
    assert "OPT-MONEY" not in codes(issues) and "MONEY_AMBIGUOUS" not in codes(issues), text


@pytest.mark.parametrize("text", AMBIGUOUS)
def test_an_absence_of_fee_that_could_be_either_is_flagged_as_ambiguous(text):
    assert bt.money_state(text) == "ambiguous", text
    assert not bt.money_in(text), text
    issues = br.option_issues(option(what=text), P)
    assert "MONEY_AMBIGUOUS" in codes(issues), text
    assert "OPT-MONEY" not in codes(issues), text


@pytest.mark.parametrize("text", CLAIMS)
def test_a_claim_that_it_is_free_is_still_money(text):
    assert bt.money_state(text) == "money", text
    assert bt.money_in(text), text
    assert "OPT-MONEY" in codes(br.option_issues(option(what=text), P)), text


def test_the_new_code_is_listed_and_the_owners_expected_outcome_stays_exempt():
    assert "MONEY_AMBIGUOUS" in br.RULE_CODES
    issues = br.option_issues(option(expected_outcome="bina fees"), P)
    assert "MONEY_AMBIGUOUS" not in codes(issues)


def test_an_amount_next_to_a_limit_is_still_money():
    assert bt.money_state("Only options without a fee, not over Rs 500") == "money"
