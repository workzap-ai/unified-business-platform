"""FT-A3b: inflection, amount and constraint matching inside the relevance scorer.

Scripted code-path checks of the matching only. Nothing here measures how well pi solves
problems, and nothing prints or asserts an acceptance verdict.
"""

import re

import pytest

from app.modules.pi.evalkit import relevance, relevance_match, relevance_report

BANNED_WORDING = (
    "meets",
    "does not meet",
    "eligible",
    "proposed 85% test",
    "acceptance test",
    "not evaluated",
    "85% agreement test",
)


def brief(constraints=(), words=("late orders",), facts=("two supervisors",), figures=()):
    return {
        "problems": [
            {
                "id": "p1",
                "title": "Problem",
                "user_words": list(words),
                "facts": list(facts),
                "figures": list(figures),
                "constraints": list(constraints),
            }
        ],
        "roles": [],
        "systems": [],
    }


def limit(text, blocks=(), kind="budget", status="confirmed"):
    return {"kind": kind, "text": text, "blocks": list(blocks), "status": status}


def verdict(constraints, idea, **kw):
    return relevance.score_candidate(brief(constraints, **kw), idea)["verdict"]


# ------------------------------------------------------------------ inflection


@pytest.mark.parametrize(
    "forms",
    [
        ("booking", "bookings", "booked", "books", "book"),
        ("stop", "stops", "stopped", "stopping"),
        ("lose", "loses", "losing"),
        ("delivery", "deliveries"),
        ("cancel", "cancels", "cancelled", "cancelling"),
        ("weekly", "week", "weeks"),
        ("try", "tried", "tries"),
    ],
)
def test_english_inflected_forms_share_one_stem(forms) -> None:
    assert len({relevance.stems(f).pop() for f in forms}) == 1, forms


COLLIDING = [
    ("employee", "employ"),
    ("appointment", "appoint"),
    ("alternative", "alter"),
    ("terminal", "terminate"),
    ("investigate", "invest"),
    ("discount", "discover"),
    ("complaint", "complete"),
    ("complaint", "compliance"),
    ("product", "produce"),
    ("supervisor", "supermarket"),
    ("receipt", "receive"),
    ("marker", "market"),
    ("evening", "even"),
]


@pytest.mark.parametrize("a,b", COLLIDING)
def test_the_five_letter_prefix_glues_these_but_the_full_stem_keeps_them_apart(a, b) -> None:
    assert relevance.stems(a, full=True) != relevance.stems(b, full=True)


@pytest.mark.parametrize(
    "a,b", [("salon", "sale"), ("salon", "sales"), ("data", "date"), ("button", "but")]
)
def test_roman_urdu_full_stems_keep_these_apart(a, b) -> None:
    assert relevance.stems(a, "roman_ur", full=True) != relevance.stems(b, "roman_ur", full=True)


def test_full_stems_still_join_real_inflections_and_figures_are_untouched() -> None:
    for forms in (
        ("hire", "hiring", "hired", "hires"),
        ("buy", "buying", "buys"),
        ("stop", "stopped", "stopping"),
        ("staff", "staffing"),
    ):
        assert len({relevance.stems(f, full=True).pop() for f in forms}) == 1, forms
    assert relevance.stems("mazdooron", "roman_ur", full=True) == relevance.stems(
        "mazdoor", "roman_ur", full=True
    )
    assert relevance.stems("20000", full=True) == {"20000"} and relevance.stems("b2b") == {"b2b"}


@pytest.mark.parametrize(
    "forms",
    [
        ("mazdoor", "mazdooron"),
        ("dukan", "dukanein", "dukanon"),
        ("chabi", "chabiyan"),
        ("bhejna", "bhejne", "bhejta", "bheja", "bheji"),
        ("bacha", "bache", "bachi"),
        ("khareedna", "khareedte", "khareeda"),
    ],
)
def test_roman_urdu_endings_share_one_stem_in_roman_urdu(forms) -> None:
    assert len({relevance.stems(f, "roman_ur").pop() for f in forms}) == 1, forms


def test_roman_urdu_endings_are_left_alone_for_other_languages() -> None:
    assert relevance.stems("bhejna") != relevance.stems("bhejta")
    assert relevance.stems("bhejna", "roman_ur") == relevance.stems("bhejta", "roman_ur")


def test_an_inflected_owner_word_links_to_the_idea_that_uses_another_form() -> None:
    b = brief(words=("customers cancelled bookings",), facts=("one clerk",))
    got = relevance.score_candidate(b, "Call customers who cancel a booking within the day")
    assert got["problem_link"] >= 2 and got["verdict"] == "relevant"


def test_roman_urdu_inflection_links_through_the_scorer() -> None:
    b = brief(words=("reminder bhejna",), facts=("ek dukan",))
    idea = "Har shaam grahak ko reminder bhejte rahein"
    plain = relevance.score_candidate(b, idea)
    inflected = relevance.score_candidate(b, idea, language="roman_ur")
    assert inflected["problem_link"] > plain["problem_link"]


# ------------------------------------------------------------ amounts and units


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3 lakh", "300000"),
        ("3,00,000", "300000"),
        ("Rs 3 lakh", "300000"),
        ("20k", "20000"),
        ("20K", "20000"),
        ("2 thousand", "2000"),
        ("1.5 crore", "15000000"),
        ("50 hazar", "50000"),
        ("PKR 50,000", "50000"),
    ],
)
def test_magnitude_words_become_the_same_figure(text, expected) -> None:
    assert expected in relevance.stems(text)
    assert relevance.stems(text) - {"lakh", "k", "thousand", "hazar"} >= {expected}


def test_different_magnitudes_no_longer_link_through_the_shared_word() -> None:
    assert relevance.stems("5 lakh") & relevance.stems("3 lakh") == set()
    assert relevance.stems("3 lakh") & relevance.stems("300000") == {"300000"}


def test_a_range_with_one_magnitude_applies_it_to_both_ends() -> None:
    assert relevance.stems("10-15k") >= {"10000", "15000"}
    assert relevance.stems("10 to 15 thousand") >= {"10000", "15000"}
    found = relevance_match.amounts("budget Rs 10-15k")
    assert [(a.lo, a.hi, a.unit) for a in found] == [(10000.0, 15000.0, "money")]
    found = relevance_match.amounts("between 10000 and 15000 rupees")
    assert [(a.lo, a.hi, a.unit) for a in found] == [(10000.0, 15000.0, "money")]


def test_a_bare_number_with_no_unit_is_not_an_amount_and_a_noun_is_a_unit() -> None:
    assert relevance_match.amounts("route 66 and 2024") == []
    found = relevance_match.amounts("hire 5 staff")
    assert [(a.hi, a.unit) for a in found] == [(5.0, relevance_match.english_stem("staff"))]


@pytest.mark.parametrize(
    "idea,broken",
    [
        ("Buy a booking system for 50000 rupees", True),
        ("Buy a tablet for 15000 rupees", False),
        ("Buy a system for 20000 rupees", False),  # the limit itself is allowed
        ("Buy a system for 50k", True),
        ("Buy a system for 15k", False),
        ("Buy a system for Rs 1 lakh", True),
        ("Buy a system for PKR 25,000", True),
        ("Buy a system for 15 thousand PKR", False),
        ("Buy a system for 1,00,000 rupees", True),
        ("Buy a system for between 15000 and 25000 rupees", False),
        ("Buy a system for 25000 to 30000 rupees", True),
        ("Buy a system for 10-15k", False),
        ("Buy a tablet for 15000 rupees and save 50000 rupees a year", False),
        ("Use the 2 halls and 50 chairs you have", False),
    ],
)
def test_a_numeric_budget_limit_is_compared_as_a_number(idea, broken) -> None:
    got = verdict([limit("cannot spend more than 20000 rupees")], idea)
    assert (got == "violates_constraint") is broken, (idea, got)


