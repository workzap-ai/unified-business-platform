"""The inbound blocklist check must never stop a message from being answered: if the lookup fails
(for example the table is not migrated yet) pi carries on as if nobody is blocked (no database)."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import ProgrammingError

from app.modules.pi import runtime
from app.modules.pi_saas.blocklist import service


class FakeSession:
    def __init__(self) -> None:
        self.savepoints = 0

    @asynccontextmanager
    async def begin_nested(self) -> Any:
        self.savepoints += 1
        yield

    async def flush(self) -> None:
        return None


def event(sender: str = "62895636626854") -> Any:
    return SimpleNamespace(payload={"sender": sender}, status="queued", processed_at=None)


async def test_a_failed_lookup_lets_the_message_through(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(*args: Any, **kwargs: Any) -> None:
        raise ProgrammingError("select", {}, Exception("relation pi_blocked_contacts missing"))

    monkeypatch.setattr(service, "match", broken)
    session, queued = FakeSession(), event()
    assert await runtime._blocked_sender(session, object(), queued) is False  # type: ignore[arg-type]
    assert session.savepoints == 1 and queued.status == "queued"


async def test_a_matching_rule_closes_the_event_and_counts_the_try(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = SimpleNamespace(hits=4, last_hit_at=None)

    async def found(*args: Any, **kwargs: Any) -> Any:
        return rule

    monkeypatch.setattr(service, "match", found)
    queued = event()
    assert await runtime._blocked_sender(FakeSession(), object(), queued) is True  # type: ignore[arg-type]
    assert queued.status == "processed" and queued.processed_at is not None
    assert rule.hits == 5 and rule.last_hit_at is not None


async def test_no_rule_leaves_the_event_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(service, "match", nothing)
    queued = event()
    assert await runtime._blocked_sender(FakeSession(), object(), queued) is False  # type: ignore[arg-type]
    assert queued.status == "queued"
