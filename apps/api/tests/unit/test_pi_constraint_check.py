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
    return cc.check_option(option, reqs(**kw), "en")


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
    assert v.status == "unknown"
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
    assert cc.check_option("Buy a tablet", Requirements(), "en").status == "ok"
    assert cc.check_option("Buy a tablet", None, "en").rule == "none"
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
