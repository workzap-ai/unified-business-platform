"""AI gateway error taxonomy.

Every terminal gateway failure is a ``GatewayUnavailable`` so callers (PI) have one
handoff signal. Messages are fixed, operator-safe strings: provider response bodies,
URLs, headers and API keys never appear in exception text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.types import Attempt


class ErrorKind(StrEnum):
    # Transient: the next provider may succeed (fallback-eligible).
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNAVAILABLE = "unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    INVALID_OUTPUT = "invalid_output"
    UNSUPPORTED = "unsupported"
    # Permanent: the request or credentials are wrong; never cascade to other providers.
    AUTH = "auth"
    INVALID_REQUEST = "invalid_request"
    CONTENT_POLICY = "content_policy"
    PERMANENT = "permanent"


TRANSIENT_KINDS = frozenset(
    {
        ErrorKind.RATE_LIMIT,
        ErrorKind.QUOTA,
        ErrorKind.TIMEOUT,
        ErrorKind.CONNECTION,
        ErrorKind.UNAVAILABLE,
        ErrorKind.MODEL_UNAVAILABLE,
        ErrorKind.INVALID_OUTPUT,
        ErrorKind.UNSUPPORTED,
    }
)
PERMANENT_KINDS = frozenset(
    {ErrorKind.AUTH, ErrorKind.INVALID_REQUEST, ErrorKind.CONTENT_POLICY, ErrorKind.PERMANENT}
)
# Failures that indicate provider ill-health (count toward the circuit breaker).
# Caller mistakes (invalid_request, content_policy), bad model output and credentials
# problems do not open the circuit.
CIRCUIT_KINDS = frozenset(
    {
        ErrorKind.RATE_LIMIT,
        ErrorKind.QUOTA,
        ErrorKind.TIMEOUT,
        ErrorKind.CONNECTION,
        ErrorKind.UNAVAILABLE,
    }
)
# Failures worth one more try on the same provider before falling back.
SAME_PROVIDER_RETRY_KINDS = frozenset(
    {ErrorKind.TIMEOUT, ErrorKind.CONNECTION, ErrorKind.UNAVAILABLE, ErrorKind.RATE_LIMIT}
)


class AIGatewayError(Exception):
    """Base class for everything raised by app.ai."""


class ProviderError(AIGatewayError):
    """One failed provider call, already classified. Raised by adapters."""

    def __init__(
        self,
        provider: str,
        kind: ErrorKind,
        *,
        status_code: int | None = None,
        code: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.provider, self.kind, self.status_code = provider, kind, status_code
        # Only a short, sanitized machine code from the provider (never its message).
        self.code = _safe_code(code)
        self.retry_after = retry_after
        super().__init__(self._describe())

    @property
    def transient(self) -> bool:
        return self.kind in TRANSIENT_KINDS

    @property
    def permanent(self) -> bool:
        return not self.transient

    def _describe(self) -> str:
        detail = f" (HTTP {self.status_code})" if self.status_code else ""
        code = f" [{self.code}]" if self.code else ""
        return f"{self.provider} {self.kind.value}{detail}{code}"


def _safe_code(code: str | None) -> str | None:
    if not code:
        return None
    cleaned = "".join(c for c in str(code)[:48] if c.isalnum() or c in "_-.")
    return cleaned or None


@dataclass(frozen=True, slots=True)
class AttemptSummary:
    """Secret-free record of one attempt or skipped provider for handoff/ops."""

    provider: str
    model: str
    outcome: str  # success | failed | skipped
    error_kind: str | None = None
    attempt: int = 0

    def label(self) -> str:
        return f"{self.provider}={self.error_kind or self.outcome}"


class GatewayUnavailable(AIGatewayError):
    """AI assistance could not be produced; callers hand off to a human.

    ``attempts`` keeps the legacy Attempt rows (fields match ai_usage_events columns).
    """

    public_message = "AI assistance is unavailable. Please contact a team member."

    def __init__(self, attempts: list[Attempt] | None = None) -> None:
        super().__init__(self.public_message)
        self.attempts: list[Attempt] = list(attempts or [])

    def __str__(self) -> str:
        return self.public_message


class AllProvidersFailed(GatewayUnavailable):
    """Every eligible provider failed transiently or was skipped (handoff signal)."""

    def __init__(
        self,
        summary: list[AttemptSummary],
        attempts: list[Attempt] | None = None,
        reason: str = "all_providers_failed",
    ) -> None:
        super().__init__(attempts)
        self.summary = summary
        self.reason = reason

    @property
    def safe_summary(self) -> str:
        parts = ", ".join(s.label() for s in self.summary) or "no provider configured"
        return f"All AI providers failed: {parts}"

    def __str__(self) -> str:
        return self.safe_summary


class PermanentProviderFailure(GatewayUnavailable):
    """A permanent error (auth, invalid request, content policy) stopped the chain."""

    def __init__(
        self,
        error: ProviderError,
        summary: list[AttemptSummary],
        attempts: list[Attempt] | None = None,
    ) -> None:
        super().__init__(attempts)
        self.error, self.kind, self.summary = error, error.kind, summary

    def __str__(self) -> str:
        return f"AI request rejected: {self.error}"


class UsageLimitExceeded(GatewayUnavailable):
    """The tenant's daily AI token or cost budget is exhausted."""

    def __init__(self, limit: str, used: str, allowed: str) -> None:
        super().__init__()
        self.limit, self.used, self.allowed = limit, used, allowed

    def __str__(self) -> str:
        return f"Daily AI {self.limit} budget exhausted ({self.used} of {self.allowed})"


class MediaValidationError(GatewayUnavailable, ValueError):
    """Media rejected before any provider call (type, signature or size)."""

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason

    def __str__(self) -> str:
        return f"Media rejected: {self.reason}"
