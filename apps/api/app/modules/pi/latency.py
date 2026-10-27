"""Per-turn stage timing for pi's WhatsApp replies.

Cheap by design: a monotonic clock around each stage, summed into one dict per turn that lives in
a ContextVar (so concurrent turns in one worker never mix). `emit` writes ONE structured log line
per turn. Nothing here changes what pi says, and a failure to time or log can never fail a turn.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_turn: ContextVar[dict[str, Any] | None] = ContextVar("pi_turn_timing", default=None)


def begin() -> dict[str, Any]:
    """Start a fresh record for this turn (stages in ms, counters)."""
    record: dict[str, Any] = {
        "stages_ms": {},
        "model_calls": 0,
        "prompt_chars": 0,
        "t0": time.perf_counter(),
    }
    _turn.set(record)
    return record


def current() -> dict[str, Any] | None:
    return _turn.get()


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Time a block; repeated stages with the same name add up."""
    start = time.perf_counter()
    record = _turn.get()
    if record is not None:
        record.setdefault("_active", []).append(name)
    try:
        yield
    finally:
        record = _turn.get()
        if record is not None:
            if record.get("_active"):
                record["_active"].pop()
            took = round((time.perf_counter() - start) * 1000, 1)
            stages = record["stages_ms"]
            stages[name] = round(stages.get(name, 0.0) + took, 1)


async def timed[T](name: str, work: Awaitable[T]) -> T:
    """Await `work` and add its time to the stage `name`."""
    with stage(name):
        return await work


def count(key: str, amount: int = 1) -> None:
    record = _turn.get()
    if record is not None:
        record[key] = record.get(key, 0) + amount


def note(key: str, value: str) -> None:
    """A short text for the turn's log line (for example why a draft was sent back). The first
    value per key wins, and it is clipped: it is for finding causes, never for the person."""
    record = _turn.get()
    if record is not None:
        record.setdefault("notes", {}).setdefault(key, str(value)[:300])


def emit(logger: logging.Logger, **extra: Any) -> None:
    """One structured line per turn; `extra` carries ids (conversation, message)."""
    record = _turn.get()
    if record is None:
        return
    try:
        logger.info(
            "pi turn timing",
            extra={
                "stages_ms": dict(record["stages_ms"]),
                "wall_ms": round((time.perf_counter() - record["t0"]) * 1000, 1),
                "model_calls": record["model_calls"],
                "prompt_chars": record["prompt_chars"],
                "rewrites": record.get("rewrites", 0),
                "notes": dict(record.get("notes", {})),
                **extra,
            },
        )
    except Exception:  # noqa: BLE001 - timing must never fail a reply
        logger.debug("pi turn timing could not be logged", exc_info=True)
    finally:
        _turn.set(None)


def summary() -> dict[str, Any] | None:
    """This turn's timing as plain numbers, small enough to keep on the message so a slow reply
    can be traced from the database alone (no log access): every stage in ms, the time since the
    turn began, and the model calls and prompt size. None when no turn is being timed."""
    record = _turn.get()
    if record is None:
        return None
    return {
        "stages_ms": {k: round(v) for k, v in record["stages_ms"].items()},
        "wall_ms": round((time.perf_counter() - record["t0"]) * 1000),
        "model_calls": record["model_calls"],
        "prompt_chars": record["prompt_chars"],
    }
