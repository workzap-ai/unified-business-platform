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


# --- spec 9.8 milestone 9: three probe conversations per industry ------------------------------

EVERYDAY = [
    "my customers pay late and the staff come late",
    "stock runs out and I do not know what to reorder",
    "sales are down this month and I cannot tell why",
    "we waste a lot of time on paperwork every day",
    "I have too many whatsapp groups and nothing is tracked",
    "my team does not follow up with leads",
    "cash does not match at the end of the day",
    "suppliers deliver late and prices keep changing",
    "I want to grow my business but things are messy",
    "customers complain and I hear about it late",
]


def probes(pack: dict) -> dict[str, str]:
    """Three ways a person of this trade might talk, made from the pack's own spec text."""
    person = " ".join(t["text"] for t in pack.get("exchange", []) if t.get("role") == "Person")
    phrases = [p["phrase"] for p in pack.get("problems", [])]
    return {
        "states the trade": f"I run a {pack['name'].lower()}. {phrases[0]}",
        "tells their story": person[:400],
        "lists two problems": " ".join(phrases[:2]),
    }


def test_every_industry_has_three_probe_conversations():
    for pack in industries():
        made = probes(pack)
        assert len(made) == 3 and all(text.strip() for text in made.values()), pack["key"]


def test_a_person_who_states_their_trade_gets_that_pack():
    right = sum(
        packs.detect([probes(p)["states the trade"]]).primary == p["key"] for p in industries()
    )
    assert right / len(industries()) >= 0.95, right


def test_everyday_complaints_that_name_no_trade_pick_no_industry():
    wrong = [text for text in EVERYDAY if packs.detect([text]).industries]
    assert wrong == []


def test_when_pi_picks_a_pack_from_the_problems_alone_it_is_usually_right():
    """Spec 7.0: unclear after two problems, pi may ask once. A wrong industry is worse than no
    industry, so precision matters more than recall here."""
    right = wrong = 0
    for p in industries():
        for name in ("tells their story", "lists two problems"):
            primary = packs.detect([probes(p)[name]]).primary
            right += primary == p["key"]
            wrong += primary is not None and primary != p["key"]
    assert right / (right + wrong) >= 0.60, (right, wrong)


@pytest.mark.parametrize(
    ("said", "key"),
    [
        ("I run a pharmacy", "pharmacies_and_medical_stores"),
        ("we have a bakery", "bakeries_mithai_and_confectionery"),
        ("I own a dental clinic", "dental_clinics"),
        ("hamara garments ka kaam hai", "garment_and_knitwear_export_units"),
        ("main pharmacy chalata hun", "pharmacies_and_medical_stores"),
        (
            "clients ask for invoices late at our accounting practice",
            "accounting_audit_and_tax_practices",
        ),
    ],
)
def test_one_word_statements_of_the_trade_are_still_enough(said, key):
    assert packs.detect([said]).primary == key


def test_a_single_rare_word_without_a_statement_is_not_enough():
    assert packs.detect(["pharmacy"]).industries == []
    assert packs.detect(["the dentist said so"]).industries == []


@pytest.mark.parametrize(
    "said",
    [
        "I'm the store manager at a pharmacy chain. My boss asked me to tell you our problems.",
        "I am the manager of a pharmacy",
        "I work at a pharmacy chain as store manager",
    ],
)
def test_a_manager_in_a_pharmacy_chain_gets_the_pharmacy_care_rules(said):
    """Golden G13: pharmacy care rules apply even though the speaker is not the owner, and the
    catch-all "retail shops and chains" pack does not take the chat over."""
    found = packs.detect([said])
    assert found.primary == "pharmacies_and_medical_stores"
    text = packs.brief(packs.get_pack(found.primary), max_chars=5200)
    assert "Care:" in text


def test_a_shop_owner_who_names_no_specific_trade_stays_with_the_catch_all_pack():
    assert packs.detect(["I own a chain of retail shops with many branches"]).primary == (
        "retail_shops_and_chains"
    )
    assert packs.detect(["we told our manager about it"]).industries == []


