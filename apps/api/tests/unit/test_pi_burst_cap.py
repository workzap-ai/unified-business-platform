"""Platform spec v1.4, 17.2: a burst is waited out for 6 s of quiet, but never longer than 25 s."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.pi import runtime


class FakeSession:
    def __init__(self, last_reply, first):
        self.values = [last_reply, first]

    async def scalar(self, _query):
        return self.values.pop(0)


def message():
    return SimpleNamespace(
        tenant_id="t", environment_id="e", conversation_id="c", created_at=datetime.now(UTC)
    )


def run(first_ago: float | None, rules: dict | None = None) -> bool:
    now = datetime.now(UTC)
    first = None if first_ago is None else now - timedelta(seconds=first_ago)
    return asyncio.run(runtime.burst_too_long(FakeSession(None, first), message(), rules or {}))


def test_a_young_burst_is_still_waited_out() -> None:
    assert run(8) is False


def test_a_burst_older_than_the_cap_is_answered_now() -> None:
    assert run(26) is True


def test_the_cap_is_tunable_inside_its_range() -> None:
    assert run(20, {"brain": {"burst_max_seconds": 15}}) is True
    assert run(20, {"brain": {"burst_max_seconds": 5}}) is True  # clamped up to 15, still over
    assert run(10, {"brain": {"burst_max_seconds": 5}}) is False


def test_no_unanswered_message_means_no_cap() -> None:
    assert run(None) is False
