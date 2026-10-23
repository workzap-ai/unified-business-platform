"""The pure parts of the learning-brain gap closers (spec 8.2, 8.5, 8.9, 11.7 step 8)."""

from collections import Counter
from types import SimpleNamespace

import pytest

from app.modules.pi import (
    experience_scorer,
    learning_audit,
    learning_drift,
    learning_gate,
    learning_lexicon,
    learning_seed,
    learning_situation,
    learning_voice,
)

# --- 8.2: the situation key and its back-off -------------------------------------------------


def test_person_type_comes_from_the_role_and_team_size_they_gave():
    assert learning_situation.person_type_of({"role": "owner", "team_size": "6 staff"}) == (
        "owner_small"
    )
    assert learning_situation.person_type_of({"role": "Founder", "team_size": "40"}) == (
        "owner_large"
    )
    assert learning_situation.person_type_of({"role": "branch manager"}) == "manager"
    assert learning_situation.person_type_of({"role": "munshi"}) == "staff"
    assert learning_situation.person_type_of({}) == ""


def test_the_backoff_drops_person_type_first_and_keeps_the_language_in_every_level():
    levels = learning_situation.backoff(
        state="S2_CLARIFYING",
        language="roman_ur",
        turn_kind="question",
        industry="dairy_farm",
        category="cash_collections",
        person_type="owner_small",
    )
    assert "person_type" in levels[0] and "person_type" not in levels[1]
    assert all(level["language"] == "roman_ur" for level in levels)
    assert levels[-1] == {"language": "roman_ur"}  # industry is the last thing to go


def test_an_old_three_part_key_still_fits():
    old = {"state": "S2_CLARIFYING", "language": "en", "turn_kind": "question"}
    level = {"industry": "dairy_farm", "state": "S2_CLARIFYING", "language": "en"}
    assert learning_situation.fits(old, level)  # a missing part means "any"
    assert not learning_situation.fits({"state": "S2_CLARIFYING"}, {"language": "en"})  # language


def test_an_example_for_one_industry_is_never_for_another():
    dental = {"industry": "dental_clinics", "language": "en"}
    allowed = learning_situation.industry_allowed
    assert not allowed(dental, "cattle_and_buffalo_dairy_farms", "C", sector_ok=True)
    assert allowed(dental, "dental_clinics", "I", sector_ok=False)
    assert allowed(
        {"language": "en"}, "cattle_and_buffalo_dairy_farms", "C", sector_ok=False
    )  # a general one


def test_the_sector_step_lets_a_sibling_industry_in_but_not_a_stranger():
    dental = {"industry": "dental_clinics", "language": "en"}
    sector = learning_situation.sector_of("dental_clinics")
    assert sector and sector == learning_situation.sector_of("clinics_and_gp_practices")
    sibling = "clinics_and_gp_practices"
    assert learning_situation.industry_allowed(dental, sibling, sector, sector_ok=True)
    assert not learning_situation.industry_allowed(dental, sibling, sector, sector_ok=False)


# --- 8.3: "noted" in every language pi replies in -----------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "Thanks. I've noted it: best-sellers running out.",
        "Shukriya. Note kar liya: udhaar ke paise wapas nahi aate.",
        "شکریہ۔ میں نے نوٹ کر لیا: ادھار کی وصولی۔",
        "شكرا. تم تسجيل المشكلة: نفاد المخزون.",
    ],
)
def test_noted_is_recognised_in_english_roman_urdu_urdu_and_arabic(line):
    assert experience_scorer.says_noted(line)


def test_a_plain_question_is_not_noted():
    assert not experience_scorer.says_noted("Is it every shop, or only some?")


# --- 11.7 step 8: the seeds --------------------------------------------------------------------


def test_golden_conversations_split_into_person_and_pi_turns():
    pairs = learning_seed.golden_pairs()
    assert pairs and all(person and reply for _, person, reply in pairs)
    assert any(gid == "G6" for gid, _, _ in pairs)  # a Roman Urdu golden conversation


def test_a_seed_passes_the_live_gate_or_is_dropped():
    ok, _ = learning_seed.admit(
        "We keep running out of our best-selling items.",
        "That's a real problem. Is it happening in every shop, or only some?",
    )
    assert ok
    named, _ = learning_seed.admit(
        "cash never matches at the Johar Town branch",
        "Thanks. I've noted it. Which of these costs you the most?",
    )
    assert not named  # a name-like word fails the redaction bar
    pitch, _ = learning_seed.admit(
        "can you make an app for this?",
        "Workzap can prepare a solution document for you. What would the app fix first?",
    )
    assert not pitch  # nothing about solutions while listening