def test_strict_and_lakh_ceilings_and_an_assumed_or_floor_limit() -> None:
    under = [limit("budget under 20000 rupees")]
    assert verdict(under, "Buy it for 20000 rupees") == "violates_constraint"
    assert verdict(under, "Buy it for 19000 rupees") != "violates_constraint"
    lakh = [limit("we can spend up to 2 lakh")]
    assert verdict(lakh, "A new mill costs Rs 3 lakh") == "violates_constraint"
    assert verdict(lakh, "A new mill costs Rs 150000") != "violates_constraint"
    assumed = [limit("cannot spend more than 20000 rupees", status="assumed")]
    assert verdict(assumed, "Buy it for 50000 rupees") != "violates_constraint"
    floor = [limit("we need at least 20000 rupees in the till", kind="cannot_change")]
    assert verdict(floor, "Buy it for 50000 rupees") != "violates_constraint"


def test_a_figure_the_owner_already_stated_is_not_a_cost() -> None:
    constraints = [limit("cannot spend more than 20000 rupees")]
    got = verdict(constraints, "Your feed bill of 3 lakh is the real cost", figures=("3 lakh",))
    assert got != "violates_constraint"


def test_a_roman_urdu_ceiling_and_a_non_money_ceiling() -> None:
    ru = [limit("20 hazar se zyada kharch nahi kar sakte")]
    got = relevance.score_candidate(brief(ru), "Naya system 50 hazar ka lagao", language="roman_ur")
    assert got["verdict"] == "violates_constraint"
    got = relevance.score_candidate(brief(ru), "Naya system 15 hazar ka lagao", language="roman_ur")
    assert got["verdict"] != "violates_constraint"
    staff = [limit("cannot have more than 3 staff", kind="staff")]
    assert verdict(staff, "Take on 5 staff for weekends") == "violates_constraint"
    assert verdict(staff, "Take on 2 staff for weekends") != "violates_constraint"
    assert verdict(staff, "Spend 5000 rupees on a rota") != "violates_constraint"


# --------------------------------------------------- verb and tried constraints


def test_cannot_buy_blocks_buying_in_any_form_but_not_renting() -> None:
    c = [limit("cannot buy a new feed mill", blocks=["feed mill"])]
    assert verdict(c, "Buy a second feed mill on a loan") == "violates_constraint"
    assert verdict(c, "Rent a feed mill for the peak months only") != "violates_constraint"
    assert verdict(c, "Lease the feed mills of a neighbour") != "violates_constraint"


def test_the_verb_and_object_alone_are_enough_when_the_fixture_gives_no_blocks() -> None:
    c = [limit("cannot buy a new feed mill", blocks=[], kind="cannot_change")]
    assert verdict(c, "Buy a feed mill with a loan") == "violates_constraint"
    assert verdict(c, "Buy a weighing scale to check the feed") != "violates_constraint"


def test_cannot_change_x_blocks_a_change_to_x_only() -> None:
    c = [limit("we cannot change the delivery route", kind="cannot_change")]
    assert verdict(c, "Change the delivery route to dodge traffic") == "violates_constraint"
    assert verdict(c, "Altering delivery routes each week") == "violates_constraint"
    assert verdict(c, "Add a signed hand-over at each stop on the delivery route") != (
        "violates_constraint"
    )


def test_verb_without_object_words_is_blocked_by_the_verb_group() -> None:
    c = [limit("we cannot hire anyone", kind="staff")]
    assert verdict(c, "Recruit two helpers for the weekend") == "violates_constraint"
    assert verdict(c, "Train the receptionist on a shared sheet") != "violates_constraint"


def test_the_object_must_be_there_and_an_assumed_rule_never_rejects() -> None:
    c = [limit("cannot refuse a family that adds guests", kind="cannot_change")]
    assert verdict(c, "Refuse any family that adds guests after the booking") == (
        "violates_constraint"
    )
    assert verdict(c, "Refuse to cook unfresh food") != "violates_constraint"
    soft = [limit("cannot buy a new feed mill", status="assumed", kind="cannot_change")]
    assert verdict(soft, "Buy a feed mill") != "violates_constraint"


@pytest.mark.parametrize(
    "idea,broken",
    [
        ("Offer a discount to regular clients", True),
        ("Discounts for the weekend slots", True),
        ("Send each client a reminder call the day before", False),
    ],
)
def test_a_thing_tried_before_and_failed_is_not_proposed_again(idea, broken) -> None:
    c = [limit("we tried a discount before and it failed", kind="cannot_change")]
    assert (verdict(c, idea) == "violates_constraint") is broken


def test_tried_phrasing_variants_and_roman_urdu() -> None:
    c = [limit("WhatsApp reminders did not work", kind="cannot_change")]
    assert verdict(c, "Send WhatsApp reminders every evening") == "violates_constraint"
    assert verdict(c, "Phone each client once") != "violates_constraint"
    ru = [limit("discount pehle try kiya lekin kaam nahi kiya", kind="cannot_change")]
    got = relevance.score_candidate(brief(ru), "Regular grahak ko discount do", language="roman_ur")
    assert got["verdict"] == "violates_constraint"
    got = relevance.score_candidate(brief(ru), "Grahak ko call karo", language="roman_ur")
    assert got["verdict"] != "violates_constraint"


def test_the_object_of_a_cannot_rule_counts_as_a_fact_the_owner_stated() -> None:
    c = [limit("cannot buy a new feed mill", blocks=["feed mill"], kind="cannot_change")]
    b = brief(c, words=("feed costs",), facts=("4000 birds",))
    got = relevance.score_candidate(b, "Rent a feed mill for the peak months only")
    assert got["verdict"] == "relevant" and got["fact_reuse"] >= 1


def test_existing_blocks_behaviour_is_unchanged_without_a_parsable_text() -> None:
    c = [limit("one receptionist", blocks=["hire", "recruit"], kind="staff")]
    assert verdict(c, "Hire two more receptionists to answer every booking") == (
        "violates_constraint"
    )
    assert verdict(c, "Hiring a night clerk") == "violates_constraint", "inflected block word"


# ------------------------------------------- audit round: collisions, commas, ceilings

TRIED = "we tried {} before and it failed"
COLLISION_CASES = [
    ("we cannot hire anyone", "Hire a night helper", "Give each employee a checklist"),
    ("we cannot hire anyone", "Employ a helper", "Book an appointment slot for each client"),
    ("we cannot hire anyone", "Appoint a helper", "Give each employee a checklist"),
    (
        "we cannot change the delivery route",
        "Alter the delivery route",
        "Use an alternative delivery route",
    ),
    ("we cannot fire anyone", "Terminate a helper", "Staff the terminal desk"),
    ("we cannot invest anything", "Invest in a tablet", "Investigate why the slots clash"),
    ("we cannot buy anything", "Buy a tablet", "Number each order at the door"),
    (TRIED.format("a discount"), "Offer a discount", "Discover which slots stay empty"),
    (TRIED.format("complaints"), "Add complaints to the chart", "Complete the form each day"),
    (TRIED.format("complaints"), "Log complaints daily", "Check compliance every week"),
    (TRIED.format("a product"), "Sell a new product", "Produce a weekly list"),
    (TRIED.format("a supervisor"), "Add a supervisor", "Visit the supermarket on Friday"),
    (TRIED.format("a receipt"), "Print a receipt", "Receive the parcels at the hub door"),
    (TRIED.format("a marker"), "Use a marker", "Go to the market on Friday"),
    (TRIED.format("evening"), "Add an evening shift", "Spread bookings even across slots"),
]


@pytest.mark.parametrize("text,bad,good", COLLISION_CASES)
def test_an_idea_using_a_colliding_word_is_not_rejected(text, bad, good) -> None:
    c = [limit(text, kind="cannot_change")]
    assert verdict(c, bad) == "violates_constraint", bad
    assert verdict(c, good) != "violates_constraint", good


def test_blocks_also_match_on_the_full_stem() -> None:
    c = [limit("one receptionist", blocks=["employ"], kind="staff")]
    assert verdict(c, "Employing a night clerk") == "violates_constraint"
    assert verdict(c, "Give each employee a checklist") != "violates_constraint"


