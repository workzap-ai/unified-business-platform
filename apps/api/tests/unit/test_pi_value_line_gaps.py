# ruff: noqa: E501  (reply lines read better unbroken)
"""Gaps in the value line found by probing the real functions (Addendum 2, Part 1): the linter runs
the value-line checks on every brain reply after plain listening, prose ideas are counted, named
products are vendors, emergency numbers are not claims, "will" is not promised, the industry
never-say list is in the linter, and the value line cannot be learned away."""

import json
import re
from pathlib import Path

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import learning, safety, solution_rules, solutions, value_line

AI_TURN = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}
WITH_LINE = (
    " Workzap could message each manager the day a best-seller runs low. Want a solution document?"
)


def ctx(latest="stock keeps running out", state="S5_READINESS", history=None, **extra):
    return {
        "latest_customer_message": latest,
        "history": [AI_TURN] if history is None else history,
        "flow": {"state": state},
        "pi_mode": "brain",
        **extra,
    }


def broke(reply, **kwargs):
    return c.lint(reply, ctx(**kwargs))


def rules(reply, **kwargs):
    return {v.rule for v in broke(reply, **kwargs)}


def hard_rules(reply, **kwargs):
    return {v.rule for v in c.hard(broke(reply, **kwargs))}


# 1. the checks run on every reply after listening ---------------------------------------------------
def test_three_numbered_ideas_are_a_hard_break_with_no_ideas_handed():
    reply = "1. Give each ad a code. 2. Ask who sent them. 3. Post on Mondays." + WITH_LINE
    assert "R-VAL-01" in hard_rules(reply)
    assert "R-VAL-01" in hard_rules(reply, state="S1_LISTENING")  # any reply that carries ideas


def test_how_to_steps_are_hard_in_the_readiness_state_without_handed_ideas():
    reply = "Step 1: open a Google Sheet, make columns for each ad, then count them. Want a solution document?"
    assert "R-VAL-04" in hard_rules(reply)
    assert "R-VAL-04" in hard_rules(
        "Pehle sheet banayein, phir har ad ka code likhein. Kya main solution document banwa doon?"
    )


def test_a_long_idea_is_soft_and_a_short_one_is_fine():
    long = (
        "You could give every single ad its own printed code at the till so that over the whole "
        "month you can see which of them brought people in and which of them did not at all."
    )
    assert "R-VAL-03" in rules(long + WITH_LINE)
    assert "R-VAL-03" not in hard_rules(long + WITH_LINE)
    short = "Give every ad its own code at the till, so you can see which one brings people in."
    assert "R-VAL-03" not in rules(short + WITH_LINE)


def test_the_conversation_budget_is_soft_and_a_referral_is_exempt():
    two = (
        "1. Give each ad a code, to see which works.\n2. Ask who sent them, to learn why."
        + WITH_LINE
    )
    assert "R-VAL-02" in rules(two, ideas_given=3)
    assert "R-VAL-02" not in rules(two, ideas_given=2)
    assert "R-VAL-02" not in rules(two, ideas_given=3, state="S5b_DECLINED")
    assert "R-VAL-02" not in hard_rules(two, ideas_given=3)


def test_ideas_that_lead_nowhere_are_soft():
    bare = "1. Give each ad a code, to see which works.\n2. Ask who sent them, to learn why."
    assert "R-VAL-06" in rules(bare)
    assert "R-VAL-06" not in rules(bare + " Which first?")
    assert "R-VAL-06" not in rules(bare + WITH_LINE)
    assert "R-VAL-06" not in hard_rules(bare)


def test_a_request_answered_with_only_a_pitch_is_soft_when_ideas_were_handed():
    pitch = "Workzap could set the whole thing up for you. Want a solution document?"
    handed = {
        "solution_ideas": ["Give each ad a code at the till", "Ask who sent them"],
        "solution_asked": True,
    }
    assert "R-SOL-01" in rules(pitch, **handed)
    assert "R-SOL-01" not in hard_rules(pitch, **handed)
    gave = "1. Give each ad a code at the till.\n2. Ask who sent them." + WITH_LINE
    assert "R-SOL-01" not in rules(gave, **handed)


def test_listening_replies_and_summaries_are_not_read_as_ideas():
    summary = "Here is what I noted:\n• Stock runs out\n• Cashiers are late\n• Cash does not match\nIs it stock?"
    assert not c.hard(broke(summary, state="S4_SORTED_SUMMARY"))
    assert not rules(
        "Noted, stock runs out. What else is getting in the way?", state="S2_CLARIFYING"
    ) & {"R-VAL-01", "R-VAL-02", "R-VAL-03", "R-VAL-04", "R-VAL-06"}


def test_the_old_context_free_lint_is_unchanged():
    reply = "1. Give each ad a code.\n2. Ask who sent them.\n3. Post on Mondays.\nWhich first?"
    assert not [v for v in c.lint(reply, {}) if v.rule == "R-VAL-01"]


