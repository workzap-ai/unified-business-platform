# ruff: noqa: E501  (the owner's phrases read better unbroken)
"""Every industry gets an idea that fits the problem, in the owner's own words (English and Roman Urdu).

14 common problems x 2 languages x 211 industries = 5,908 probes through the real matcher and the
library router. Two numbers, measured 2026-10-26, each a RATCHET (it may only go up):
- WITH the category the model files the problem under: 94% sensible. Goal 98%.
- WITHOUT it (only the person's words): 39% sensible (English 34%, Roman Urdu 44%). Goal 80%.
The gap is the router's word cues: 8 of the 18 library categories have none, and "late" sent
late payments to the shift rota. The 14 phrases below are the acceptance set: add to it, never edit
a phrase to make a probe pass."""

from app.modules.pi import solution_ideas as si
from app.modules.pi import solution_library as lib
from app.modules.pi import solutions

WITH_GROUP_FLOOR = 0.98  # goal 0.98, reached 2026-10-26
WORDS_ONLY_FLOOR = 0.80  # goal 0.80, reached 2026-10-26

# (expected library category, English, Roman Urdu)
PROBLEMS = [
    (
        "loss_security",
        "I think my staff is stealing and stock goes missing",
        "mujhe lagta hai staff chori kar raha hai aur maal kam nikalta hai",
    ),
    (
        "cash_collections",
        "customers pay late and I keep chasing the payment",
        "customers payment late dete hain aur main wusooli ke liye chase karta hoon",
    ),
    (
        "stock_inventory",
        "I have a lot of unsold stock sitting in the warehouse",
        "mera bohat sara maal warehouse mein parha hai bik nahi raha",
    ),
    (
        "sales_revenue",
        "people ask the price and then go quiet and never order",
        "log price poochte hain phir reply hi nahi aata order nahi aate",
    ),
    (
        "marketing_leads",
        "I run ads and get views but no enquiries",
        "ads chalata hoon views aate hain lekin enquiry nahi aati",
    ),
    (
        "customers_retention",
        "customers buy once and never come back",
        "customers aik baar kharidte hain dobara nahi aate",
    ),
    (
        "orders_fulfilment",
        "parcels get returned and deliveries are late",
        "parcel wapas aa jate hain aur delivery late hoti hai",
    ),
    (
        "people_staff",
        "staff come late and the shifts are a mess",
        "staff late aata hai aur shift ka masla hai",
    ),
    (
        "suppliers_purchasing",
        "my supplier delivers late and the quality changes",
        "supplier late maal deta hai aur quality badalti rehti hai",
    ),
    (
        "margin_cost",
        "my costs keep rising and profit is falling",
        "kharcha barhta ja raha hai aur munafa kam ho raha hai",
    ),
    (
        "quality_complaints",
        "customers complain about faulty products",
        "customers kharab product ki shikayat karte hain",
    ),
    (
        "operations_process",
        "everything depends on me and the work is slow and messy",
        "sab kaam mujh par hai aur kaam sust aur uljha hua hai",
    ),
    (
        "tech_systems",
        "we type the same data in many places and records do not match",
        "hum aik hi data kai jagah likhte hain aur record mel nahi khate",
    ),
    (
        "communication_coordination",
        "messages get lost in groups and nobody knows who is doing what",
        "groups mein messages kho jate hain aur kisi ko pata nahi kaun kya kar raha",
    ),
]


def _probe(with_group: bool) -> tuple[int, int]:
    industries = {
        i: (solutions.load(i) or {}).get("problems") or [] for i in solutions.industries()
    }
    library = lib.load()
    good = total = 0
    for category, english, roman in PROBLEMS:
        for phrase in (english, roman):
            for problems in industries.values():
                total += 1
                entry = si.match_problem(problems, category if with_group else "", "", phrase)
                if entry is not None:
                    good += 1
                    continue
                noted = [
                    {
                        "title": phrase,
                        "user_words": [phrase],
                        "group": category if with_group else "",
                    }
                ]
                routed = [c for c in lib.best_category(noted) if c]
                good += bool(
                    routed and routed[0] == category and library.get(category, {}).get("ideas")
                )
    return good, total


def test_with_the_models_category_most_problems_reach_a_fitting_idea():
    good, total = _probe(with_group=True)
    assert total == 5908 and good / total >= WITH_GROUP_FLOOR, f"{good / total:.0%}"


def test_from_the_owners_words_alone_the_router_finds_the_category():
    good, total = _probe(with_group=False)
    assert good / total >= WORDS_ONLY_FLOOR, f"{good / total:.0%}"


def test_every_library_category_has_cue_words():
    # 8 of 18 had none on 2026-10-26: such a category can only be reached by the model's label
    missing = sorted(set(lib.load()) - set(lib.CUES))
    assert missing == [], missing