@pytest.mark.parametrize(
    ("said", "key"),
    [
        ("مرحباً، عندنا مطعم في دبي والطلبات من التطبيقات تضيع", "restaurants"),  # golden G8
        ("عندي صيدلية والمخزون ينفد", "pharmacies_and_medical_stores"),
        ("أنا أملك مخبز صغير", "bakeries_mithai_and_confectionery"),
        ("عندنا مصنع ملابس", "garment_and_knitwear_export_units"),
        ("میرا ریسٹورنٹ ہے", "restaurants"),
        ("ہم گارمنٹس کا کاروبار کرتے ہیں", "garment_and_knitwear_export_units"),
        ("ہمارا ہوٹل ہے", "hotels"),
    ],
)
def test_a_person_who_writes_in_arabic_or_urdu_script_gets_an_industry(said, key):
    """Before this, a message in either script matched no industry at all: the packs hold only
    English and Roman Urdu words."""
    assert packs.detect([said]).primary == key


@pytest.mark.parametrize(
    "said",
    [
        "الطلبات تضيع والموظفين يتأخرون",  # orders get lost and staff come late
        "مرحبا كيف حالك",  # hello, how are you
        "ذهب إلى السوق",  # he went to the market ("ذهب" also means gold)
        "میں نے کل کھانا کھایا",  # I ate yesterday
        "مال ختم ہو جاتا ہے اور عملہ دیر سے آتا ہے",  # stock runs out and staff come late
    ],
)
def test_ordinary_arabic_and_urdu_talk_picks_no_industry(said):
    assert packs.detect([said]).industries == []


def test_the_script_words_belong_to_real_packs_and_match_however_they_are_written():
    from app.modules.pi.industry_words import TRADE_WORDS

    assert set(TRADE_WORDS) <= set(packs.load_packs())
    # with or without the article, vowel marks, or the Urdu or Arabic form of the same letter
    for said in ("عندنا المطعم", "عِندنا مطعمٌ", "وعندنا مطعم"):
        assert packs.detect([said]).primary == "restaurants", said


@pytest.mark.parametrize(
    ("said", "key"),
    [
        ("I run a dental clinic", "dental_clinics"),
        ("I run a vet clinic for animals", "veterinary_clinics_and_animal_health_suppliers"),
        ("عندنا عيادة اسنان", "dental_clinics"),
        ("عندنا عيادة بيطرية", "veterinary_clinics_and_animal_health_suppliers"),
        ("عندنا عيادة نفسية", "mental_health_and_therapy_practices"),
        ("عندي عيادة جلدية", "aesthetic_and_dermatology_clinics"),
        ("I run a skin and dermatology clinic", "aesthetic_and_dermatology_clinics"),
        ("I run a clinic", "clinics_and_gp_practices"),
        ("I run a school", "private_schools_and_school_chains"),
    ],
)
def test_a_care_trade_wins_over_the_general_pack_that_shares_one_of_its_words(said, key):
    """The care packs carry the stricter rules (no diagnosis, no treatment advice), so a dental,
    veterinary, mental health or dermatology clinic must not end up with the general clinic pack
    because of the alphabet."""
    assert packs.detect([said]).primary == key


@pytest.mark.parametrize(
    "said",
    [
        "I work at a bank and my wife visits a pharmacy",
        "We have a problem. The pharmacy next door is cheaper",
        "I have a lot of work and a pharmacy owner is my friend",
        "عندي ولد عمره 5 سنوات",  # I have a son aged 5 ("عمره" is also "umrah")
        "عندي مشكلة في الكلية",  # I have a problem with my kidney ("كلية" is also "college")
        "عندي كمبيوتر قديم",  # I have an old computer
    ],
)
def test_a_statement_elsewhere_or_an_everyday_word_does_not_name_a_trade(said):
    """One trade word is enough only when the person states their trade in the same clause."""
    assert packs.detect([said]).industries == []


def test_a_statement_must_sit_in_the_same_clause_as_the_trade_word():
    assert packs.detect(["I run a pharmacy"]).primary == "pharmacies_and_medical_stores"
    assert packs.detect(["Hello. I run a pharmacy, stock is a mess"]).primary == (
        "pharmacies_and_medical_stores"
    )
    assert packs.detect(["I run a business. The pharmacy next door is cheaper"]).industries == []
