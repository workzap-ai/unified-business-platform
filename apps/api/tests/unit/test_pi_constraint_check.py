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
    assert (
        check("A change to the layout of the shop", cannot=["we cannot change the layout"]).status
        == "ok"
    )


def test_roman_urdu_limits_and_options():
    limit = ["hum naya system nahi kharid sakte"]
    assert check("Naya system kharid lein", cannot=limit).status == "violates"
    assert check("Kiraye par system lein", cannot=limit).status == "ok"


def test_other_scripts_are_unknown_never_ok():
    urdu_limit = ["ہم سسٹم تبدیل نہیں کر سکتے"]
    v = check("Replace the POS system", cannot=urdu_limit)
    assert v.status == "unknown" and "script" in v.reason
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
    option = "ٹیبلیٹ 50000 روپے"
    assert check(option, budget="Rs 20000").status == "unknown"
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
    shared = ["the", "we", "hum", "aap", "hai", "के", "है", "हम", "کے", "ہے", "ہم", "في", "من", "نحن"]
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
    assert with_staff("Hire one cashier", "only 2 staff").status == "ok"
    assert with_staff("Hire two cashiers", "up to two employees").status == "ok"
    assert with_staff("Use a paper register at the counter", "only 2 staff").status == "ok"
    v = with_staff("Hire more staff", "only 2 staff")
    assert v.status == "unknown" and "count" in v.reason
    assert with_staff("naye staff ko rakh lein", "only 2 staff").status == "unknown"


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
    assert check("Call the customers", tried=[("reminder calls", "")]).status == "ok"
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
    assert cc._option("کچھ اور سوچیں").latin is False
    assert cc._option("کچھ اور سوچیں").unread >= 1


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
    assert with_staff(option, "only 5 staff").status == "ok", option


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
