# ruff: noqa: E501  (the allow-list reasons read better unbroken)
"""FT-C6: the ideas stored in the packs are vetted like model text.

Every stored line pi can say (the free ideas, the build lines, the first question, the pack's
questions and build ideas, the care text) goes through the same checks a model reply gets: the idea
check (`solution_rules.check_idea`, the R-SOL rules), the build-line check, and the reply linter's
hard rules in a neutral brain-mode context. A violation is either fixed in the builder or listed
in ALLOWED below with a one-line reason; the list is exact (a stale entry fails too), so it
cannot grow without being seen. Pack data is built by scripts/build_industry_packs.py and
scripts/build_industry_solutions.py: fix the builder, never the JSON by hand.
"""

import json
from pathlib import Path

from app.modules.pi import constitution as c
from app.modules.pi import solution_rules as sr

PI_DIR = Path(c.__file__).parent
PACKS = PI_DIR / "packs" / "industry"
SOLUTIONS = PI_DIR / "packs" / "solutions"
AI_TURN = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}

# Rules about what a line says (promises, results, prices, advice, money, privacy). The shape rules
# (one question, no offer words while listening, tool words in a builder's own catalogue) judge a
# whole reply to a person, not a stored fragment, so they are not applied to question and build text.
CONTENT = (
    "R-PROM",
    "R-HONEST",
    "R-ADV",
    "R-PAY",
    "R-PRIV",
    "A2-",
    "R-META",
    "R-SOL",
    "R-LEGAL",
    "R-MED",
    "R-FIN",
)


def _ctx(latest: str, ideas: list[str] | None = None) -> dict:
    ctx: dict = {
        "latest_customer_message": latest,
        "history": [AI_TURN],
        "flow": {"state": "S2_CLARIFYING"},
    }
    if ideas:
        ctx["solution_ideas"] = ideas  # the reply carries ideas for an owner who asked for a fix
    return ctx


def _hard(text: str, ctx: dict, only: tuple[str, ...] | None = None) -> list[str]:
    rules = [v.rule for v in c.hard(c.lint(text, ctx))]
    return [r for r in rules if only is None or r.startswith(only)]


