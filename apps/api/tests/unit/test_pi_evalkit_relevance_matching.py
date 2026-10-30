"""FT-A3b: inflection, amount and constraint matching inside the relevance scorer.

Scripted code-path checks of the matching only. Nothing here measures how well pi solves
problems, and nothing prints or asserts an acceptance verdict.
"""

import pytest

from app.modules.pi.evalkit import relevance, relevance_match


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


def test_inflection_does_not_glue_different_words_or_touch_figures() -> None:
    assert relevance.stems("class") != relevance.stems("clas")
    assert relevance.stems("clerk") != relevance.stems("clear")
    assert relevance.stems("20000") == {"20000"} and relevance.stems("b2b") == {"b2b"}


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
    assert verdict(c, "Purchasing a feed mill would cut the bill") == "violates_constraint"
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