# 2. prose ideas ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply, n",
    [
        ("First give each ad a code, second ask who sent them, third post on Mondays.", 3),
        (
            "Pehle har ad ka code rakhein, doosra poochein kaun laya, teesra Monday ko post karein.",
            3,
        ),
        ("Ek tareeqa ad code hai. Dusra tareeqa poochna hai. Teesra Monday post hai.", 3),
        ("One way is a code per ad. Another way is to ask. A third is to post on Mondays.", 3),
        ("First, tell me which shop this is.", 0),
        ("One way is a code per ad. Another way is to ask.", 2),
        ("It took a second to load. Sentence number 3 says hello.", 0),
    ],
)
def test_prose_ideas_are_counted(reply, n):
    assert solution_rules.count_ideas(reply) == n


def test_three_prose_ideas_break_the_count_rule():
    reply = (
        "One way is a code per ad. Another way is to ask who sent them. A third is posting on Mondays."
        + WITH_LINE
    )
    assert "R-VAL-01" in hard_rules(reply)


# 3. RV-05 named products ---------------------------------------------------------------------------
PRODUCT_LINES = [
    "Use Shopify, it is best.",
    "Just use Canva for the posters.",
    "Keep the udhaar in Tally ERP every night.",
    "Try Zoho for the follow-ups.",
    "Odoo handles this well.",
    "QuickBooks would sort the invoices.",
    "The WhatsApp Business API can send them.",
    "Put it in Google Sheets.",
    "Excel does the job for stock.",
    "Track it in Notion or Trello.",
]


@pytest.mark.parametrize("line", PRODUCT_LINES)
def test_a_named_product_is_a_hard_break_in_the_live_linter_and_the_idea_check(line):
    assert "R-VAL-05" in hard_rules(
        line + " Want a solution document?", latest="how do I fix stock"
    )
    assert not solution_rules.check_idea(line).ok


def test_a_product_the_customer_named_may_be_acknowledged_but_not_recommended():
    said = "we keep everything in Tally and Shopify right now"
    assert "R-VAL-05" not in hard_rules(
        "Noted, Shopify and Tally are both in use. Want a solution document?", latest=said
    )
    assert "R-VAL-05" in hard_rules(
        "Use Shopify for that, it is best. Want a solution document?", latest=said
    )
    assert solution_rules.named_products("Noted, you use Tally.", said) == []


def test_ordinary_words_are_not_products():
    for line in (
        "Tally the walk-ins at the door every day, to see the real number.",
        "That notion is worth testing for a week.",
        "The shop will stay slack on Mondays unless something changes.",
        "Give every ad its own code at the till.",
    ):
        assert not solution_rules.named_products(line), line


# 4. RV-07 safety referrals are not claims ----------------------------------------------------------
@pytest.mark.parametrize("number", ["1122", "15", "911", "999", "998", "16", "997"])
def test_safety_referral_given_in_full_past_the_budget(number):
    """VAL-6."""
    reply = (
        f"If the animal is down or struggling to breathe, call {number} or your vet now. "
        "1. Give each ad a code, to see which works.\n2. Ask who sent them, to learn why."
        + WITH_LINE
    )
    found = broke(reply, ideas_given=4)
    assert not c.hard(found), [(v.rule, v.message) for v in found]
    assert "R-VAL-02" not in {v.rule for v in found}
    assert solution_rules.check_sample_reply(reply) == []


def test_a_real_claim_is_still_flagged_next_to_a_referral():
    assert (
        solution_rules.check_sample_reply("Call 1122 now, and sales will rise 300 per month.") != []
    )
    assert solution_rules.check_sample_reply("Ads bring 5000 people.") != []


def test_every_known_emergency_number_is_exempt():
    numbers = {n for row in safety.NUMBERS.values() for n in row.values()}
    assert numbers >= {"15", "1122", "16", "999", "998", "997", "911"}
    for n in numbers:
        assert not solution_rules.claim_hits(f"Call {n} now.")


# 5. RB-06 "will" ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "Workzap will fix it.",
        "It will stop the stock-outs.",
        "You will see every ad's result.",
        "Is se masla theek ho jaye ga.",
        "Sab kuch theek ho jayegi.",
        "This will save you hours.",
        "That will fix the delay.",
    ],
)
def test_will_about_the_build_is_a_hard_break_in_a_given_turn(line):
    assert "R-BUILD-06" in {
        v.rule for v in c.hard(broke(line, state="S3_NOTED", solution_asked=True))
    }


def test_would_and_could_are_fine():
    ok = "Workzap would message each manager the day stock runs low, and it could send a morning note."
    assert "R-BUILD-06" not in rules(ok, state="S3_NOTED", solution_asked=True)


