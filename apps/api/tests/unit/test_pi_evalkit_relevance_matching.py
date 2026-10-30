"""FT-A3b: inflection, amount and constraint matching inside the relevance scorer.

Scripted code-path checks of the matching only. Nothing here measures how well pi solves
problems, and nothing prints or asserts an acceptance verdict.
"""

import pytest

from app.modules.pi.evalkit import relevance, relevance_match

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
    assert relevance_match.amounts("50,000, then 60,000. ", bare=True)[0].lo == 50000.0


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


def test_a_stated_figure_is_exempt_only_in_its_own_unit() -> None:
    c = [limit("cannot spend more than 2 lakh")]
    same_unit = brief(c, figures=("3 lakh",))
    got = relevance.score_candidate(same_unit, "A new mill costs Rs 3 lakh")["verdict"]
    assert got != "violates_constraint"
    staff_said = brief(c, figures=("300000 staff",))
    got = relevance.score_candidate(staff_said, "A new mill costs Rs 3 lakh")["verdict"]
    assert got == "violates_constraint"


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
