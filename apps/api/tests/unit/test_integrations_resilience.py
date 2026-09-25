"""Retry classification, circuit breaker, rate limiter (Redis via fakes), credentials."""

import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.config import Settings
from app.integrations.circuit import Circuit
from app.integrations.crypto import CredentialManager, hint
from app.integrations.errors import (
    CredentialsUnavailable,
    IntegrationError,
    RateLimited,
    classify_status,
    error_for_status,
)
from app.integrations.rate_limit import LocalBuckets, ProviderRateLimiter, take
from app.integrations.retry import RetryPolicy, backoff_seconds, should_retry, with_retry


def settings(**overrides):
    values = {
        "app_env": "test",
        "database_url": "postgresql+asyncpg://t:t@h:1/t",
        "redis_url": "redis://h:1/0",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "status,kind",
    [
        (500, "retryable"),
        (502, "retryable"),
        (503, "retryable"),
        (408, "retryable"),
        (429, "rate_limited"),
        (401, "auth"),
        (403, "auth"),
        (400, "permanent"),
        (404, "permanent"),
        (422, "permanent"),
    ],
)
def test_status_classification(status, kind):
    assert classify_status(status) == kind
    assert error_for_status(status).kind == kind


def test_retry_decisions_and_retry_after():
    policy = RetryPolicy(max_attempts=3, base_seconds=1, max_seconds=10)
    assert should_retry(error_for_status(503), 1, policy)
    assert should_retry(RateLimited(5), 2, policy)
    assert not should_retry(error_for_status(503), 3, policy)  # bounded
    assert not should_retry(error_for_status(401), 1, policy)
    assert not should_retry(error_for_status(400), 1, policy)
    ambiguous = IntegrationError("PROVIDER_TIMEOUT", "t", kind="ambiguous")
    assert not should_retry(ambiguous, 1, policy)
    assert policy.delay(1, retry_after=7) == 7
    assert policy.delay(1, retry_after=10_000) == policy.max_retry_after_seconds
    rng = random.Random(1)
    assert all(0 <= policy.delay(n, rng=rng) <= min(10, 2 ** (n - 1)) for n in range(1, 8))
    assert 15 <= backoff_seconds(2, 15, 3600) <= 30
    assert backoff_seconds(10, 30, 600) <= 600
    assert backoff_seconds(1, 30, 600, retry_after=120) == 120


async def test_with_retry_stops_on_permanent_and_honours_retry_after():
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)

    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RateLimited(2) if attempts["n"] == 1 else error_for_status(502)
        return "done"

    assert await with_retry(flaky, RetryPolicy(max_attempts=3), sleep=sleep) == "done"
    assert sleeps[0] == 2 and len(sleeps) == 2

    async def denied():
        attempts["n"] += 1
        raise error_for_status(401)

    attempts["n"] = 0
    with pytest.raises(IntegrationError):
        await with_retry(denied, RetryPolicy(max_attempts=5), sleep=sleep)
    assert attempts["n"] == 1


def test_circuit_transitions():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    breaker = Circuit(threshold=3, cooldown=timedelta(seconds=60))
    assert breaker.allow(t0) and breaker.state == "closed"
    for _ in range(2):
        breaker.record_failure(t0)
    assert breaker.state == "closed" and breaker.failures == 2
    breaker.record_failure(t0)
    assert breaker.state == "open" and breaker.opened_at == t0
    assert not breaker.allow(t0 + timedelta(seconds=59))
    assert breaker.allow(t0 + timedelta(seconds=60)) and breaker.state == "half_open"
    breaker.record_failure(t0 + timedelta(seconds=61))  # failed probe re-opens
    assert breaker.state == "open"
    assert breaker.allow(t0 + timedelta(seconds=200)) and breaker.state == "half_open"
    breaker.record_success()
    assert breaker.state == "closed" and breaker.failures == 0 and breaker.opened_at is None
    assert Circuit.counts(error_for_status(503)) and not Circuit.counts(error_for_status(401))


