"""How industry knowledge reaches pi: nothing that forbids is cut, the sector's never-rules reach
every pack of the sector, what was noted decides the questions, seasons fit the customer's country,
and detection is measured on the specification's own exchanges."""

import sys
from pathlib import Path

import pytest

from app.modules.pi import industry_packs as packs
from app.modules.pi import spec_handbook

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import measure_industry_detection as measure  # noqa: E402


def industries() -> list[dict]:
    return [p for p in packs.load_packs().values() if p["kind"] == "industry"]


# --- 1 and 4: the sector's never-rules and the brief that carries them ----------------------------

SECTOR_PHRASES = {
    "C.1": "never diagnoses animals",
    "C.2": "never gives agronomy advice",
    "D.2": "safety-engineering",
    "E.1": "under-invoicing",
    "F.1": "safety-engineering advice",
    "G.1": "at-sea incident",
    "I.1": "never asks for or records any patient",
    "J.1": "never asks for, records or repeats any student",
    "K.1": "never gives the professional advice",
    "L.1": "never gives financial",
    "M.1": "deceased-person",
}


def test_every_sector_with_rules_in_the_specification_has_them_stored():
    intros = packs.sector_intros()
    for key, phrase in SECTOR_PHRASES.items():
        assert phrase in intros[key]["rules"], key
        assert intros[key]["rules"] in intros[key]["intro"], key


@pytest.mark.parametrize("pack", industries(), ids=lambda p: p["key"])
def test_every_pack_gets_its_sectors_rules(pack):
    assert packs.sector_key(pack) in packs.sector_intros(), pack["key"]
    rules = packs.sector_rules(pack)
    if rules:
        assert rules in packs.brief(pack, max_chars=5200), pack["key"]
        assert rules in packs.brief(pack, max_chars=2600), pack["key"]


def test_children_and_patients_rules_reach_every_school_and_clinic_pack():
    for pack in industries():
        if pack["sector"]["code"] == "J":
            assert "never asks for, records or repeats" in packs.brief(pack, max_chars=5200)
        if pack["sector"]["code"] == "I":
            assert "patient" in packs.sector_rules(pack)


def test_a_secondary_pack_still_brings_its_sectors_never_rules():
    found = packs.Detection(industries=["restaurants", "hospitals"])
    section = packs.prompt_section(found)
    assert "never asks for or records any patient" in section
    # one sector's rules are said once, not once per pack
    both = packs.Detection(industries=["hospitals", "dental_clinics"])
    assert packs.prompt_section(both).count("never asks for or records any patient") == 1


@pytest.mark.parametrize("pack", industries(), ids=lambda p: p["key"])
def test_care_and_scope_rules_are_never_cut(pack):
    text = packs.brief(pack, max_chars=5200)
    for item in pack["care"]:
        assert "Care: " + " ".join(item.split()) in text, item
    assert "Scope: " + " ".join(pack["scope_rule"].split()) in text
    for line in text.splitlines():
        if line.startswith(("Care: ", "Scope: ", "Sector rules")):
            assert line.rstrip().endswith((".", ")", '"', "”", "!", "?")), line


def test_clipping_keeps_the_prohibitions_and_cuts_on_sentences():
    long = "pi notes sales and stock. " + "It does nothing else of use here. " * 30
    long += "pi never gives medical advice. It never asks for a card number."
    clipped = packs._clip_sentences(long, 300)
    assert "never gives medical advice" in clipped
    assert "never asks for a card number" in clipped
    assert clipped.endswith(".")


def test_a_pack_with_the_longest_rules_in_three_packs_keeps_every_rule_inside_the_budget():
    biggest = sorted(industries(), key=lambda p: -packs.core_size(p))[:3]
    found = packs.Detection(industries=[p["key"] for p in biggest])
    section = packs.prompt_section(found)
    assert len(section) <= packs.DEFAULT_BUDGET
    for pack in biggest:
        for item in pack["care"]:
            assert " ".join(item.split()) in section


# --- 2: what was noted decides the questions and the phrases ------------------------------------


def test_questions_and_phrases_follow_the_noted_problem_categories():
    pack = packs.get_pack("retail_shops_and_chains")
    cash = packs.brief(pack, ["cash_collections"], max_chars=5200)
    stock = packs.brief(pack, ["stock_inventory"], max_chars=5200)
    assert cash != stock
    assert "Heard as cash_collections/" in cash and "Heard as stock_inventory/" not in cash
    assert "Heard as stock_inventory/" in stock
    assert (
        packs.pick_questions(pack, ["cash_collections"])
        == packs.questions_for(pack, "cash_collections")[:3]
    )


def test_with_nothing_noted_the_questions_rotate_through_every_area():
    pack = packs.get_pack("poultry_farms")
    seen: set[str] = set()
    for turn in range(len(pack["questions"])):
        seen.update(packs.pick_questions(pack, (), rotation=turn))
    openers = {qs[0] for qs in pack["questions"].values() if qs}
    assert openers <= seen
    assert packs.pick_questions(pack, (), rotation=0) != packs.pick_questions(pack, (), rotation=1)
    # every problem phrase gets a turn too, not just the first fourteen of the PDF
    shown = {p["phrase"] for turn in range(12) for p in packs.pick_problems(pack, (), turn)}
    assert len(shown) == len(pack["problems"])


