"""Per-connection circuit breaker: closed -> open -> half_open -> closed.

State is persisted on the connection row (circuit_state, circuit_failure_count,
circuit_opened_at, last_failure_at) so health can report it and every worker/API process
agrees. `Circuit` is the pure transition logic; `load`/`store` copy to and from the row.

* closed: calls flow; each counted failure increments the count; reaching the threshold
  opens the circuit.
* open: calls are rejected (CircuitOpen) until `cooldown` has elapsed since opening.
* half_open: after the cooldown one probe is allowed; success closes, failure re-opens.

Only provider-side failures count (retryable, rate limited, ambiguous, malformed
responses). Credential rejections change the connection status instead.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from app.integrations.errors import IntegrationError

CircuitState = Literal["closed", "open", "half_open"]
COUNTED_KINDS = frozenset({"retryable", "rate_limited", "ambiguous", "invalid_response"})


@dataclass(slots=True)
class Circuit:
    threshold: int
    cooldown: timedelta
    state: CircuitState = "closed"
    failures: int = 0
    opened_at: datetime | None = None
    last_failure_at: datetime | None = None

    def allow(self, now: datetime) -> bool:
        if self.state == "open":
            if self.opened_at is not None and now - self.opened_at >= self.cooldown:
                self.state = "half_open"
                return True
            return False
        return True

    def record_success(self) -> None:
        self.state, self.failures, self.opened_at = "closed", 0, None

    def record_failure(self, now: datetime) -> None:
        self.failures += 1
        self.last_failure_at = now
        if self.state == "half_open" or self.failures >= self.threshold:
            self.state, self.opened_at = "open", now

    @staticmethod
    def counts(error: BaseException) -> bool:
        return isinstance(error, IntegrationError) and error.kind in COUNTED_KINDS


def load(row: Any, threshold: int, cooldown_seconds: int) -> Circuit:
    return Circuit(
        threshold=threshold,
        cooldown=timedelta(seconds=cooldown_seconds),
        state=row.circuit_state,
        failures=row.circuit_failure_count,
        opened_at=row.circuit_opened_at,
        last_failure_at=row.last_failure_at,
    )


def store(circuit: Circuit, row: Any) -> None:
    row.circuit_state = circuit.state
    row.circuit_failure_count = circuit.failures
    row.circuit_opened_at = circuit.opened_at
    if circuit.last_failure_at is not None:
        row.last_failure_at = circuit.last_failure_at