@pytest.mark.parametrize(
    "text,bad,good",
    [
        ("sales pehle try kiya lekin kaam nahi kiya", "Sales ka naya offer do", "Salon ko dekho"),
        ("date pehle try kiya lekin kaam nahi kiya", "Naya date offer do", "Data entry karo"),
        ("button pehle try kiya lekin kaam nahi kiya", "Ek button lagao", "Lekin ye karo"),
    ],
)
def test_roman_urdu_collisions_are_not_rejected(text, bad, good) -> None:
    c = [limit(text, kind="cannot_change")]
    got = relevance.score_candidate(brief(c), bad, language="roman_ur")["verdict"]
    assert got == "violates_constraint", bad
    got = relevance.score_candidate(brief(c), good, language="roman_ur")["verdict"]
    assert got != "violates_constraint", good


def test_purchasing_is_the_buy_family_when_the_fixture_gives_no_blocks() -> None:
    c = [limit("cannot buy a new feed mill", blocks=[], kind="cannot_change")]
    assert verdict(c, "Purchasing a feed mill would cut the bill") == "violates_constraint"
    assert verdict(c, "Rent a feed mill for the peak months") != "violates_constraint"


def test_roman_urdu_rule_verb_and_idea_use_the_same_stem() -> None:
    c = [limit("naya feed mill kharid nahi kar sakte", kind="cannot_change")]
    for idea in ("Feed mill kharidna theek nahi", "Ek feed mill kharid lo"):
        got = relevance.score_candidate(brief(c), idea, language="roman_ur")
        assert got["verdict"] == "violates_constraint", idea
    c = [limit("hum purchase nahi kar sakte", kind="cannot_change")]
    got = relevance.score_candidate(brief(c), "Ek tablet purchase karo", language="roman_ur")
    assert got["verdict"] == "violates_constraint"


@pytest.mark.parametrize(
    "idea",
    [
        "Buy a system for Rs 50000, then train the clerk",
        "Buy a system for 50,000 rupees, then train the clerk",
        "Buy a system for Rs 50,000.",
        "Buy a system for 50000 rupees.",
        "Buy a system for 50k, then train the clerk",
    ],
)
def test_a_trailing_comma_or_full_stop_is_punctuation_not_part_of_the_figure(idea) -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert 50000.0 in [a.lo for a in relevance_match.amounts(idea)]
    assert verdict(c, idea) == "violates_constraint"


def test_a_ceiling_followed_by_a_comma_still_counts_and_a_figure_list_stays_a_list() -> None:
    c = [limit("cannot spend more than 20000, so keep it small")]
    assert verdict(c, "Buy a system for 50000 rupees") == "violates_constraint"
    assert verdict(c, "Buy a system for 15000 rupees") != "violates_constraint"
    listed = relevance_match.amounts("120,150,180 rupees")
    assert [(a.lo, a.unit) for a in listed] == [(180.0, "money")]
    assert relevance_match.fold_magnitudes("120,150,180 and 20,000") == "120 150 180 and 20,000"
    assert relevance.stems("120,150,180") == {"120", "150", "180"}
    assert relevance_match.amounts("50,000, then 60,000. ", context=True)[0].lo == 50000.0


@pytest.mark.parametrize("kind", ["staff", "cannot_change", "deadline"])
def test_a_roman_urdu_ceiling_after_the_figure_works_without_a_budget_kind(kind) -> None:
    ru = [limit("20 hazar se zyada kharch nahi kar sakte", kind=kind)]
    over = relevance.score_candidate(
        brief(ru), "Naya system 50 hazar ka lagao", language="roman_ur"
    )
    under = relevance.score_candidate(
        brief(ru), "Naya system 15 hazar ka lagao", language="roman_ur"
    )
    assert over["verdict"] == "violates_constraint"
    assert under["verdict"] != "violates_constraint"
    found = relevance_match.ceilings_of("20 hazar se zyada kharch nahi kar sakte", kind)
    assert found == [relevance_match.Ceiling(20000.0, "money", False)]


def test_under_a_budget_kind_the_first_money_figure_is_the_ceiling() -> None:
    found = relevance_match.ceilings_of("2 staff, budget 20000 rupees", "budget")
    assert found == [relevance_match.Ceiling(20000.0, "money", False)]
    c = [limit("2 staff, budget 20000 rupees")]
    assert verdict(c, "Buy a system for 50000 rupees") == "violates_constraint"
    assert verdict(c, "Buy a system for 15000 rupees") != "violates_constraint"
    both = relevance_match.ceilings_of(
        "cannot have more than 3 staff, budget 20000 rupees", "budget"
    )
    assert {x.unit for x in both} == {relevance_match.english_stem("staff"), "money"}


def test_a_ceiling_cue_must_sit_right_before_its_figure() -> None:
    found = relevance_match.ceilings_of("cannot hire more than 3 staff; the rota costs 9000 rupees")
    assert [x.unit for x in found] == [relevance_match.english_stem("staff")]


def test_a_stated_figure_is_exempt_only_when_restated_not_when_bought() -> None:
    c = [limit("cannot spend more than 2 lakh")]
    said = brief(c, figures=("3 lakh",))
    restated = relevance.score_candidate(said, "Your 3 lakh feed bill is the real cost")
    assert restated["verdict"] != "violates_constraint"
    bought = relevance.score_candidate(said, "A new mill costs Rs 3 lakh")
    assert bought["verdict"] == "violates_constraint", "same value, but written as a new cost"
    staff_said = brief(c, figures=("300000 staff",))
    got = relevance.score_candidate(staff_said, "Your 3 lakh feed bill is the real cost")
    assert got["verdict"] == "violates_constraint", "another unit is not the same figure"
    past = brief(
        [limit("cannot spend more than 20000 rupees")],
        facts=("I paid 50000 for the old diary software",),
    )
    got = relevance.score_candidate(past, "Buy new software for Rs 50000")
    assert got["verdict"] == "violates_constraint"


def test_benefit_words_exempt_a_figure_only_when_tied_to_it() -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, "Buy sales software for 50000 rupees") == "violates_constraint"
    assert verdict(c, "Buy a mill worth Rs 3 lakh") == "violates_constraint"
    assert verdict(c, "Pay 50000 rupees for profit tracking") == "violates_constraint"
    saved = "Use a 15000 rupee tablet and save 50000 rupees a year"
    assert verdict(c, saved) != "violates_constraint"
    profit = "Expect profit of Rs 3 lakh from the 15000 rupee tablet"
    assert verdict(c, profit) != "violates_constraint"


def test_a_descriptive_never_or_fails_is_not_a_prohibition() -> None:
    c = [limit("the supplier fails to deliver on time", kind="cannot_change")]
    assert verdict(c, "Ask the supplier to deliver on Fridays") != "violates_constraint"
    c = [limit("the supplier never delivers on time", kind="cannot_change")]
    assert verdict(c, "Deliver the parcels on time with a list") != "violates_constraint"
    c = [limit("we do not deliver on Sundays", kind="cannot_change")]
    assert verdict(c, "Deliver the parcels on Sundays") != "violates_constraint"
    c = [limit("the supplier failed us last year", kind="cannot_change")]
    assert verdict(c, "Ask the supplier for a price list") != "violates_constraint"
    c = [limit("we do not want to change the delivery route", kind="cannot_change")]
    assert verdict(c, "Change the delivery route") == "violates_constraint"


def test_a_milder_verb_skips_only_its_own_block_not_the_whole_check() -> None:
    c = [limit("cannot buy a new feed mill", blocks=["feed mill", "loan"], kind="cannot_change")]
    assert verdict(c, "Rent a feed mill for the peak months") != "violates_constraint"
    assert verdict(c, "Rent a feed mill and pay it with a loan") == "violates_constraint"


