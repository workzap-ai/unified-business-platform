"""Platform spec v1.4, 17.7: the pure parts of the outage queue (holding lines, backoff, keys)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects import postgresql

from app.modules.pi import outage, runtime
from app.modules.pi.language import detect_language
from app.modules.pi.models import PiMessage


def test_backoff_doubles_from_a_minute_and_stops_at_fifteen() -> None:
    assert [outage.backoff_seconds(n) for n in (1, 2, 3, 4, 5, 6, 20)] == [
        60,
        120,
        240,
        480,
        900,
        900,
        900,
    ]
    assert outage.backoff_seconds(0) == 60


def test_the_holding_line_is_in_the_owners_language_and_promises_no_time() -> None:
    roman = "Mera stock bohat kam ho raha hai, kya karun"
    assert detect_language(roman) == "roman_ur"
    held = outage.notice_for(outage.HOLDING_NOTICES, roman, None)
    assert held == outage.HOLDING_NOTICES["roman_ur"] and "mehfooz" in held
    english = outage.notice_for(outage.HOLDING_NOTICES, "My shop stock keeps running out", None)
    assert english == outage.HOLDING_NOTICES["en"]
    for text in [*outage.HOLDING_NOTICES.values(), *outage.UPDATE_NOTICES.values()]:
        assert "?" not in text and "!" not in text  # no question to the owner, no cheer
        assert not any(w in text.lower() for w in ("minute", "hour", "shortly"))


def test_no_english_update_for_a_roman_urdu_chat() -> None:
    chat = outage.notice_for(outage.UPDATE_NOTICES, "kuch samajh nahi aa raha", "roman_ur")
    assert chat == outage.UPDATE_NOTICES["roman_ur"] != outage.UPDATE_NOTICES["en"]


def test_holding_lines_are_recognised_by_their_key_and_are_not_answers() -> None:
    assert outage.is_outage_key(f"{outage.KEY_PREFIX}abc:hold:1")
    assert not outage.is_outage_key("pi-optout:abc") and not outage.is_outage_key(None)
    sql = str(
        outage.real_reply().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "NOT LIKE 'pi-outage:%" in sql and "IS NULL" in sql


def test_the_state_travels_on_the_message_and_park_marks_it_queued() -> None:
    message = PiMessage(media={"timing": {"x": 1}}, status="received")
    assert outage.state_of(message) == {}
    outage._save(message, {"failures": 2})
    assert outage.state_of(message) == {"failures": 2} and message.media["timing"] == {"x": 1}
    outage.park(message)
    assert (message.status, message.error_code) == ("skipped", outage.CODE)


def test_the_outage_queue_joins_the_burst_and_keeps_the_sweeper_grace() -> None:
    assert outage.CODE in runtime.BURST_CODES  # the answer after recovery covers the queued turn
    assert runtime.EVENT_GRACE_SECONDS >= 90
    now = datetime(2026, 10, 28, 5, 0, tzinfo=UTC)
    assert outage.UPDATE_AFTER == timedelta(minutes=30) and outage.ALERT_AFTER == timedelta(hours=2)
    assert outage._when(now.isoformat()) == now
    assert outage._when("garbage") is None
