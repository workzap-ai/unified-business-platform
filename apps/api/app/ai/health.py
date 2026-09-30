"""In-process circuit breaker per provider (closed -> open -> half_open -> closed)."""

from __future__ import annotations

import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.core.config import Settings

CircuitState = Literal["closed", "open", "half_open"]


@dataclass(slots=True)
class _Circuit:
    failures: int = 0
    opened_at: float | None = None
    probing: bool = False
    cooldown: float | None = None  # None = the default transient cooldown
    reason: str | None = None  # "auth"/"quota" when the account itself can't serve
    fingerprint: str | None = None  # credential the verdict was about


class ProviderHealth:
    """Consecutive transient failures >= threshold open the circuit for ``cooldown``.

    After the cooldown one probe request is allowed (half_open); success closes the
    circuit, failure re-opens it. State is per process (each API/worker process
    learns independently) and never shared through Redis.

    ``disable`` opens the circuit at once for ``disable_seconds`` when the provider
    account can't serve anyone (rejected key, credits/quota finished). Saving a new key
    clears it immediately: see ``credential``.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        disable_seconds: float = 600.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.disable_seconds = disable_seconds
        self.clock = clock
        self._circuits: dict[str, _Circuit] = {}

    def _get(self, provider: str) -> _Circuit:
        return self._circuits.setdefault(provider, _Circuit())

    def state(self, provider: str) -> CircuitState:
        circuit = self._get(provider)
        if circuit.opened_at is None:
            return "closed"
        cooldown = self.cooldown_seconds if circuit.cooldown is None else circuit.cooldown
        if self.clock() - circuit.opened_at >= cooldown:
            return "half_open"
        return "open"

    def allow(self, provider: str) -> bool:
        """True when a request may be sent; reserves the single half-open probe."""
        state = self.state(provider)
        if state == "closed":
            return True
        if state == "open":
            return False
        circuit = self._get(provider)
        if circuit.probing:
            return False
        circuit.probing = True
        return True

    def record_success(self, provider: str) -> None:
        self._circuits[provider] = _Circuit(fingerprint=self._get(provider).fingerprint)

    def disable(self, provider: str, reason: str) -> None:
        """Take the provider out now for ``disable_seconds`` (then one probe is allowed)."""
        circuit = self._get(provider)
        circuit.failures += 1
        circuit.opened_at, circuit.probing = self.clock(), False
        circuit.cooldown, circuit.reason = self.disable_seconds, reason

    def credential(self, provider: str, fingerprint: str) -> None:
        """A different key than the one a verdict was about: forget that verdict."""
        circuit = self._get(provider)
        if circuit.fingerprint != fingerprint:
            self._circuits[provider] = _Circuit(fingerprint=fingerprint)

    def record_failure(self, provider: str) -> None:
        circuit = self._get(provider)
        circuit.probing = False
        if circuit.opened_at is not None:  # failed half-open probe: open again
            circuit.opened_at = self.clock()
            return
        circuit.cooldown, circuit.reason = None, None
        circuit.failures += 1
        if circuit.failures >= self.failure_threshold:
            circuit.opened_at = self.clock()

    def release(self, provider: str) -> None:
        """Release a half-open probe that ended without a health verdict."""
        self._get(provider).probing = False

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            name: {
                "state": self.state(name),
                "consecutive_failures": c.failures,
                "reason": c.reason if c.opened_at is not None else None,
            }
            for name, c in self._circuits.items()
        }


_health_by_settings: dict[int, ProviderHealth] = {}


def health_for(settings: Settings) -> ProviderHealth:
    """Process-wide breaker bound to one Settings object (the app/worker singleton).

    Keyed by identity so independently configured apps (and tests) do not share state.
    """
    key = id(settings)
    health = _health_by_settings.get(key)
    if health is None:
        health = ProviderHealth(
            settings.llm_circuit_failure_threshold,
            settings.llm_circuit_cooldown_seconds,
            disable_seconds=settings.llm_circuit_quota_cooldown_seconds,
        )
        _health_by_settings[key] = health
        weakref.finalize(settings, _health_by_settings.pop, key, None)
    return health
