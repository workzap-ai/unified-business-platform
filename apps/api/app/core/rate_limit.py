import hashlib
import logging

from fastapi import Request

logger = logging.getLogger("platform")


def client_ip(request: Request) -> str:
    """Use X-Forwarded-For only for the configured number of trusted proxy hops."""
    hops = request.app.state.settings.trusted_proxy_hops
    forwarded = request.headers.get("x-forwarded-for", "")
    if hops and forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return str(parts[-hops])[:64]
    return (request.client.host if request.client else "unknown")[:64]


async def hit(request: Request, bucket: str, key: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window counter in Redis. Returns False when the limit is exceeded.

    Fails open when Redis is unavailable: durable account lockout in PostgreSQL still
    protects credentials, and an outage must not lock every user out.
    """
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    redis_key = f"ratelimit:{bucket}:{digest}"
    try:
        redis = request.app.state.redis
        count = await redis.incr(redis_key)
        if count == 1:
            await redis.expire(redis_key, window_seconds)
        return int(count) <= limit
    except Exception:
        logger.warning("rate_limit_unavailable")
        return True
