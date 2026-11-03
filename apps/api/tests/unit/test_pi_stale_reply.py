"""Platform spec v1.4, 17.2 (staleReply): a draft is dropped when the owner wrote again meanwhile,
unless the burst is already older than its cap."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.pi import runtime


class FakeSession:
    """newer_waiting asks once; burst_too_long asks for the last reply and the first message."""

    def __init__(self, newer, last_reply, first):
        self.values = [newer, last_reply, first]

    async def scalar(self, _query):
        return self.values.pop(0)


def stale(newer, first_ago):
    now = datetime.now(UTC)
    message = SimpleNamespace(
        tenant_id="t", environment_id="e", conversation_id="c", id="m", created_at=now
    )
    first = now - timedelta(seconds=first_ago)
    return asyncio.run(runtime.stale_reply(FakeSession(newer, None, first), message, {}))


def test_a_newer_message_makes_the_draft_stale() -> None:
    assert stale(newer="n1", first_ago=9) is True


def test_no_newer_message_the_draft_is_sent() -> None:
    assert stale(newer=None, first_ago=9) is False


def test_an_old_burst_is_answered_even_with_a_newer_message() -> None:
    assert stale(newer="n1", first_ago=40) is False
