"""Circuit breaker, counters, small caches and redaction. Pure and in-process.

The breaker and the counters live in each API process (pi runs several); the numbers an operator
reads across processes are the audit rows and the log lines (docs/pi-saas/nori-bridge.md).
"""

import logging
import re
import time
from collections.abc import Callable
from typing import Literal

logger = logging.getLogger("app.pi.nori_credits")

Clock = Callable[[], float]
State = Literal["closed", "open", "half_open"]


class Breaker:
    """closed -> open after `threshold` consecutive failures -> half_open after `cooldown`
    (exactly one probe call is let through) -> closed on a success, open again on a failure."""

    def __init__(self, threshold: int, cooldown: float, clock: Clock = time.monotonic) -> None:
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.state: State = "closed"
        self.failures = 0
        self.opened_at = 0.0
        self._probing = False

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.clock() - self.opened_at < self.cooldown:
                return False
            self.state, self._probing = "half_open", False
        if self._probing:
            return False  # one probe at a time
        self._probing = True
        return True

    def success(self) -> None:
        self.state, self.failures, self._probing = "closed", 0, False

    def failure(self) -> None:
        self._probing = False
        self.failures += 1
        if self.state == "half_open" or self.failures >= self.threshold:
            self.state, self.opened_at = "open", self.clock()

    def release(self) -> None:
        """A call that was allowed but ended without telling us anything (not counted)."""
        self._probing = False


_breakers: dict[str, Breaker] = {}


def breaker_for(key: str, threshold: int, cooldown: float) -> Breaker:
    found = _breakers.get(key)
    if found is None:
        found = _breakers[key] = Breaker(threshold, cooldown)
    else:
        found.threshold, found.cooldown = threshold, cooldown  # a setting change applies at once
    return found


def reset_breakers() -> None:
    _breakers.clear()


class Counters:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def inc(self, name: str, *labels: str) -> None:
        key = ":".join([name, *labels])
        self.values[key] = self.values.get(key, 0) + 1
        logger.info("nori_bridge_metric", extra={"metric": key})

    def snapshot(self) -> dict[str, int]:
        return dict(self.values)

    def reset(self) -> None:
        self.values.clear()


METRICS = Counters()


class TtlCache:
    def __init__(self, clock: Clock = time.monotonic, limit: int = 2000) -> None:
        self.clock, self.limit = clock, limit
        self.items: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        found = self.items.get(key)
        if found is None:
            return None
        if found[0] < self.clock():
            self.items.pop(key, None)
            return None
        return found[1]

    def put(self, key: str, value: object, ttl: float) -> None:
        if len(self.items) >= self.limit:
            self.items.clear()
        self.items[key] = (self.clock() + ttl, value)

    def clear(self) -> None:
        self.items.clear()


IDENTIFY_CACHE = TtlCache()

_DIGITS = re.compile(r"[^0-9]+")


def digits(number: object) -> str:
    return _DIGITS.sub("", str(number or ""))


def mask_number(number: object) -> str:
    """92***4567: enough to tell two people apart in a log, never the whole number."""
    value = digits(number)
    if len(value) < 8:
        return "***"
    return f"{value[:2]}***{value[-4:]}"