def test_industry_context_passes_the_noted_categories_and_country():
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import industry_context

    customer = SimpleNamespace(
        industry_primary=None, industry_secondary=[], industry_confidence=None
    )
    context = industry_context(
        customer,
        ["I run a poultry farm, feed stock and dealer credit"],
        categories=["cash_collections"],
        country="AE",
    )
    text = context["industry_knowledge"]
    assert "Heard as cash_collections/" in text
    assert "Canada:" not in text.split("Seasons and peaks:")[1].split("\n")[0]


# --- 3: seasons for the customer's country, whole ------------------------------------------------


@pytest.mark.parametrize("country", ["PK", "AE", "CA"])
def test_seasons_are_whole_parts_and_include_the_customers_country(country):
    mark = packs.COUNTRY_MARKS[country]
    for pack in industries():
        shown = packs.seasons_for(pack["seasons"], country)
        assert shown, pack["key"]
        original = " ".join(str(pack["seasons"]).split())
        for part in shown.split("; "):
            assert part in original, (pack["key"], part)
        own = [
            p.strip(" .")
            for p in packs._SEASON_SPLIT.split(str(pack["seasons"]).lstrip("- "))
            if mark.search(p) and sum(bool(m.search(p)) for m in packs.COUNTRY_MARKS.values()) == 1
        ]
        if own:
            assert any(o in shown for o in own), (pack["key"], country)


def test_seasons_drop_the_other_countries_and_keep_all_when_the_country_is_unknown():
    pack = packs.get_pack("poultry_farms")
    uae = packs.seasons_for(pack["seasons"], "AE")
    assert "UAE" in uae and "Canada" not in uae and "Pakistan: broiler" not in uae
    unknown = packs.seasons_for(pack["seasons"], None)
    assert "UAE" in unknown and "Canada" in unknown and "Pakistan" in unknown


# --- 5: detection --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "key"),
    [
        (
            "we run an aesthetic clinic, bookings from Instagram",
            "aesthetic_and_dermatology_clinics",
        ),
        ("we have a spa and wellness centre, therapists commission", "spas_and_wellness_centres"),
        (
            "we distribute medical equipment to hospitals",
            "medical_equipment_and_device_distributors",
        ),
        ("we are a pharmaceutical manufacturing company, batches", "pharmaceutical_manufacturing"),
        ("we run a cold chain business with reefer trucks", "cold_chain_logistics"),
        ("we service lifts, AMC renewals are a mess", "elevator_and_escalator_services"),
        ("we install solar panels for homes", "solar_epc_and_installers"),
        ("we do facility management for buildings", "facility_management"),
        ("we rent cars with drivers", "car_rental_and_chauffeur_services"),
        ("we sell and install AC units", "hvac_ac_sales_installation_and_service"),
        ("we rent out farmhouses on weekends", "resorts_and_farmhouse_rentals"),
        ("we send nurses to patients homes", "home_healthcare_and_nursing_agencies"),
        ("we are an architecture firm", "architects_and_engineering_consultancies"),
        ("I run a used car showroom", "used_car_dealers"),
        ("عندنا شركة تنظيف", "cleaning_and_janitorial_companies"),
        ("ہم لفٹ کی سروس کرتے ہیں", "elevator_and_escalator_services"),
    ],
)
def test_natural_statements_of_a_trade_get_that_pack(said, key):
    assert packs.detect([said]).primary == key


@pytest.mark.parametrize(
    "said",
    ["Hamara kaam theek hai, bas customer call bahut karte hain", "driving us mad this month"],
)
def test_everyday_words_inside_a_trades_name_do_not_pick_it(said):
    assert packs.detect([said]).industries == []


def test_detection_rates_on_the_specifications_own_exchanges_do_not_regress():
    """Measured before this work (first message, first two, whole story): right 73/81/89, none
    104/87/77, wrong 34/43/45 of 211. Wrong loads another trade's care rules, so it is held down."""
    result = measure.measure()
    bound = {"first": (78, 26), "two": (85, 32), "all": (92, 33)}
    for scenario, (min_right, max_wrong) in bound.items():
        assert len(result[scenario]["right"]) >= min_right, scenario
        assert len(result[scenario]["wrong"]) <= max_wrong, scenario


# --- handbook ------------------------------------------------------------------------------------


def test_the_handbook_carries_every_sector_intro_and_can_add_them_for_a_customer():
    book = spec_handbook.sections()
    assert {f"7.S.{key}" for key in packs.sector_intros()} <= set(book)
    text = spec_handbook.guidance("S1_LISTENING", "hello", sectors=["I.1"])
    assert "never asks for or records any patient" in text
    assert "never asks for or records any patient" not in spec_handbook.guidance(
        "S1_LISTENING", "hello"
    )


def test_the_addendum_scope_of_each_sector_reaches_every_pack_of_that_sector() -> None:
    """Addendum 2 Part 4 intros: e.g. 7.G part 2 (nothing here touches finance terms, licensing,
    safety engineering or the legality of trade practices) and 7.H (roles, not names)."""
    from app.modules.pi import industry_packs as ip

    intros = ip.sector_intros()
    with_scope = {k for k, v in intros.items() if v.get("addendum_scope")}
    assert len(with_scope) >= 16
    checked = 0
    for pack in ip.load_packs().values():
        scope = str(intros.get(ip.sector_key(pack), {}).get("addendum_scope") or "")
        if scope:
            assert scope.lower() in ip.sector_rules(pack).lower()
            checked += 1
    assert checked > 100
