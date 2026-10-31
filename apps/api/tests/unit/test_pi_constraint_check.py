"""L2-1: constraint_check is pure and reads the owner's stated limits. Statements are not limits,
floors are not ceilings, whole words only, unknown is a real answer."""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.pi import constraint_check as cc
from app.modules.pi.requirements_types import (
    Constraints,
    Limit,
    ProblemRequirements,
    Requirements,
    TriedItem,
)


def reqs(budget=None, deadline=None, cannot=(), tried=(), staff=None):
    constraints = Constraints(
        budget=Limit(budget) if budget else None,
        staff=Limit(staff) if staff else None,
        deadline=Limit(deadline) if deadline else None,
        cannot_change=tuple(Limit(c) for c in cannot),
    )
    return Requirements(
        problems=(
            ProblemRequirements(
                constraints=constraints,
                tried=tuple(TriedItem(w, o) for w, o in tried),
            ),
        )
    )


def check(option, **kw):
    """The verdict of the limits the test states. With no budget stated the "no budget, looks
    costly" probe is left out so each test reads one rule; it has its own tests below."""
    return cc._check_option(option, reqs(**kw), probe_budget="budget" in kw)


# ------------------------------------------------------------------------------ purity


def test_the_module_imports_nothing_from_evalkit_a_database_a_model_or_the_network():
    source = Path(cc.__file__).read_text(encoding="utf-8")
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert not [m for m in modules if "evalkit" in m]
    banned = ("sqlalchemy", "httpx", "requests", "socket", "openai", "anthropic", "asyncio")
    assert not [m for m in modules if m.split(".")[0] in banned]
    assert "app.modules.pi.requirements_read" not in modules


# ------------------------------------------------------------- whole-word verb families


@pytest.mark.parametrize(
    "word",
    ["employee", "employees", "appointment", "appointments", "discount", "discounts", "discover",
     "complaint", "complete", "product", "products", "receipt", "receipts", "marker", "evening",
     "cute", "care", "careful", "cars", "carpet", "marketplace", "orderly"],
)  # fmt: skip
def test_look_alike_words_belong_to_no_verb_family(word):
    assert cc.verb_families(word) == frozenset()


@pytest.mark.parametrize(
    "word,family",
    [("employ", "HIRE"), ("employed", "HIRE"), ("employing", "HIRE"), ("appoint", "HIRE"),
     ("discontinue", "STOP"), ("discontinued", "STOP"), ("produce", "MAKE"),
     ("producing", "MAKE"), ("receive", "ACCEPT"), ("received", "ACCEPT"), ("market", "PROMOTE"),
     ("marketing", "PROMOTE"), ("cut", "CUT"), ("cutting", "CUT"), ("use", "USE"),
     ("using", "USE"), ("used", "USE"), ("uses", "USE"), ("buying", "BUY"), ("bought", "BUY"),
     ("replaced", "CHANGE"), ("replacing", "CHANGE"), ("renting", "RENT")],
)  # fmt: skip
def test_inflected_verbs_reach_their_family_on_the_full_word(word, family):
    assert family in cc.verb_families(word)


# ----------------------------------------------------------------------- cannot_change


def test_replacing_the_system_the_owner_cannot_change_is_rejected_with_its_words():
    v = check("Replace the POS system with a cloud one", cannot=["we cannot change our POS system"])
    assert v.status == "violates" and v.rule == "cannot_change"
    assert "replace" in v.evidence and "pos" in v.evidence
    assert "cannot change" in v.reason or "cannot do" in v.reason


def test_adding_to_the_system_is_not_changing_it():
    v = check(
        "Add a barcode scanner next to the POS system", cannot=["we cannot change our POS system"]
    )
    assert v.status == "ok"


def test_a_bare_thing_in_cannot_change_means_it_cannot_be_changed():
    assert check("Switch to a new POS", cannot=["POS system"]).status == "violates"
    assert check("Print a weekly sales report", cannot=["POS system"]).status == "ok"


def test_the_same_verb_on_a_different_object_is_ok_but_on_a_generic_neighbour_unknown():
    limit = ["we cannot change our POS system"]
    assert check("Replace the website banner", cannot=limit).status == "ok"
    v = check("Replace the inventory system", cannot=limit)
    assert v.status == "unknown" and v.rule == "cannot_change"


def test_buying_is_rejected_but_renting_is_not_buying():
    limit = ["we cannot buy new tablets"]
    assert check("Buy a tablet for each cashier", cannot=limit).status == "violates"
    assert check("Purchasing tablets for the counter", cannot=limit).status == "violates"
    assert check("Rent a tablet for each cashier", cannot=limit).status == "ok"
    assert check("Lease tablets monthly", cannot=limit).status == "ok"


def test_a_verb_that_is_negated_or_replaced_is_not_proposed():
    limit = ["we cannot buy new tablets"]
    assert check("Rent a tablet instead of buying one", cannot=limit).status == "ok"
    assert check("There is no need to buy a tablet", cannot=limit).status == "ok"
    assert check("Rent a tablet, do not purchase tablets", cannot=limit).status == "ok"
    limit = ["we cannot change our POS system"]
    assert check("Keep the POS system, no need to replace it", cannot=limit).status == "ok"


def test_cannot_afford_a_thing_rejects_buying_it_and_leaves_renting_unknown():
    limit = ["we cannot afford new equipment"]
    assert check("Purchase new equipment for the kitchen", cannot=limit).status == "violates"
    v = check("Lease equipment for the kitchen", cannot=limit)
    assert v.status == "unknown"
    assert check("Reorganise the shelves by weight", cannot=limit).status == "ok"


def test_cannot_afford_an_outcome_is_a_goal_not_a_purchasable_object():
    limit = ["we cannot afford downtime"]
    v = check("Buy a backup generator so a power cut never causes downtime", cannot=limit)
    assert v.status == "ok"
    assert (
        check("Install a backup battery and avoid downtime during power cuts", cannot=limit).status
        == "ok"
    )
    assert check("Buy a backup generator", cannot=limit).status == "ok"
    v = check("Move the shop to the new system over the weekend, with some downtime", cannot=limit)
    assert v.status == "unknown" and "downtime" in v.evidence


def test_cannot_afford_to_do_something_is_an_action_limit():
    limit = ["we cannot afford to hire anyone"]
    assert check("Hire a part-time clerk for the evenings", cannot=limit).status == "violates"
    assert check("Train the existing team on the new scanner", cannot=limit).status == "ok"


def test_employee_is_not_employ_and_appointment_is_not_appoint():
    assert (
        check("Give each employee a login", cannot=["we cannot employ more people"]).status == "ok"
    )
    assert check("Employ a driver", cannot=["we cannot employ more people"]).status == "violates"
    v = check("Send appointment reminders to the manager", cannot=["we cannot appoint a manager"])
    assert v.status == "ok"
    assert (
        check("Appoint a manager for the branch", cannot=["we cannot appoint a manager"]).status
        == "violates"
    )


def test_discount_is_not_discontinue_and_product_is_not_produce():
    assert (
        check(
            "Offer a discount on slow items", cannot=["we cannot discontinue the old line"]
        ).status
        == "ok"
    )
    assert (
        check("Discontinue the old line", cannot=["we cannot discontinue the old line"]).status
        == "violates"
    )
    assert (
        check("Show the product labels clearly", cannot=["we cannot produce our own labels"]).status
        == "ok"
    )
    assert (
        check("Produce your own labels", cannot=["we cannot produce our own labels"]).status
        == "violates"
    )


def test_receipt_is_not_receive_market_the_place_is_not_market_the_verb():
    assert check("Print a receipt for each sale", cannot=["we cannot receive cash"]).status == "ok"
    assert (
        check("Receive cash at the counter", cannot=["we cannot receive cash"]).status == "violates"
    )
    limit = ["we cannot market online"]
    assert check("Go to the market on Saturday", cannot=limit).status == "ok"
    assert check("Put a marker on the shelf", cannot=limit).status == "ok"
    assert check("Market online every day", cannot=limit).status == "violates"


def test_cut_is_not_cute_and_car_is_not_care():
    assert check("Use cute packaging", cannot=["we cannot cut prices"]).status == "ok"
    assert check("Cut prices by ten percent", cannot=["we cannot cut prices"]).status == "violates"
    assert check("Add a care guide to each pack", cannot=["we cannot buy a car"]).status == "ok"
    assert check("Buy a car for deliveries", cannot=["we cannot buy a car"]).status == "violates"
    assert check("Evening shifts only", cannot=["we cannot even out the rota"]).status != "violates"


def test_using_and_used_reach_use():
    limit = ["we cannot use cloud software"]
    assert check("Using cloud software for orders", cannot=limit).status == "violates"
    assert check("The team used cloud software last year", cannot=limit).status == "violates"
    assert check("Use a paper register", cannot=limit).status == "ok"


def test_closing_and_stopping_take_their_own_object():
    assert (
        check("Close the shop on Sundays", cannot=["we cannot close on Sundays"]).status
        == "violates"
    )
    assert check("Open on Sundays", cannot=["we cannot close on Sundays"]).status == "ok"
    limit = ["we cannot stop taking cash"]
    assert check("Stop accepting cash at the counter", cannot=limit).status == "violates"
    assert check("Accept cash and cards", cannot=limit).status == "ok"


def test_a_noun_use_of_a_verb_word_is_not_the_verb():
    # a noun phrase that proposes a change is not a verb this check can weigh: unknown, never ok
    assert (
        check("A change to the layout of the shop", cannot=["we cannot change the layout"]).status
        == "unknown"
    )
    assert (
        check("Photograph the layout of the shop", cannot=["we cannot change the layout"]).status
        == "unknown"
    )
    assert (
        check("Keep the layout of the shop", cannot=["we cannot change the layout"]).status == "ok"
    )


def test_roman_urdu_limits_and_options():
    limit = ["hum naya system nahi kharid sakte"]
    assert check("Naya system kharid lein", cannot=limit).status == "violates"
    assert check("Kiraye par system lein", cannot=limit).status == "ok"


def test_other_scripts_are_unknown_never_ok():
    urdu_limit = ["ہم سسٹم تبدیل نہیں کر سکتے"]
    v = check("Replace the POS system", cannot=urdu_limit)
    assert v.status == "violates"  # an Urdu limit is read now: "we cannot change the system"
    v = check("Use a paper register", cannot=["ہم کچھ ٹھیک نہیں کر سکتے"])
    assert v.status == "unknown" and "read" in v.reason  # a limit it cannot read never clears
    v = cc.check_option(
        "نیا سسٹم خریدیں",
        reqs(cannot=["we cannot buy a new system"]),
        "ur",
    )
    assert v.status == "violates"  # an Urdu option is read now: buying a new system is buying
    hindi = "हम सिस्टम नहीं बदल सकते"
    assert check("Replace the POS", cannot=[hindi]).status == "unknown"


# --------------------------------------------------------------------------------- tried


FAILED_CALLS = [("reminder calls to customers", "didn't work, they ignored the calls")]


def test_repeating_what_failed_is_rejected():
    v = check("Call customers with reminder calls every morning", tried=FAILED_CALLS)
    assert v.status == "violates" and v.rule == "tried_failed"
    assert "reminder" in v.evidence or "call" in v.evidence


def test_a_different_approach_or_a_named_alternative_is_not_a_repeat():
    assert (
        check("Send WhatsApp messages instead of reminder calls", tried=FAILED_CALLS).status == "ok"
    )
    assert (
        check(
            "Take a different approach: a weekly summary of reminder calls missed",
            tried=FAILED_CALLS,
        ).status
        == "ok"
    )
    assert check("Send a weekly price list", tried=FAILED_CALLS).status == "ok"


def test_what_worked_may_be_repeated_and_an_unclear_outcome_is_unknown():
    assert (
        check(
            "Make reminder calls to customers",
            tried=[("reminder calls to customers", "it worked well")],
        ).status
        == "ok"
    )
    v = check("Make reminder calls to customers", tried=[("reminder calls to customers", "")])
    assert v.status == "unknown" and v.rule == "tried_failed"


def test_roman_urdu_failed_outcome():
    v = check("Customers ko reminder calls karein", tried=[("reminder calls", "kaam nahi kiya")])
    assert v.status == "violates"


# --------------------------------------------------------------------------------- amounts


@pytest.mark.parametrize(
    "text,value",
    [("Rs 50000", 50000), ("Rs. 50,000", 50000), ("Rs 3,00,000", 300000),
     ("Rs 3,000,000", 3000000), ("Rs 2.5m", 2500000), ("Rs 1m", 1000000), ("Rs 5 lakh", 500000),
     ("Rs 2 crore", 20000000), ("Rs 20 hazar", 20000), ("Rs 20k", 20000), ("PKR 1.5 lakh", 150000),
     ("Rs 10 to 20 hazar", 20000), ("between Rs 10000 and 25000", 25000), ("INR 3 lac", 300000)],
)  # fmt: skip
def test_amounts_are_parsed_with_units_magnitudes_grouping_and_ranges(text, value):
    found = [a for a in cc.parse_amounts(text) if a.role != "none"]
    assert len(found) == 1 and found[0].value == Decimal(value)


def test_indian_and_western_grouping_differ():
    indian = cc.parse_amounts("Rs 3,00,000")[0].value
    western = cc.parse_amounts("Rs 3,000,000")[0].value
    assert (indian, western) == (Decimal(300000), Decimal(3000000))


@pytest.mark.parametrize(
    "budget,over,fits",
    [("Rs 20000", "Buy a tablet for Rs 25000", "Buy a tablet for Rs 15000"),
     ("20k", "Buy a tablet for 25k", "Buy a tablet for 20k"),
     ("Rs 5 lakh", "It costs Rs 6,00,000", "It costs Rs 3,00,000"),
     ("Rs 5 lakh", "It costs Rs 3,000,000", "It costs Rs 4,50,000"),
     ("20 hazar", "Pay 3 lakh for a system", "Pay 15 hazar for a system"),
     ("under 5 lakh", "Invest Rs 2 crore in a system", "Invest Rs 4 lakh in a system")],
)  # fmt: skip
def test_a_cost_figure_above_the_ceiling_violates_and_one_within_it_is_ok(budget, over, fits):
    assert check(over, budget=budget).status == "violates"
    assert check(over, budget=budget).rule == "budget"
    assert check(fits, budget=budget).status == "ok"


