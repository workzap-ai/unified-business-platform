"""The Solution Box offer: the signals that were never set (R3, "no other problems", cause unknown,
just corrected, in a hurry), the spec's wording, and that the legacy offer stays when box_offer is
off (platform spec Book 5, 5.4)."""

import pytest

from app.modules.pi import box, box_signals, decisions, solution_ask

FULL = box.OfferFacts(
    problem_count=4,
    understood_count=3,
    map_reviewed=True,
    ranked=True,
    voluntary_count=2,
    pi_message_count=9,
)


def context(said="", noted=None, brief=None, **extra):
    return {
        "latest_customer_message": said,
        "noted_problems": noted if noted is not None else [],
        "brief": brief or {},
        "history": [],
        **extra,
    }


@pytest.mark.parametrize(
    "said",
    [
        "no other problems",
        "Bas yahi masle hain",
        "bas yahi",
        "aur koi masla nahi hai",
        "that's all",
        "nothing else is wrong",
    ],
)
def test_no_other_problems_is_recognised(said):
    assert box_signals.says_no_others(said)


@pytest.mark.parametrize(
    "said",
    [
        "nothing else works",
        "that's all very well but the stock is wrong",
        "is that all the problems?",
        "aur koi masla hai?",
        "",
    ],
)
def test_it_is_not_read_into_other_words(said):
    assert not box_signals.says_no_others(said)


@pytest.mark.parametrize(
    "said",
    [
        "who would do this?",
        "How long would it take?",
        "can Workzap do this for us",
        "kaun karega ye sab",
        "kitna time lagega",
    ],
)
def test_who_or_how_long_is_r3_and_lets_the_offer_through(said):
    assert box_signals.asks_who_or_how_long(said)
    facts = box.offer_facts(context(said, noted=[{"title": "A"}]))
    assert facts.asked_who_or_how_long
    assert box.can_offer(facts)[:2] == (True, "R3")


def test_a_plain_message_is_no_r3():
    assert not box_signals.asks_who_or_how_long("the cashiers come late")
    assert not box.offer_facts(context("the cashiers come late")).asked_who_or_how_long


def test_cost_alone_is_r1_not_r3():
    assert not box_signals.asks_who_or_how_long("kitna lagega?")


def test_just_corrected_and_in_a_hurry_hold_the_offer_back():
    full = {"brief": {"map_reviewed": True, "ranked": True}}
    noted = [
        {"title": "A", "cause": "x", "raised_voluntarily": True, "since": "2020"},
        {"title": "B", "cause": "y", "since": "2020"},
        {"title": "C", "cause": "z"},
    ]
    history = [{"role": "ai", "text": "x", "at": "2026-10-01 10:00"}] * 9
    base = context("ok", noted=noted, history=history, **full)
    assert box.can_offer(box.offer_facts(base))[0] is True
    corrected = {**base, "latest_customer_message": "no, that is not what I said, it is wrong"}
    allowed, rule, reason = box.can_offer(box.offer_facts(corrected))
    assert (allowed, rule) == (False, "B") and "corrected" in reason
    hurry = {**base, "latest_customer_message": "abhi busy hoon, baad mein baat karte hain"}
    allowed, _, reason = box.can_offer(box.offer_facts(hurry))
    assert not allowed and "hurry" in reason


def test_a_busy_shop_is_not_a_hurry():
    assert not box_signals.in_a_hurry("the shop is busy every weekend")
    assert not box_signals.in_a_hurry("we are busy in december")


def test_the_cause_of_the_main_problem_is_known_or_not():
    unknown = [{"title": "Stock runs out", "cause": ""}]
    assert not box_signals.main_cause_known(context(noted=unknown))
    known = [{"title": "Stock runs out", "cause": "supplier is late"}]
    assert box_signals.main_cause_known(context(noted=known))
    # the first-ranked problem is the main one
    mixed = [
        {"title": "A", "cause": "", "rank": 2},
        {"title": "B", "cause": "staff", "rank": 1},
    ]
    assert box_signals.main_cause_known(context(noted=mixed))
    # nothing noted: nothing to be unsure about; pi's own diagnosis counts with no open question
    assert box_signals.main_cause_known(context())
    diag = {"expert_diag": {"causes": ["late supplier"], "question": ""}}
    assert not box_signals.main_cause_known(context(noted=unknown, brief=diag))  # pi's guess alone
    asking = {"expert_diag": {"causes": ["late supplier"], "question": "Which supplier?"}}
    assert not box_signals.main_cause_known(context(noted=unknown, brief=asking))
    assert box_signals.main_cause_known(context(noted=unknown, brief={"main_cause_known": True}))


def test_an_unknown_main_cause_blocks_a_b_offer_but_never_r1_to_r3():
    facts = FULL.__class__(**{**FULL.__dict__, "main_cause_known": False})
    allowed, rule, reason = box.can_offer(facts)
    assert (allowed, rule) == (False, "B") and "cause" in reason
    asked = FULL.__class__(**{**facts.__dict__, "asked_who_or_how_long": True})
    assert box.can_offer(asked)[:2] == (True, "R3")


