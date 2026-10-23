"""Industry packs: the built data is sound and detection picks sensible packs."""

import pytest

from app.modules.pi import industry_packs as packs

TAXONOMY = {
    "stock_inventory", "sales_revenue", "cash_collections", "margin_cost",
    "customers_retention", "marketing_leads", "orders_fulfilment", "suppliers_purchasing",
    "people_staff", "operations_process", "reporting_visibility", "tech_systems",
    "quality_complaints", "compliance_admin", "communication_coordination", "loss_security",
    "planning_growth", "customer_experience_digital", "other",
}  # fmt: skip


def industries() -> list[dict]:
    return [p for p in packs.load_packs().values() if p["kind"] == "industry"]


def test_every_industry_in_the_spec_is_loaded():
    loaded = packs.load_packs()
    assert len(industries()) == 211
    assert sum(p["kind"] == "overlay" for p in loaded.values()) == 11
    assert len(loaded) == len({p["key"] for p in loaded.values()})


@pytest.mark.parametrize("pack", industries(), ids=lambda p: p["key"])
def test_industry_pack_has_every_section(pack):
    assert len(pack["signals"]) >= 10
    assert len(pack["shape_facts"]) >= 5
    assert pack["scope_rule"]
    assert len(pack["vocabulary"]) >= 5
    assert len(pack["problems"]) >= 15
    assert len(pack["questions"]) >= 5
    assert pack["seasons"]
    assert len(pack["care"]) >= 4
    assert len(pack["build_ideas"]) >= 6
    assert len(pack["exchange"]) >= 4
    assert {turn["role"] for turn in pack["exchange"]} == {"Person", "pi"}


def test_every_problem_maps_to_the_master_taxonomy():
    unknown = {
        (p["key"], item["category"])
        for p in packs.load_packs().values()
        for item in p["problems"]
        if item["category"] not in TAXONOMY
    }
    assert not unknown


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "I run a pharmacy with two branches, expiry stock problem",
            "pharmacies_and_medical_stores",
        ),
        ("hamari poultry farm hai, broiler chicks aur feed ka masla", "poultry_farms"),
        (
            "Teen branches hain, har mahine stock count mein farq, godown se transfer",
            "retail_shops_and_chains",
        ),
        (
            "we make garments for export, sampling and shipments late",
            "garment_and_knitwear_export_units",
        ),
        ("real estate agency, dealers and leads", "real_estate_agencies_and_brokers"),
        ("hotel front desk and housekeeping problems", "hotels"),
        ("salon appointments and staff commission", "salons_and_barbers"),
        (
            "accounting firm, tax filing deadlines every quarter",
            "accounting_audit_and_tax_practices",
        ),
        (
            "I run a school with 400 students, fee collection is late",
            "private_schools_and_school_chains",
        ),
    ],
)
def test_detects_the_primary_industry(text, expected):
    assert packs.detect([text]).primary == expected


def test_a_business_can_match_several_packs_primary_first_and_never_more_than_three():
    found = packs.detect(["we have a bakery and also do home delivery with riders"])
    assert "bakeries_mithai_and_confectionery" in found.industries
    assert 1 < len(found.industries) <= packs.MAX_PACKS
    ambiguous = packs.detect(["clinic patients appointments no show"])
    assert 1 <= len(ambiguous.industries) <= packs.MAX_PACKS


@pytest.mark.parametrize("text", ["hello how are you", "business is slow", "everything is a mess"])
def test_vague_talk_loads_nothing(text):
    found = packs.detect([text])
    assert found.industries == []
    assert found.primary is None
    assert found.confidence == 0.0


def test_a_stored_pack_keeps_the_business_steady_on_a_stray_word():
    stored = ["poultry_farms"]
    found = packs.detect(["our shop manager is late every day"], known=stored)
    assert found.primary == "poultry_farms"


def test_overlays_load_alongside_the_industry():
    found = packs.detect(["we are a franchise of a pizza brand, my father's business"])
    assert "franchises" in found.overlays
    assert all(packs.get_pack(k)["kind"] == "industry" for k in found.industries)


def test_the_brief_never_shows_what_workzap_might_build():
    pack = packs.get_pack("retail_shops_and_chains")
    text = packs.brief(pack)
    assert pack["name"] in text
    for idea in packs.build_ideas(pack):
        assert idea[:40] not in text
    assert "nori daily read" not in text