@pytest.mark.parametrize(
    "option",
    ["Buy a 50000 tablet", "Invest 50000 in a system", "Get a system at 50000",
     "Buy a tablet for 1m", "Spend Rs 2.5m on a system", "Pay 50000 for the setup",
     "The setup costs 50,000", "Rs 50000 system with support"],
)  # fmt: skip
def test_cost_figures_in_their_usual_phrasings_are_costs(option):
    v = check(option, budget="Rs 20000")
    assert v.status == "violates", (option, v)


@pytest.mark.parametrize(
    "option",
    ["Sell the old mill for Rs 80000", "Charge Rs 50000 for a package",
     "This can save Rs 100000 a month", "You could earn 5 lakh more a year",
     "Revenue may grow by Rs 3,00,000", "Expect a profit of Rs 90000",
     "Buy a machine and sell it for Rs 80000"],
)  # fmt: skip
def test_income_and_benefit_figures_are_never_costs(option):
    v = check(option, budget="Rs 20000")
    assert v.status != "violates", (option, v)


def test_a_number_with_no_money_context_is_ignored():
    for option in ["Count the 60000 items every week", "Train 50 staff in 3 months",
                   "Keep 100000 records in the register", "Run it for 2026 customers",
                   "Order 5000 labels"]:  # fmt: skip
        assert check(option, budget="Rs 20000").status != "violates", option
    assert check("Install a 5m cable to the counter", budget="Rs 20000").status != "violates"


@pytest.mark.parametrize(
    "budget",
    ["Rs 20000 at most", "20000 or less", "should not cross 20000", "not more than Rs 20000",
     "up to 20k", "max 20000", "between 10000 and 20000", "10000 to 20000", "below 20000"],
)  # fmt: skip
def test_ceiling_phrasings_are_ceilings(budget):
    ceiling = cc.parse_ceiling(budget)
    assert ceiling.value == Decimal(20000), budget
    assert check("Buy a tablet for Rs 25000", budget=budget).status == "violates"
    assert check("Buy a tablet for Rs 18000", budget=budget).status == "ok"


def test_a_floor_is_never_a_ceiling_and_never_hides_a_later_ceiling():
    only_floor = cc.parse_ceiling("at least Rs 50000")
    assert only_floor.value is None and only_floor.floor_only
    assert check("Buy a tablet for Rs 90000", budget="at least Rs 50000").status == "unknown"
    for text in ["at least 2 staff so max 20000", "minimum 10000 with no more than 20000",
                 "at least Rs 5000 since we are small, up to Rs 20000",
                 "at least 5000 because we want quality but under 20000",
                 "at least 5000 and at most 20000"]:  # fmt: skip
        assert cc.parse_ceiling(text).value == Decimal(20000), text
    assert cc.parse_ceiling("minimum 10000, so around 20000").value == Decimal(20000)


def test_an_owner_figure_is_not_exempt_unless_unit_and_role_match():
    # the owner talks about 80000 as income; an option that SPENDS 80000 is still a cost
    requirements = Requirements(
        problems=(
            ProblemRequirements(
                constraints=Constraints(budget=Limit("Rs 20000")),
                expected_outcome="earn Rs 80000 a month",
            ),
        )
    )
    assert (
        cc.check_option("Spend Rs 80000 on a new system", requirements, "en").status == "violates"
    )
    assert cc.check_option("Sell the old mill for Rs 80000", requirements, "en").status == "ok"
    assert cc.check_option("Buy a tablet for Rs 20000", requirements, "en").status == "ok"


def test_zero_budget_rejects_any_cost_figure_and_unparsed_budget_is_unknown():
    assert check("Buy a tablet for Rs 5000", budget="no budget").status == "violates"
    v = check("Use a paper register", budget="tight")
    assert v.status == "unknown" and v.rule == "budget"


def test_spending_with_no_figure_is_unknown_and_a_free_option_is_ok():
    v = check("Buy a tablet for each cashier", budget="Rs 20000")
    assert v.status == "unknown" and v.rule == "budget"
    assert check("Use a paper register at the counter", budget="Rs 20000").status == "ok"


def test_another_currency_than_the_budget_is_unknown():
    assert check("Buy a tablet for $500", budget="Rs 20000").status == "unknown"


def test_a_figure_in_urdu_script_has_no_known_role_so_over_ceiling_is_unknown():
    # a figure with a currency word is money; one with no word the tables know has no role
    assert check("ٹیبلیٹ 50000 روپے", budget="Rs 20000").status == "violates"
    assert check("کچھ 50000", budget="Rs 20000").status == "unknown"
    assert check("ٹیبلیٹ 5000 روپے", budget="Rs 20000").status == "ok"


# ------------------------------------------------------------------------------ deadline


def test_a_deadline_the_option_plainly_cannot_meet_is_unknown_never_ok():
    v = check("The setup takes about 3 months", deadline="within 2 weeks")
    assert v.status == "unknown" and v.rule == "deadline" and "cannot meet" in v.reason
    assert check("Ready in 5 days", deadline="within 2 weeks").status == "ok"
    assert check("It takes a week to set up", deadline="by tomorrow").status == "unknown"


def test_a_deadline_with_no_comparable_time_is_unknown():
    assert check("Use a paper register", deadline="within 2 weeks").status == "unknown"
    assert check("Ready in 5 days", deadline="before Eid").status == "unknown"
    assert check("Ready in 5 days", deadline="by 15 March").status == "unknown"


def test_roman_urdu_durations():
    assert cc.parse_days("2 hafte mein", need_cue=True) == 14.0
    assert cc.parse_days("kal tak", need_cue=False) == 1.0
    assert check("Setup 3 mahine lagega", deadline="2 hafte mein").status == "unknown"


# ---------------------------------------------------------------------------- aggregation


def test_no_requirements_is_ok_but_unreadable_requirements_are_unknown():
    assert cc.check_option("Use a paper register", Requirements(), "en").status == "ok"
    assert cc.check_option("Use a paper register", None, "en").rule == "none"
    v = cc.check_option("Buy a tablet", Requirements(columns_available=False), "en")
    assert v.status == "unknown" and v.rule == "unreadable"
    assert cc.check_option("  ", reqs(budget="Rs 5"), "en").status == "unknown"


def test_a_violation_beats_an_unknown_and_unknown_beats_ok():
    v = check(
        "Buy a tablet for Rs 90000",
        budget="Rs 20000",
        deadline="before Eid",
    )
    assert v.status == "violates"
    v = check("Use a paper register", budget="Rs 20000", deadline="before Eid")
    assert v.status == "unknown" and v.rule == "deadline"
    assert check("Use a paper register", budget="Rs 20000", cannot=["POS system"]).status == "ok"


def test_staff_and_cause_do_not_decide_anything_yet():
    assert check("Use a paper register", staff="only 2 staff").status == "ok"


def test_the_verdict_is_deterministic():
    one = check("Replace the POS system", cannot=["POS system"], budget="Rs 5")
    two = check("Replace the POS system", cannot=["POS system"], budget="Rs 5")
    assert one == two


# ------------------------------------------------- audit lessons: robustness, text, scale


def test_homographs_fire_and_close_follow_the_owners_meaning():
    fire = ["we cannot fire anyone"]
    assert check("Fire two cashiers to save money", cannot=fire).status == "violates"
    assert check("Dismiss the driver", cannot=fire).status == "violates"
    for harmless in [
        "Run a monthly fire drill",
        "Add fire extinguishers",
        "Install a fire alarm for the staff room",
    ]:
        assert check(harmless, cannot=fire).status == "ok", harmless
    bare = ["we cannot fire"]  # no object stated: the guard alone separates the two senses
    assert check("Run a monthly fire drill", cannot=bare).status == "ok"
    assert check("Fire the cashier", cannot=bare).status == "violates"
    close = ["we cannot close"]
    assert check("Close the shop on Sundays", cannot=close).status == "violates"
    for harmless in ["Book a hall close to the station", "Keep a spare key close by"]:
        assert check(harmless, cannot=close).status == "ok", harmless


def test_invisible_marks_and_look_alike_letters_cannot_hide_or_fake_a_word():
    assert cc.norm("Rs 2​5000") == "rs 25000"
    assert cc.norm("B‮uy‏") == "buy"
    assert cc.norm("الْكَتاب") == cc.norm("الکتاب")
    assert cc.norm("أإآٱ") == cc.norm("اااا")  # alef forms
    assert cc.norm("ي ى") == cc.norm("ی ی")  # yeh forms
    assert cc.norm("ة ہ") == cc.norm("ه ه")  # heh forms
    assert cc.norm("Rs ５００００ ٥٠٠٠٠ ५००००") == "rs 50000 50000 50000"
    assert cc.norm("Вuy a tаblet") == "buy a tablet"  # Cyrillic letters inside Latin words
    assert cc.norm("Rs 5 l a k h") == "rs 5 lakh"  # letter-spacing collapsed
    over = "Buy a tablet for Rs 2​5000"
    assert check(over, budget="Rs 20000").status == "violates"
    assert check("Replace the POS", cannot=["we cannot chаnge the POS"]).status == "violates"
    assert check("Buy a tablet for Rs 5 l a k h", budget="Rs 20000").status == "violates"
    assert cc.norm("привет") == "привет"  # a Russian word is not folded into Latin


def test_letter_spaced_text_that_cannot_be_read_is_unknown_not_ok():
    v = check("B u y a t a b l e t", budget="Rs 20000")
    assert v.status == "unknown" and "spaced" in v.reason


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("fifty thousand rupees", 50000),
        ("two lakh", 200000),
        ("five hundred rupees", 500),
        ("twenty five thousand", 25000),
        ("one crore", 10000000),
        ("a million dollars", 1000000),
        ("pachas hazar rupay", 50000),
        ("do lakh rupay", 200000),
        ("paanch sau rupay", 500),
        ("पचास हज़ार रुपये", 50000),
        ("दो लाख रुपये", 200000),
        ("پچاس ہزار روپے", 50000),
        ("دو لاکھ روپے", 200000),
        ("خمسين ألف ريال", 50000),
        ("مئة ألف ريال", 100000),
    ],
)
def test_number_words_in_five_languages_are_amounts(text, value):
    found = [a.value for a in cc.parse_amounts(text, assume_money=True)]
    assert found == [Decimal(value)]


def test_number_words_make_a_cost_and_do_not_turn_a_count_into_money():
    assert check("Buy a tablet for fifty thousand rupees", budget="Rs 20000").status == "violates"
    assert check("Buy a tablet for pachas hazar rupay", budget="Rs 20000").status == "violates"
    assert check("Buy a tablet for ten thousand rupees", budget="Rs 20000").status == "ok"
    assert check("Sell fifty thousand eggs", budget="Rs 20000").status == "ok"
    assert check("Sell 50k eggs", budget="Rs 20000").status == "ok"
    assert check("Earn fifty thousand rupees extra", budget="Rs 20000").status == "ok"
    assert check("Hire one cashier", budget="Rs 20000").status != "violates"


def test_a_common_word_in_any_of_five_languages_is_never_support():
    shared = ["the", "we", "hum", "aap", "hai", "के", "है", "हम", "کے", "ہے", "ہم", "في", "من", "نحن"]  # noqa: E501
    for word in shared:
        assert word in cc.STOPWORDS, word
    for common in [
        "hamara hamare hamari",
        "کوئی نہیں میں",
        "على هذا نحن",
        "the and we",
        "आप यह वह",
    ]:
        assert cc._tried_words(common) == [], common  # nothing here can count as support
    assert cc._tried_words("hamara van") != []  # a real content word still does


def test_checks_never_raise_on_malformed_input():
    import random

    rng = random.Random(7)
    junk = [None, 0, 3.5, b"bytes", [], {}, ["x"], {"a": 1}, object(), "", " ", "\x00"]
    junk += ["​" * 30, "9" * 400, "Rs " * 200, "﷽" * 50, "a" * 3000]
    words = ["buy", "Rs", "50000", "lakh", "we", "cannot", "fire", "close", "tried", "failed"]
    words += ["ہزار", "हज़ार", "ألف", "k", "m", "3,00,000", "-", "to", "so", "at least", "کے"]
    for n in range(500):
        if n % 3 == 0:
            option = rng.choice(junk)
        else:
            option = " ".join(rng.choice(words) for _ in range(rng.randint(0, 12)))
        limit = rng.choice(junk[:6] + [" ".join(rng.choice(words) for _ in range(5))])
        shapes = [
            Requirements(),
            None,
            "not requirements",
            reqs(budget=limit if isinstance(limit, str) else None, cannot=[str(limit)]),
            Requirements(problems=(None,)),
            Requirements(problems=("x",)),
        ]
        for shape in shapes:
            verdict = cc.check_option(option, shape, rng.choice([None, "en", "ur", 5]))
            assert verdict.status in {"ok", "violates", "unknown"}
            assert isinstance(verdict.reason, str) and verdict.reason


def test_a_bad_input_is_unknown_with_a_reason_not_an_ok():
    for bad in (None, 5, [], b"x"):
        v = cc.check_option(bad, reqs(budget="Rs 20000"), "en")
        assert v.status == "unknown" and "not text" in v.reason