def test_no_other_problems_opens_b1_with_fewer_than_three():
    base = dict(FULL.__dict__, problem_count=2)
    assert not box.can_offer(box.OfferFacts(**base))[0]
    assert box.can_offer(box.OfferFacts(**{**base, "no_other_problems": True}))[0]
    said = box.offer_facts(context("bas yahi masle hain", noted=[{"title": "A"}, {"title": "B"}]))
    assert said.no_other_problems


# --- wording --------------------------------------------------------------------------------------


def test_the_box_offer_is_the_solution_box_line_not_the_old_document_line():
    on = context(
        "", noted=[{}] * 4, box_offer=True, reply_language="en", brief={"map_reviewed": True}
    )
    lines = {solution_ask.offer_line("en", {**on, "latest_message_id": str(i)}) for i in range(12)}
    assert len(lines) >= 2  # it rotates
    for line in lines:
        assert "Solution Box" in line or "map looks" in line
        assert "solution document" not in line.lower()
        assert line.rstrip().endswith("?")  # the one question is the last sentence
        assert line.count("?") == 1
    assert any("4 problems" in line for line in lines)


def test_the_neutral_wording_does_not_claim_a_finished_picture():
    thin = context("", noted=[{}], box_offer=True, reply_language="en")
    line = solution_ask.offer_line("en", thin)
    assert "Solution Box" in line and "picture" not in line and "complete" not in line
    unreviewed = context("", noted=[{}] * 4, box_offer=True, reply_language="en")
    for i in range(12):
        picked = solution_ask.offer_line("en", {**unreviewed, "latest_message_id": str(i)})
        assert "complete" not in picked  # B needs the map reviewed


def test_roman_urdu_uses_the_spec_words_with_the_question_last():
    ctx = context("", noted=[{}] * 4, box_offer=True, reply_language="roman_ur")
    line = solution_ask.offer_line("roman_ur", {**ctx, "brief": {"map_reviewed": True}})
    assert "Solution Box" in line or "Naqsha ab kaafi" in line
    assert line.rstrip().endswith("?") and line.count("?") == 1


def test_other_languages_have_a_solution_box_line_too():
    for code in ("ur", "ar", "fr", "fa", "es"):
        line = solution_ask.BOX_OFFERS[code]["C"]
        assert "Solution Box" in line and line.rstrip().endswith(("?", "؟", " ?"))
        assert "{" not in line


def test_with_box_offer_off_the_old_offer_line_stays():
    assert solution_ask.offer_line("en", context("", noted=[{}] * 4, reply_language="en")) == (
        "Shall I get one solution document and a quote made for all of these together?"
    )
    assert solution_ask.offer_line("en") == solution_ask.OFFER_AFTER["en"]


def test_the_box_offer_is_recognised_as_an_offer_and_gets_buttons():
    ctx = context("", noted=[{}] * 3, box_offer=True, reply_language="en")
    line = solution_ask.offer_line("en", ctx)
    assert solution_ask.already_offers(line) or "map looks" in line
    assert decisions.buttons_for(line) == decisions.OFFER_BUTTONS["en"]
    roman = solution_ask.offer_line("roman_ur", {**ctx, "reply_language": "roman_ur"})
    assert decisions.buttons_for(roman) == decisions.OFFER_BUTTONS["roman_ur"]


def test_a_model_written_solution_box_offer_is_not_doubled():
    assert solution_ask.already_offers("Here you go. Shall I write this into a Solution Box?")


def test_the_summary_gate_uses_the_box_wording_when_the_box_is_on():
    facts = {
        "problem_count": 4,
        "brief": {},
        "box_offer": FULL,
        "message_id": "m1",
        "problem_refs": ["a", "b", "c", "d"],
    }
    made = decisions.decide(decisions.State.S4_SORTED_SUMMARY, "yes that is right", "en", facts)
    assert made is not None and made.reply and "Solution Box" in made.reply
    legacy = decisions.decide(
        decisions.State.S4_SORTED_SUMMARY,
        "quote bhej dein",
        "en",
        {**facts, "box_offer": None},
    )
    assert legacy is not None and legacy.reply and "solution document" in legacy.reply.lower()


def test_the_naya_line_and_the_box_v2_offer():
    ctx = context("", noted=[{}] * 5, box_offer=True, reply_language="roman_ur")
    ctx["brief"] = {"box_naya": ["Cashiers late", "Rent due"]}
    line = solution_ask.offer_line("roman_ur", ctx)
    assert line.startswith("Naya: Cashiers late; Rent due") and "Box v2" in line
    english = solution_ask.offer_line("en", {**ctx, "reply_language": "en"})
    assert english.startswith("New: Cashiers late; Rent due") and "Box v2" in english
