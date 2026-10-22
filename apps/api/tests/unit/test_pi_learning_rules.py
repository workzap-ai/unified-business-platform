"""Decision rules of the nightly learning jobs (spec 8.5; learning evals L9, L11, L12, L14)."""

from datetime import UTC, datetime, timedelta

from app.modules.pi import learning_rules as r


def test_an_exchange_becomes_a_candidate_only_when_it_went_well_clean_and_redacted():
    assert r.should_promote_example(3, 1.8, False, 0.98)
    assert not r.should_promote_example(2, 1.9, False, 0.99)  # reward too low
    assert not r.should_promote_example(5, 1.7, False, 0.99)  # rubric too low
    assert not r.should_promote_example(5, 2.0, True, 0.99)  # a rule break is never learned
    assert not r.should_promote_example(5, 2.0, False, 0.97)  # not redacted confidently enough


def test_the_bank_keeps_one_example_per_business_and_a_cap_per_situation():
    rows = [
        {"situation": "s1", "business": "a", "reward": 3},
        {"situation": "s1", "business": "a", "reward": 5},  # same business: only the best stays
        {"situation": "s1", "business": "b", "reward": 4},
    ]
    kept = r.balance_examples(rows)
    assert [(x["business"], x["reward"]) for x in kept] == [("a", 5), ("b", 4)]
    many = [{"situation": "s", "business": str(i), "reward": i} for i in range(50)]
    assert len(r.balance_examples(many)) == r.MAX_PER_SITUATION


def test_deleting_a_contact_removes_what_came_from_them():  # L11
    rows = [
        {"id": 1, "source_contacts": ["ali"]},
        {"id": 2, "source_contacts": ["sara", "ali"]},
        {"id": 3, "source_contacts": ["sara"]},
    ]
    kept, removed = r.without_contact(rows, "ali")
    assert [x["id"] for x in kept] == [3] and removed == 2


def test_a_term_is_learned_after_five_businesses_and_ninety_percent_agreement():
    seen = [("udhaar", f"b{i}", "cash_collections") for i in range(5)]
    assert r.lexicon_terms(seen) == {"udhaar": "cash_collections"}
    assert r.lexicon_terms(seen[:4]) == {}  # four businesses is not enough
    mixed = [("khata", f"b{i}", "cash_collections") for i in range(8)] + [
        ("khata", "b9", "people_staff"),
        ("khata", "b10", "people_staff"),
    ]
    assert r.lexicon_terms(mixed) == {}  # 80% agreement is not enough
    same_business = [("hisaab", "b1", "cash_collections")] * 9
    assert r.lexicon_terms(same_business) == {}  # one loud business is not five


CONTROL = r.Rates(conversations=400, reward=1.0, opt_out=0.01, confusion=0.05, correction=0.08)


def test_a_canary_with_rising_opt_outs_is_rolled_back_at_once():  # L9
    worse = r.Rates(conversations=40, reward=1.5, opt_out=0.03, confusion=0.05, correction=0.08)
    assert r.canary_decision(CONTROL, worse) == "rollback"
    assert r.breached(CONTROL, worse) == ["opt_out"]


def test_any_rule_break_rolls_back_whatever_else_improved():
    breaking = r.Rates(conversations=900, reward=3.0, rule_break=0.001)
    assert r.canary_decision(CONTROL, breaking) == "rollback"


def test_a_canary_is_promoted_only_with_enough_conversations_and_no_worse_reward():
    good = r.Rates(conversations=350, reward=1.2, opt_out=0.01, confusion=0.04, correction=0.07)
    assert r.canary_decision(CONTROL, good) == "promote"
    assert r.canary_decision(CONTROL, r.Rates(100, 1.2, opt_out=0.01)) == "continue"  # too few
    assert r.canary_decision(CONTROL, r.Rates(400, 0.9, opt_out=0.01)) == "continue"  # worse


def test_a_setting_moves_one_step_inside_its_range_and_at_most_weekly():
    now = datetime(2026, 11, 10, tzinfo=UTC)
    assert r.next_setting_value("summary_trigger", 7, +1, None, now) == 8
    assert r.next_setting_value("summary_trigger", 7, -1, now - timedelta(days=8), now) == 6
    assert r.next_setting_value("summary_trigger", 7, +1, now - timedelta(days=2), now) == 7
    assert r.next_setting_value("summary_trigger", 10, +1, None, now) == 10  # top of the range
    assert r.next_setting_value("summary_trigger", 5, -1, None, now) == 5
    assert r.next_setting_value("max_clarify", 3, +1, None, now) == 3  # never above the rule


def test_a_pack_is_drafted_for_five_unclassified_businesses():  # L12
    assert r.should_draft_pack(5) and not r.should_draft_pack(4)


def test_listening_sections_can_go_live_but_care_sections_never_do():  # L12
    assert r.pack_may_go_live("Questions", 20, 1.7, 1.6)
    assert not r.pack_may_go_live("Questions", 19, 1.7, 1.6)  # not enough shadow conversations
    assert not r.pack_may_go_live("Questions", 30, 1.5, 1.6)  # worse than the generic fallback
    assert not r.pack_may_go_live("Scope rule", 500, 2.0, 1.0)
    assert not r.pack_may_go_live("Handle with care", 500, 2.0, 1.0)
    assert not r.pack_may_go_live("Anything else", 500, 2.0, 1.0)  # unknown sections are held
    assert r.needs_human_review("Scope rule") and r.needs_human_review("Handle with care")
    assert not r.needs_human_review("Words")
