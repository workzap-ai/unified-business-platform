"""Live inbox signals (no database, no Redis): the ticket, the publisher that must never hurt a
message, the connection caps, and the stream's frames."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.modules.pi import live_events

TENANT, ENV, USER = uuid4(), uuid4(), uuid4()


def settings(*, on: bool = True, key: str | None = "k" * 32) -> Any:
    return SimpleNamespace(
        pi_events_enabled=on, secrets_encryption_key=SecretStr(key) if key else None
    )


# ---- ticket ------------------------------------------------------------------------------------


def test_a_ticket_round_trips_to_its_workspace_and_person() -> None:
    ticket = live_events.make_ticket(settings(), TENANT, ENV, USER)
    assert live_events.read_ticket(settings(), ticket) == (TENANT, ENV, USER)


def test_an_expired_ticket_is_refused() -> None:
    ticket = live_events.make_ticket(settings(), TENANT, ENV, USER, now=1_000.0)
    assert live_events.read_ticket(settings(), ticket, now=1_000.0 + 59) is not None
    assert live_events.read_ticket(settings(), ticket, now=1_000.0 + 61) is None


def test_a_ticket_signed_with_another_key_or_changed_is_refused() -> None:
    ticket = live_events.make_ticket(settings(), TENANT, ENV, USER)
    assert live_events.read_ticket(settings(key="z" * 32), ticket) is None
    body, signature = ticket.rsplit(".", 1)
    forged = live_events.make_ticket(settings(), uuid4(), ENV, USER).rsplit(".", 1)[0]
    assert live_events.read_ticket(settings(), f"{forged}.{signature}") is None
    assert live_events.read_ticket(settings(), f"{body}.{'0' * 40}") is None


@pytest.mark.parametrize("junk", ["", "abc", "a.b", "....", "e30.deadbeef", "é.é"])
def test_a_malformed_ticket_is_refused_not_raised(junk: str) -> None:
    assert live_events.read_ticket(settings(), junk) is None


def test_the_feature_is_off_unless_the_flag_and_a_key_are_set() -> None:
    assert live_events.enabled(settings())
    assert not live_events.enabled(settings(on=False))
    assert not live_events.enabled(settings(key=None))


# ---- publish never hurts the caller ------------------------------------------------------------


class Recorder:
    def __init__(self, *, fail: bool = False, hang: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail, self.hang = fail, hang

    async def publish(self, name: str, data: str) -> int:
        if self.hang:
            await asyncio.sleep(10)
        if self.fail:
            raise ConnectionError("redis is down")
        self.sent.append((name, data))
        return 1


async def test_publish_sends_one_kind_on_the_workspace_channel() -> None:
    redis = Recorder()
    assert await live_events.publish(redis, settings(), TENANT, ENV, "inbox")
    [(name, data)] = redis.sent
    assert name == live_events.channel(TENANT, ENV)
    assert live_events.split_signal(data)[0] == "inbox"  # "inbox|<epoch ms>"


async def test_publish_does_nothing_when_off_or_without_redis_or_for_a_strange_kind() -> None:
    redis = Recorder()
    assert not await live_events.publish(redis, settings(on=False), TENANT, ENV)
    assert not await live_events.publish(None, settings(), TENANT, ENV)
    assert not await live_events.publish(redis, settings(), TENANT, ENV, "customer-name")
    assert redis.sent == []


async def test_a_redis_error_is_swallowed() -> None:
    assert not await live_events.publish(Recorder(fail=True), settings(), TENANT, ENV)


async def test_a_hanging_redis_costs_half_a_second_at_most(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_events, "PUBLISH_TIMEOUT", 0.05)
    started = asyncio.get_running_loop().time()
    assert not await live_events.publish(Recorder(hang=True), settings(), TENANT, ENV)
    assert asyncio.get_running_loop().time() - started < 1.0


# ---- connection caps ---------------------------------------------------------------------------


def test_a_person_can_hold_only_a_few_streams_and_slots_come_back() -> None:
    person = uuid4()
    held = [live_events.acquire(person) for _ in range(live_events.MAX_PER_USER)]
    assert all(held) and not live_events.acquire(person)
    live_events.release(person)
    assert live_events.acquire(person)
    for _ in range(live_events.MAX_PER_USER):
        live_events.release(person)
    assert live_events.acquire(uuid4())  # another person is unaffected
    assert person.hex not in str(live_events._open_by_user)


# ---- the stream --------------------------------------------------------------------------------


class FakePubSub:
    def __init__(self, messages: list[Any]) -> None:
        self.messages = list(messages)
        self.subscribed: list[str] = []
        self.closed = False

    async def subscribe(self, name: str) -> None:
        self.subscribed.append(name)

    async def get_message(self, **kwargs: Any) -> Any:
        if self.messages:
            return self.messages.pop(0)
        await asyncio.sleep(0.01)
        return None

    async def aclose(self) -> None:
        self.closed = True


class FakeRedis:
    def __init__(self, messages: list[Any], *, publisher: bool = False) -> None:
        self.ps = FakePubSub(messages)
        self.publisher = publisher

    def pubsub(self) -> FakePubSub:
        return self.ps

    async def exists(self, key: str) -> int:
        return int(self.publisher)


def message(data: Any) -> dict[str, Any]:
    return {"type": "message", "data": data}


async def collect(redis: FakeRedis, seconds: float) -> list[str]:
    return [f async for f in live_events.stream(redis, TENANT, ENV, max_seconds=seconds)]


async def test_the_stream_says_ready_then_forwards_only_known_kinds() -> None:
    redis = FakeRedis([message(b"inbox"), message(b"something else"), message("handoff")])
    frames = await collect(redis, 0.2)
    assert frames[0].startswith("retry: 5000") and "event: ready" in frames[0]
    changes = [f for f in frames if f.startswith("event: change")]
    assert [json.loads(f.split("data: ")[1])["kind"] for f in changes] == ["inbox", "handoff"]
    assert redis.ps.subscribed == [live_events.channel(TENANT, ENV)]


async def test_an_event_frame_carries_nothing_but_its_kind() -> None:
    assert live_events.frame("inbox") == 'event: change\ndata: {"kind": "inbox"}\n\n'


async def test_the_stream_sends_heartbeats_ends_on_time_and_unsubscribes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_events, "HEARTBEAT_SECONDS", 0.05)
    redis = FakeRedis([])
    frames = await collect(redis, 0.3)
    assert any(f.startswith("event: ping") for f in frames)
    assert redis.ps.closed


async def test_leaving_early_still_unsubscribes() -> None:
    redis = FakeRedis([message(b"inbox")] * 3)
    generator = live_events.stream(redis, TENANT, ENV, max_seconds=5)
    await anext(generator)  # ready
    await anext(generator)  # one change
    await generator.aclose()  # the person left
    assert redis.ps.closed


async def test_the_screen_is_told_live_only_while_a_worker_is_publishing() -> None:
    quiet = await collect(FakeRedis([], publisher=False), 0.1)
    assert quiet[0].endswith('data: {"live": false}\n\n')
    busy = await collect(FakeRedis([], publisher=True), 0.1)
    assert busy[0].endswith('data: {"live": true}\n\n')


async def test_the_ping_repeats_the_live_bit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_events, "HEARTBEAT_SECONDS", 0.05)
    frames = await collect(FakeRedis([], publisher=True), 0.3)
    pings = [f for f in frames if f.startswith("event: ping")]
    assert pings and all('"live": true' in f for f in pings)


async def test_an_unreachable_redis_means_not_live_not_an_error() -> None:
    class Broken:
        async def exists(self, key: str) -> int:
            raise ConnectionError("down")

    assert await live_events.publisher_alive(Broken()) is False


async def test_the_worker_leaves_a_short_lived_mark_only_when_on() -> None:
    marks: list[tuple[str, str, int]] = []

    class R:
        async def set(self, key: str, value: str, ex: int) -> None:
            marks.append((key, value, ex))

    await live_events.heartbeat({"redis": R(), "settings": settings()})
    assert marks == [(live_events.PUBLISHER_KEY, "1", live_events.PUBLISHER_SECONDS)]
    await live_events.heartbeat({"redis": R(), "settings": settings(on=False)})
    await live_events.heartbeat({"settings": settings()})  # no Redis: nothing, no error
    assert len(marks) == 1


async def test_fire_never_makes_the_caller_wait_for_redis() -> None:
    redis = Recorder(hang=True)
    started = asyncio.get_running_loop().time()
    live_events.fire(redis, settings(), TENANT, ENV)  # a hanging Redis, and fire returns at once
    assert asyncio.get_running_loop().time() - started < 0.05
    live_events.fire(None, settings(), TENANT, ENV)
    live_events.fire(redis, settings(on=False), TENANT, ENV)
    for task in list(live_events._pending):
        task.cancel()
    await live_events.drain()


async def test_fire_delivers_in_the_background() -> None:
    redis = Recorder()
    live_events.fire(redis, settings(), TENANT, ENV, "handoff")
    await live_events.drain()
    [(name, data)] = redis.sent
    assert name == live_events.channel(TENANT, ENV)
    assert live_events.split_signal(data)[0] == "handoff"