def test_long_input_with_no_punctuation_finishes_quickly() -> None:
    import time

    started = time.perf_counter()
    text = ("word " * 20000) + ("1," * 5000) + ("x" * 50000) + (" " * 20000) + "tried"
    relevance.score_candidate(brief([limit(text, kind="cannot_change")]), text)
    relevance.score_candidate(brief([limit("cannot spend more than 20000 rupees")]), text)
    assert time.perf_counter() - started < 5


def test_the_module_docstrings_have_no_verdict_wording_and_state_the_fact_rule() -> None:
    assert "count as stated facts" in " ".join((relevance._vocab.__doc__ or "").split())
    for doc in (relevance.__doc__, relevance_match.__doc__):
        folded = " ".join((doc or "").casefold().split())
        for word in BANNED_WORDING:
            assert word not in folded, f"{word!r} implies a computed acceptance"


# ------------------------------------------------ third round: money tails, homographs, stems

MONEY_LIMITS = [
    "cannot spend more than 20000 this month",
    "cannot spend more than 20000 because cash is tight",
    "budget under 20000 monthly",
    "we cannot spend more than 20000, so keep it small",
    "cannot spend more than 20000 rupees this month",
]


@pytest.mark.parametrize("text", MONEY_LIMITS)
def test_a_money_ceiling_stays_money_when_words_follow_the_figure(text) -> None:
    found = relevance_match.ceilings_of(text, "cannot_change")
    assert found and found[0].unit == "money" and found[0].value == 20000.0, text
    c = [limit(text, kind="cannot_change")]
    assert verdict(c, "Buy a system for 50000 rupees") == "violates_constraint"
    assert verdict(c, "Buy a system for 15000 rupees") != "violates_constraint"


@pytest.mark.parametrize(
    "idea",
    [
        "Buy a 50k tablet",
        "Buy a system for 50000 then train the clerk",
        "Buy a system for 50000 this month",
        "Buy a system for 50000 because it is faster",
        "Buy a tablet that costs 50000 monthly",
        "Pay 50000 and train the clerk",
    ],
)
def test_an_idea_money_figure_stays_money_when_words_follow_it(idea) -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, idea) == "violates_constraint", idea
    assert verdict(c, idea.replace("50000", "15000").replace("50k", "15k")) != (
        "violates_constraint"
    )


def test_roman_urdu_money_with_a_tail_word_and_counted_nouns_stay_nouns() -> None:
    ru = [limit("20 hazar se zyada kharch nahi kar sakte", kind="cannot_change")]
    over = relevance.score_candidate(
        brief(ru), "Naya system 50 hazar mein lagao", language="roman_ur"
    )
    under = relevance.score_candidate(
        brief(ru), "Naya system 15 hazar mein lagao", language="roman_ur"
    )
    assert over["verdict"] == "violates_constraint"
    assert under["verdict"] != "violates_constraint"
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, "Hire 50 staff for the weekend") != "violates_constraint"
    assert verdict(c, "Order 3 lakh birds") != "violates_constraint"
    assert verdict(c, "Buy 50 chairs for the hall") != "violates_constraint"
    assert [a.unit for a in relevance_match.amounts("for 50 chairs")] == ["chair"]


def test_a_floor_clause_is_left_out_but_the_rest_of_the_limit_still_counts() -> None:
    text = "we need at least 2 staff and cannot spend more than 20000 rupees"
    found = relevance_match.ceilings_of(text, "budget")
    assert found == [relevance_match.Ceiling(20000.0, "money", False)]
    c = [limit(text)]
    assert verdict(c, "Buy a system for 50000 rupees") == "violates_constraint"
    assert relevance_match.ceilings_of("we need at least 2 staff", "staff") == []
    first = "cannot spend more than 20000 rupees, but we need at least 5 staff"
    assert [x.unit for x in relevance_match.ceilings_of(first, "budget")] == ["money"]


@pytest.mark.parametrize(
    "text,bad,good",
    [
        ("we cannot close", "Close the shop on Fridays", "Book a live band for the hall"),
        ("we cannot close the shop", "Close the shop early", "Book a live band for the shop"),
        ("we cannot fire anyone", "Fire the cleaner", "Install a fire alarm"),
        ("we cannot fire anyone", "Ask them to fire a helper", "Check the fire exit each week"),
        ("we cannot cut anything", "Cut the evening shift", "Add a cute mascot"),
        ("we cannot cut anything", "Cutting hours helps", "Place the order at the door"),
        ("we cannot change anything", "Change the route", "Add a stop on each route"),
    ],
)
def test_a_verb_rule_is_not_fired_by_a_noun_that_looks_like_the_verb(text, bad, good) -> None:
    c = [limit(text, kind="cannot_change")]
    assert verdict(c, bad) == "violates_constraint", bad
    assert verdict(c, good) != "violates_constraint", good


@pytest.mark.parametrize(
    "a,b",
    [
        ("button", "buttons"),
        ("station", "stations"),
        ("machine", "machines"),
        ("coupon", "coupons"),
        ("mazdooron", "mazdoor"),
    ],
)
def test_roman_urdu_plural_goes_before_the_endings_in_the_full_space(a, b) -> None:
    assert relevance.stems(a, "roman_ur", full=True) == relevance.stems(b, "roman_ur", full=True)


@pytest.mark.parametrize("a,b", [("version", "verse"), ("lesson", "less"), ("coupon", "coup")])
def test_roman_urdu_full_stems_keep_these_apart_too(a, b) -> None:
    assert relevance.stems(a, "roman_ur", full=True) != relevance.stems(b, "roman_ur", full=True)


@pytest.mark.parametrize(
    "forms",
    [
        ("reply", "replied", "replies"),
        ("supply", "supplied", "supplies"),
        ("cancel", "cancelled", "cancelling", "cancels"),
        ("hire", "hiring", "hired", "hires"),
        ("create", "creating", "created"),
        ("close", "closing", "closed"),
        ("raise", "raising", "raised"),
        ("rate", "rates"),
        ("plan", "planning", "planned"),
    ],
)
def test_full_stems_join_these_inflections(forms) -> None:
    assert len({relevance.stems(f, full=True).pop() for f in forms}) == 1, forms


@pytest.mark.parametrize(
    "a,b", [("care", "car"), ("plane", "plan"), ("wine", "win"), ("rate", "rat"), ("cute", "cut")]
)
def test_full_stems_keep_these_apart(a, b) -> None:
    assert relevance.stems(a, full=True) != relevance.stems(b, full=True)


def test_verbs_on_the_stop_list_still_work_as_rule_verbs() -> None:
    c = [limit("we cannot give discounts", kind="cannot_change")]
    assert verdict(c, "Give discounts to regular clients") == "violates_constraint"
    assert verdict(c, "Offer a discount to regular clients") == "violates_constraint"
    assert verdict(c, "Send a reminder to regular clients") != "violates_constraint"
    c = [limit("we cannot use cash", kind="cannot_change")]
    assert verdict(c, "Use cash at the door") == "violates_constraint"
    assert verdict(c, "Use a card at the door") != "violates_constraint"


def test_curly_apostrophes_afford_and_the_passive_make_rules() -> None:
    c = [limit("we can’t hire anyone", kind="staff")]
    assert verdict(c, "Hire a helper") == "violates_constraint"
    c = [limit("we don’t want to change the delivery route", kind="cannot_change")]
    assert verdict(c, "Change the delivery route") == "violates_constraint"
    c = [limit("we cannot afford a new feed mill", kind="cannot_change")]
    assert verdict(c, "Buy a feed mill on a loan") == "violates_constraint"
    assert verdict(c, "Rent a feed mill for the peak months") != "violates_constraint"
    c = [limit("the delivery route cannot be changed", kind="cannot_change")]
    assert verdict(c, "Change the delivery route") == "violates_constraint"
    assert verdict(c, "Add a signed hand-over at each stop") != "violates_constraint"
    c = [limit("we like it but the delivery route cannot be changed", kind="cannot_change")]
    assert verdict(c, "Alter the delivery route") == "violates_constraint"


