"""Platform spec v1.4, 17.7: the return line states the handoff status, once, promising no time."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.pi import service_conversation as sc

OPEN = {"id": "req-1", "kind": "human_requested"}


def ctx(**over):
    base = {"pending_handoff": OPEN, "hours_away": 6, "reply_language": "en", "brief": {}}
    return {**base, **over}


def test_a_returning_owner_with_an_open_request_is_told_once() -> None:
    assert sc.handoff_status_line(ctx()) == sc.HANDOFF_STATUS["en"]
    assert sc.handoff_status_line(ctx(reply_language="roman_ur")) == sc.HANDOFF_STATUS["roman_ur"]
    assert sc.handoff_status_line(ctx(brief={"handoff_status_said": "req-1"})) == ""


def test_no_open_request_or_a_short_gap_says_nothing() -> None:
    assert sc.handoff_status_line(ctx(pending_handoff={})) == ""
    assert sc.handoff_status_line(ctx(hours_away=1)) == ""


def test_the_line_promises_no_time() -> None:
    for text in sc.HANDOFF_STATUS.values():
        assert not any(ch.isdigit() for ch in text)


def test_hours_away_counts_whole_hours_since_their_last_message() -> None:
    now = datetime.now(UTC)
    earlier = SimpleNamespace(
        id=1, sender_type="customer", created_at=now - timedelta(hours=5, minutes=20)
    )
    ours = SimpleNamespace(id=2, sender_type="ai", created_at=now - timedelta(hours=1))
    message = SimpleNamespace(id=3, created_at=now)
    assert sc.hours_away(message, [earlier, ours], None) == 5  # type: ignore[arg-type]
    assert sc.hours_away(message, [], None) == 0  # type: ignore[arg-type]
    assert sc.hours_away(message, [], now - timedelta(hours=9)) == 9  # type: ignore[arg-type]
