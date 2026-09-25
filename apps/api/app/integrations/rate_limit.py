"""Outbound rate limiting: token buckets per connection and per tenant+provider in Redis.

Fairness: every connection has its own bucket, and all connections of one tenant share a
tenant+provider bucket, so one tenant cannot consume the budget of others and cannot
multiply its budget by creating many connections.

Failure policy ("fail open to conservative"): if Redis is unavailable we do not block all
integrations (that would turn a cache outage into a platform outage), but we fall back to
an in-process bucket with the much lower `integration_rate_limit_fallback_per_minute`
rate, per process. Providers' own 429 responses remain the final authority and feed the
connection's `rate_limited_until`.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

logger = logging.getLogger("platform")

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 't', 'ts')
local tokens = tonumber(data[1]) or capacity
local ts = tonumber(data[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)
local allowed = 0
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = (1 - tokens) / rate
end
redis.call('HSET', key, 't', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, math.ceil(capacity / rate) + 60)
return {allowed, tostring(wait)}
"""


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    retry_after: float = 0.0
    degraded: bool = False  # True when the conservative in-process fallback decided


def take(
    tokens: float, updated: float, now: float, rate: float, capacity: float
) -> tuple[bool, float, float]:
    """Pure bucket step (mirrors the Lua script). Returns (allowed, tokens, wait)."""
    tokens = min(capacity, tokens + max(0.0, now - updated) * rate)
    if tokens >= 1:
        return True, tokens - 1, 0.0
    return False, tokens, (1 - tokens) / rate


class LocalBuckets:
    def __init__(self) -> None:
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, rate: float, capacity: float, now: float) -> tuple[bool, float]:
        with self._lock:
            tokens, updated = self._state.get(key, (capacity, now))
            allowed, tokens, wait = take(tokens, updated, now, rate, capacity)
            self._state[key] = (tokens, now)
            if len(self._state) > 10000:  # bounded memory
                self._state.pop(next(iter(self._state)))
            return allowed, wait


_fallback = LocalBuckets()


class ProviderRateLimiter:
    def __init__(
        self,
        redis: Any,
        per_minute: int,
        fallback_per_minute: int,
        *,
        clock: Any = time.time,
        local: LocalBuckets | None = None,
    ) -> None:
        self.redis, self.clock = redis, clock
        self.rate = per_minute / 60.0
        self.fallback_rate = fallback_per_minute / 60.0
        self.local = local or _fallback

    def keys(self, provider: str, tenant_id: UUID, connection_id: UUID) -> list[str]:
        return [
            f"intg:rl:conn:{provider}:{connection_id}",
            f"intg:rl:tenant:{provider}:{tenant_id}",
        ]

    async def acquire(self, provider: str, tenant_id: UUID, connection_id: UUID) -> Decision:
        now = float(self.clock())
        conn_key, tenant_key = self.keys(provider, tenant_id, connection_id)
        # Tenant bucket allows 3x a single connection's rate (bounded fan-out).
        buckets = [
            (conn_key, self.rate, max(1.0, self.rate * 10)),
            (tenant_key, self.rate * 3, max(1.0, self.rate * 30)),
        ]
        if self.redis is not None:
            try:
                for key, rate, capacity in buckets:
                    allowed, wait = await self.redis.eval(
                        TOKEN_BUCKET_LUA, 1, key, rate, capacity, now
                    )
                    if not int(allowed):
                        return Decision(False, float(wait))
                return Decision(True)
            except Exception:
                logger.warning("integration_rate_limit_degraded")
        for key, _rate, _capacity in buckets:
            rate = self.fallback_rate
            allowed_local, wait_local = self.local.hit(key, rate, max(1.0, rate * 10), now)
            if not allowed_local:
                return Decision(False, wait_local, degraded=True)
        return Decision(True, degraded=True)