def test_a_prohibition_without_a_modal_is_documented_as_not_handled() -> None:
    assert relevance_match.parse_rules("no hiring this year", None, relevance._full_stems) == []
    assert relevance_match.parse_rules("never hire anyone", None, relevance._full_stems) == []
    assert "Not handled" in " ".join((relevance_match.parse_rules.__doc__ or "").split())


def test_250_500_000_is_one_grouped_figure_and_a_list_ending_in_digits_stays_a_list() -> None:
    assert relevance.tokens("250,500,000") == ["250500000"]
    assert relevance.tokens("120,150,180") == ["120", "150", "180"]
    assert relevance_match.amounts("Rs 250,500,000")[0].lo == 250500000.0
    assert relevance_match.fold_magnitudes("250,500,000 and 120,150,180") == (
        "250,500,000 and 120 150 180"
    )


def test_the_standing_note_and_the_borderline_section_carry_no_verdict_wording() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        section = relevance_report.borderline_section(Path(tmp) / "a.jsonl", "lane E", "scan")
    for text in (relevance.DISCLAIMER, section):
        folded = " ".join(text.casefold().split())
        for word in BANNED_WORDING:
            assert word not in folded, f"{word!r} implies a computed acceptance"
    assert "Current scorer:" in section


# ------------------------------------------------------------- fourth round


@pytest.mark.parametrize(
    "text,good",
    [
        (
            "we cannot afford downtime",
            "Buy a backup generator so a power cut never causes downtime",
        ),
        ("we cannot afford mistakes", "Pay a clerk to catch mistakes before they reach the client"),
        ("we cannot afford delays", "Pay a courier to avoid delays on Fridays"),
        ("we cannot lose any customers", "Call quiet customers so you avoid losing them"),
        ("we cannot afford to lose customers", "Buy a till that flags customers who go quiet"),
        ("we cannot risk late deliveries", "Pay a rider to cut late deliveries"),
    ],
)
def test_a_stated_goal_is_not_a_prohibition_on_ideas_that_name_it(text, good) -> None:
    rules = relevance_match.parse_rules(text, None, relevance._full_stems)
    assert all(r.kind == "goal" for r in rules), text
    assert verdict([limit(text, kind="cannot_change")], good) != "violates_constraint"


@pytest.mark.parametrize(
    "text,bad,good",
    [
        ("we cannot afford a new feed mill", "Buy a feed mill on a loan", "Rent a feed mill"),
        ("we cannot afford booking software", "Buy booking software", "Use a paper sheet"),
        ("we cannot afford more staff", "Hire two helpers as staff", "Train the staff we have"),
        ("we cannot afford a generator", "Purchase a generator", "Rent a generator"),
    ],
)
def test_cannot_afford_a_purchasable_thing_still_blocks_buying_it(text, bad, good) -> None:
    c = [limit(text, kind="cannot_change")]
    assert verdict(c, bad) == "violates_constraint", bad
    assert verdict(c, good) != "violates_constraint", good


@pytest.mark.parametrize(
    "text",
    [
        "we need at least 2 staff so we cannot spend more than 20000 rupees",
        "need at least 2 staff with a budget under 20000",
        "we need at least 2 staff because we cannot spend more than 20000 rupees",
        "at least 2 staff while spending no more than 20000 rupees",
        "we need at least 2 staff, aur 20000 rupees se zyada kharch nahi kar sakte",
    ],
)
def test_a_floor_clause_ends_at_its_conjunction(text) -> None:
    found = relevance_match.ceilings_of(text, "cannot_change")
    assert [c for c in found if c.unit == "money"], text
    c = [limit(text, kind="cannot_change")]
    assert verdict(c, "Buy a system for 50000 rupees") == "violates_constraint"
    assert verdict(c, "Buy a system for 15000 rupees") != "violates_constraint"


@pytest.mark.parametrize(
    "forms",
    [
        ("use", "using", "used", "uses"),
        ("type", "typed", "typing", "types"),
        ("style", "styled", "styles", "styling"),
        ("free", "freed", "frees"),
        ("size", "sized", "sizes"),
    ],
)
def test_short_stems_agree_across_their_forms(forms) -> None:
    assert len({relevance._full_stems(f, None).pop() for f in forms}) == 1, forms
    assert relevance._full_stems("used", None) != relevance._full_stems("user", None)


def test_use_as_a_rule_verb_matches_using_and_used() -> None:
    c = [limit("we cannot use cash", kind="cannot_change")]
    for idea in ("Use cash at the door", "Using cash at the door", "Used cash is accepted here"):
        assert verdict(c, idea) == "violates_constraint", idea
    assert verdict(c, "Use a card at the door") != "violates_constraint"


def test_blocks_phrases_are_not_narrowed_by_the_rule_verbs() -> None:
    c = [limit("no discounts", blocks=["give discount"], kind="cannot_change")]
    assert verdict(c, "Offer a discount to regular clients") == "violates_constraint"
    assert verdict(c, "Discounts for the weekend slots") == "violates_constraint"
    assert verdict(c, "Send a reminder to regular clients") != "violates_constraint"


def test_every_development_blocks_phrase_still_matches_itself() -> None:
    from app.modules.pi.evalkit import relevance_calibration, splits

    checked = 0
    for case in relevance_calibration.load_cases():
        if splits.split_of(case) == splits.HELD_OUT:
            continue
        b = case["input"]["brief"]
        for problem in b.get("problems") or []:
            for lim in problem.get("constraints") or []:
                if lim.get("status", "confirmed") != "confirmed":
                    continue
                for phrase in lim.get("blocks") or []:
                    got = relevance.violated(b, set(), case["language"], phrase)
                    assert got, (case["id"], phrase)
                    checked += 1
    assert checked >= 10


@pytest.mark.parametrize(
    "text,good",
    [
        ("we cannot fire anyone", "Run a monthly fire drill"),
        ("we cannot fire anyone", "Add fire extinguishers to the hall"),
        ("we cannot fire anyone", "Run a fire-safety walk each week"),
        ("we cannot close", "Book a hall close to the station"),
        ("we cannot hire anyone", "Ask the new hire to keep the sheet"),
        ("we cannot hire anyone", "Give the new hire a checklist"),
    ],
)
def test_more_noun_positions_do_not_fire_a_verb_rule(text, good) -> None:
    c = [limit(text, kind="cannot_change")]
    assert verdict(c, good) != "violates_constraint", good


def test_band_is_a_homograph_in_roman_urdu_too() -> None:
    c = [limit("hum band nahi kar sakte", kind="cannot_change")]
    got = relevance.score_candidate(
        brief(c), "Live band book karo for the shop", language="roman_ur"
    )
    assert got["verdict"] != "violates_constraint"
    got = relevance.score_candidate(brief(c), "Dukan band karo", language="roman_ur")
    assert got["verdict"] == "violates_constraint"


@pytest.mark.parametrize(
    "idea",
    [
        "Buy a 50000 tablet",
        "Buy 50000 worth of stock",
        "Buy a 50000-rupee tablet",
        "Get a system at 50000",
        "Invest 50000 in a new system",
        "Buy a 2.5m machine",
        "Buy a 1m generator",
        "Buy a 50 k tablet",
        "Buy a 50k tablet",
        "Pay 50k tablets",
    ],
)
def test_bare_and_new_figure_forms_are_money_costs(idea) -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, idea) == "violates_constraint", idea


@pytest.mark.parametrize(
    "idea",
    ["Buy 50 chairs", "Sell 50k eggs", "Message your 50k followers", "Hire 5 staff", "Open at 6"],
)
def test_counts_and_times_are_not_money(idea) -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, idea) != "violates_constraint", idea


def test_a_budget_of_gives_a_ceiling_for_any_kind_and_millions_are_read() -> None:
    for kind in ("cannot_change", "deadline", "staff"):
        found = relevance_match.ceilings_of("a budget of 20000 for this", kind)
        assert [(c.value, c.unit) for c in found] == [(20000.0, "money")], kind
    assert relevance_match.amounts("a 2.5m machine")[0].lo == 2500000.0
    assert relevance_match.amounts("1m generator")[0].lo == 1000000.0
    assert relevance_match.amounts("a 5 k fee")[0].lo == 5000.0
    assert "2500000" in relevance.stems("2.5m")


