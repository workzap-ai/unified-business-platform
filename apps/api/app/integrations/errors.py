"""Integration errors with safe, operator-readable messages and a retry classification.

`message` is always safe to persist in `last_error` and return to the UI: never a provider
response body, stack trace, credential or URL with secrets.
"""

from typing import Literal

from app.shared.errors import BusinessRuleViolation

ErrorKind = Literal[
    "retryable",  # transient: 5xx, 408, network error, timeout before request was sent
    "rate_limited",  # 429 (retryable after Retry-After)
    "auth",  # 401/403: credential invalid or insufficient scope; never retried
    "permanent",  # 4xx validation errors, unsupported operations
    "invalid_response",  # malformed / oversized provider response
    "configuration",  # our side is not configured (missing key, bad URL)
    "ambiguous",  # timeout after the request may have been processed (non-idempotent)
]


class IntegrationError(Exception):
    """Base error for provider and framework failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        kind: ErrorKind = "permanent",
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.kind = code, message, kind
        self.status, self.retry_after = status, retry_after

    @property
    def retryable(self) -> bool:
        return self.kind in {"retryable", "rate_limited"}


class OutboundUrlRejected(IntegrationError):
    def __init__(self, reason: str) -> None:
        # The reason names the policy (not the resolved address) so it is safe to show.
        super().__init__("URL_REJECTED", f"Destination URL is not allowed: {reason}")
        self.reason = reason


class CircuitOpen(IntegrationError):
    def __init__(self) -> None:
        super().__init__(
            "CIRCUIT_OPEN",
            "Calls are paused after repeated failures; they resume automatically",
            kind="retryable",
        )


class RateLimited(IntegrationError):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__(
            "RATE_LIMITED",
            "Provider rate limit reached; retrying later",
            kind="rate_limited",
            status=429,
            retry_after=retry_after,
        )


class CredentialsUnavailable(BusinessRuleViolation):
    """Raised when credential storage is used without an encryption key (fail closed)."""

    def __init__(self) -> None:
        super().__init__(
            "ENCRYPTION_NOT_CONFIGURED",
            "Credential storage is not configured on this server (SECRETS_ENCRYPTION_KEY)",
            503,
        )


def classify_status(status: int) -> ErrorKind:
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "auth"
    if status in (408, 425) or status >= 500:
        return "retryable"
    return "permanent"


def error_for_status(status: int, retry_after: float | None = None) -> IntegrationError:
    kind = classify_status(status)
    if kind == "rate_limited":
        return RateLimited(retry_after)
    if kind == "auth":
        return IntegrationError(
            "INVALID_CREDENTIALS",
            "The provider rejected the credentials or they lack required access",
            kind="auth",
            status=status,
        )
    if kind == "retryable":
        return IntegrationError(
            "PROVIDER_UNAVAILABLE",
            f"The provider is temporarily unavailable (HTTP {status})",
            kind="retryable",
            status=status,
            retry_after=retry_after,
        )
    return IntegrationError(
        "PROVIDER_REJECTED", f"The provider rejected the request (HTTP {status})", status=status
    )
