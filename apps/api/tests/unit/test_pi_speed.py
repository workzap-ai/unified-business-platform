"""The speed numbers (no database, no Redis): the percentiles, the signal's timestamp, and the
live-update samples the open screens report."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.modules.pi import live_events, speed

TENANT, ENV = uuid4(), uuid4()


def test_percentiles_of_nothing_is_none_and_of_a_list_is_its_spread() -> None:
    assert speed.percentiles([]) is None
    spread = speed.percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert spread == {"p50": 6, "p90": 10, "avg": 5.5, "max": 10}
    assert speed.percentiles([2.5]) == {"p50": 2.5, "p90": 2.5, "avg": 2.5, "max": 2.5}


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0),
        (1500, 1500),
        ("42", 42),
        (600_000, 600_000),
        (-1, None),
        (600_001, None),
        ("x", None),
    ],
)
def test_a_reported_time_is_a_whole_number_in_range_or_dropped(
    value: object, expected: int | None
) -> None:
    assert speed.clamp_ms(value) == expected
    assert speed.clamp_ms(None) is None


def test_a_signal_carries_its_publish_time_and_the_wait_is_measured_on_one_clock() -> None:
    assert live_events.split_signal("inbox|1000", now_ms=1250) == ("inbox", 250)
    assert live_events.split_signal("handoff|1000", now_ms=900) == ("handoff", 0)  # never negative
    assert live_events.split_signal("inbox") == ("inbox", None)  # an older publisher
    assert live_events.split_signal("inbox|abc") == ("inbox", None)


def test_a_frame_names_its_kind_and_wait_and_nothing_else() -> None:
    assert live_events.frame("inbox") == 'event: change\ndata: {"kind": "inbox"}\n\n'
    assert live_events.frame("inbox", 40) == (
        'event: change\ndata: {"kind": "inbox", "lag_ms": 40}\n\n'
    )


class Pipe:
    def __init__(self, parent: "Store") -> None:
        self.parent, self.ops = parent, []

    def lpush(self, key: str, value: str) -> "Pipe":
        self.ops.append(("lpush", key, value))
        return self

    def ltrim(self, key: str, start: int, stop: int) -> "Pipe":
        self.ops.append(("ltrim", key, start, stop))
        return self

    def expire(self, key: str, seconds: int) -> "Pipe":
        self.ops.append(("expire", key, seconds))
        return self

    async def execute(self) -> list[Any]:
        if self.parent.fail:
            raise ConnectionError("down")
        self.parent.ops.extend(self.ops)
        return []


class Store:
    def __init__(self, *, fail: bool = False, alive: bool = True, items: list[Any] | None = None):
        self.ops: list[tuple[Any, ...]] = []
        self.fail, self.alive, self.items = fail, alive, items or []

    def pipeline(self) -> Pipe:
        return Pipe(self)

    async def exists(self, key: str) -> int:
        return int(self.alive)

    async def lrange(self, key: str, start: int, stop: int) -> list[Any]:
        if self.fail:
            raise ConnectionError("down")
        return self.items


def settings(*, on: bool = True) -> Any:
    return SimpleNamespace(pi_events_enabled=on, secrets_encryption_key=SecretStr("k" * 32))


async def test_a_sample_is_kept_capped_and_expiring() -> None:
    store = Store()
    assert await speed.record_timing(store, TENANT, ENV, 40, 700)
    kinds = [op[0] for op in store.ops]
    assert kinds == ["lpush", "ltrim", "expire"]
    assert store.ops[0][2].startswith("40,700,")
    assert store.ops[1][2:] == (0, speed.TIMING_KEEP - 1)


async def test_a_bad_or_unsaveable_sample_is_dropped_without_an_error() -> None:
    store = Store()
    assert not await speed.record_timing(store, TENANT, ENV, -5, 10)
    assert not await speed.record_timing(store, TENANT, ENV, 10, 10**9)
    assert not await speed.record_timing(None, TENANT, ENV, 10, 10)
    assert not await speed.record_timing(Store(fail=True), TENANT, ENV, 10, 10)
    assert store.ops == []


async def test_live_stats_when_off_say_so_and_touch_nothing() -> None:
    stats = await speed.live_stats(Store(), settings(on=False), TENANT, ENV)
    assert stats["enabled"] is False and stats["samples"] == 0 and stats["total_ms"] is None


async def test_live_stats_report_the_spread_and_whether_a_worker_is_publishing() -> None:
    store = Store(items=[b"100,400,1", b"300,600,2", b"bad", b"x,y,z"])
    stats = await speed.live_stats(store, settings(), TENANT, ENV)
    assert stats["enabled"] and stats["publishing"] and stats["samples"] == 2
    assert stats["server_lag_ms"]["max"] == 300 and stats["screen_ms"]["max"] == 600
    assert stats["total_ms"]["max"] == 900
    quiet = await speed.live_stats(Store(alive=False), settings(), TENANT, ENV)
    assert quiet["publishing"] is False and quiet["samples"] == 0


async def test_live_stats_survive_an_unreachable_redis() -> None:
    stats = await speed.live_stats(Store(fail=True), settings(), TENANT, ENV)
    assert stats["enabled"] and stats["samples"] == 0


async def test_a_sample_can_name_the_slowest_refetch_and_only_known_names() -> None:
    store = Store()
    assert await speed.record_timing(store, TENANT, ENV, 5, 600, 9000, "conversations")
    assert store.ops[0][2].endswith(",9000,conversations")
    assert await speed.record_timing(store, TENANT, ENV, 5, 600, 9000, "drop table")
    assert store.ops[3][2].endswith(",9000,")  # an unknown name is not kept


async def test_live_stats_name_the_slowest_part_and_its_time() -> None:
    items = [b"1,600,1,9000,conversations", b"1,700,2,8000,conversations", b"1,500,3,100,messages"]
    stats = await speed.live_stats(Store(items=items), settings(), TENANT, ENV)
    assert stats["slowest_part"] == "conversations" and stats["slowest_ms"]["max"] == 9000
    old = await speed.live_stats(Store(items=[b"1,600,1"]), settings(), TENANT, ENV)
    assert old["slowest_part"] is None and old["samples"] == 1  # samples from before still count