def test_token_bucket_math():
    allowed, tokens, wait = take(1.0, 0.0, 0.0, rate=1.0, capacity=5)
    assert allowed and tokens == 0
    allowed, tokens, wait = take(0.0, 0.0, 0.5, rate=1.0, capacity=5)
    assert not allowed and wait == pytest.approx(0.5)
    allowed, tokens, _ = take(0.0, 0.0, 100.0, rate=1.0, capacity=5)
    assert allowed and tokens == 4  # refill capped at capacity


class FakeRedis:
    """Implements the token-bucket script semantics in Python (no Redis locally)."""

    def __init__(self):
        self.state = {}

    async def eval(self, script, numkeys, key, rate, capacity, now):
        tokens, updated = self.state.get(key, (capacity, now))
        allowed, tokens, wait = take(tokens, updated, now, rate, capacity)
        self.state[key] = (tokens, now)
        return [1 if allowed else 0, str(wait)]


class DownRedis:
    async def eval(self, *args):
        raise ConnectionError("redis down")


async def test_rate_limiter_fairness_and_fail_open_to_conservative():
    clock = [1000.0]
    limiter = ProviderRateLimiter(
        FakeRedis(),
        per_minute=60,
        fallback_per_minute=6,
        clock=lambda: clock[0],
        local=LocalBuckets(),
    )
    tenant, conn_a, conn_b = uuid4(), uuid4(), uuid4()
    results = [await limiter.acquire("stripe", tenant, conn_a) for _ in range(12)]
    assert sum(r.allowed for r in results) == 10  # connection bucket capacity
    assert not results[-1].allowed and results[-1].retry_after > 0
    other = await limiter.acquire("stripe", uuid4(), uuid4())
    assert other.allowed  # another tenant is unaffected
    assert (await limiter.acquire("stripe", tenant, conn_b)).allowed

    degraded = ProviderRateLimiter(
        DownRedis(),
        per_minute=6000,
        fallback_per_minute=6,
        clock=lambda: clock[0],
        local=LocalBuckets(),
    )
    decisions = [await degraded.acquire("resend", tenant, conn_a) for _ in range(3)]
    assert decisions[0].allowed and decisions[0].degraded
    assert not all(d.allowed for d in decisions)  # conservative fallback rate applies


def test_credentials_fail_closed_without_key():
    manager = CredentialManager(settings())
    assert not manager.configured
    with pytest.raises(CredentialsUnavailable):
        manager.encrypt("secret")


def test_multifernet_rotation():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    legacy = CredentialManager(settings(secrets_encryption_key=SecretStr(old)))
    token = legacy.encrypt_json({"api_key": "re_123456789012"})
    rotated_settings = settings(secrets_encryption_key=SecretStr(f"{new},{old}"))
    rotating = CredentialManager(rotated_settings)
    assert rotating.decrypt_json(token) == {"api_key": "re_123456789012"}
    rotated = rotating.rotate(token)
    only_new = CredentialManager(settings(secrets_encryption_key=SecretStr(new)))
    assert only_new.decrypt_json(rotated) == {"api_key": "re_123456789012"}
    with pytest.raises(IntegrationError):
        only_new.decrypt(token)  # old key removed: old ciphertext unreadable
    via_previous = CredentialManager(
        settings(
            secrets_encryption_key=SecretStr(new), secrets_encryption_previous_keys=SecretStr(old)
        )
    )
    assert via_previous.decrypt_json(token)["api_key"] == "re_123456789012"
    # The first key encrypts.
    assert only_new.decrypt(rotating.encrypt("x")) == "x"


def test_invalid_key_is_configuration_error_and_hints_are_short():
    with pytest.raises(IntegrationError):
        CredentialManager(settings(secrets_encryption_key=SecretStr("not-a-key")))
    assert hint("sk_test_1234567890abcd") == "…abcd"
    assert hint("short") == "…"
