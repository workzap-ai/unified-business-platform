"""Tunable numbers (spec 9.9, 9.10) and the Ramadan follow-up pause (R-FUP-04)."""

from datetime import UTC, datetime

from app.modules.pi import brain_config as bc
from app.modules.pi.followups import iftar_pause
from app.modules.pi.problems import summary_due


def test_defaults_come_from_the_spec_table():
    assert bc.value({}, "debounce_seconds") == 10
    assert bc.value(None, "summary_trigger") == 7
    assert bc.value({}, "redisclose_days") == 30
    assert bc.value({}, "followup_silence_hours") == 20
    assert bc.value({}, "paused_followup_days") == 3


def test_a_workspace_value_is_used_but_clamped_to_the_tested_range():
    assert bc.value({"brain": {"summary_trigger": 5}}, "summary_trigger") == 5
    assert bc.value({"brain": {"summary_trigger": 99}}, "summary_trigger") == 10
    assert bc.value({"brain": {"summary_trigger": 1}}, "summary_trigger") == 5
    assert bc.value({"brain": {"max_clarify": 9}}, "max_clarify") == 3  # never above the rule
    assert bc.value({"brain": {"redisclose_days": "soon"}}, "redisclose_days") == 30
    assert bc.value({"brain": {"redisclose_days": True}}, "redisclose_days") == 30


def test_describe_lists_every_setting_with_its_range():
    shown = bc.describe({"brain": {"summary_trigger": 6}})
    assert shown["summary_trigger"] == {"value": 6, "default": 7, "low": 5, "high": 10}
    assert set(shown) == set(bc.TUNABLES)


def test_the_summary_trigger_follows_the_setting():
    assert summary_due("hmm", 5, 5, trigger=5) == "many"
    assert summary_due("hmm", 5, 5) is None
    assert summary_due("that's all", 1, 0) == "done"


RAMADAN = {"ramadan": [{"start": "2027-02-08", "end": "2027-03-09"}], "maghrib": "18:30"}


def at(day, hour, minute=0):
    # Asia/Karachi is UTC+5
    return datetime(2027, 2, day, hour - 5, minute, tzinfo=UTC)


def test_no_follow_up_within_an_hour_either_side_of_maghrib_in_ramadan():
    end = iftar_pause("Asia/Karachi", RAMADAN, at(15, 18, 0))
    assert end is not None and end == datetime(2027, 2, 15, 14, 30, tzinfo=UTC)  # 19:30 PKT
    assert iftar_pause("Asia/Karachi", RAMADAN, at(15, 17, 45)) is not None
    assert iftar_pause("Asia/Karachi", RAMADAN, at(15, 19, 15)) is not None


def test_outside_the_window_or_outside_ramadan_nothing_is_paused():
    assert iftar_pause("Asia/Karachi", RAMADAN, at(15, 16, 0)) is None
    assert iftar_pause("Asia/Karachi", RAMADAN, at(15, 19, 31)) is None
    assert iftar_pause("Asia/Karachi", RAMADAN, at(5, 18, 30)) is None  # before Ramadan
    assert iftar_pause("Asia/Karachi", {}, at(15, 18, 30)) is None  # no dates configured
    assert iftar_pause("Asia/Karachi", {**RAMADAN, "maghrib": "late"}, at(15, 18, 45)) is not None


def test_the_9_10_numbers_stay_inside_the_spec_ranges():
    assert bc.value(None, "quiet_before_summary") == 2
    assert bc.value({"brain": {"quiet_before_summary": 9}}, "quiet_before_summary") == 3
    assert bc.value({"brain": {"quiet_before_summary": 0}}, "quiet_before_summary") == 1
    for key, base in (("word_cap", 60), ("summary_word_cap", 160), ("document_word_cap", 120)):
        assert bc.value(None, key) == base
        assert bc.value({"brain": {key: 10_000}}, key) == round(base * 1.3)  # +30% at most
        assert bc.value({"brain": {key: 1}}, key) == round(base * 0.7)  # -30% at least


def test_word_caps_follow_the_workspace_setting_but_one_question_still_applies():
    from app.modules.pi import constitution

    def broke(words: int, caps: dict[str, int]) -> list[str]:
        context = {
            "pi_mode": "brain",
            "strict_voice": True,
            "flow": {"state": "S2_CLARIFYING"},
            "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
            "brain_settings": caps,
        }
        reply = " ".join(["stock"] * (words - 1)) + " today?"
        return [v.rule for v in constitution.lint(reply, context) if v.rule == "R-VOICE-01"]

    assert broke(70, {}) == ["R-VOICE-01"]  # 60 by default
    assert broke(70, {"word_cap": 78}) == []  # +30% is allowed
    assert broke(50, {"word_cap": 42}) == ["R-VOICE-01"]  # and so is -30%
    assert broke(50, {}) == []


def test_the_summary_comes_after_the_workspaces_own_number_of_empty_replies():
    from app.modules.pi import problems

    assert problems.summary_due("ok", 2, 1, quiet_replies=1) is None
    assert problems.summary_due("ok", 2, 1, quiet_replies=1, quiet_limit=1) == "quiet"
    assert problems.summary_due("ok", 2, 1, quiet_replies=2) == "quiet"
    assert problems.summary_due("ok", 2, 1, quiet_replies=2, quiet_limit=3) is None