@pytest.mark.parametrize("size", [5000, 50000])
def test_long_input_is_checked_in_linear_time(size):
    import time

    unit = "Buy a tablet for Rs 25000 and use a paper register for 3 days. "
    heavy = [
        (unit * (size // len(unit) + 1))[:size],
        ("Rs " * size)[:size],
        ("1," * size)[:size],
        ("a " * size)[:size],
        ("fifty thousand " * size)[:size],
        ("​" * size),
        ("x " * size)[:size],
    ]
    r = reqs(
        budget="Rs 20000",
        cannot=["we cannot change the POS"],
        deadline="in 3 days",
        tried=[("reminder calls", "didn't work")],
    )
    started = time.perf_counter()
    for text in heavy:
        cc.check_option(text, r, "en")
    elapsed = time.perf_counter() - started
    assert elapsed < (1.0 if size == 5000 else 6.0), elapsed


def test_the_cost_of_a_long_input_grows_roughly_with_its_length():
    import time

    unit = "Buy a tablet for Rs 25000 and use a paper register for 3 days. "
    r = reqs(budget="Rs 20000", cannot=["we cannot change the POS"])

    def took(n):
        text = (unit * (n // len(unit) + 1))[:n]
        best = 9.0
        for _ in range(3):
            t = time.perf_counter()
            cc.check_option(text, r, "en")
            best = min(best, time.perf_counter() - t)
        return best

    small, large = took(5000), took(50000)
    assert large < max(small, 0.005) * 25  # quadratic code is ~100x


# ----------------------------------------- round 2: a stored limit never silently yields ok


def with_staff(option, staff):
    return cc._check_option(option, reqs_with_staff(staff), probe_budget=False)


def reqs_with_staff(staff):
    return Requirements(
        problems=(ProblemRequirements(constraints=Constraints(staff=Limit(staff))),)
    )


@pytest.mark.parametrize(
    ("option", "staff"),
    [
        ("Hire 5 more staff", "only 2 staff"),
        ("Add 3 people to the night shift", "only 2 staff"),
        ("Assign three people to inventory daily", "only 2 staff"),
        ("Recruit four workers for the counter", "at most 3 employees"),
        ("Hire a cashier", "no more staff"),
        ("Hire a cashier", "headcount is fixed"),
        ("Assign three people to inventory daily", "صرف دو لوگ"),
        ("Assign three people to inventory daily", "केवल दो लोग"),
        ("Hire pachas staff", "only 2 staff"),
    ],
)
def test_a_staff_limit_is_enforced_against_the_people_an_option_adds(option, staff):
    v = with_staff(option, staff)
    assert v.status == "violates" and v.rule == "staff" and v.evidence, (option, staff)


def test_a_staff_limit_within_reach_is_ok_and_a_missing_count_is_unknown():
    assert with_staff("Hire one cashier", "at most 2 staff").status == "ok"
    assert with_staff("Hire two cashiers", "up to two employees").status == "ok"
    assert with_staff("Use a paper register at the counter", "only 2 staff").status == "ok"
    v = with_staff("Hire more staff", "at most 2 staff")
    assert v.status == "unknown" and "count" in v.reason
    assert with_staff("naye staff ko rakh lein", "at most 2 staff").status == "unknown"


@pytest.mark.parametrize("staff", ["blah blah", "at least 2 staff", "", "the team", "x"])
def test_a_staff_limit_that_cannot_be_read_is_unknown_never_ok(staff):
    v = with_staff("Hire a cashier", staff)
    assert v.status == "unknown" and v.rule == "staff", staff


def test_the_staff_limit_numbers_in_five_languages():
    for text, cap in [("only 2 staff", 2), ("at most three employees", 3), ("max 10 people", 10),
                      ("صرف دو لوگ", 2), ("केवल दो लोग", 2), ("sirf paanch staff", 5),
                      ("فقط ثلاثة موظفين", 3), ("hiring is frozen", 0)]:  # fmt: skip
        assert cc.parse_staff_limit(text) == cap, text
    assert cc.parse_staff_limit("at least 2 staff") is None
    assert cc.parse_staff_limit("we do what we can") is None  # "do" is not the number two


@pytest.mark.parametrize(
    "vague",
    ["the thing", "x", "etc", "see above", "as discussed", "same as before", "they know",
     "you know what", "we cannot say", "we cannot change the thing", "the system"],
)  # fmt: skip
def test_a_vague_limit_is_unknown_never_ok(vague):
    for option in ["Replace the POS", "Train a cashier"]:
        v = check(option, cannot=[vague])
        assert v.status == "unknown", (vague, option, v)


@pytest.mark.parametrize(
    ("option", "limit"),
    [
        ("Start home delivery", "we cannot deliver"),
        ("Open a shop in Lahore", "we cannot expand beyond Karachi"),
        ("Open in Lahore", "outside Karachi is not possible"),
        ("Ship nationwide", "only Karachi"),
        ("Install a computer system", "we cannot use computers"),
        ("Use a cloud tool", "no internet at the shop"),
        ("Open on Saturday and Sunday", "we cannot work weekends"),
        ("Visit suppliers in Dubai", "we cannot travel"),
        ("Open until midnight", "we cannot stay open late"),
        ("Add a 300 sqft display area", "the shop is only 100 sqft"),
        ("Deliver by van", "we have no car"),
    ],
)
def test_location_resource_hours_size_and_verb_limits_are_real_rules(option, limit):
    v = check(option, cannot=[limit])
    assert v.status == "violates" and v.rule == "cannot_change" and v.evidence, (option, limit)


def test_those_limits_do_not_reject_an_option_that_does_not_touch_them():
    cases = [("Use a paper register at the counter", "we cannot deliver"),
             ("Open a second counter in Karachi", "only Karachi"),
             ("Add a 50 sqft display area", "the shop is only 100 sqft"),
             ("Use a paper register", "we have no car"),
             ("Open on Monday morning", "we cannot work weekends"),
             ("Use a paper register", "we cannot stay open late"),
             ("Use a paper register", "no internet at the shop")]  # fmt: skip
    for option, limit in cases:
        assert check(option, cannot=[limit]).status == "ok", (option, limit)
    # a place the lexicon does not know, and a size in another unit: unknown, never ok
    assert check("Open a branch in Wazirabad", cannot=["only Karachi"]).status == "unknown"
    assert (
        check("Add a 30 square metre area", cannot=["the shop is only 100 sqft"]).status
        == "unknown"
    )
    assert check("Open a branch", cannot=["only Karachi"]).status == "unknown"
    # a verb the limit mentions but the check does not enforce is unknown for any option
    assert (
        check("Use a paper register", cannot=["we cannot photograph receipts"]).status == "unknown"
    )


@pytest.mark.parametrize(
    "limit",
    ["do not hire anyone", "don't hire", "not to hire anyone", "shouldn't hire anyone",
     "hiring is frozen", "there is a hiring freeze", "hiring is not allowed", "avoid hiring",
     "no more staff", "headcount is fixed", "we cannot take on more staff",
     "cannot afford staff", "we have no budget to hire", "we cannot hire more staff"],
)  # fmt: skip
def test_every_way_of_saying_no_hiring_rejects_a_hire(limit):
    assert check("Hire a cashier", cannot=[limit]).status == "violates", limit


@pytest.mark.parametrize(
    "option",
    ["Hire a developer", "Hire an accountant", "Hire a designer", "Hire a plumber",
     "Hire a part-time marketer", "Hire an agency", "Recruit a sales rep",
     "Take on someone for the counter"],
)  # fmt: skip
def test_a_hire_of_any_role_breaks_a_no_hiring_limit(option):
    assert check(option, cannot=["we cannot hire more staff"]).status == "violates", option
    assert check("Train the cashier", cannot=["we cannot hire more staff"]).status == "ok"


@pytest.mark.parametrize(
    "limit",
    ["we can't hire; we can train", "we cannot hire. we can train", "cannot hire, but we can train",
     "we cannot hire because rent is high", "we cannot change the P.O.S."],
)  # fmt: skip
def test_a_trailing_clause_does_not_blind_the_limit(limit):
    option = "Replace the POS" if "P.O.S" in limit else "Hire a cashier"
    assert check(option, cannot=[limit]).status == "violates", limit
    assert check("Use a paper register", cannot=[limit]).status == "ok", limit


def test_limit_clauses_keep_each_limit_and_drop_the_offer_to_do_something_else():
    assert cc.limit_clauses("we can't hire; we can train") == ["we can't hire"]
    assert len(cc.limit_clauses("we cannot hire, we cannot fire")) == 2
    assert cc.limit_clauses("POS system") == ["pos system"]  # no limit wording: the whole text
    assert cc.limit_clauses("we cannot change the POS, the printer") == [
        "we cannot change the pos the printer"
    ]


@pytest.mark.parametrize(
    "option",
    [
        "Buy a scanner for Rs 90 000",
        "Buy a scanner for PKR 90 000",
        "Buy a scanner for Rs９０ ０００",
        "Buy a scanner for Rs 9 0 0 0 0",
        "Buy a scanner for 9 0 , 0 0 0 rupees",
        "Buy a scanner for 1,2 lakh",
        "Buy 3 tablets at Rs 20,000 each",
    ],
)
def test_spaced_split_and_multiplied_figures_are_read_as_money(option):
    assert check(option, budget="50k").status == "violates", option


@pytest.mark.parametrize(
    "option",
    ["price: 90000", "software 1 lakh", "laptop 100000 ka", "ek lakh ka software",
     "scanner 80000 mein", "Pay Rs 30,000 per month",
     "Buy a scanner for 90000 ريال", "Buy a scanner for 90000 USD", "naya scanner kharidein"],
)  # fmt: skip
def test_a_figure_that_cannot_be_attributed_is_unknown_never_a_free_ok(option):
    v = check(option, budget="Rs 50000")
    assert v.status == "unknown", (option, v)


def test_a_per_period_figure_is_compared_over_the_same_period_only():
    assert check("Pay Rs 30,000 per month", budget="Rs 20000 per month").status == "violates"
    assert check("Pay Rs 10,000 per month", budget="Rs 20000 per month").status == "ok"
    assert check("Pay Rs 5,000", budget="Rs 20000 per month").status == "ok"
    assert check("Pay Rs 50,000", budget="Rs 20000 per month").status == "unknown"
    assert cc.parse_amounts("Rs 3 per month")[0].period == "month"
    assert cc.parse_amounts("Rs 3 yearly")[0].period == "year"


def test_each_means_per_piece_and_a_bare_each_is_one():
    assert cc.parse_amounts("Buy 3 tablets at Rs 20,000 each")[-1].value == Decimal(60000)
    assert cc.parse_amounts("Buy three tablets at Rs 20,000 each")[-1].value == Decimal(60000)
    assert cc.parse_amounts("Buy a tablet at Rs 20,000 each")[-1].value == Decimal(20000)
    assert cc.parse_amounts("Buy 3 tablets at Rs 20,000")[-1].value == Decimal(20000)


def test_roman_urdu_spend_verbs_with_no_figure_are_unknown_and_zyada_nahi_is_a_ceiling():
    for option in ["naya scanner kharidein", "scanner khareedna hai", "scanner lena hai"]:
        assert check(option, budget="Rs 20000").status == "unknown", option
    ceiling = cc.parse_ceiling("50 hazar se zyada nahi")
    assert ceiling.value == Decimal(50000) and not ceiling.floor_only
    assert check("Buy one for Rs 60000", budget="50 hazar se zyada nahi").status == "violates"
    assert check("Buy one for Rs 20000", budget="50 hazar se zyada nahi").status == "ok"


def test_an_option_longer_than_the_cap_is_unknown_without_being_scanned():
    r = reqs(budget="Rs 20000", cannot=["we cannot change the POS"])
    for text in ["9" * 10_000, "Replace the POS " * 400, "a " * 5000]:
        v = cc.check_option(text, r, "en")
        assert v.status == "unknown" and "too long" in v.reason
    just_under = ("Use a paper register. " * 200)[: cc.OPTION_CHARS]
    assert cc.check_option(just_under, r, "en").status == "ok"


@pytest.mark.parametrize(
    "make",
    [
        lambda n: "9" * n,
        lambda n: "9 " * (n // 2),
        lambda n: "Rs 25000 " * (n // 9),
        lambda n: "buy tablet " * (n // 11),
        lambda n: "a b c " * (n // 6),
        lambda n: "fifty thousand " * (n // 15),
        lambda n: "1," * (n // 2),
    ],
    ids=["digits", "spaced digits", "amounts", "words", "spaced letters", "number words", "commas"],
)
def test_the_scanners_grow_linearly_at_1k_10k_and_100k(make):
    import time

    def took(n):
        text = make(n)
        best = 9.0
        for _ in range(3):
            t = time.perf_counter()
            cc.parse_amounts(text)
            cc.norm(text)
            cc.words_of(text)
            best = min(best, time.perf_counter() - t)
        return best

    small, mid, big = took(1000), took(10_000), took(100_000)
    floor = 0.002
    assert mid < max(small, floor) * 60 and big < max(mid, floor) * 40, (small, mid, big)


def test_investigating_or_ruling_out_a_change_is_not_proposing_it():
    limit = ["we cannot change the POS system"]
    for ok_option in ["Measure first whether replacing the POS is worth it",
                      "Replacing the POS is not an option, so train staff",
                      "Check whether switching the POS system would help",
                      "Replacing the POS is not possible, so keep it"]:  # fmt: skip
        assert check(ok_option, cannot=limit).status == "ok", ok_option
    assert check("Replace the POS system next month", cannot=limit).status == "violates"


def test_roman_urdu_instead_of_names_what_comes_before_it():
    tried = [("Facebook ads", "nahi chala")]
    assert check("Facebook ads ki jagah referral lein", tried=tried).status == "ok"
    assert check("Facebook ads dobara chalayein", tried=tried).status != "ok"


@pytest.mark.parametrize(
    ("option", "limit"),
    [
        ("Raise prices by 5%", "we cannot change our prices"),
        ("Cut prices on weekdays", "we cannot change our prices"),
        ("Terminate the contract of the cleaner", "we cannot fire anyone"),
        ("naya POS kharid lein", "hum POS badal nahi sakte"),
        ("prices barha dein", "hum prices badal nahi sakte"),
        ("staff ko nikal dein", "we cannot fire anyone"),
    ],
)
def test_verb_synonyms_and_roman_urdu_reach_the_limit(option, limit):
    assert check(option, cannot=[limit]).status == "violates", (option, limit)


# --------------------------------------------- killing the survivors of the first audit


def test_a_rule_that_raises_is_unknown_never_ok(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cc, "_check_budget", boom)
    v = cc.check_option("Buy a tablet", reqs(budget="Rs 20000"), "en")
    assert v.status == "unknown" and v.rule == "unreadable"


def test_requirements_of_a_wrong_type_are_unknown():
    v = cc.check_option("Buy a tablet", "not requirements", "en")
    assert v.status == "unknown" and "form" in v.reason


def test_a_limit_text_is_clipped_so_a_huge_one_is_not_scanned():
    budget = "Rs 20000" + " " * (cc.LIMIT_CHARS + 500) + " under Rs 1"
    assert check("Buy a tablet for Rs 5000", budget=budget).status == "ok"
    assert len(cc._clip(Limit("x" * 5000)).text) == cc.LIMIT_CHARS
    short = Limit("short")
    assert cc._clip(short) is short


def test_an_option_in_another_script_is_unknown_for_every_rule():
    assert check("ٹیبلیٹ خریدیں", budget="Rs 20000").status == "unknown"
    assert check("کچھ اور سوچیں", cannot=["we cannot change the POS"]).status == "unknown"
    assert check("کچھ اور سوچیں", tried=[("reminder calls", "failed")]).status == "unknown"


def test_two_ceilings_choose_the_lower_and_figures_that_are_not_money_are_ignored():
    assert cc.parse_ceiling("under Rs 20000 or up to Rs 50000").value == Decimal(20000)
    assert cc.parse_ceiling("up to Rs 50000, under Rs 20000").value == Decimal(20000)
    roles = lambda text: [a.role for a in cc.parse_amounts(text)]  # noqa: E731
    assert roles("Increase the price by 50000%") == ["none"]  # a percentage
    assert roles("Order 5000 labels") == ["none"]  # a count of things
    assert roles("Launch in 2026 and buy a tablet") == ["none"]  # a year
    assert roles("Buy 5 tablets") == ["none"]  # a small count
    assert roles("Pay Rs 5") == ["cost"]
    assert check("Launch the website in 2026", budget="Rs 1000").status == "ok"


def test_deadline_comparisons_and_their_cue():
    assert cc.parse_days("in 3 days", need_cue=True) == 3
    assert cc.parse_days("3 days of training", need_cue=True) is None
    assert cc.parse_days("3 days", need_cue=False) == 3
    assert check("Set up in 2 weeks", deadline="within 3 days").status == "unknown"
    assert check("Set up in 2 days", deadline="within 3 days").status == "ok"
    assert check("Set up soon", deadline="within 3 days").status == "unknown"
    assert check("Set up in 2 days", deadline="by the 5th of March").status == "unknown"


def test_tried_items_with_nothing_to_compare_or_in_another_script_are_unknown():
    assert check("Call the customers", tried=[("the", "failed")]).status == "unknown"
    # it overlaps with something tried whose outcome is not stated: never a free ok
    assert check("Call the customers", tried=[("reminder calls", "")]).status == "unknown"
    assert check("Post a notice on the door", tried=[("reminder calls", "")]).status == "ok"
    assert check("Call the customers", tried=[("اشتہار", "failed")]).status == "unknown"
    assert check("Send reminder calls", tried=[("reminder calls", "failed")]).status == "violates"
    # most of the tried words must be repeated before it counts as repeated (60 percent)
    assert check("Send reminder emails", tried=[("reminder calls", "failed")]).status in {
        "ok",
        "unknown",
    }
    assert (
        check("Send reminder calls", tried=[("daily reminder calls", "failed")]).status
        == "violates"
    )
    partial = check("Send emails and calls", tried=[("reminder emails calls batches", "failed")])
    assert partial.status == "unknown" and "overlaps" in partial.reason


def test_a_limit_with_a_verb_the_check_does_not_know_is_unknown_for_every_option():
    v = check("Use a paper register", cannot=["we cannot photograph receipts"])
    assert v.status == "unknown" and "not one this check enforces" in v.reason
    v = check("Photograph the receipts daily", cannot=["we cannot photograph receipts"])
    assert v.status == "unknown" and "receipt" in " ".join(v.evidence)


def test_a_many_word_object_needs_half_of_its_words_to_match():
    limit = ["we cannot change the front desk booking calendar"]  # four object words, two needed
    assert check("Replace the front desk booking calendar", cannot=limit).status == "violates"
    assert check("Replace the booking calendar", cannot=limit).status == "violates"  # 2 of 4
    assert check("Replace the booking printer", cannot=limit).status != "violates"  # 1 of 4


def test_hire_and_add_staff_and_keep_forms():
    assert check("Add two cashiers", cannot=["we cannot hire more staff"]).status == "violates"
    assert check("Add fire extinguishers", cannot=["we cannot hire more staff"]).status == "ok"
    assert check("Hire a cashier", cannot=["we cannot add staff"]).status == "violates"
    assert check("Replace the POS", cannot=["keep our POS system"]).status == "violates"
    assert check("Keep the POS system", cannot=["keep our POS system"]).status == "ok"
    assert check("Replace the printer", cannot=["keep our POS system"]).status == "ok"


def test_renting_what_the_owner_cannot_afford_to_buy_is_unknown_not_ok():
    v = check("Rent a new oven", cannot=["we cannot afford a new oven"])
    assert v.status == "unknown" and "renting" in v.reason


def test_currency_is_pulled_apart_from_digits_and_text_is_normalised_the_same_way_in_ascii():
    assert cc.norm("PKR50000 and Rs500") == "pkr 50000 and rs 500"
    assert cc.norm("A`b") == "a'b"
    assert cc.norm("Ｒｓ５０００") == cc.norm("Rs5000")
    assert cc.norm(None) == "" and cc.norm(5) == ""
    assert cc.norm("p.o.s. system") == "pos system"
    assert cc.norm("Rs 90 000") == "rs 90000"
    assert cc.norm("1,2 lakh") == "1.2 lakh"
    assert cc.norm("9 0 , 0 0 0") == "90,000"


def test_a_role_no_list_knows_is_still_a_hire_and_a_budget_with_no_currency_meets_a_foreign_one():
    for option in ["Hire a welder", "Hire a pastry chef", "Recruit a florist"]:
        assert check(option, cannot=["we cannot hire more staff"]).status == "violates", option
        assert check(option, cannot=["hiring is frozen"]).status == "violates", option
    for option in [
        "Buy a scanner for 90000 USD",
        "Buy a scanner for 90000 ريال",
        "Buy a scanner for $900",
    ]:
        v = check(option, budget="50000")
        assert v.status == "unknown" and "currency" in v.reason, option


def test_buying_something_for_a_thing_is_not_changing_it_but_buying_a_new_one_is():
    limit = ["we cannot change our POS"]
    assert check("Buy paper rolls for the POS", cannot=limit).status == "ok"
    assert check("Buy a new POS", cannot=limit).status == "violates"
    assert check("Buy another POS", cannot=limit).status == "violates"


def test_a_roman_urdu_hiring_limit_rejects_a_hire_of_any_role():
    limit = ["hum staff bharti nahi kar sakte"]
    assert check("Hire a welder", cannot=limit).status == "violates"
    assert check("Use a paper register", cannot=limit).status == "ok"


def test_a_hindi_buy_with_a_cost_above_the_budget_violates():
    assert check("scanner खरीदें 80 हज़ार में", budget="Rs 50000").status == "violates"


# ------------------------------- round 3: options in Urdu script, Arabic and Hindi are read

HIRE_LIMIT = ["we cannot hire more staff"]
POS_LIMIT = ["we cannot change the POS"]
PRICE_LIMIT = ["we cannot change our prices"]
CLOSE_LIMIT = ["we cannot close the shop"]

GOLDEN = {
    "urdu": {
        "violates": [
            ("نیا کلرک رکھیں", HIRE_LIMIT),
            ("POS بدلیں", POS_LIMIT),
            ("نیا POS خریدیں", POS_LIMIT),
            ("قیمتیں بڑھائیں", PRICE_LIMIT),
            ("دکان بند کریں", CLOSE_LIMIT),
            ("اسٹاف کو نکالیں", ["we cannot fire anyone"]),
        ],
        "ok": [
            ("نیا کلرک نہ رکھیں", HIRE_LIMIT),
            ("نیا کلرک رکھنا نہیں", HIRE_LIMIT),
            ("جانچیں کہ POS بدلیں", POS_LIMIT),
            ("POS رکھیں", POS_LIMIT),
            ("دکان کھولیں", CLOSE_LIMIT),
        ],
        "unknown": [
            ("کچھ اور سوچیں", HIRE_LIMIT),
            ("نیا کلرک رکھیں اور میز سجائیں", ["we cannot change the POS"]),
        ],
    },
    "arabic": {
        "violates": [
            ("توظيف موظف جديد", HIRE_LIMIT),
            ("استبدال نظام POS", POS_LIMIT),
            ("رفع الأسعار", PRICE_LIMIT),
            ("إغلاق المتجر", CLOSE_LIMIT),
            ("فصل الموظفين", ["we cannot fire anyone"]),
        ],
        "ok": [
            ("لا نوظف موظف جديد", HIRE_LIMIT),
            ("تحقق من تغيير نظام POS", POS_LIMIT),
            ("فتح المتجر", CLOSE_LIMIT),
        ],
        "unknown": [
            ("فكر في شيء آخر", HIRE_LIMIT),
            ("توظيف موظف جديد مع طاولة", POS_LIMIT),
        ],
    },
    "hindi": {
        "violates": [
            ("नया कर्मचारी रखें", HIRE_LIMIT),
            ("नया क्लर्क भर्ती करें", HIRE_LIMIT),
            ("POS बदलें", POS_LIMIT),
            ("नया POS खरीदें", POS_LIMIT),
            ("कीमतें बढ़ाएं", PRICE_LIMIT),
            ("दुकान बंद करें", CLOSE_LIMIT),
        ],
        "ok": [
            ("नया कर्मचारी न रखें", HIRE_LIMIT),
            ("जाँचें कि POS बदलें", POS_LIMIT),
            ("दुकान खोलें", CLOSE_LIMIT),
        ],
        "unknown": [
            ("कुछ और सोचें", HIRE_LIMIT),
            ("नया कर्मचारी रखें और मेज़ सजाएं", POS_LIMIT),
        ],
    },
}


@pytest.mark.parametrize("language", sorted(GOLDEN))
@pytest.mark.parametrize("expected", ["violates", "ok", "unknown"])
def test_golden_options_in_urdu_arabic_and_hindi_meet_the_same_limits(language, expected):
    for option, limit in GOLDEN[language][expected]:
        v = check(option, cannot=limit)
        assert v.status == expected, (language, option, limit, v)


def test_a_violation_in_another_script_names_the_limit_and_the_words():
    v = check("نیا کلرک رکھیں", cannot=HIRE_LIMIT)
    assert v.status == "violates" and v.rule == "cannot_change" and v.evidence


def test_the_reading_tables_turn_known_words_into_english_and_count_the_unknown():
    mapped, read, unread = cc.scripts.to_english(
        cc.norm("نیا کلرک رکھیں"),
        cc.SCRIPT_TABLE,
        cc.SCRIPT_STOP,
        is_known=lambda w: False,
        is_person=lambda w: cc.object_key(w) == "STAFF",
        is_verb=lambda w: bool(cc.verb_families(w)),
    )
    assert mapped == "new clerk hire" and read == 3 and unread == 0
    for text, expected in [("POS رکھیں", "pos keep"), ("نیا کلرک نہ رکھیں", "new clerk not hire")]:
        out = cc.scripts.to_english(
            cc.norm(text),
            cc.SCRIPT_TABLE,
            cc.SCRIPT_STOP,
            is_known=lambda w: False,
            is_person=lambda w: cc.object_key(w) == "STAFF",
            is_verb=lambda w: bool(cc.verb_families(w)),
        )[0]
        assert out == expected, text
    assert cc._option("کچھ سوچیں").latin is False  # nothing in it is known
    assert cc._option("کچھ اور سوچیں").unread == 2  # "اور" (and) is known, the rest is not


def test_property_an_option_in_any_script_with_an_unrecognised_verb_is_never_ok():
    import random

    rng = random.Random(23)
    alphabets = {
        "urdu": "ابتثجحخدرزسشصضطظعغفقلمنہوی",
        "arabic": "ابتثجحخدذرزسشصضطظعغفقلمنهوي",
        "hindi": "कखगघचछजझटठडढतथदधनपफबभमयरलवशसह",
    }
    known = set(cc.SCRIPT_TABLE) | set(cc.SCRIPT_STOP) | set(cc.SMALL_NUMBER_WORDS)
    limits = [
        HIRE_LIMIT, POS_LIMIT, PRICE_LIMIT, CLOSE_LIMIT, ["we cannot fire anyone"],
        ["we cannot afford a new oven"], ["we cannot deliver"], ["only Karachi"],
    ]  # fmt: skip
    nouns = ["کلرک", "نظام", "قیمتیں", "दुकान", "المتجر", "POS", "staff"]  # known nouns, no verb
    seen = 0
    for _ in range(400):
        alphabet = alphabets[rng.choice(sorted(alphabets))]
        words = []
        for _ in range(rng.randint(1, 5)):
            word = "".join(rng.choice(alphabet) for _ in range(rng.randint(3, 6)))
            if cc.norm(word) not in known:
                words.append(word)
        if rng.random() < 0.5:
            words.insert(rng.randint(0, len(words)), rng.choice(nouns))
        option = " ".join(words)
        for requirement in (reqs(cannot=rng.choice(limits)), reqs(staff="only 2 staff")):
            v = cc._check_option(option, requirement, probe_budget=False)
            assert v.status != "ok", (option, v)
            seen += 1
    assert seen == 800


def test_a_known_verb_with_an_unknown_word_is_unknown_not_ok_but_still_violates_when_it_does():
    assert check("نیا کلرک رکھیں اور میز سجائیں", cannot=POS_LIMIT).status == "unknown"
    assert check("نیا کلرک رکھیں اور میز سجائیں", cannot=HIRE_LIMIT).status == "violates"


@pytest.mark.parametrize(
    "option",
    ["دو اور کلرک رکھیں", "توظيف موظفين اثنين", "दो और क्लर्क रखें", "ہم دو کلرک رکھیں"],
)
def test_staff_caps_are_enforced_against_hires_in_urdu_arabic_and_hindi(option):
    v = with_staff(option, "only 1 staff")
    assert v.status == "violates" and v.rule == "staff", option
    assert with_staff(option, "at most 5 staff").status == "ok", option
    # "only 5 staff" states the team: hiring any more breaks it
    assert with_staff(option, "only 5 staff").status == "violates", option


def test_staff_caps_in_the_docstring_and_in_the_gate_are_enforced():
    assert "not enforced (no rule for them yet)" not in " ".join((cc.__doc__ or "").split())
    assert "ceiling on the people" in (cc.__doc__ or "")
    assert with_staff("Hire 3 more staff", "at most 2 employees").status == "violates"
    assert with_staff("Assign 2 people to stock", "at most 2 employees").status == "ok"


@pytest.mark.parametrize(
    "option", ["Take a deposit through an app", "mehnga job tracking system", "Buy a tablet",
               "Install a new system", "Subscribe to a software tool"],
)  # fmt: skip
def test_with_no_budget_stated_a_costly_idea_is_unknown_never_clear(option):
    for requirement in (None, Requirements(), reqs(cannot=["we cannot change the POS"])):
        v = cc.check_option(option, requirement, "en")
        assert v.status == "unknown" and v.rule == "budget", (option, requirement, v)
        assert "no budget" in v.reason


def test_with_no_budget_stated_a_free_idea_is_clear_and_a_stated_budget_is_compared():
    assert cc.check_option("Ask customers for referrals", None, "en").status == "ok"
    assert cc.check_option("Use a paper register", reqs(cannot=POS_LIMIT), "en").status == "ok"
    assert cc.check_option("Buy a tablet for Rs 5000", reqs(budget="Rs 20000"), "en").status == "ok"
    assert (
        cc.check_option("Buy a tablet for Rs 50000", reqs(budget="Rs 20000"), "en").status
        == "violates"
    )
    # an option in another script that costs money with no budget stated is unknown too
    assert cc.check_option("نیا ٹیبلیٹ خریدیں", None, "en").status == "unknown"


def test_a_limit_about_promising_a_topic_is_not_a_limit_on_the_topic():
    limit = ["we cannot promise delivery days"]
    for fine in ["Ask the courier for a tracking link", "Use the courier's own delivery estimate",
                 "Tell customers the courier will message them"]:  # fmt: skip
        assert check(fine, cannot=limit).status == "ok", fine
    for promise in [
        "Promise delivery in 2 days",
        "Guarantee next-day delivery",
        "We assure delivery by Friday",
    ]:
        assert check(promise, cannot=limit).status == "violates", promise
    assert check("Never promise delivery days", cannot=limit).status == "ok"
    assert cc.parse_limit("we cannot promise delivery days").kind == "promise"


def test_a_new_one_of_the_thing_that_cannot_change_violates():
    limit = ["we cannot change courier"]
    assert check("Use a new courier", cannot=limit).status == "violates"
    assert check("Switch to another courier", cannot=limit).status == "violates"
    assert check("Try a new courier for Lahore", cannot=limit).status == "violates"
    assert check("Ask the courier for a tracking link", cannot=limit).status == "ok"
    assert check("Use a new packing box", cannot=limit).status == "ok"
    assert check("Measure whether a new courier is worth it", cannot=limit).status == "ok"


# ------------- round 4: LIMITS written in Urdu script, Arabic and Hindi are rules too

LIMIT_GOLDEN = {
    "urdu": {
        "violates": [
            ("نیا کلرک رکھیں", "ہم مزید عملہ نہیں رکھ سکتے"),
            ("POS بدلیں", "ہم POS نہیں بدل سکتے"),
            ("دکان بند کریں", "ہم دکان بند نہیں کر سکتے"),
            ("ڈیلیوری شروع کریں", "ہم ڈیلیوری نہیں کر سکتے"),
            ("ڈیلیوری کے دن کا وعدہ کریں", "ہم ڈیلیوری کے دنوں کا وعدہ نہیں کر سکتے"),
            ("کمپیوٹر پر ڈیش بورڈ بنائیں", "یہ صرف فون پر چلنا چاہیے"),
        ],
        "ok": [
            ("واٹس ایپ پر پیغام بھیجیں", "یہ صرف فون پر چلنا چاہیے"),
            ("ایک نئی ٹیبلیٹ خریدیں", "ہم مزید عملہ نہیں رکھ سکتے"),
            (
                "کاغذ رجسٹر رکھیں",
                "ہم POS نہیں بدل سکتے",
            ),  # all of it is understood: keeping a register
        ],
        "unknown": [
            ("POS بدلیں", "ہم کچھ ٹھیک نہیں کر سکتے"),
            ("نیا سسٹم خریدیں", "ہمارے پاس سسٹم نہیں ہے"),
        ],
    },
    "arabic": {
        "violates": [
            ("توظيف موظف جديد", "لا نستطيع توظيف موظفين جدد"),
            ("استبدال نظام POS", "لا نستطيع تغيير نظام POS"),
            ("إغلاق المتجر", "لا نستطيع إغلاق المتجر"),
            ("افتح فرعا في لاهور", "نعمل فقط في كراتشي"),
            ("وظفوا طباخين اثنين", "لا نستطيع توظيف المزيد"),
        ],
        "ok": [("فتح المتجر", "لا نستطيع إغلاق المتجر")],
        "unknown": [
            ("كورير جديد", "لا نستطيع وعد الزبائن بأيام التوصيل"),
            ("فتح المتجر", "لا نستطيع شيئا"),
        ],
    },
    "hindi": {
        "violates": [
            ("नया कर्मचारी रखें", "हम और कर्मचारी नहीं रख सकते"),
            ("POS बदलें", "हम POS नहीं बदल सकते"),
        ],
        "ok": [("फोन पर संदेश भेजें", "यह केवल फ़ोन पर चलना चाहिए")],
        "unknown": [("दुकान खोलें", "हम कुछ ठीक नहीं कर सकते")],
    },
}


@pytest.mark.parametrize("language", sorted(LIMIT_GOLDEN))
@pytest.mark.parametrize("expected", ["violates", "ok", "unknown"])
def test_golden_limits_in_urdu_arabic_and_hindi_become_rules(language, expected):
    for option, limit in LIMIT_GOLDEN[language][expected]:
        v = check(option, cannot=[limit])
        assert v.status == expected, (language, option, limit, v)


def test_a_limit_in_another_script_is_localised_into_english_order():
    for source, _verb, word in [
        ("ہم POS نہیں بدل سکتے", "change", "pos"),
        ("لا نستطيع تغيير نظام POS", "change", "pos"),
        ("हम और कर्मचारी नहीं रख सकते", "hire", "employee"),
    ]:
        mapped = cc.localise_limit(source)[0].lower().split()
        assert mapped[:3] == ["we", "cannot", mapped[2]] and cc.verb_families(mapped[2]), source
        assert word in mapped, source
    text, unread = cc.localise_limit("ہم POS نہیں بدل سکتے")
    assert unread == 0
    assert cc.localise_limit("ہم کچھ ٹھیک نہیں کر سکتے")[1] == 2  # two words are not read
    assert cc.localise_limit("a plain English limit") == ("a plain English limit", 0)


def test_property_limit_text_the_tables_do_not_understand_never_clears_an_option():
    import random

    rng = random.Random(41)
    alphabets = {
        "urdu": "ابتثجحخدرزسشصضطظعغفقلمنہوی",
        "arabic": "ابتثجحخدذرزسشصضطظعغفقلمنهوي",
        "hindi": "कखगघचछजझटठडढतथदधनपफबभमयरलवशसह",
    }
    known = set(cc.SCRIPT_TABLE) | set(cc.SCRIPT_STOP) | set(cc.SMALL_NUMBER_WORDS)
    options = ["Hire a cashier", "Replace the POS system", "Use a paper register", "Open in Lahore"]
    seen = 0
    for _ in range(300):
        alphabet = alphabets[rng.choice(sorted(alphabets))]
        words = []
        for _ in range(rng.randint(1, 5)):
            word = "".join(rng.choice(alphabet) for _ in range(rng.randint(3, 6)))
            if cc.norm(word) not in known:
                words.append(word)
        limit = " ".join(words)
        for kind in ("cannot", "staff", "budget", "deadline"):
            requirement = reqs(**{kind: [limit] if kind == "cannot" else limit})
            for option in options:
                v = cc._check_option(option, requirement, probe_budget=False)
                assert v.status != "ok", (kind, limit, option, v)
                seen += 1
    assert seen == 300 * 4 * 4


@pytest.mark.parametrize(
    ("option", "staff"),
    [
        ("Hire a second receptionist", "only one receptionist"),
        ("Hire two more drivers", "only 2 drivers"),
        ("Add one more cook", "only two cooks"),
        ("Hire another driver", "only 2 drivers"),
        ("Recruit an additional accountant", "only 1 accountant"),
        ("ek aur receptionist rakh lein", "ek hi receptionist"),
        ("دو اور باورچی رکھیں", "صرف 2 باورچی"),
        ("وظفوا طباخين اثنين", "فقط 2 طباخين"),
        ("दो और रसोइया रखें", "केवल 2 रसोइया"),
    ],
)
def test_a_cap_phrased_with_a_role_is_enforced_against_another_of_that_role(option, staff):
    v = with_staff(option, staff)
    assert v.status == "violates" and v.rule == "staff" and v.evidence, (option, staff, v)


def test_a_role_cap_does_not_reject_what_adds_nobody_and_a_pure_cap_still_counts():
    assert with_staff("Use a paper register", "only 2 drivers").status == "ok"
    assert with_staff("Train the drivers", "only 2 drivers").status == "ok"
    assert with_staff("Hire two cooks", "at most 2 cooks").status == "ok"
    assert with_staff("Hire three cooks", "at most 2 cooks").status == "violates"
    assert cc.staff_limit_form("only 2 cooks") == "total"
    assert cc.staff_limit_form("at most 2 cooks") == "cap"
    assert cc.staff_limit_form("hiring is frozen") == "cap"
    assert with_staff("Hire some cooks", "hiring is frozen").status == "violates"  # no count needed


def test_a_budget_in_urdu_arabic_and_hindi_is_a_ceiling_with_its_currency_and_digits():
    cases = [
        ("نیا سسٹم 80000 روپے میں خریدیں", "ہمارے پاس صرف 30,000 روپے کا بجٹ ہے"),
        ("اشتر نظاما بـ 80000 ريال", "ميزانيتنا 30,000 ريال فقط"),
        ("नया सिस्टम 80000 रुपये में खरीदें", "हमारे पास केवल 30,000 रुपये का बजट है"),
    ]
    for option, budget in cases:
        assert check(option, budget=budget).status == "violates", (option, budget)
    assert (
        check(
            "ٹیبلیٹ 10000 روپے میں خریدیں", budget="اس مہینے 20000 روپے سے زیادہ خرچ نہیں کر سکتے"
        ).status
        == "ok"
    )
    ceiling = cc.parse_ceiling(
        cc.localise_limit("اس مہینے 20000 روپے سے زیادہ خرچ نہیں کر سکتے")[0]
    )
    assert ceiling.value == Decimal(20000)
    assert cc.parse_ceiling(
        cc.localise_limit("ہمارے پاس صرف 30,000 روپے کا بجٹ ہے")[0]
    ).value == Decimal(30000)


def test_no_money_for_a_thing_rejects_spending_on_that_thing_only():
    assert check("نیا سسٹم خریدیں", budget="نئے سسٹم کے لیے پیسے نہیں ہیں").status == "violates"
    v = check("Buy paper rolls for the counter", budget="no money for a new system")
    assert v.status == "unknown" and "names something else" in v.reason
    assert check("Buy a new system", budget="no money for a new system").status == "violates"
    assert check("Buy paper", budget="no budget").status == "violates"  # no subject: any spending
    assert check("Use a paper register", budget="no budget").status == "ok"


def test_channel_limits_must_work_on_x_only():
    limit = ["it must work on my phone only"]
    assert check("Build a laptop dashboard", cannot=limit).status == "violates"
    assert check("Print a paper sheet for the desk", cannot=limit).status == "violates"
    assert check("Send a WhatsApp message", cannot=limit).status == "ok"
    assert check("Send a message", cannot=["it must work on WhatsApp"]).status == "ok"
    assert (
        check("Build a laptop dashboard", cannot=["it must work on my phone"]).status == "unknown"
    )
    assert (
        check("Send a message", cannot=["it must work on the phone only, without any print"]).status
        == "ok"
    )
    assert (
        check("Print a sheet", cannot=["it must work on the phone only, without any print"]).status
        == "violates"
    )
    assert (
        check(
            "Use a paper register", cannot=["it must work on a printed sheet only, no screen"]
        ).status
        == "ok"
    )
    assert (
        check("Open a phone app", cannot=["it must work on a printed sheet only, no screen"]).status
        == "violates"
    )


def test_a_partner_word_is_not_what_has_to_match():
    limit = ["we cannot change our caterer partner"]
    assert check("Switch to another caterer", cannot=limit).status == "violates"
    assert check("Ask the partner for a discount", cannot=limit).status != "violates"


def test_costly_ideas_with_no_budget_are_unknown_in_every_language_and_say_why():
    for option in ["Take a deposit through an app", "repair the screen at a paid shop",
                   "naya system kharidein", "mehnga job tracking system",
                   "نیا سسٹم خریدیں", "اشتر نظاما جديدا", "नया सिस्टम खरीदें"]:  # fmt: skip
        v = cc.check_option(option, reqs(cannot=["we cannot hire more staff"]), "en")
        assert (
            v.status == "unknown" and v.rule == "budget" and "no budget was stated" in v.reason
        ), option
    assert cc.check_option("Ask customers for referrals", None, "en").status == "ok"


def test_the_arabic_endings_and_comma_numbers_and_minutes():
    assert cc.norm("30,000") == "30,000"
    assert cc.parse_days("ایک منٹ", need_cue=False) is None  # not mapped here: no guessing
    mapped = cc.localise_limit("ہر بکنگ ایک منٹ سے کم میں ہونی چاہیے")[0]
    assert cc.parse_days(mapped, need_cue=False) == pytest.approx(1 / 1440)
    for word, english in [("وظفوا", "hire"), ("طباخين", "cooks"), ("موظفي", "employee")]:
        assert cc.scripts._lookup(cc.norm(word), cc.SCRIPT_TABLE) == english


def test_a_limit_with_an_unread_word_can_reject_but_never_clears():
    limit = ["ہم POS نہیں بدل سکتے اور کچھ"]
    assert check("Replace the POS", cannot=limit).status == "violates"
    v = check("Use a paper register", cannot=limit)
    assert v.status == "unknown" and "stated limit were not read" in v.reason
    # a bare object next to an unread word is not understood as a limit at all
    assert check("Replace the POS system", cannot=["POS system"]).status == "violates"
    assert check("Replace the POS system", cannot=["POS سسٹم ٹھیک"]).status == "unknown"


def test_another_second_and_extra_are_each_one_more_person():
    for option in [
        "Hire another cook",
        "Hire a second cook",
        "Hire an extra cook",
        "Hire an additional cook",
    ]:
        assert with_staff(option, "at most 1 cook").status == "ok", option
        assert with_staff(option, "at most 0 cook").status == "violates", option
    assert with_staff("Hire third cook", "at most 1 cook").status == "ok"


def test_a_bare_partner_word_does_not_have_to_match():
    limit = ["we cannot change our caterer partner"]
    assert check("Switch the caterer", cannot=limit).status == "violates"
    assert check("Switch the partner", cannot=limit).status != "violates"


def test_a_limit_about_spending_rejects_buying_and_renting():
    assert check("Buy a tablet", cannot=["we cannot spend"]).status == "violates"
    assert check("Rent a hall", cannot=["we cannot spend"]).status == "violates"
    assert check("Ask customers for referrals", cannot=["we cannot spend"]).status == "ok"


def test_whole_phrases_in_three_scripts_are_read_as_ceilings_and_floors():
    for source in ["پچاس ہزار روپے سے زیادہ نہیں", "50000 रुपये से ज़्यादा नहीं", "كحد اقصى 50000 ريال"]:  # noqa: E501
        mapped = cc.localise_limit(source)[0]
        assert "at most" in mapped, source
        assert cc.parse_ceiling(mapped).value == Decimal(50000), source
    floor = cc.localise_limit("کم از کم 2 لوگ")[0]
    assert "at least" in floor and cc.parse_staff_limit(floor) is None
    assert "because" in cc.localise_limit("معاہدے کی وجہ سے ہم کوریئر نہیں بدل سکتے")[0]
    assert "per month" in cc.localise_limit("50,000 روپے مہینہ")[0]
    assert "per month" in cc.localise_limit("لدينا 50,000 ريال في الشهر")[0]


def test_an_arabic_no_more_than_spending_limit_is_a_ceiling():
    budget = "لا نستطيع إنفاق أكثر من 20000 روبية"
    assert check("اشتر نظاما 25000 روبية", budget=budget).status == "violates"
    assert check("اشتر نظاما 15000 روبية", budget=budget).status == "ok"
    assert "no more than" in cc.localise_limit(budget)[0]


# ----- round 5 audit: a limit whose subject the option names is never a free ok -----

PRICE_EN = "we cannot change prices"
MENU_EN = "I cannot change the menu"
SHOP_TIME_RU = "dukan ka waqt nahi badal sakta"
RATE_RU = "rate nahi badal sakte"
SHOP_TIME_UR = "ہم دکان کا وقت نہیں بدل سکتے"
SHOP_TIME_AR = "لا نستطيع تغيير وقت المتجر"
SHOP_TIME_HI = "हम दुकान का समय नहीं बदल सकते"
PRICE_UR = "ہم قیمتیں نہیں بدل سکتے"
PRICE_AR = "لا نستطيع تغيير الأسعار"
PRICE_HI = "हम कीमतें नहीं बदल सकते"

SYNONYM_VIOLATIONS = [
    # English: synonyms of change, and of the object
    ("Update the prices", PRICE_EN),
    ("Adjust prices", PRICE_EN),
    ("Revise pricing", PRICE_EN),
    ("Alter the prices", PRICE_EN),
    ("Modify prices for lunch", PRICE_EN),
    ("Raise prices by five percent", PRICE_EN),
    ("Lower prices on weekdays", PRICE_EN),
    ("Rework how you charge customers", PRICE_EN),
    ("Revamp the rate card", PRICE_EN),
    ("Redesign the menu", MENU_EN),
    ("Update the menu", MENU_EN),
    ("Rework the menu", MENU_EN),
    ("Swap the menu for a shorter one", MENU_EN),
    ("Replace the menu", MENU_EN),
    ("Revise the menu", MENU_EN),
    ("Edit the menu every week", MENU_EN),
    ("Amend the menu", MENU_EN),
    ("Tweak the menu", MENU_EN),
    # Roman Urdu limits and options
    ("dukan ka waqt badlein", SHOP_TIME_RU),
    ("dukan ka time badlein", SHOP_TIME_RU),
    ("Shop timing badal dein", SHOP_TIME_RU),
    ("opening hours change karein", SHOP_TIME_RU),
    ("change shop timing", SHOP_TIME_RU),
    ("shop timing tabdeel karein", SHOP_TIME_RU),
    ("dukan ka waqt change karna", SHOP_TIME_RU),
    ("Change the price of biryani", RATE_RU),
    ("Increase the price of biryani", RATE_RU),
    ("rate badlein", RATE_RU),
    ("price badal dein", RATE_RU),
    ("rate tabdeel karein", RATE_RU),
    ("Lower the pricing", RATE_RU),
    # Urdu script
    ("دکان کا وقت بدلیں", SHOP_TIME_UR),
    ("دکان کا وقت تبدیل کریں", SHOP_TIME_UR),
    ("ٹائمنگ اپڈیٹ کریں", SHOP_TIME_UR),
    ("قیمتیں بڑھائیں", PRICE_UR),
    ("ریٹ اپڈیٹ کریں", PRICE_UR),
    # Arabic
    ("تغيير وقت المتجر", SHOP_TIME_AR),
    ("تعديل وقت المتجر", SHOP_TIME_AR),
    ("تحديث وقت المتجر", SHOP_TIME_AR),
    ("رفع الأسعار", PRICE_AR),
    ("تعديل السعر", PRICE_AR),
    # Hindi
    ("दुकान का समय बदलें", SHOP_TIME_HI),
    ("समय अपडेट करें", SHOP_TIME_HI),
    ("समय एडजस्ट करें", SHOP_TIME_HI),
    ("कीमतें बढ़ाएं", PRICE_HI),
    ("रेट अपडेट करें", PRICE_HI),
]


@pytest.mark.parametrize(("option", "limit"), SYNONYM_VIOLATIONS)
def test_every_way_of_changing_what_cannot_change_is_rejected(option, limit):
    v = check(option, cannot=[limit])
    assert v.status == "violates", (option, limit, v)


TRIED_VIOLATIONS = [
    "Try a facebook ad",
    "Try facebook ad",
    "Use Facebook advertising",
    "Run a facebook ad campaign",
    "Post a Facebook advert",
    "Start facebook ads again",
]


@pytest.mark.parametrize("option", TRIED_VIOLATIONS)
def test_a_failed_thing_is_matched_on_its_stems_in_both_directions(option):
    v = check(option, tried=[("facebook ads", "did not work")])
    assert v.status == "violates", (option, v)
    assert (
        check("Try facebook ads", tried=[("a facebook ad campaign", "failed")]).status == "violates"
    )
    assert (
        check("Use advertising on facebook", tried=[("facebook ad", "no luck")]).status
        == "violates"
    )


def test_a_different_approach_or_an_unrelated_option_is_not_matched_to_a_failed_thing():
    tried = [("facebook ads", "did not work")]
    assert check("Ask customers for referrals", tried=tried).status == "ok"
    assert check("Instead of facebook ads, ask customers for referrals", tried=tried).status == "ok"
    assert check("Try a different approach to facebook ads", tried=tried).status == "ok"
    assert check("Post in neighbourhood groups", tried=tried).status == "ok"
    # overlap on one of the two words is never a free ok
    assert check("Post on Facebook groups", tried=tried).status == "unknown"


@pytest.mark.parametrize(
    ("option", "limit"),
    [
        ("Print the menu on cards", MENU_EN),
        ("Photograph the menu for the wall", MENU_EN),
        ("Laminate the menu", MENU_EN),
        ("Cook the menu items in bulk", MENU_EN),
        ("Frame the prices for the wall", PRICE_EN),
        ("Charge customers a delivery fee on Fridays", PRICE_EN),
        ("dukan ka waqt ko behtar banane ka sochein", SHOP_TIME_RU),
        ("dukan ka waqt likh kar lagayein", SHOP_TIME_RU),
    ],
)
def test_naming_the_subject_with_no_verb_the_check_knows_is_unknown_never_ok(option, limit):
    v = check(option, cannot=[limit])
    assert v.status == "unknown", (option, limit, v)
    assert (
        "no verb it recognises" in v.reason or "not read" in v.reason or "shares only" in v.reason
    )


@pytest.mark.parametrize(
    ("option", "limit"),
    [
        ("Keep the menu and put a sign on the door", MENU_EN),
        ("Measure which menu items sell best", MENU_EN),
        ("Ask customers which dish they like", MENU_EN),
        ("Tell customers the prices on WhatsApp", PRICE_EN),
        ("Check the prices every Monday", PRICE_EN),
        ("Send the menu to regulars", MENU_EN),
        ("Use a paper register at the counter", MENU_EN),
        ("Train staff on the prices", PRICE_EN),
    ],
)
def test_options_that_keep_check_or_tell_the_subject_are_not_blocked(option, limit):
    assert check(option, cannot=[limit]).status == "ok", (option, limit)


def test_the_staff_check_has_a_guard_for_an_option_it_cannot_read():
    from app.modules.pi.requirements_types import Limit as _Limit

    unreadable = cc._option("کچھ سوچیں")
    assert unreadable.latin is False
    v = cc._check_staff(unreadable, _Limit("only 2 staff"))
    assert v.status == "unknown" and "script" in v.reason
    assert with_staff("کچھ سوچیں", "only 2 staff").status == "unknown"
    assert with_staff("کچھ سوچیں", "hiring is frozen").status == "unknown"


# ----- keeping a list is not hiring a clerk (journeys: rakhein / رکھیں) -----


@pytest.mark.parametrize(
    "option",
    [
        "Fees ki list clerk ke phone par rakhein",
        "Fees ki list clerk ke phone par rakhna",
        "Register clerk ke paas rakhein",
        "Booking sheet receptionist ke desk par rakhein",
        "Reminder list manager ke phone par rakhein",
    ],
)
def test_keeping_a_list_with_a_person_is_not_hiring_that_person(option):
    v = with_staff(option, "ek clerk")
    assert v.status != "violates", (option, v)
    assert with_staff(option, "only 1 clerk").status != "violates"


def test_the_urdu_journey_keeping_a_shared_list_is_not_a_hire():
    option = "بکنگ کے لیے ایک ہی مشترکہ فہرست رکھیں"
    limit = "ہم کسی کو بھرتی نہیں کر سکتے"
    v = check(option, cannot=[limit])
    assert v.status != "violates", v
    for other in ["رجسٹر رکھیں", "کیلنڈر رکھیں", "فائل کلرک کے فون پر رکھیں"]:
        assert check(other, cannot=[limit]).status != "violates", other
    assert cc.localise_limit(limit)[0] == "we cannot hire anyone"


@pytest.mark.parametrize(
    ("option", "limit"),
    [
        ("clerk rakhein", "ek clerk"),
        ("naya clerk rakh lein", "ek clerk"),
        ("Hire a clerk", "ek clerk"),
        ("Fees ki list banayein aur ek aur clerk rakhein", "ek clerk"),
    ],
)
def test_hiring_a_person_still_breaks_a_one_person_team(option, limit):
    assert with_staff(option, limit).status == "violates", (option, limit)


@pytest.mark.parametrize(
    "option", ["نیا کلرک رکھیں", "नया क्लर्क रखें", "توظيف موظف جديد", "ایک اور اسسٹنٹ رکھیں"]
)
def test_hiring_a_person_still_breaks_a_no_hire_limit_in_every_script(option):
    limits = ["ہم کسی کو بھرتی نہیں کر سکتے", "لا نستطيع توظيف احد", "हम किसी को भर्ती नहीं कर सकते"]  # noqa: E501
    assert any(check(option, cannot=[limit]).status == "violates" for limit in limits), option
    assert check(option, cannot=["we cannot hire anyone"]).status == "violates"


def test_a_bare_limit_that_names_only_time_is_a_real_subject_not_a_generic_word():
    assert check("Change the timing", cannot=["the timing"]).status == "violates"
    assert check("Change the timing", cannot=["the thing"]).status == "unknown"
    assert cc.parse_limit("the timing").kind == "object_only"


# ---- round 6: the subject of a "cannot change" limit is judged by a whitelist of verbs ----

HOURS_LIMITS = ["We cannot change our opening hours", "We cannot change the shop timing",
                "Our hours are fixed"]  # fmt: skip
AUDIT_CASES = (
    [(o, h) for h in HOURS_LIMITS for o in [
        "Extend the opening hours", "Shift the shop timing", "Move the opening time earlier",
        "Open later in the evening", "Stay open 24 hours", "Close on Fridays", "Add a night shift"]]
    + [(o, "We cannot change our prices") for o in [
        "Reprice the menu", "Qeemat badha dein", "Start charging a delivery fee",
        "Add a service charge", "Discount the menu items"]]
    + [(o, "We cannot change the menu") for o in [
        "Drop items from the menu", "Cancel the lunch special", "Add new dishes to the menu"]]
    + [(o, "We cannot change the delivery area") for o in [
        "Expand the delivery area", "Shift delivery to other areas", "Stop delivery in far areas",
        "Cancel delivery to Gulshan", "Move delivery radius"]]
    + [(o, "We cannot change our staff") for o in [
        "Fire the helper", "Shift the staff to nights", "Move the cashier to another shop",
        "Change who works where"]]
    + [("Bring in a new clerk", "We cannot hire anyone")]
)  # fmt: skip


@pytest.mark.parametrize(("option", "limit"), AUDIT_CASES)
def test_a_known_change_or_unknown_verb_on_the_subject_is_never_ok(option, limit):
    v = check(option, cannot=[limit])
    assert v.status in {"violates", "unknown"}, (option, limit, v)
    if option not in {
        "Cancel delivery to Gulshan",
        "Move delivery radius",
        "Change who works where",
    }:
        assert v.status == "violates", (option, limit, v)


@pytest.mark.parametrize(
    ("limit", "option"),
    [
        ("bilkul budget nahi", "Paid ads chalayein"),
        ("بجٹ نہیں ہے", "پیسے خرچ کریں"),
        ("no budget", "Run paid ads"),
        ("budget nahi hai", "Rs 10000 ka software kharidein"),
        ("zero budget", "Hire an agency"),
    ],
)
def test_a_costly_option_with_no_budget_is_never_ok(limit, option):
    v = check(option, budget=limit)
    assert v.status in {"violates", "unknown"}, (limit, option, v)
    assert check("Send free WhatsApp reminders", budget=limit).status == "ok"


def test_text_of_only_invisible_characters_is_empty_like_an_empty_string():
    for text in ["​", "​​​", "‎‏", "  ​ ﻿ "]:
        v = cc.check_option(text, reqs(budget="Rs 20000"), "en")
        assert v.status == "unknown" and "empty" in v.reason, text


# the generated matrix: verbs x subjects x five languages

SAFE_EN = ["keep", "maintain", "check", "measure", "track", "record", "remind customers about",
           "tell customers", "announce", "review", "compare", "explain", "post"]  # fmt: skip
CHANGE_EN = ["extend", "shift", "move", "cancel", "drop", "stop", "scrap", "switch", "add",
             "close", "open", "expand", "reduce", "raise", "lower", "introduce", "start", "update",
             "adjust", "revise", "remove", "increase", "cut"]  # fmt: skip
SUBJECTS_EN = [  # (limit, noun phrase)
    ("we cannot change our prices", "the prices"),
    ("we cannot change the menu", "the menu"),
    ("we cannot change our opening hours", "the opening hours"),
    ("we cannot change the delivery area", "the delivery area"),
    ("we cannot change our staff", "the staff"),
    ("we cannot change our shop", "the shop"),
    ("we cannot change our ads", "the ads"),
    ("we cannot change our suppliers", "the suppliers"),
]
SUBJECTS_RU = [
    ("qeemat nahi badal sakte", "qeemat"), ("menu nahi badal sakte", "menu"),
    ("dukan ka waqt nahi badal sakte", "dukan ka waqt"),
    ("delivery area nahi badal sakte", "delivery area"), ("staff nahi badal sakte", "staff"),
    ("dukan nahi badal sakte", "dukan"), ("ads nahi badal sakte", "ads"),
    ("suppliers nahi badal sakte", "suppliers"),
]  # fmt: skip
CHANGE_RU = ["badha dein", "kam karo", "band karo", "shuru karo", "hata do", "nikal do",
             "badal dein", "change karein", "update karein", "reduce karein",
             "add karein"]  # fmt: skip
SAFE_RU = ["check karein", "measure karein", "track karein", "record karein", "review karein",
           "compare karein", "keep karein"]  # fmt: skip
SUBJECTS_UR = [
    ("ہم قیمتیں نہیں بدل سکتے", "قیمتیں"), ("ہم مینو نہیں بدل سکتے", "مینو"),
    ("ہم دکان کا وقت نہیں بدل سکتے", "دکان کا وقت"), ("ہم علاقہ نہیں بدل سکتے", "علاقہ"),
    ("ہم عملہ نہیں بدل سکتے", "عملہ"), ("ہم دکان نہیں بدل سکتے", "دکان"),
    ("ہم اشتہار نہیں بدل سکتے", "اشتہار"), ("ہم سپلائرز نہیں بدل سکتے", "سپلائرز"),
]  # fmt: skip
CHANGE_UR = ["بڑھائیں", "کم کریں", "بند کریں", "شروع کریں", "ہٹائیں", "بدلیں", "اپڈیٹ کریں"]
SAFE_UR = ["جانچیں", "ناپیں"]  # "رکھیں" is keep OR hire: with a person it hires
SUBJECTS_AR = [
    ("لا نستطيع تغيير الأسعار", "الأسعار"), ("لا نستطيع تغيير المنيو", "المنيو"),
    ("لا نستطيع تغيير وقت المتجر", "وقت المتجر"), ("لا نستطيع تغيير منطقة", "منطقة"),
    ("لا نستطيع تغيير الموظفين", "الموظفين"), ("لا نستطيع تغيير المتجر", "المتجر"),
    ("لا نستطيع تغيير الاعلان", "الاعلان"), ("لا نستطيع تغيير موردين", "موردين"),
]  # fmt: skip
CHANGE_AR = ["رفع", "خفض", "اغلاق", "حذف", "توسيع", "نقل", "تغيير", "تعديل"]
SAFE_AR = ["تحقق من", "احتفظ", "قيم"]
SUBJECTS_HI = [
    ("हम कीमतें नहीं बदल सकते", "कीमतें"), ("हम मेन्यू नहीं बदल सकते", "मेन्यू"),
    ("हम दुकान का समय नहीं बदल सकते", "दुकान का समय"), ("हम क्षेत्र नहीं बदल सकते", "क्षेत्र"),
    ("हम कर्मचारी नहीं बदल सकते", "कर्मचारी"), ("हम दुकान नहीं बदल सकते", "दुकान"),
    ("हम विज्ञापन नहीं बदल सकते", "विज्ञापन"), ("हम सप्लायर नहीं बदल सकते", "सप्लायर"),
]  # fmt: skip
CHANGE_HI = ["बढ़ाएं", "घटाएं", "बंद करें", "शुरू करें", "हटाएं", "बदलें", "अपडेट करें"]
SAFE_HI = ["जाँचें", "जांचें"]  # "रखें" is keep OR hire: with a person it hires


def _matrix(subjects, changes, safes, order):
    for limit, noun in subjects:
        for verb in changes:
            option = f"{verb.capitalize()} {noun}" if order == "vo" else f"{noun} {verb}"
            yield "change", option, limit
        for verb in safes:
            option = f"{verb.capitalize()} {noun}" if order == "vo" else f"{noun} {verb}"
            yield "safe", option, limit


MATRIX = (
    [("en", *x) for x in _matrix(SUBJECTS_EN, CHANGE_EN, SAFE_EN, "vo")]
    + [("roman_ur", *x) for x in _matrix(SUBJECTS_RU, CHANGE_RU, SAFE_RU, "ov")]
    + [("ur", *x) for x in _matrix(SUBJECTS_UR, CHANGE_UR, SAFE_UR, "ov")]
    + [("ar", *x) for x in _matrix(SUBJECTS_AR, CHANGE_AR, SAFE_AR, "vo")]
    + [("hi", *x) for x in _matrix(SUBJECTS_HI, CHANGE_HI, SAFE_HI, "ov")]
)


def test_the_matrix_is_large_and_covers_all_five_languages():
    assert len(MATRIX) >= 20 * 8 * 5 * 0.8
    assert {m[0] for m in MATRIX} == {"en", "roman_ur", "ur", "ar", "hi"}
    assert len(CHANGE_EN) + len(SAFE_EN) >= 20 and len(SUBJECTS_EN) >= 8


def test_matrix_a_change_verb_is_never_ok_and_a_safe_verb_never_violates():
    outcomes: dict[tuple[str, str], dict[str, int]] = {}
    for language, kind, option, limit in MATRIX:
        v = check(option, cannot=[limit])
        outcomes.setdefault((language, kind), {"ok": 0, "violates": 0, "unknown": 0})[v.status] += 1
        if kind == "change":
            assert v.status != "ok", (language, option, limit, v)
        else:
            assert v.status != "violates", (language, option, limit, v)
    # the gate is not "unknown for everything": English and Roman Urdu change verbs are rejected
    for language in ("en", "roman_ur"):
        counts = outcomes[(language, "change")]
        assert counts["violates"] >= 0.8 * sum(counts.values()), (language, counts)
    for language in ("ur", "ar", "hi"):
        assert outcomes[(language, "change")]["violates"] >= 8, (language, outcomes)
    assert outcomes[("en", "safe")]["ok"] >= 0.6 * sum(outcomes[("en", "safe")].values())


# ---- survivors of the round-5 audit ----


def test_stems_never_shorten_a_two_letter_word_and_do_shorten_a_plural():
    assert cc.verb_stems("us") == {"us"}
    assert "ad" in cc.verb_stems("ads")


def test_a_metre_figure_is_a_length_unless_the_option_buys_it():
    roles = lambda text: [a.role for a in cc.parse_amounts(text)]  # noqa: E731
    assert roles("Buy a 3m cable") == ["none"]  # a length noun
    assert roles("Get 3m") == ["none"]  # no strong cost word: not a million
    assert roles("Buy it for 3m") == ["cost"]


def test_a_filler_word_is_not_a_role_in_what_a_hire_names():
    v = check("Hire more staff", cannot=["we cannot hire anyone"])
    assert v.status == "violates" and "more" not in v.evidence and "staff" in v.evidence


def test_an_unnumbered_hire_adds_no_known_people_and_is_flagged():
    assert cc.added_people("Hire more staff") == (0, True, ("staff",))
    assert cc.added_people("Hire two cooks") == (2, False, ("cooks",))


def test_a_word_exactly_the_length_of_a_suffix_plus_two_is_not_stripped():
    assert cc.scripts._lookup(cc.norm("لاا"), cc.SCRIPT_TABLE) is None
    assert cc.scripts._lookup(cc.norm("لاان"), cc.SCRIPT_TABLE) in (None, "not")


def test_a_plural_topic_word_is_a_hit_and_a_plain_one_too():
    assert cc.lex.topic_hits("delivery", ["deliveries"]) == ["deliveries"]
    assert cc.lex.topic_hits("delivery", ["delivery"]) == ["delivery"]
    assert cc.lex.topic_hits("delivery", ["pizza"]) == []


def test_an_ing_word_before_the_subject_is_a_modifier_and_a_verb_after_it_is_no_act():
    hours = ["We cannot change our opening hours"]
    assert check("Keep the same opening hours and remind customers", cannot=hours).status == "ok"
    assert check("Send a reminder at closing time", cannot=hours).status == "ok"
    assert check("Post your hours on Google", cannot=hours).status == "ok"
    assert check("Buy a poster for the opening hours", cannot=hours).status == "ok"  # context only
    assert check("Opening hours update", cannot=hours).status == "violates"
    assert check("Menu update", cannot=["We cannot change the menu"]).status == "violates"
    assert check("Stop opening hours", cannot=hours).status != "ok"


def test_rakhein_keeps_a_thing_in_every_path_and_hires_only_a_person():
    limit = ["hum naya banda nahi rakh sakte"]
    assert check("Fees ki list rakhein", cannot=limit).status != "violates"
    assert check("Fees ki list clerk ke phone par rakhein", cannot=limit).status != "violates"
    for hire in ["naya clerk rakh lein", "clerk rakhein", "Ek naya clerk bharti karein"]:
        assert check(hire, cannot=limit).status == "violates", hire


def test_a_costly_urdu_option_under_a_no_budget_limit_violates():
    assert check("پیسے خرچ کریں", budget="بجٹ نہیں ہے").status == "violates"
    assert cc.localise_limit("بجٹ نہیں ہے")[0] == "no budget"


# ---- round 7: ok needs positive evidence; the subject comes from the limit's own words ----

SUBJECT_LIMITS = [
    ("No changes to packages", "packages"),
    ("branch are fixed", "branch"),
    ("suppliers stay as is", "suppliers"),
    ("commission", "commission"),
    ("working hours are fixed", "working hours"),
    ("shifts jaisay hain waisay rahenge", "shifts"),
    ("branch mein koi tabdeeli nahi ho gi", "branch"),
    ("rates are non-negotiable", "rates"),
    ("Owner won't allow changes to shifts", "shifts"),
]


@pytest.mark.parametrize(("limit", "noun"), SUBJECT_LIMITS)
def test_a_limit_yields_a_subject_stem_from_its_own_words(limit, noun):
    stems = cc.subject_stems(cc.limit_clauses(limit)[0])
    assert stems, limit
    flat = set().union(*stems)
    assert any(word in flat or word.rstrip("s") in flat for word in noun.split()), (limit, flat)


@pytest.mark.parametrize(("limit", "noun"), SUBJECT_LIMITS)
def test_unlisted_verbs_on_the_subject_are_never_ok_but_safe_ones_are(limit, noun):
    first = noun.split()[0]
    for verb in ["pilot", "test-run", "rebrand", "automate", "relax", "loosen", "slash", "trim",
                 "rotate", "resume", "sponsor", "double", "relocate", "unbundle", "hike"]:  # fmt: skip  # noqa: E501
        for option in [f"{verb.capitalize()} the {noun} next month", f"Just {verb} the {noun}",
                       f"Review the {noun}, then {verb} them", f"Keep the {noun} and {verb} them"]:  # fmt: skip  # noqa: E501
            assert check(option, cannot=[limit]).status != "ok", (limit, option)
    for option in [f"Keep the {noun} as they are", f"Check the {noun} every Monday",
                   f"Tell customers about the {noun}", f"Track the {noun} weekly",
                   f"Keep the {first} and post a notice"]:  # fmt: skip
        assert check(option, cannot=[limit]).status == "ok", (limit, option)
    assert check("Ask customers for referrals", cannot=[limit]).status == "ok"  # shares no stem


def test_a_pronoun_after_then_and_just_is_the_last_named_subject():
    limit = ["We cannot change our prices"]
    assert check("Review prices, then trim them", cannot=limit).status != "ok"
    assert check("Keep prices and just slash them", cannot=limit).status != "ok"
    assert check("Check the prices, then tell customers about them", cannot=limit).status == "ok"
    assert check("Review prices, then hike it", cannot=limit).status == "violates"


@pytest.mark.parametrize(
    "option",
    ["Offer a discount on lunch", "Create a combo deal", "Make it cheaper for regulars",
     "Give 10% off", "Run a promo", "Waive the fee", "Bundle the meals", "Hand out a coupon",
     "Free delivery for orders", "Markdown the old stock", "Introduce a voucher",
     "Cut the prıces", "Offer a dıscount", "Offer a díscount", "Ｏffer a discount"],
)  # fmt: skip
def test_a_discount_or_offer_touches_a_price_even_with_odd_letters(option):
    v = check(option, cannot=["prices are fixed"])
    assert v.status in {"violates", "unknown"}, (option, v)


def test_dotless_i_and_accents_are_plain_letters_before_matching():
    assert cc.norm("prıces") == "prices"
    assert cc.norm("díscount") == "discount"
    assert cc.norm("Ｆree") == "free"
    assert cc.norm("نیا") == cc.norm("نیا")  # other scripts keep their own marks
    assert cc.norm("é") == "e"


def test_ok_still_holds_for_unrelated_and_safe_only_options():
    for limit in ["prices are fixed", "We cannot change our opening hours", "branch are fixed"]:
        for option in ["Ask customers for referrals", "Send WhatsApp reminders to regulars",
                       "Train the cashier on the new greeting"]:  # fmt: skip
            assert check(option, cannot=[limit]).status == "ok", (limit, option)
    assert check("Keep the opening days as they are and post a notice",
                 cannot=["opening days are fixed"]).status == "ok"  # fmt: skip
    assert (
        check("Remind customers about the opening days", cannot=["opening days are fixed"]).status
        == "ok"
    )
    assert (
        check("opening days ka record rakhein", cannot=["opening days fixed hain"]).status == "ok"
    )
    assert check("Keep shifts and commission, track sales weekly",
                 cannot=["shifts are fixed", "We cannot change commission"]).status == "ok"  # fmt: skip  # noqa: E501


@pytest.mark.parametrize(
    "option",
    ["rakhein helper", "helper rakhein", "naya banda rakh lein", "naye log rakhein", "naye log bharti karein",  # noqa: E501
     "ek aur clerk rakh lein", "naya banda bharti karein", "Add 3 new staff to the shift"],
)  # fmt: skip
def test_roman_urdu_hiring_phrases_with_a_person_are_a_hire(option):
    assert with_staff(option, "just 3 employees").status == "violates", option
    assert with_staff(option, "only one receptionist").status == "violates", option


def test_a_hire_with_a_person_breaks_a_roman_urdu_no_hire_limit_and_a_list_does_not():
    limit = ["hum naya banda nahi rakh sakte"]
    for hire in [
        "helper rakhein",
        "naye log rakhein",
        "clerk rakh lein",
        "naya banda bharti karein",
    ]:
        assert check(hire, cannot=limit).status == "violates", hire
    for keep in ["list rakhein", "register rakh lein", "fees ki sheet rakhein"]:
        assert check(keep, cannot=limit).status != "violates", keep


@pytest.mark.parametrize(
    "option",
    ["Sponsor a local match", "Buy a banner", "Pay an influencer", "Rent a stall", "Hire a helper",
     "Run ads", "Print flyers", "Order brochures", "Install a camera", "Subscribe to a tool",
     "Upgrade the phone", "Automate the reminders", "Launch a loyalty app", "Set up a website",
     "Do something creative", "Boost posts", "Run paid ads", "Make a video"],
)  # fmt: skip
def test_nothing_that_is_not_clearly_free_is_ok_under_no_budget(option):
    for limit in ["no budget", "zero budget", "bilkul budget nahi", "budget nahi hai"]:
        assert check(option, budget=limit).status in {"violates", "unknown"}, (limit, option)


def test_clearly_free_options_are_ok_under_no_budget():
    for option in ["Keep a list of regulars", "Ask customers to share on WhatsApp",
                   "Tell customers about the offer", "Call the regulars", "Track sales weekly",
                   "Check stock every morning"]:  # fmt: skip
        assert check(option, budget="no budget").status == "ok", option


def test_the_false_violations_of_the_round_six_audit_are_ok():
    assert check("Keep the opening days as they are and post a notice",
                 cannot=["opening days are fixed"]).status == "ok"  # fmt: skip
    assert (
        check("Remind customers about the opening days", cannot=["opening days are fixed"]).status
        == "ok"
    )
    assert (
        check("opening days ka record rakhein", cannot=["opening days fixed hain"]).status == "ok"
    )
    assert check("Keep shifts and commission, track sales weekly",
                 cannot=["shifts are fixed", "We cannot change commission"]).status == "ok"  # fmt: skip  # noqa: E501


# ---- survivors of the round-six audit ----


def test_an_unresolved_subject_is_named_when_no_known_verb_is_at_work():
    toks = cc._option("The menu board").tokens
    assert cc._unresolved_subject(toks, ("menu",)) == "menu"
    assert cc._unresolved_subject(toks, ()) is None
    assert cc._unresolved_subject(cc._option("Keep the menu board").tokens, ("menu",)) is None
    assert cc._unresolved_subject(cc._option("The staff room").tokens, ("kitchen",)) is None
    v = check("Photograph the shop", cannot=["we cannot close the shop"])
    assert v.status == "unknown" and "recognises" in v.reason


def test_a_negated_spend_verb_is_not_a_spend():
    toks = cc._option("do not buy a tablet").tokens
    index = next(i for i, t in enumerate(toks) if t.word == "buy")
    assert cc._is_spend_verb(toks, index) is False
    plain = cc._option("buy a tablet").tokens
    assert cc._is_spend_verb(plain, 0) is True
    v = check("Do not buy a tablet, ask customers to bring theirs", budget="Rs 20000")
    assert v.status == "ok"


def test_an_option_in_a_script_it_cannot_read_is_unknown_for_a_cannot_limit():
    option = cc._option("کچھ سوچیں")
    assert option.latin is False
    v = cc._check_cannot(option, Limit("we cannot change prices"))
    assert v.status == "unknown" and "script" in v.reason


# ---- a generated matrix of verbs and nouns that are in no table ----

NOUNS_25 = ["packages", "plans", "commission", "margins", "shifts", "rosters", "uniforms", "signage",  # noqa: E501
            "packaging", "invoices", "contracts", "warranties", "deposits", "receipts", "vouchers",
            "memberships", "subscriptions", "tiers", "bundles", "rebates", "appointments", "classes",  # noqa: E501
            "routes", "zones", "recipes"]  # fmt: skip
VERBS_150 = """abolish accelerate adapt amplify anchor arrange assemble auction balance bargain bend
blend boost broaden burn calibrate cap carve centralise chop circulate clone combine compress
concentrate condense convert coordinate crank curtail customise decrease delete demolish deploy
devalue dilute diminish disband discontinue dismantle dissolve distribute diversify divide double
downsize downgrade duplicate elevate eliminate enhance enlarge enrich equalise erase escalate
exchange expedite flatten flip fold forbid forge formalise fuse gamify grow halve hasten heighten
hike ignore improve inflate inject innovate insert intensify invert lengthen level liberalise limit
liquidate localise magnify mandate mark mask maximise minimise mix mobilise modernise multiply mute
narrow negotiate neutralise normalise optimise outsource overhaul pad patch peg phase pilot pivot
pool prune push quadruple quicken ration rearrange reboot recalibrate reconfigure redefine redirect
refine reform reinvent relax relocate remodel renegotiate reroute reset reshape resize retire retool
revamp reverse revolutionise rewrite rework roll rotate scale seal shave shorten shrink simplify
skip slash soften sponsor squeeze standardise stretch strip subsidise substitute suspend sweeten
swap tailor tame taper terminate tighten toggle transfer transform translate triple tune twist
unbundle undo unify unlock upgrade upscale vary widen withdraw withhold""".split()


def test_the_matrix_verbs_and_nouns_are_outside_the_tables():
    assert len(VERBS_150) >= 150 and len(NOUNS_25) >= 25
    assert not set(VERBS_150) & cc.BENIGN_VERBS
    flat = {w for stems in map(cc.object_key, NOUNS_25) for w in [stems]}
    assert not flat & {"STAFF", "SHOP", "PRICE", "TIME", "MENU", "AD"}


def test_matrix_english_no_verb_outside_the_safe_set_is_ever_ok_on_a_fixed_subject():
    unsafe = 0
    total = 0
    for noun in NOUNS_25:
        for limit in [f"{noun} are fixed", f"We cannot change {noun}", f"No changes to {noun}"]:
            for verb in VERBS_150:
                for option in (f"{verb.capitalize()} the {noun}", f"Just {verb} the {noun}",
                               f"Review the {noun}, then {verb} them"):  # fmt: skip
                    total += 1
                    if check(option, cannot=[limit]).status == "ok":
                        unsafe += 1
    assert total >= 3 * 25 * 150 * 3 * 0.9
    assert unsafe == 0, (unsafe, total)


def test_matrix_roman_urdu_no_unlisted_verb_is_ever_ok_on_a_fixed_subject():
    unsafe = 0
    for noun in NOUNS_25:
        for limit in [f"{noun} nahi badal sakte", f"{noun} jaisay hain waisay rahenge",
                      f"{noun} mein koi tabdeeli nahi ho gi"]:  # fmt: skip
            for verb in VERBS_150[:60]:
                option = f"{noun} ko {verb} karein"
                if check(option, cannot=[limit]).status == "ok":
                    unsafe += 1
    assert unsafe == 0, unsafe


def test_matrix_safe_verbs_on_a_fixed_subject_never_violate_and_are_mostly_ok():
    safe = ["keep", "check", "track", "record", "remind customers about", "tell customers about",
            "review", "explain", "post", "compare"]  # fmt: skip
    ok = total = 0
    for noun in NOUNS_25:
        for limit in [f"{noun} are fixed", f"We cannot change {noun}"]:
            for verb in safe:
                v = check(f"{verb.capitalize()} the {noun}", cannot=[limit])
                total += 1
                ok += v.status == "ok"
                assert v.status != "violates", (limit, verb, noun, v)
    assert ok >= 0.9 * total, (ok, total)


def test_matrix_more_phrasings_of_limits_and_options_never_give_an_unsafe_ok():
    limits = ["{n} stay as is", "{n} are non-negotiable", "{n} nahi badal sakte",
              "{n} jaisay hain waisay rahenge", "{n} mein koi tabdeeli nahi ho gi"]  # fmt: skip
    options = ["We should {v} our {n}", "Let's {v} {n} soon", "{n} ko {v} karein",
               "Please {v} the {n} and tell customers", "Keep the {n} and {v} them"]  # fmt: skip
    unsafe = total = 0
    for n in NOUNS_25[::2]:
        for lim in limits:
            for v in VERBS_150[::2]:
                for o in options:
                    total += 1
                    status = check(o.format(v=v, n=n), cannot=[lim.format(n=n)]).status
                    unsafe += status == "ok"
    assert total >= 13 * 5 * 75 * 5 * 0.95
    assert unsafe == 0, (unsafe, total)


def test_a_limit_with_no_cannot_wording_still_has_a_subject():
    for limit in ["commission", "suppliers", "working hours"]:
        assert check("Rebrand the " + limit, cannot=[limit]).status != "ok", limit
        assert check("Keep the " + limit, cannot=[limit]).status == "ok", limit


def test_skip_takes_an_object_and_is_not_a_blanket_negation():
    assert check("Skip the packages", cannot=["packages are fixed"]).status != "ok"
    assert (
        check("Review the packages, then skip them", cannot=["packages are fixed"]).status != "ok"
    )
    assert check("Avoid changing the packages", cannot=["packages are fixed"]).status == "ok"


def test_an_ing_word_before_a_noun_is_not_the_verb_of_a_limit():
    assert cc.parse_limit("opening days nahi badal sakte").families == {"CHANGE"}
    assert (
        check("opening days tabdeel karein", cannot=["opening days nahi badal sakte"]).status
        == "violates"
    )
    assert (
        check("Keep the opening days", cannot=["opening days mein koi tabdeeli nahi ho gi"]).status
        == "ok"
    )
    assert (
        check(
            "opening days extend karein", cannot=["opening days mein koi tabdeeli nahi ho gi"]
        ).status
        == "violates"
    )


def test_a_noun_that_starts_like_a_hiring_verb_is_not_a_hiring_freeze():
    for noun in ["appointments", "engagements", "recruitments", "employment terms"]:
        assert cc.parse_limit(f"we cannot change {noun}").families == {"CHANGE"}, noun
    assert cc.parse_limit("we cannot appoint anyone").families == {"HIRE"}
    assert (
        check("Abolish the appointments", cannot=["We cannot change appointments"]).status != "ok"
    )
