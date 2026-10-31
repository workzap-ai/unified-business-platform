"""L2-3 hardening: the text patterns behind OPT-PROMISE, OPT-MONEY and OPT-CAUSE-FACT.

Each string below escaped the first version of the rules (found by an independent audit). Pure, no
model, no database."""

import time

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import blueprint_text as bt
from app.modules.pi import brain_docs
from app.modules.pi.constitution import PROMISE

PROMISES = [
    "zaroor hoga",
    "ضمان",
    "الضمان",
    "ٱلضَّمَان",
    "results are assured",
    "definitely works every time",
    "kaam pakka karega",
    "نتیجہ یقینی ہے",
    "this is certain to work",
    "it works for sure",
    "G u a r a n t e e d",
    "g.u.a.r.a.n.t.e.e.d",
    "gu​aranteed",
    "gu‍ar⁠anteed",
    "guarantееd cyrillic e",
    "ＧＵＡＲＡＮＴＥＥＤ",
    "गारंटी",
    "पक्का",
    "ज़रूर होगा",
    "مضمون",
    "بالتأكيد سينجح",
    "یقینی طور پر",
    "100 percent",
    "no doubt it works",
    "without fail",
    "risk free",
]

CLEAN = [
    "It would help the morning check",
    "It will not replace the till",
    "A short checklist would be agreed for the evening count",
    "Make sure the owner agrees first",
    "It affects a certain shelf",
    "A definite plan would come from the owner",
    "The count would be checked every time it is skipped",
    "It would cover 4 shops since 2024",
]


@pytest.mark.parametrize("text", PROMISES)
def test_a_promise_in_any_spelling_is_caught(text):
    assert bt.promise_in(text, PROMISE, bt.WILL), text


@pytest.mark.parametrize("text", CLEAN)
def test_ordinary_text_is_not_a_promise(text):
    assert not bt.promise_in(text, PROMISE, bt.WILL), text


MONEY = [
    "PKR50000",
    "Rs500",
    "Rs 5",
    "500 dollars",
    "500 bucks",
    "EUR 300",
    "300 euros",
    "300 eur",
    "50000",
    "50 000",
    "5 0 0 0 0",
    "٥٠٠٠٠",
    "Rs５００",
    "five hundred thousand",
    "half a million",
    "a million",
    "fifty-thousand",
    "5L",
    "50000 rupay",
    "paanch hazaar",
    "aik lakh rupay",
    "پانچ لاکھ",
    "پچاس ہزار روپے",
    "पाँच लाख",
    "5,00,000",
    "$500",
    "fee 5000",
    "1.5m",
]

NOT_MONEY = [
    "It would cover 4 shops since 2024",
    "40 staff would need it",
    "since 2025",
    "call +923001234567 when ready",
    "03001234567",
    "a 20% improvement is not promised",
    "3 people",
    "step 2 of 3",
    "version 2.5",
    "about 15 minutes a day",
    "between 100 and 200 customers",
]


@pytest.mark.parametrize("text", MONEY)
def test_an_amount_in_any_script_or_as_words_is_caught(text):
    assert bt.money_in(text), text


@pytest.mark.parametrize("text", NOT_MONEY)
def test_counts_years_phone_numbers_and_percentages_are_not_money(text):
    assert not bt.money_in(text), text


def option(**over):
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
        "evidence": (bm.Evidence("m1", ("count", "stock")),),
    }
    base.update(over)
    return bm.Option(**base)


def codes(issues):
    return {i.code for i in issues}


@pytest.mark.parametrize("text", PROMISES)
def test_the_rule_catches_a_promise_in_what(text):
    assert "OPT-PROMISE" in codes(br.option_issues(option(what=text), {"P1"}))


@pytest.mark.parametrize("text", MONEY)
def test_the_rule_catches_money_in_benefit(text):
    assert "OPT-MONEY" in codes(br.option_issues(option(benefit=text), {"P1"}))


