"""Bounded exponential backoff with full jitter and Retry-After support.

Classification lives on `IntegrationError.kind`:
  retryable / rate_limited -> retried (bounded); auth / permanent / invalid_response /
  configuration -> never retried; ambiguous (a non-idempotent call timed out after it may
  have been processed) -> never blindly retried: the caller must reconcile first.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.integrations.errors import IntegrationError


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_seconds: float = 0.5
    max_seconds: float = 30.0
    max_retry_after_seconds: float = 120.0

    def delay(
        self, attempt: int, retry_after: float | None = None, rng: random.Random | None = None
    ) -> float:
        """Delay before attempt `attempt + 1` (attempt is 1-based)."""
        if retry_after is not None:
            # Honour the provider, but never beyond our own ceiling.
            return max(0.0, min(retry_after, self.max_retry_after_seconds))
        ceiling = min(self.max_seconds, self.base_seconds * (2 ** max(0, attempt - 1)))
        return (rng or random).uniform(0, ceiling)  # full jitter


def should_retry(error: BaseException, attempt: int, policy: RetryPolicy) -> bool:
    if attempt >= policy.max_attempts:
        return False
    return isinstance(error, IntegrationError) and error.retryable


def backoff_seconds(
    attempt: int, base: float, maximum: float, retry_after: float | None = None
) -> float:
    """Durable (worker-level) schedule: exponential with jitter in [50%, 100%]."""
    if retry_after is not None:
        return min(max(retry_after, base), maximum)
    ceiling = min(maximum, base * (2 ** max(0, attempt - 1)))
    return random.uniform(ceiling / 2, ceiling)


async def with_retry[T](
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy | None = None,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    policy = policy or RetryPolicy()
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except IntegrationError as error:
            if not should_retry(error, attempt, policy):
                raise
            await sleep(policy.delay(attempt, error.retry_after))
