"""The follow-up policy of spec 3.9.1 (R-FUP-01 to 05)."""

from datetime import UTC, datetime, timedelta

from app.modules.pi import followup_policy as fp
from app.modules.pi.flow import State as S

T0 = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)


def chat(state, **more):
    base = {"state": state, "last_inbound_at": T0, "sent": {}}
    base.update(more)
    return fp.Chat(**base)


def test_silence_mid_description_gets_one_nudge_inside_the_window_after_20_hours():
    due = fp.next_followup(chat(S.S1_LISTENING))
    assert due == fp.Due("silent", T0 + timedelta(hours=20), needs_template=False)
    assert fp.next_followup(chat(S.S2_CLARIFYING, sent={"silent": 1})) is None  # at most 1


def test_the_silence_hours_follow_the_clamped_setting():
    rules = {"brain": {"followup_silence_hours": 6}}
    assert fp.next_followup(chat(S.S1_LISTENING), rules).at == T0 + timedelta(hours=6)
    rules = {"brain": {"followup_silence_hours": 99}}  # clamped to 23, still inside the window
    assert fp.next_followup(chat(S.S1_LISTENING), rules).at == T0 + timedelta(hours=23)


def test_a_declined_offer_is_never_followed_up():
    for state in (S.S5B_DECLINED, S.S9B_DECLINED_QUOTE, S.X_BLOCKED):
        assert fp.next_followup(chat(state, documents_sent_at=T0)) is None


def test_later_gets_one_template_after_three_days_then_stops():
    paused = T0 + timedelta(hours=1)
    due = fp.next_followup(chat(S.X_PAUSED, paused_at=paused))
    assert due.kind == "paused" and due.at == paused + timedelta(days=3)
    assert due.needs_template  # three days is outside the 24-hour window
    assert fp.next_followup(chat(S.X_PAUSED, paused_at=paused, sent={"paused": 1})) is None


def test_documents_are_followed_up_after_2_days_then_7_days_and_no_more():
    sent = T0
    first = fp.next_followup(chat(S.S7_DELIVERED, documents_sent_at=sent))
    assert first.kind == "documents" and first.at == sent + timedelta(days=2)
    second = fp.next_followup(chat(S.S8_REVIEW, documents_sent_at=sent, sent={"documents": 1}))
    assert second.at == sent + timedelta(days=7)
    assert (
        fp.next_followup(chat(S.S8_REVIEW, documents_sent_at=sent, sent={"documents": 2})) is None
    )


def test_kickoff_reminders_come_24_hours_and_1_hour_before():
    kick = T0 + timedelta(days=5)
    first = fp.next_followup(chat(S.S12_KICKOFF, kickoff_at=kick))
    assert first.kind == "kickoff_24h" and first.at == kick - timedelta(hours=24)
    second = fp.next_followup(chat(S.S12_KICKOFF, kickoff_at=kick, sent={"kickoff_24h": 1}))
    assert second.kind == "kickoff_1h" and second.at == kick - timedelta(hours=1)
    assert (
        fp.next_followup(
            chat(S.S12_KICKOFF, kickoff_at=kick, sent={"kickoff_24h": 1, "kickoff_1h": 1})
        )
        is None
    )


def test_stop_ends_everything():
    assert fp.next_followup(chat(S.S1_LISTENING, opted_out=True)) is None
    assert fp.next_followup(chat(S.X_PAUSED, paused_at=T0, opted_out=True)) is None


def test_nothing_is_returned_before_it_is_due():
    now = T0 + timedelta(hours=5)
    assert fp.next_followup(chat(S.S1_LISTENING), now=now) is None
    assert fp.next_followup(chat(S.S1_LISTENING), now=T0 + timedelta(hours=21)) is not None


def test_no_follow_up_ever_pressures_the_person():  # R-FUP-01
    for kind, table in fp.MESSAGES.items():
        for language, text in table.items():
            lower = text.lower()
            assert not any(word in lower for word in fp.PRESSURE), (kind, language)
            assert "!" not in text


def test_the_texts_name_the_noted_problems_and_the_kickoff_time():
    assert "4 noted problems" in fp.text_for("paused", "en", n=4)
    assert "kickoff is Friday 3 PM" in fp.text_for("kickoff_24h", "en", when="Friday 3 PM")
    assert "masail" in fp.text_for("paused", "roman_ur", n=2)