@pytest.mark.parametrize(
    "idea",
    [
        "Sell the old mill for Rs 80000",
        "Charge Rs 50000 for a premium package",
        "Collect Rs 50000 from late payers",
        "Raise Rs 50000 from donors",
        "Get Rs 50000 from the bank grant",
        "Make Rs 50000 a month from a stall",
        "Receive Rs 50000 up front",
    ],
)
def test_income_verbs_make_a_figure_income_not_a_cost(idea) -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, idea) != "violates_constraint", idea


def test_buying_next_to_selling_is_still_a_cost() -> None:
    c = [limit("cannot spend more than 20000 rupees")]
    assert verdict(c, "Sell the old mill and buy a new one for Rs 80000") == "violates_constraint"


@pytest.mark.parametrize(
    "text",
    [
        "20000 at most",
        "20000 rupees or less",
        "we should not cross 20000 rupees",
        "keep it to 20000 rupees at most",
        "maximum 20000 rupees",
    ],
)
def test_a_ceiling_cue_after_the_figure_or_cross_counts(text) -> None:
    found = relevance_match.ceilings_of(text, "cannot_change")
    assert found and found[0].value == 20000.0, text
    assert verdict([limit(text, kind="cannot_change")], "Buy it for 50000 rupees") == (
        "violates_constraint"
    )


def test_the_budget_fallback_never_turns_income_into_a_ceiling() -> None:
    text = "we earn 80000 a month, cannot buy a mill"
    assert relevance_match.ceilings_of(text, "budget") == []
    c = [limit(text, kind="budget")]
    assert verdict(c, "Pay 30000 rupees for a scale") != "violates_constraint"
    assert verdict(c, "Buy a feed mill") == "violates_constraint"
    sales = relevance_match.ceilings_of("sales are 90000 monthly; spending max 20000", "budget")
    assert [c.value for c in sales] == [20000.0]


TOOL_BANNED = re.compile(
    r"\b(?:pass|passed|passes|fail|failed|fails|accepted|accept|threshold met|meets|"
    r"does not meet|eligible|acceptance test|not evaluated)\b|85%",
    re.IGNORECASE,
)


def test_the_report_output_carries_no_verdict_wording_for_the_tool_itself() -> None:
    import tempfile
    from pathlib import Path

    from app.modules.pi.evalkit import relevance_calibration, splits

    cases = [
        c for c in relevance_calibration.load_cases() if c.get("kind") != "borderline_relevance"
    ]
    dev = [c for c in cases if splits.split_of(c) != splits.HELD_OUT]
    with tempfile.TemporaryDirectory() as tmp:
        text, _ = relevance_report.build(dev, Path(tmp) / "a.jsonl", "lane E", "wording scan")
    for source in (text, relevance.DISCLAIMER):
        assert not TOOL_BANNED.search(source), TOOL_BANNED.search(source).group()
    assert "Current scorer, Development borderline set:" in text
    assert "earlier scorer" in text


# ------------------------------------------------------------- fifth round: fail safe


def full(limit_text, idea, kind="cannot_change", language=None):
    return relevance.score_candidate(brief([limit(limit_text, kind=kind)]), idea, language=language)


@pytest.mark.parametrize(
    "text,kind,idea",
    [
        ("we dont have money to buy a van", "budget", "Buy a van"),
        ("we won't change the menu", "cannot_change", "Change the menu"),
        ("never open on Sundays", "cannot_change", "Open on Sundays"),
        ("we cannot work after 6pm", "deadline", "Add an evening shift"),
        ("we cannot work after 6pm", "deadline", "Add a morning shift"),
        ("we have only 2 staff", "staff", "Hire 3 more staff"),
        ("we have only 2 staff", "staff", "Train your 2 staff"),
        ("deadline is Friday", "deadline", "Finish by Monday"),
    ],
)
def test_a_limit_the_scorer_cannot_read_makes_the_verdict_unknown(text, kind, idea) -> None:
    got = full(text, idea, kind)
    assert got["verdict"] == "unknown", (text, idea, got["verdict"])
    assert got["unknown_reason"] == "limit_not_understood"
    assert relevance.score_candidate(brief([limit(text, kind=kind)]), idea)["verdict"] not in (
        "relevant",
        "irrelevant",
    )


def test_a_limit_with_blocks_is_still_understood_and_an_assumed_one_is_ignored() -> None:
    c = [limit("one receptionist", blocks=["hire"], kind="staff")]
    assert verdict(c, "Train the receptionist on a shared sheet") != "unknown"
    soft = [limit("we have only 2 staff", kind="staff", status="assumed")]
    assert verdict(soft, "Train your staff on the sheet") != "unknown"


URDU_LIMIT = "بجٹ 20000 سے زیادہ نہیں"
URDU_IDEA = "نیا سسٹم 50000 روپے میں خریدیں"
HINDI_LIMIT = "हम नया मिल नहीं खरीद सकते"
ARABIC_LIMIT = "لا نستطيع شراء مطحنة جديدة"


@pytest.mark.parametrize("language", ["ur", None, "hi", "ar"])
@pytest.mark.parametrize(
    "text,idea",
    [
        (URDU_LIMIT, URDU_IDEA),
        (HINDI_LIMIT, "नया मिल खरीदें"),
        (ARABIC_LIMIT, "اشتر مطحنة جديدة"),
    ],
)
def test_a_limit_in_urdu_hindi_or_arabic_script_is_unknown(text, idea, language) -> None:
    got = full(text, idea, "budget", language)
    assert got["verdict"] == "unknown"
    # a budget kind with a figure in it is read as a ceiling, but the idea's script is not read
    assert got["unknown_reason"] in ("limit_not_understood", "script_not_read")


def test_an_idea_in_another_script_is_unknown_when_the_limit_is_read_from_words_or_numbers() -> (
    None
):
    got = full("cannot spend more than 20000 rupees", URDU_IDEA, "budget", "ur")
    assert got["verdict"] == "unknown" and got["unknown_reason"] == "script_not_read"
    c = [limit("one receptionist", blocks=["hire"], kind="staff")]
    got = relevance.score_candidate(brief(c), URDU_IDEA, language="ur")
    assert got["verdict"] != "unknown", "a limit given as fixture blocks still works in any script"


def test_roman_urdu_under_a_unread_limit_in_the_scorers_own_example_is_unknown_not_relevant() -> (
    None
):
    b = brief([limit("hum staff nahi rakh sakte", kind="staff")], words=("late orders",))
    got = relevance.score_candidate(b, "naya staff rakhein late orders ke liye")
    assert got["verdict"] == "unknown"


@pytest.mark.parametrize(
    "text,bad,good",
    [
        (
            "hum staff nahi rakh sakte",
            "naya staff rakhein late orders ke liye",
            "staff ko train karo",
        ),
        ("hum cash nahi le sakte", "cash mein payment lein", "card se payment lein"),
        ("hum discount nahi de sakte", "regular grahak ko discount dein", "grahak ko call karein"),
        (
            "hum naya system install nahi kar sakte",
            "naya system lagayein",
            "purana system theek karo",
        ),
        ("hum naya mill kharid nahi sakte", "naya mill kharido", "mill kiraye par lein"),
        ("hum naya mill kharid nahi kar sakte", "naya mill kharidein", "mill kiraye par lein"),
    ],
)
def test_roman_urdu_verbs_the_scorer_knows_make_working_rules(text, bad, good) -> None:
    assert full(text, bad, language="roman_ur")["verdict"] == "violates_constraint", bad
    assert full(text, good, language="roman_ur")["verdict"] != "violates_constraint", good


def test_a_roman_urdu_verb_outside_the_list_makes_the_limit_unknown() -> None:
    got = full("hum mill nahi ugaa sakte", "naya mill lagayein", language="roman_ur")
    assert got["verdict"] == "unknown"


