"""The plan case file (FT-A3, case format v2) keeps its promises: 30 synthetic cases, an envelope
the loader can trust, no text shared between splits or with the extraction cases, every expected
value traceable to what the owner said, and the 132 extraction cases untouched. These check the
data, not a model, and none of them is a measure of how well pi solves problems."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.modules.pi.evalkit import replay, splits

CASES_DIR = Path(replay.__file__).with_name("cases")
PLAN_PATH = CASES_DIR / "plan.json"
EXTRACTION_PATH = CASES_DIR / "extraction.json"
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
EXTRACTION = replay.load_cases(str(EXTRACTION_PATH))
# sha256 of extraction.json with CRLF folded to LF, taken before FT-A3 began: the file never changes
EXTRACTION_SHA256 = "6b0f3cd6b6ed4851600e8bcb2082613b15b249b085389b89e41ef7a83befb570"
VERDICTS = {"relevant", "irrelevant", "generic", "violates_constraint", "restates_owner"}
KINDS = {"solution_relevance", "constraint_violation", "no_idea_valid", "borderline_relevance"}
LANGUAGES = {"en", "roman_ur", "ur", "ar", "hi"}
BUSINESS = {
    "booking": {"sports_clubs_academies_and_turf_court_rentals", "resorts_and_farmhouse_rentals"},
    "rental": {
        "car_rental_and_chauffeur_services",
        "generator_sales_rental_and_service",
        "property_management_and_rentals",
    },
    "e_commerce": {"e_commerce_and_d2c_brands"},
    "saas": {"saas_companies", "it_services_and_software_houses"},
    "wedding_banquet": {"banquet_halls_and_marquees", "wedding_planners_and_event_management"},
    "healthcare": {
        "clinics_and_gp_practices",
        "pharmacies_and_medical_stores",
        "dental_clinics",
    },
    "education": {"tuition_centres_and_academies", "private_schools_and_school_chains"},
    "logistics": {
        "courier_and_last_mile_delivery_companies",
        "trucking_and_goods_transport_companies",
    },
    "agriculture": {"poultry_farms", "crop_farming", "cattle_and_buffalo_dairy_farms"},
}
PII = [
    re.compile(r"\+?\d[\d\s-]{8,}\d"),  # a phone-like run of digits
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),  # an email
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # a card-like number
]


def split(case: dict) -> str:
    return splits.split_of(case)


CORE = [c for c in PLAN if c["kind"] != "borderline_relevance"]
BORDER = [c for c in PLAN if c["kind"] == "borderline_relevance"]
HELD = [c for c in PLAN if split(c) == splits.HELD_OUT]
OTHERS = [c for c in PLAN if split(c) != splits.HELD_OUT]


def texts(case: dict) -> list[str]:
    """The case text the sharing rule covers: messages, titles, limits and candidate ideas. Reviewer
    reasons are notes no scorer reads, a generic candidate is boilerplate by design ("use better
    software"), and single stated facts ("WhatsApp", "Excel") are shared words, so none counts."""
    out = list(case["input"]["messages"])
    for problem in case["input"]["brief"]["problems"]:
        out += [problem["title"]]
        out += [c["text"] for c in problem["constraints"]]
    out += [c["text"] for c in case["expected"]["candidates"] if c.get("verdict") != "generic"]
    return out


def test_the_plan_file_has_thirty_core_cases_and_twelve_borderline_cases() -> None:
    assert isinstance(PLAN, list) and len(CORE) == 30 and len(BORDER) == 12


def test_the_extraction_cases_are_untouched() -> None:
    raw = EXTRACTION_PATH.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == EXTRACTION_SHA256
    assert len(EXTRACTION) == 132
    by_split = Counter(split(c) for c in EXTRACTION)
    assert by_split == {splits.HELD_OUT: 60, splits.DEVELOPMENT: 69, splits.REGRESSION: 3}


def test_ids_are_unique_across_both_case_files() -> None:
    ids = [c["id"] for c in PLAN] + [c["id"] for c in EXTRACTION]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", PLAN, ids=lambda c: c["id"])
def test_every_case_has_the_v2_envelope(case) -> None:
    assert case["case_type"] == "plan" and case["format_version"] == 2
    assert case["kind"] in KINDS and case["language"] in LANGUAGES
    assert case["synthetic"] is True and case["regression"] is False
    assert {"author", "reviewer", "created", "origin"} <= set(case["provenance"])
    assert case["provenance"]["origin"] == "hand_written"
    assert "split" not in case, "the split is the hash of the id, never stored"
    assert 0 < len(case["title"].split()) <= 8
    assert case["industry"] in set().union(*BUSINESS.values())


@pytest.mark.parametrize("case", PLAN, ids=lambda c: c["id"])
def test_every_expected_value_is_something_the_owner_said(case) -> None:
    said = " ".join(case["input"]["messages"]).casefold()
    for problem in case["input"]["brief"]["problems"]:
        for phrase in [*problem["figures"], *problem["user_words"]]:
            assert phrase.casefold() in said, f"{phrase!r} is not in the owner's message"
        for c in problem["constraints"]:
            assert c["status"] in {"confirmed", "assumed"}
            if case["kind"] != "borderline_relevance":
                assert c["blocks"], "a core limit names the words that would break it"
            if c["status"] == "confirmed":
                assert c["text"].casefold() in said, "a confirmed constraint must be stated"


@pytest.mark.parametrize("case", CORE, ids=lambda c: c["id"])
def test_candidates_carry_allowed_verdicts_and_the_right_negative_controls(case) -> None:
    verdicts = [c["verdict"] for c in case["expected"]["candidates"]]
    assert verdicts and set(verdicts) <= VERDICTS
    if case["kind"] == "no_idea_valid":
        assert "relevant" not in verdicts, "a no-idea case must not hide a relevant idea"
        return
    assert "relevant" in verdicts and set(verdicts) - {"relevant"}
    if case["kind"] == "constraint_violation":
        assert "violates_constraint" in verdicts


@pytest.mark.parametrize("case", BORDER, ids=lambda c: c["id"])
def test_borderline_candidates_carry_no_label_in_the_case_file(case) -> None:
    """Agent-drafted labels live in their own file, never in the case file."""
    for candidate in case["expected"]["candidates"]:
        assert set(candidate) == {"id", "text", "problem"}
        assert candidate["text"].strip()


def test_the_borderline_set_covers_the_requested_difficulties() -> None:
    text = json.dumps(BORDER, ensure_ascii=False)
    assert {c["language"] for c in BORDER} >= {"en", "roman_ur", "ur", "ar", "hi"}
    assigned = [
        p["constraints"]
        for c in BORDER
        for p in c["input"]["brief"]["problems"]
        if p["constraints"]
    ]
    statuses = {k["status"] for constraints in assigned for k in constraints}
    assert statuses == {"confirmed", "assumed"}, "an implied limit is assumed, never confirmed"
    assert "implied" in text


def test_no_text_is_shared_between_held_out_and_the_other_plan_cases() -> None:
    held = {t for c in HELD for t in texts(c)}
    others = {t for c in OTHERS for t in texts(c)}
    assert held and others, "both a Held-out and a Development share must exist"
    assert held & others == set()


def test_no_plan_text_is_copied_from_an_extraction_case() -> None:
    extraction = {m for c in EXTRACTION for m in c["messages"]}
    plan = {t for c in PLAN for t in c["input"]["messages"]}
    plan |= {x["text"] for c in PLAN for x in c["expected"]["candidates"]}
    assert extraction & plan == set()


def test_the_cases_cover_the_nine_business_types_and_five_languages() -> None:
    count = Counter()
    for case in PLAN:
        for name, keys in BUSINESS.items():
            if case["industry"] in keys:
                count[name] += 1
    assert set(count) == set(BUSINESS) and min(count.values()) >= 2
    assert {c["language"] for c in PLAN} == LANGUAGES


def test_there_are_constraint_cases_and_a_no_idea_case() -> None:
    kinds = Counter(c["kind"] for c in CORE)
    assert kinds["constraint_violation"] >= 4 and kinds["no_idea_valid"] >= 1


@pytest.mark.parametrize("case", PLAN, ids=lambda c: c["id"])
def test_no_personal_data_and_roles_are_not_names(case) -> None:
    for text in texts(case):
        for pattern in PII:
            assert not pattern.search(text), f"pattern {pattern.pattern} found in {text!r}"
    for role in case["input"]["brief"]["roles"]:
        assert not re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", role), "a role, never a name"


def test_the_split_is_still_the_hash_of_the_id() -> None:
    for case in PLAN:
        digest = hashlib.sha256(case["id"].encode("utf-8")).digest()
        expected = splits.HELD_OUT if digest[0] % 100 < splits.HELD_OUT_PERCENT else "development"
        assert split(case) == expected