@pytest.mark.parametrize(
    ("question", "slot"),
    [
        ("How often does it happen?", "frequency"),
        ("Which routes worry you most right now?", "scope"),
        ("What does it cost you each month?", "impact"),
        ("How do you handle it today?", "workaround"),
        ("Do you like blue?", None),
    ],
)
def test_pack_questions_map_to_a_question_slot(question, slot):
    assert learning_seed.slot_of(question) == slot


# --- 8.5 job 4: spelling variants --------------------------------------------------------------


def test_roman_urdu_spelling_variants_are_one_term():
    counts = Counter({"nuksan": 5, "nuqsan": 3, "nuksaan": 1, "udhaar": 4})
    clusters = learning_lexicon.cluster_variants(counts)
    assert clusters["nuqsan"][0] == "nuksan" and clusters["nuksaan"][0] == "nuksan"
    assert sorted(clusters["nuksan"][1]) == ["nuksaan", "nuqsan"]
    assert clusters["udhaar"] == ("udhaar", [])


def test_the_lesson_names_the_other_spellings():
    text = learning_lexicon.lesson_text("nuksan", "cash_losses", ["nuqsan"])
    assert 'When someone says "nuksan" (or "nuqsan")' in text


# --- voice seeds in Roman Urdu -----------------------------------------------------------------


def test_roman_urdu_voice_seeds_follow_the_style_and_pass_the_gate():
    for moment, by_language in learning_voice.SEEDS.items():
        seeds = by_language["roman_ur"]
        assert len(seeds) >= learning_voice.MIN_LIVE
        for text in seeds:
            assert learning_voice.valid(moment, text) == [], text


# --- 8.9: the frozen drift reference ------------------------------------------------------------


def stats(replies=40, words=20.0, many=0.0, emoji=0.0, english=0.0):
    return learning_drift.Stats(replies, words, many, emoji, english)


def test_slow_creep_is_caught_against_the_frozen_first_week():
    golden, first = stats(), stats(words=20.0)
    # Each week only a little longer than the week before, so the rolling window never trips.
    assert learning_drift.drift(stats(words=24.0), stats(words=26.0)) == []
    assert "replies longer than the frozen reference" in learning_drift.drift_from_frozen(
        golden, first, stats(words=27.0)
    )


def test_the_frozen_reference_catches_more_questions_and_emoji_and_stays_quiet_otherwise():
    found = learning_drift.drift_from_frozen(stats(), stats(), stats(many=0.2, emoji=0.2))
    assert len(found) == 2
    assert learning_drift.drift_from_frozen(stats(), stats(), stats()) == []
    assert learning_drift.drift_from_frozen(stats(), None, stats(replies=5, words=99.0)) == []


def test_the_golden_baseline_is_made_from_the_spec_conversations():
    assert learning_drift.golden_stats().replies >= learning_drift.MIN_GOLDEN


# --- 8.5 job 9: the replay grade ---------------------------------------------------------------

LISTEN = {
    "pi_mode": "brain",
    "strict_voice": True,
    "flow": {"state": "S2_CLARIFYING"},
    "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
    "latest_customer_message": "stock runs out",
}


def test_a_clean_conversation_grades_two_and_a_hard_break_is_a_rule_break():
    clean = learning_gate.grade_replies([("That's a real problem. Is it every shop?", LISTEN)])
    assert clean.mean == 2.0 and not clean.rule_break
    broke = learning_gate.grade_replies(
        [("Please send me your card number and the OTP so I can check?", LISTEN)]
    )
    assert broke.rule_break and broke.reasons


def test_the_replay_bar_is_the_spec_10_3_bar():
    from app.modules.pi import learning_grader as g

    good = [("en", g.Grade(False, 1.9, [])) for _ in range(5)]
    assert g.release_gate(good).ok
    bad = [*good, ("roman_ur", g.Grade(False, 1.2, []))]
    assert not g.release_gate(bad).ok


# --- 8.9: the audit stamp ----------------------------------------------------------------------


def test_the_prompt_version_is_stable_and_pack_versions_name_the_industry_pack():
    assert learning_audit.prompt_version() == learning_audit.prompt_version() != ""
    conversation = SimpleNamespace(service_brief={})
    versions = learning_audit.pack_versions(conversation, {"industry": "dental_clinics"})
    assert list(versions) == ["dental_clinics"] and versions["dental_clinics"]