@pytest.mark.parametrize(
    "text,idea,broken",
    [
        ("we cannot hire anyone", "Hire out the spare room", False),
        ("we cannot hire anyone", "Rent out the spare room and hire out the hall", False),
        ("we cannot hire anyone", "Hire a rider", True),
        ("we cannot buy a van", "Rent out the van to a neighbour", False),
        ("we cannot buy a van", "Buy a van", True),
    ],
)
def test_phrasal_out_is_letting_not_hiring_or_buying(text, idea, broken) -> None:
    assert (full(text, idea)["verdict"] == "violates_constraint") is broken, idea


def test_renting_out_is_income_not_a_cost() -> None:
    c = [limit("cannot spend more than 20000")]
    assert verdict(c, "Rent out the hall for 80000") != "violates_constraint"
    assert verdict(c, "Lease out the old van for Rs 90000") != "violates_constraint"
    assert verdict(c, "Rent the hall for 80000") == "violates_constraint"


@pytest.mark.parametrize(
    "text,idea",
    [
        ("we cannot offer discounts", "Run a discount week"),
        ("we cannot offer discounts", "Offer a discount code"),
        ("we cannot give discounts", "Offer a discount code"),
        ("we cannot give discounts", "Launch a discount for new clients"),
        ("we cannot give discounts", "Start a discount day"),
    ],
)
def test_running_or_offering_the_blocked_object_is_a_violation(text, idea) -> None:
    assert full(text, idea)["verdict"] == "violates_constraint", idea


def test_run_does_not_fire_a_rule_about_something_else() -> None:
    assert full("we cannot offer discounts", "Run a reminder week")["verdict"] != (
        "violates_constraint"
    )
    assert full("we cannot close", "Run a reminder week")["verdict"] != "violates_constraint"


@pytest.mark.parametrize(
    "text,bad,good",
    [
        ("we cannot afford a loan", "Take a loan for the shop", "Repay the old loan early"),
        ("cannot afford new equipment", "Buy a new oven", "Repair the old oven"),
        ("cannot afford new equipment", "Purchase a mixer", "Clean the mixer daily"),
        ("we cannot afford software", "Buy a booking app", "Use a paper sheet"),
        ("we cannot hire staff", "Hire a rider", "Train the rider we have"),
    ],
)
def test_equipment_software_and_staff_cover_what_they_are(text, bad, good) -> None:
    assert full(text, bad)["verdict"] == "violates_constraint", bad
    assert full(text, good)["verdict"] != "violates_constraint", good


@pytest.mark.parametrize(
    "text,bad,good",
    [
        ("we cannot lose any customers", "Lose the unhappy customers", "Call quiet customers"),
        ("we cannot lose any customers", "Let customers lose interest", "Thank each customer"),
        ("we cannot afford downtime", "Cause downtime by switching systems", "Add a spare router"),
        ("we cannot miss deadlines", "Miss the deadline if it is tight", "Plan each deadline"),
    ],
)
def test_a_goal_is_broken_by_an_idea_that_does_the_loss(text, bad, good) -> None:
    assert full(text, bad)["verdict"] == "violates_constraint", bad
    assert full(text, good)["verdict"] != "violates_constraint", good


@pytest.mark.parametrize(
    "text,idea",
    [
        ("we cannot lose any customers", "Call quiet customers so you avoid losing them"),
        (
            "we cannot afford downtime",
            "Buy a backup generator so a power cut never causes downtime",
        ),
        ("we cannot miss deadlines", "Add a checklist so you never miss a deadline"),
        ("we cannot afford waste", "Track stock to reduce waste"),
        ("we cannot buy a printer", "Do not buy a printer, print at a shop"),
        ("we cannot buy a printer", "Avoid buying a printer and print at a shop"),
        ("we cannot buy a printer", "Print at a shop instead of buying a printer"),
    ],
)
def test_a_negated_verb_in_the_idea_does_not_break_the_limit(text, idea) -> None:
    assert full(text, idea)["verdict"] != "violates_constraint", idea


@pytest.mark.parametrize(
    "idea,broken",
    [
        ("Buy 3 machines at 10000 each", True),
        ("Buy 3 machines for 10000 rupees each", True),
        ("Buy 2 machines at 5000 each", False),
        ("Buy 3 x 10000 rupees of stock", True),
    ],
)
def test_a_price_each_is_multiplied_by_its_quantity(idea, broken) -> None:
    c = [limit("cannot spend more than 20000")]
    assert (verdict(c, idea) == "violates_constraint") is broken, idea


def test_a_price_each_with_no_quantity_and_a_spelled_number_are_unknown() -> None:
    c = [limit("cannot spend more than 20000")]
    got = relevance.score_candidate(brief(c), "Buy a machine at 10000 each")
    assert got["verdict"] == "unknown" and got["unknown_reason"] == "quantity_unclear"
    got = relevance.score_candidate(brief(c), "Buy a machine for five thousand")
    assert got["verdict"] == "unknown" and got["unknown_reason"] == "spelled_number"


SIZES = (200, 800, 1600, 4000, 50000)
SHAPES = {
    "spaces": " ",
    "newlines": "\n",
    "five": "5 ",
    "nahi": "nahi ",
    "tried": "tried ",
    "failed": "failed ",
    "digits": "1",
    "sakt": "kharid nahi kar sakte ",
}


def time_budget() -> float:
    """100 ms, or 40 times what a trivial candidate costs right now, so a loaded machine does
    not flake the check while a growth with size (quadratic or worse) still fails it."""
    trivial = best_of(
        lambda i: relevance.score_candidate(
            brief([limit("cannot buy a van" + "x" * i, kind="cannot_change")]),
            "Buy a van" + "y" * i,
        ),
        7,
    )
    return max(0.1, 40 * trivial)