def _found() -> list[tuple[str, str, str, str]]:
    """(pack, field, rule, text) for every violation in every stored line."""
    out: list[tuple[str, str, str, str]] = []

    def add(pack: str, field: str, rules: list[str], text: str) -> None:
        out.extend((pack, field, rule, text) for rule in rules)

    for path in sorted(SOLUTIONS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for problem in data.get("problems", []):
            ask = "how can I fix this? " + str(problem.get("words", ""))
            ideas = list(problem.get("quick_ideas", [])) + [
                str(e.get("text", "")) for e in problem.get("extra_ideas", [])
            ]
            for text in ideas:
                add(path.stem, "idea", [r.split(" (")[0] for r in sr.check_idea(text).reject], text)
                add(path.stem, "idea", _hard("- " + text, _ctx(ask, [text])), text)
            build = problem.get("workzap_build") or {}
            if build:
                text = str(build.get("text", ""))
                why = sr.check_build_line(text, list(build.get("keys", [])))
                add(path.stem, "build", why, text)
            first = problem.get("ask_first")
            if first:
                add(path.stem, "ask_first", _hard(first, _ctx(ask), CONTENT), first)
        sample = ((data.get("sample_reply") or {}).get("pi")) or ""
        if sample:
            add(
                path.stem,
                "sample_reply",
                _hard(sample, _ctx("how can I fix this?"), CONTENT),
                sample,
            )

    for path in sorted(PACKS.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for text in pack.get("build_ideas", []):
            add(
                path.stem,
                "build_ideas",
                _hard("- " + text, _ctx("how can I fix this?", [text]), CONTENT),
                text,
            )
        for group in (pack.get("questions") or {}).values():
            for text in group:
                add(path.stem, "question", _hard(text, _ctx("my work is slow"), CONTENT), text)
        for text in pack.get("care", []):
            add(path.stem, "care", _hard(text, _ctx("my work is slow"), CONTENT), text)
    return out


# (pack, field, rule, first 40 characters of the line) -> why it is accepted. Exact and complete.
ALLOWED: dict[tuple[str, str, str, str], str] = {
    (
        "aircraft_maintenance_and_parts",
        "idea",
        "tool words or a build named for free",
        "Count your most-used part numbers once a",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    (
        "bus_coach_and_school_transport_operators",
        "build_ideas",
        "R-PRIV-07",
        "Parent or client WhatsApp alerts for dep",
    ): (
        "alert or ticket flow that names a parent/guest in the product description; no personal data is stored in the pack"
    ),
    (
        "catering_and_event_food",
        "build_ideas",
        "A2-1.5-SECRETS",
        "Quote builder: menu items, per-head pric",
    ): (
        "'pricing logic set by the caterer/plant' describes the owner's own rule; no price or bank detail is stored"
    ),
    ("clinics_and_gp_practices", "idea", "R-PAY-05", "Note when each panel bill was sent and w"): (
        "owner records when their own customers paid (a ledger idea); not pi taking or confirming a payment"
    ),
    (
        "cloud_kitchens_and_virtual_brands",
        "idea",
        "tool words or a build named for free",
        "Invite repeat customers to order direct ",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    (
        "cloud_kitchens_and_virtual_brands",
        "idea",
        "tool words or a build named for free",
        "Time how long each brand really takes at",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    ("cold_chain_logistics", "idea", "R-PAY-02", "Give one dispatcher the job of recording"): (
        "owner records departure and return times for loads; the linter reads 'return' next to money words"
    ),
    (
        "community_associations_and_clubs",
        "idea",
        "R-PAY-05",
        "Give one staff member one notebook for e",
    ): (
        "owner records when their own customers paid (a ledger idea); not pi taking or confirming a payment"
    ),
    (
        "cosmetics_and_beauty_retail",
        "idea",
        "R-BUILD-06",
        "Count your testers and high-risk small i",
    ): (
        "'you'll see' in the benefit clause reads as a promised result; builder should rewrite to 'so you can see'"
    ),
    (
        "courier_and_last_mile_delivery_companies",
        "build",
        "a claim, an amount, a vendor or a named product",
        "Order upload that accepts merchants' spr",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "dairy_processing",
        "build_ideas",
        "A2-1.5-SECRETS",
        "Farmer payment calculator using the plan",
    ): (
        "'pricing logic set by the caterer/plant' describes the owner's own rule; no price or bank detail is stored"
    ),
    (
        "dropshipping_and_social_commerce_sellers",
        "idea",
        "R-PAY-05",
        "Count orders with payment confirmed but ",
    ): (
        "owner records when their own customers paid (a ledger idea); not pi taking or confirming a payment"
    ),
    (
        "edtech_and_online_course_businesses",
        "care",
        "R-HONEST-01",
        "Income or job guarantees in course marke",
    ): (
        "care text names the banned claim ('guaranteed visa', 'earn $1,000') in order to forbid it; human-reviewed instruction"
    ),
    (
        "edtech_and_online_course_businesses",
        "care",
        "R-PROM-01",
        "Income or job guarantees in course marke",
    ): (
        "care text names the banned claim or 'guarantee' in order to forbid it; human-reviewed instruction"
    ),
    (
        "fast_food_and_qsr_chains",
        "idea",
        "tool words or a build named for free",
        "Match one app's payout against POS order",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    (
        "florists_and_gifting",
        "sample_reply",
        "R-HONEST-01",
        "Yes, this can be brought under control, ",
    ): (
        "opening 'this can be brought under control' / 'there is a way through this' is a soft reassurance the linter flags; builder should drop the claim"
    ),
    (
        "freelancers_solopreneurs_and_home_based_businesses",
        "idea",
        "tool words or a build named for free",
        "Collect your strongest work samples in o",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    (
        "general_contractors",
        "build_ideas",
        "R-PROM-01",
        "Bank guarantee, insurance and licence ex",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "government_contractors_and_public_sector_suppliers",
        "build",
        "a claim, an amount, a vendor or a named product",
        "a guarantee register with issue, expiry ",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "government_contractors_and_public_sector_suppliers",
        "build_ideas",
        "R-PROM-01",
        "Guarantee and security register with iss",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "government_contractors_and_public_sector_suppliers",
        "care",
        "R-PROM-01",
        "Never collect officials’ names, departme",
    ): (
        "care text names the banned claim or 'guarantee' in order to forbid it; human-reviewed instruction"
    ),
    (
        "government_contractors_and_public_sector_suppliers",
        "question",
        "R-PROM-01",
        "How much of your cash feels stuck in gua",
    ): ("asks how much cash is stuck in guarantees (a bank guarantee), not a promise"),
    ("hotels", "build_ideas", "R-PRIV-07", "Maintenance ticket flow from desk or gue"): (
        "alert or ticket flow that names a parent/guest in the product description; no personal data is stored in the pack"
    ),
    (
        "hr_and_recruitment_agencies",
        "build",
        "a claim, an amount, a vendor or a named product",
        "a candidate pipeline per job order throu",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "hr_and_recruitment_agencies",
        "build",
        "a claim, an amount, a vendor or a named product",
        "fee invoicing triggered by the joining d",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "hr_and_recruitment_agencies",
        "build_ideas",
        "R-PROM-01",
        "Candidate pipeline per job order with st",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "hr_and_recruitment_agencies",
        "build_ideas",
        "R-PROM-01",
        "Client contract register with fee terms ",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "hr_and_recruitment_agencies",
        "build_ideas",
        "R-PROM-01",
        "Placement and guarantee register with gu",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "importers_and_trading_houses",
        "build",
        "a claim, an amount, a vendor or a named product",
        "A connection so sales and receipts are e",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "importers_and_trading_houses",
        "build_ideas",
        "R-PROM-01",
        "Connection between stock system and Tall",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "insurance_agencies_and_brokers",
        "build_ideas",
        "R-META-01",
        "Renewal register with due dates by line ",
    ): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "internet_service_providers_and_cable_tv_operators",
        "build",
        "a claim, an amount, a vendor or a named product",
        "A new connection pipeline from request t",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "internet_service_providers_and_cable_tv_operators",
        "sample_reply",
        "R-META-01",
        "Ji, is ka rasta nikal sakta hai, aur peh",
    ): (
        "sample reply says what Workzap can do for the problem ('kar sakta hai', 'ho sakta hai'); reviewer to confirm wording"
    ),
    (
        "kids_wear_toys_and_baby_stores",
        "build_ideas",
        "R-META-01",
        "Repeat-purchase reminders on WhatsApp fo",
    ): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "kids_wear_toys_and_baby_stores",
        "care",
        "A2-1.5-SECRETS",
        "Infant-formula pricing rules or restrict",
    ): (
        "care text mentions pricing rules/regulation in order to say pi only notes them; human-reviewed instruction"
    ),
    ("language_centres", "build_ideas", "R-META-01", "WhatsApp FAQ responder for timings, leve"): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "marketing_creative_and_digital_agencies",
        "sample_reply",
        "R-HONEST-01",
        "Yes, there is a way through this, and no",
    ): (
        "opening 'this can be brought under control' / 'there is a way through this' is a soft reassurance the linter flags; builder should drop the claim"
    ),
    (
        "microfinance_field_operations",
        "ask_first",
        "R-ADV-01",
        "Do new officers mostly get loan files wr",
    ): (
        "asks whether officers get loan files wrong, an operations question; reads as financial advice topic only"
    ),
    (
        "milk_collection_centres_and_chillers",
        "sample_reply",
        "R-META-01",
        "Ji haan, ye theek ho sakta hai, aur is k",
    ): (
        "sample reply says what Workzap can do for the problem ('kar sakta hai', 'ho sakta hai'); reviewer to confirm wording"
    ),
    (
        "mobile_wallet_and_payment_agents",
        "build_ideas",
        "R-PROM-01",
        "Busy-hour chart from counter logs to pla",
    ): (
        "'guarantee' or 'connection' as a business noun (bank guarantee register, placement guarantee), not a promise by pi"
    ),
    (
        "music_art_and_dance_schools",
        "build_ideas",
        "R-META-01",
        "WhatsApp enquiry auto-reply with timings",
    ): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "new_car_dealerships_and_showrooms",
        "build",
        "a claim, an amount, a vendor or a named product",
        "a short morning read of leads, bookings,",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "ngos_charities_and_trusts",
        "build_ideas",
        "R-META-01",
        "Donation register capturing every channe",
    ): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    ("orchards", "build_ideas", "R-META-01", "Theka contract tracker: terms, instalmen"): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "pharmacies_and_medical_stores",
        "care",
        "A2-1.5-SECRETS",
        "Regulatory topics (drug licensing, contr",
    ): (
        "care text mentions pricing rules/regulation in order to say pi only notes them; human-reviewed instruction"
    ),
    (
        "pharmacies_and_medical_stores",
        "idea",
        "R-BUILD-06",
        "Do one expiry sweep and list what expire",
    ): (
        "'you'll see' in the benefit clause reads as a promised result; builder should rewrite to 'so you can see'"
    ),
    (
        "property_management_and_rentals",
        "idea",
        "tool words or a build named for free",
        "Check that each platform's calendar is l",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    (
        "quran_academies_and_madrassas",
        "build_ideas",
        "R-META-01",
        "Parent FAQ responder on WhatsApp for tim",
    ): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "real_estate_agencies_and_brokers",
        "idea",
        "tool words or a build named for free",
        "Send all portal enquiries to one office ",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
    (
        "solar_panels_inverters_and_batteries",
        "build_ideas",
        "R-META-01",
        "Maintenance reminder messages on WhatsAp",
    ): (
        "describes a WhatsApp auto-reply or reminder Workzap would build; internal catalogue wording, never said as-is"
    ),
    (
        "study_abroad_and_education_consultants",
        "care",
        "R-HONEST-01",
        "“Guaranteed visa” or “100% success” mark",
    ): (
        "care text names the banned claim ('guaranteed visa', 'earn $1,000') in order to forbid it; human-reviewed instruction"
    ),
    (
        "study_abroad_and_education_consultants",
        "care",
        "R-PROM-01",
        "“Guaranteed visa” or “100% success” mark",
    ): (
        "care text names the banned claim or 'guarantee' in order to forbid it; human-reviewed instruction"
    ),
    (
        "surgical_and_dental_instruments_manufacturing",
        "idea",
        "R-PAY-05",
        "Note each shipped order with shipment da",
    ): (
        "owner records when their own customers paid (a ledger idea); not pi taking or confirming a payment"
    ),
    (
        "unstitched_fabric_lawn_and_textile_retail",
        "build",
        '"will", not "would": no promised results (R-BUILD-06)',
        "sell-through by design and volume by wee",
    ): (
        "'designs will be left over' describes the owner's stock, not a promised result; builder should say 'would'"
    ),
    (
        "unstitched_fabric_lawn_and_textile_retail",
        "idea",
        "R-PRIV-04",
        "Give one person the job of writing the s",
    ): (
        "asks the owner to write a salesman name on a sale record (a third-party name); builder should say 'salesman role/code'"
    ),
    (
        "warehousing_and_3pl",
        "build",
        "a claim, an amount, a vendor or a named product",
        "Order intake that accepts client spreads",
    ): (
        "a business noun the check reads as a claim ('connection', 'guarantee', 'spreadsheets', 'pipeline'), not a vendor or amount"
    ),
    (
        "water_tanker_and_ro_filtration_plant_operators",
        "sample_reply",
        "R-META-01",
        "Haan, is par kaam ho sakta hai, aur is k",
    ): (
        "sample reply says what Workzap can do for the problem ('kar sakta hai', 'ho sakta hai'); reviewer to confirm wording"
    ),
    (
        "yacht_and_boat_charters",
        "idea",
        "tool words or a build named for free",
        "Match one month's platform payouts again",
    ): (
        "names a system or platform the owner already uses (app, POS, calendar, portal); the idea is an owner action, not a Workzap build; reviewer to confirm"
    ),
}


def test_every_stored_pack_line_passes_the_idea_and_reply_checks() -> None:
    found = _found()
    keys = {(p, f, r, t[:40]) for p, f, r, t in found}
    unlisted = sorted(k for k in keys if k not in ALLOWED)
    stale = sorted(k for k in ALLOWED if k not in keys)
    assert not unlisted, "violations not in ALLOWED:\n" + "\n".join(map(repr, unlisted))
    assert not stale, "ALLOWED entries that no longer fire:\n" + "\n".join(map(repr, stale))


def test_the_vetting_sees_what_it_should() -> None:
    """The harness itself: it reads the fields and it does catch a promise, advice and a price."""
    assert len(list(SOLUTIONS.glob("*.json"))) > 200 and len(list(PACKS.glob("*.json"))) > 200
    assert sr.check_idea("Count your stock once, so you see the gap in 20% of lines").reject
    assert sr.check_idea("Guarantee your customers a 30% rise, so sales grow").reject
    assert _hard("We guarantee results.", _ctx("my work is slow"), CONTENT)
    assert sr.check_build_line("a board that will raise sales", ["job_tracking"])