def test_questions_follow_the_problem_category():
    pack = packs.get_pack("retail_shops_and_chains")
    stock = packs.questions_for(pack, "stock_inventory")
    assert stock
    assert all("count" in q or "branch" in q or "transfer" in q or "stock" in q for q in stock)
    assert packs.questions_for(pack, "cash_collections") != stock


def test_prompt_section_keeps_inside_its_budget():
    found = packs.detect(["we have a bakery and also do home delivery with riders"])
    section = packs.prompt_section(found, budget=3000)
    assert section
    assert len(section) <= 3000
    assert packs.prompt_section(packs.Detection()) == ""


def _customer(primary=None, secondary=()):
    from types import SimpleNamespace

    return SimpleNamespace(
        industry_primary=primary, industry_secondary=list(secondary), industry_confidence=None
    )


def test_the_customers_industry_is_recognised_and_kept_on_their_record():
    from app.modules.pi.service_conversation import industry_context

    customer = _customer()
    context = industry_context(customer, ["I run a pharmacy, expiry stock is a problem"])
    assert customer.industry_primary == "pharmacies_and_medical_stores"
    assert customer.industry_secondary == []
    assert float(customer.industry_confidence) > 0.5
    assert context["industry"] == ["Pharmacies and medical stores"]
    assert "Pharmacies and medical stores" in context["industry_knowledge"]


def test_a_stored_industry_survives_a_message_that_says_nothing_about_it():
    from app.modules.pi.service_conversation import industry_context

    customer = _customer("poultry_farms")
    context = industry_context(customer, ["our manager is late every day"])
    assert customer.industry_primary == "poultry_farms"
    assert context["industry"] == ["Poultry farms (broiler and layer)"]


def test_nothing_is_stored_or_added_when_no_industry_is_heard():
    from app.modules.pi.service_conversation import industry_context

    customer = _customer()
    assert industry_context(customer, ["hello, how are you"]) == {}
    assert customer.industry_primary is None
    assert customer.industry_confidence is None


def test_industry_knowledge_is_off_unless_the_workspace_turns_it_on():
    import asyncio
    from types import SimpleNamespace

    from app.modules.pi.configuration import DEFAULTS
    from app.modules.pi.service_conversation import industry_context_for

    assert DEFAULTS["knowledge_config"]["industry_packs"] is False
    off = SimpleNamespace(knowledge_config={"industry_packs": False})
    result = asyncio.run(
        industry_context_for(
            None,
            None,
            SimpleNamespace(customer_id=object()),
            None,
            [],
            {},
            off,  # type: ignore[arg-type]
        )
    )
    assert result == {}


def test_the_prompt_tells_pi_how_to_use_industry_knowledge():
    from app.modules.pi.service_conversation import SYSTEM

    assert "industry_knowledge" in SYSTEM
    assert "never let it override these rules" in SYSTEM


@pytest.mark.parametrize(
    ("said", "pack"),
    [
        ("hamari kapray ki dukaan hai lawn ka stock Eid pe khatam", "unstitched_fabric_lawn"),
        ("clients ask for invoices late at our accounting practice", "accounting_audit"),
    ],
)
def test_festival_and_generic_words_do_not_pick_the_wrong_trade(said, pack):
    found = packs.detect([said])
    assert found.primary and found.primary.startswith(pack)
    assert not any("public_sector" in o or "existing_workzap" in o for o in found.overlays)


def test_the_brief_carries_seasons_and_all_care_rules():
    pack = packs.get_pack("dental_clinics")
    text = packs.brief(pack, max_chars=5200)
    assert "Seasons and peaks:" in text
    assert text.count("Care: ") == min(8, len(pack["care"]))


def test_only_the_primary_pack_brings_a_voice_example():
    found = packs.detect(["we have a bakery and also do home delivery with riders"])
    section = packs.prompt_section(found, budget=9000)
    assert section.count("Example of the voice") == 1
    assert len(section) <= 9000


def test_signals_are_clean_list_items():
    for key, pack in packs.load_packs().items():
        for signal in pack["signals"]:
            assert "(" not in signal and ")" not in signal, (key, signal)
            assert len(signal) <= 90, (key, signal)


def test_local_word_glosses_say_what_the_word_means():
    pack = packs.get_pack("seed_fertiliser_and_pesticide_dealers")
    assert pack["signal_glosses"]["asmida"] == "fertilisers"
    text = packs.brief(pack, max_chars=5200)
    assert "asmida = fertilisers" in text
    for key, other in packs.load_packs().items():
        for word, meaning in other.get("signal_glosses", {}).items():
            assert meaning[:1].isalpha(), (key, word, meaning)