# 6. industry never-say in the linter ---------------------------------------------------------------
TAX_NEVER = [
    "Any view on a client's tax position, what they owe, or how to reduce tax. Anything that helps backdate documents, alter records or hide income."
]


def test_an_industry_never_say_phrase_is_a_hard_break():
    bad = "Sure, I can help backdate documents for the season. What else is slow?"
    assert "R-NEVER-IND" in hard_rules(bad, solution_never_say=TAX_NEVER, state="S2_CLARIFYING")
    assert "R-NEVER-IND" in hard_rules(
        "Here is how to reduce tax this year. What else?",
        solution_never_say=TAX_NEVER,
        state="S2_CLARIFYING",
    )


def test_refusing_or_other_words_do_not_trip_the_never_say_check():
    fine = "I can't help with how to reduce tax, that is for your accountant. What else is slow?"
    assert "R-NEVER-IND" not in rules(fine, solution_never_say=TAX_NEVER, state="S2_CLARIFYING")
    assert "R-NEVER-IND" not in rules(
        "Noted, returns pile up in September. What else?", solution_never_say=TAX_NEVER
    )


def test_the_industry_key_pulls_the_never_say_list():
    key = "accounting_audit_and_tax_practices"
    assert solutions.load(key)
    bad = "I can help backdate documents. What else is slow?"
    assert "R-NEVER-IND" in hard_rules(bad, industry_key=key, state="S2_CLARIFYING")
    assert "R-NEVER-IND" not in rules(bad, state="S2_CLARIFYING")


def test_every_industry_never_say_gives_some_fragments():
    empty = [
        k
        for k in solutions.industries()
        if not solution_rules.never_say_fragments(solutions.never_say([k]))
    ]
    assert empty == []


# 7. never-learn holes -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    [
        "max_ideas",
        "free_ideas_per_message",
        "idea_count",
        "ideas_before_offer",
        "value_line_on",
        "howto_for_free",
        "offer_after_ideas",
    ],
)
def test_value_line_settings_cannot_be_learned(name):
    assert not value_line.may_learn(name)


def test_no_setting_name_with_idea_or_value_can_be_learned_and_real_ones_still_can():
    for stem in ("idea", "value", "free"):
        for name in (
            stem,
            f"x_{stem}",
            f"{stem}_x",
            f"max_{stem}s",
            f"{stem.upper()}_COUNT",
            f"a_{stem}_b",
        ):
            assert not value_line.may_learn(name), name
    from app.modules.pi import brain_config

    for name in brain_config.RANGES if hasattr(brain_config, "RANGES") else ():
        assert value_line.may_learn(name), name
    assert value_line.may_learn("question_arms")


@pytest.mark.parametrize(
    "text",
    [
        "give a fifth idea",
        "share the full how-to for free",
        "one more idea per message",
        "give a third idea when they ask",
        "send the complete how-to in the chat",
        "extra ideas are fine",
        "how to set it up for free",
    ],
)
def test_attempts_to_loosen_the_value_line_are_never_learned(text):
    assert learning.VALUE_LINE_ATTEMPT.search(text)
    assert learning.never_learn(text)


def test_ordinary_text_is_not_mistaken_for_an_attempt():
    for text in (
        "They ask about the first idea we gave.",
        "Stock runs out at the weekend.",
        "A free consultation is not offered.",
    ):
        assert not learning.VALUE_LINE_ATTEMPT.search(text), text


# 8. the 211 sample replies ----------------------------------------------------------------------------
SAMPLES = Path(solutions.__file__).parent / "packs" / "solutions"


def _sample_failures() -> dict[str, list[str]]:
    out = {}
    for path in sorted(SAMPLES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sample = data["sample_reply"]
        why = solution_rules.check_sample_reply(sample["pi"], sample["person"])
        if why:
            out[data["industry"]] = why
    return out


def test_the_sample_replies_no_longer_lead_the_build_with_automatically():
    files = sorted(SAMPLES.glob("*.json"))
    assert len(files) == 211
    leads = re.compile(r"automatically for you|khud-ba-khud kar sakta hai", re.IGNORECASE)
    stuck = [
        p.stem
        for p in files
        if leads.search(json.loads(p.read_text(encoding="utf-8"))["sample_reply"]["pi"])
    ]
    # platform spec A2-FIX-4: only the Arabic sample and one tuition sample (whose own build
    # sentence could not be parsed mechanically) keep the document's wording
    assert set(stuck) <= {"tuition_centres_and_academies"}, stuck


def test_no_two_industries_in_a_sector_open_a_sample_reply_the_same_way():
    seen: dict[tuple[str, str], str] = {}
    for p in sorted(SAMPLES.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        opener = data["sample_reply"]["pi"].splitlines()[0].strip()
        key = (data["sector"], opener)
        assert key not in seen, (p.stem, seen.get(key))
        seen[key] = p.stem


def test_every_sample_reply_passes_the_value_line_check():
    assert _sample_failures() == {}