def best_of(fn, runs=3) -> float:
    import time

    best = 1e9
    for i in range(runs):
        started = time.perf_counter()
        fn(i)
        best = min(best, time.perf_counter() - started)
    return best


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("size", SIZES)
def test_limit_parsing_is_linear_and_flags_a_limit_that_is_too_long(shape, size) -> None:
    unit = SHAPES[shape]
    for lang in (None, "roman_ur"):

        def once(i, unit=unit, size=size, lang=lang):
            text = (unit * (size // len(unit) + 1))[:size] + "x" * i  # i defeats the caches
            return relevance.score_candidate(
                brief([limit(text, kind="cannot_change")]),
                "Buy a system for 50000 rupees",
                language=lang,
            )

        assert best_of(once, 5) < time_budget(), (shape, size, lang)
    text = (unit * (size // len(unit) + 1))[:size]
    got = relevance.score_candidate(brief([limit(text, kind="cannot_change")]), "Buy a van")
    if len(relevance_match.collapse(text)) > relevance_match.MAX_LIMIT_TEXT:
        assert got["limit_text_truncated"] is True and got["verdict"] == "unknown"
        assert got["unknown_reason"] == "limit_text_truncated"


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("size", SIZES)
def test_idea_parsing_is_linear_and_flags_an_idea_that_is_too_long(shape, size) -> None:
    unit = SHAPES[shape]
    c = [limit("cannot spend more than 20000 rupees")]

    def once(i):
        text = (unit * (size // len(unit) + 1))[:size] + "x" * i
        return relevance.score_candidate(brief(c), text, language="roman_ur")

    assert best_of(once, 5) < time_budget(), (shape, size)
    text = (unit * (size // len(unit) + 1))[:size]
    got = relevance.score_candidate(brief(c), text)
    if len(relevance_match.collapse(text)) > relevance_match.MAX_IDEA_TEXT:
        assert got["text_truncated"] is True and got["verdict"] == "unknown"


def test_the_soft_prefix_no_longer_inflates_relevance() -> None:
    b = brief(words=("employee morale low",), facts=("discount codes",))
    got = relevance.score_candidate(b, "Discover how to employ the right tool")
    assert got["problem_link"] == 0 and got["verdict"] != "relevant"
    got = relevance.score_candidate(b, "Raise employee morale with discount codes")
    assert got["problem_link"] >= 1


def test_the_disclaimer_says_what_is_reported_as_unknown() -> None:
    note = " ".join(relevance.DISCLAIMER.split())
    assert "Urdu, Hindi and Arabic script" in note
    assert "Roman Urdu verbs outside the supported list" in note
    assert "'unknown'" in note and "never scored as relevant or irrelevant" in note
    assert "unknown" in " ".join((relevance.__doc__ or "").split())


def test_the_report_counts_unknown_in_its_own_column() -> None:
    import tempfile
    from pathlib import Path

    from app.modules.pi.evalkit import relevance_calibration, splits

    cases = [
        c for c in relevance_calibration.load_cases() if c.get("kind") != "borderline_relevance"
    ]
    dev = [c for c in cases if splits.split_of(c) != splits.HELD_OUT]
    with tempfile.TemporaryDirectory() as tmp:
        text, totals = relevance_report.build(
            dev, Path(tmp) / "a.jsonl", "lane E", "unknown column"
        )
    assert "not read (unknown, counted apart)" in text
    assert all("unknown" in v for k, v in totals.items() if k.startswith("split:"))
    agg = relevance.aggregate(
        [
            {
                "candidates": 2,
                "agree": 1,
                "false_relevant": 0,
                "missed_relevant": 0,
                "hard_misses": 0,
                "unknown": 1,
            }
        ]
        * 3
    )
    assert agg["unknown"] == 3


def test_no_source_text_names_a_fixture_case() -> None:
    from pathlib import Path

    here = Path(relevance.__file__).parent
    for name in ("relevance.py", "relevance_match.py"):
        assert "feed mill" not in (here / name).read_text(encoding="utf-8"), name


def test_fuzz_500_strings_never_raise_and_always_give_a_known_verdict() -> None:
    import random

    rng = random.Random(20261031)
    words = [
        "buy",
        "hire",
        "cannot",
        "never",
        "5k",
        "20000",
        "rupees",
        "each",
        "at",
        "for",
        "nahi",
        "sakte",
        "kar",
        "staff",
        "oven",
        "loan",
        "discount",
        "out",
        "rent",
        "not",
        "avoid",
        "lose",
        "customers",
        "afford",
        "downtime",
        "tried",
        "failed",
        "before",
        "and",
        "so",
        "at least",
        "budget",
        "lakh",
        "2.5m",
        "five thousand",
        "بجٹ",
        "हम",
        "شراء",
        "kharid",
        "rakh",
        "le",
        "de",
        "do",
        "x",
        "",
        "  ",
        "\n",
        "-",
        ",",
        "1,2,3",
        "120,150,180",
        "250,500,000",
        "$",
        "Rs.",
        "’",
        "can't",
        "won't",
    ]
    allowed = set(relevance.VERDICTS) | {relevance.UNKNOWN}
    for n in range(500):

        def piece(k):
            return " ".join(rng.choice(words) for _ in range(rng.randint(0, k)))

        limit_text, idea = piece(14), piece(14)
        kind = rng.choice(["budget", "staff", "deadline", "cannot_change", ""])
        lang = rng.choice([None, "roman_ur", "ur", "hi", "ar", "en"])
        status = rng.choice(["confirmed", "confirmed", "assumed"])
        blocks = [piece(3)] if rng.random() < 0.3 else []
        b = brief([limit(limit_text, blocks=blocks, kind=kind, status=status)])
        got = relevance.score_candidate(b, idea, owner_text=piece(10), language=lang)
        assert got["verdict"] in allowed, (n, limit_text, idea, got)


# ------------------------------------------------------------- sixth round

EXPENSIVE = "buy an expensive tracking system costing 90000 rupees to cut late orders"


@pytest.mark.parametrize(
    "text",
    [
        "we cannot afford much right now",
        "cannot afford much",
        "cannot pay much",
        "can't afford a lot",
        "can’t afford a lot of things",
        "cannot afford extras",
        "unable to spend more",
        "we cannot spend any more",
        "cannot afford anything extra",
        "we cannot afford stuff",
    ],
)
def test_a_vague_limit_is_not_read_as_a_rule_and_stays_unknown(text) -> None:
    assert relevance_match.parse_rules(text, None, relevance._full_stems) == [], text
    got = full(text, EXPENSIVE, "budget")
    assert got["verdict"] == "unknown" and got["unknown_reason"] == "limit_not_understood", text


@pytest.mark.parametrize(
    "text,idea,language",
    [
        ("hum zyada nahi de sakte", "naya tracking system 90000 rupees mein lagayein", "roman_ur"),
        ("hum bohat nahi kharid sakte", "naya tracking system kharidein", "roman_ur"),
        (
            "ہم بہت زیادہ خرچ نہیں کر سکتے",
            EXPENSIVE,
            "ur",
        ),
        (
            "हम बहुत ज़्यादा खर्च नहीं कर सकते",
            EXPENSIVE,
            "hi",
        ),
        (
            "لا نستطيع أن ننفق الكثير",
            EXPENSIVE,
            "ar",
        ),
    ],
)
def test_vague_words_in_the_other_four_languages_stay_unknown_too(text, idea, language) -> None:
    got = full(text, idea, "budget", language)
    assert got["verdict"] == "unknown", (text, got["verdict"])


def test_a_real_object_after_a_money_verb_is_still_a_rule() -> None:
    assert full("we cannot afford a booking app", "Buy a booking app")["verdict"] == (
        "violates_constraint"
    )
    assert full("we cannot hire anyone", "Hire a rider")["verdict"] == "violates_constraint"
    assert full("we cannot close", "Close the second shop")["verdict"] == "violates_constraint"


def test_mutation_without_the_vague_list_the_vague_limit_would_be_a_rule(monkeypatch) -> None:
    relevance_match._rules_cached.cache_clear()
    monkeypatch.setattr(relevance_match, "_VAGUE", set())
    try:
        rules = relevance_match.parse_rules("cannot afford much", None, relevance._full_stems)
        assert rules, "the vague-object guard is what stops this rule"
    finally:
        relevance_match._rules_cached.cache_clear()


@pytest.mark.parametrize(
    "text,idea,broken",
    [
        ("cannot rent out our van", "rent out the van to cover late orders", True),
        ("we cannot rent out our van", "Rent out the van on Sundays", True),
        ("cannot rent out our van", "Rent a van for the weekend", False),
        ("cannot rent out our van", "Buy a van", False),
        ("cannot hire out staff", "hire out two supervisors to cover late orders", True),
        ("cannot hire out staff", "Hire a supervisor", False),
        ("cannot hire out staff", "Hire out the spare room", False),
        ("cannot lease out the hall", "Lease out the hall on weekends", True),
        ("cannot lease out the hall", "Lease the hall from a neighbour", False),
        ("we cannot hire anyone", "Hire out the spare room", False),
        ("we cannot hire new staff", "hire on a part-time clerk", True),
        ("we cannot hire new staff", "Hire a part-time clerk", True),
        ("we cannot hire on new staff", "Hire on a part-time clerk", True),
        ("we cannot hire on new staff", "Hire out a part-time clerk", False),
        ("we cannot buy a van", "Rent out the van to a neighbour", False),
    ],
)
def test_a_verb_with_a_particle_in_the_limit_is_broken_by_the_same_phrase(
    text, idea, broken
) -> None:
    got = full(text, idea)["verdict"] == "violates_constraint"
    assert got is broken, (text, idea)


def test_mutation_without_the_particle_match_the_phrase_rule_would_not_fire(monkeypatch) -> None:
    c = [limit("cannot hire out staff", kind="cannot_change")]
    assert verdict(c, "hire out two supervisors") == "violates_constraint"
    monkeypatch.setattr(relevance_match, "phrasal_pairs", lambda text, language: frozenset())
    assert verdict(c, "hire out two supervisors") != "violates_constraint"


def test_on_is_a_preposition_not_a_particle_so_close_on_sundays_is_still_a_close() -> None:
    assert full("we cannot close on Sundays", "Close early on Sunday")["verdict"] == (
        "violates_constraint"
    )