def test_a_promise_is_caught_in_every_text_pi_wrote():
    said = "this will definitely fix it"
    for field in (
        {"risks": (bm.Risk(said),)},
        {"dependencies": (bm.Dependency("other", "guaranteed result"),)},
        {"constraint_checks": (bm.ConstraintCheck("budget", "ok", "guaranteed"),)},
        {"status": "rejected", "rejected_because": "guaranteed"},
        {"limits": (said,)},
        {"trade_offs": (said,)},
    ):
        assert "OPT-PROMISE" in codes(br.option_issues(option(**field), {"P1"})), field


def test_the_old_patterns_still_run():
    assert bt.MONEY_IN_TEXT.pattern == brain_docs.MONEY_IN_TEXT.pattern
    assert bt.WILL.pattern == brain_docs.WILL.pattern
    for text in ("Rs 450,000", "AED 900", "This will fix the problem", "100% works"):
        assert bt.money_in(text) or bt.promise_in(text, PROMISE, bt.WILL)


def test_folding_removes_invisible_marks_and_look_alikes():
    assert bt.fold("gu​aran‍teed") == "guaranteed"
    assert bt.fold("guarantееd") == "guaranteed"
    assert bt.fold("٥٠٠") == "500"
    assert bt.fold("ＡＢＣ") == "abc"
    assert bt.fold("ٱلضَّمَان") == bt.fold("الضمان")


def test_a_long_text_is_scanned_in_bounded_time():
    for text in ("1," * 5000 + "x", "1" * 20000 + "x", "a " * 10000, "a-" * 10000, "one " * 5000):
        started = time.perf_counter()
        bt.money_in(text)
        bt.promise_in(text, PROMISE, bt.WILL)
        assert time.perf_counter() - started < 2.0


def test_a_text_over_the_limit_is_malformed_not_scanned_past_the_limit():
    long = "x " * (bt.MAX_TEXT // 2 + 10)
    issues = br.option_issues(option(what=long), {"P1"})
    assert [i.code for i in issues] == ["MALFORMED"]
    assert "too long" in issues[0].detail


# --- a guessed cause worded as a fact -----------------------------------------------------------

CAUSE = "staff do not count stock at night"


@pytest.mark.parametrize(
    "text",
    [
        "The cause is that staff do not count stock at night",
        "staff don't count stock at night",
        "Night stock counting is skipped by staff",
        "STAFF  DO NOT\nCOUNT STOCK AT NIGHT",
        "staff do not count stock at night. maybe not",
        "Because staff do not count stock at night, if you agree",
        "staff do not count stock at night. May the checklist help",
        "Staff do not count stock at night (if)",
        "the reason is staff do not count stock at night; agar",
        "staff do not count stock at night, agar nahi",
        "Staff do not count stock at night, so it would help",
    ],
)
def test_a_guessed_cause_worded_as_a_fact_is_caught(text):
    assert bt.states_as_fact(CAUSE, text), text


@pytest.mark.parametrize(
    "text",
    [
        "Maybe staff do not count stock at night",
        "If staff do not count stock at night, a checklist may help",
        "Perhaps stock is not counted at night by staff",
        "A checklist would help the evening",
        "Stock would be counted",
    ],
)
def test_a_hedged_or_unrelated_text_is_not_a_fact_claim(text):
    assert not bt.states_as_fact(CAUSE, text), text


def test_the_hedge_must_sit_in_the_same_clause_as_the_cause_words():
    assert bt.states_as_fact(CAUSE, "Staff do not count stock at night. Maybe a checklist helps.")


def test_the_rule_flags_a_paraphrase_in_what_benefit_and_risks():
    cause = bm.RootCause(CAUSE)
    paraphrase = "Night stock counting is skipped by staff"
    for field in ({"what": paraphrase}, {"benefit": paraphrase}, {"risks": (bm.Risk(paraphrase),)}):
        issues = br.option_issues(option(**field), {"P1"}, cause=cause)
        assert "OPT-CAUSE-FACT" in codes(issues), field
    stated = bm.RootCause(CAUSE, status="owner_said")
    assert "OPT-CAUSE-FACT" not in codes(
        br.option_issues(option(what=paraphrase), {"P1"}, cause=stated)
    )
