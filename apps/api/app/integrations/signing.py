"""Signature scheme for outbound webhooks sent by the platform.

Headers on every delivery:
  X-Platform-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>." + raw body)>
  X-Platform-Event: <event type>
  X-Platform-Delivery: <delivery id>   (changes per subscription)
  Idempotency-Key: <event id>:<subscription id>  (stable across retries)

Receivers should recompute v1 over the exact raw body, compare in constant time and reject
timestamps older than a few minutes.
"""

import hmac
import time

from app.integrations.providers.base import hmac_sha256_hex

SIGNATURE_HEADER = "X-Platform-Signature"


def signature_header(secret: str, body: bytes, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    return f"t={ts},v1={hmac_sha256_hex(secret, f'{ts}.'.encode() + body)}"


def verify_signature_header(
    secret: str, body: bytes, header: str, *, now: float | None = None, tolerance: int = 300
) -> bool:
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        parts.setdefault(key, []).append(value)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError, IndexError):
        return False
    if abs((time.time() if now is None else now) - ts) > tolerance:
        return False
    expected = hmac_sha256_hex(secret, f"{ts}.".encode() + body)
    return any(hmac.compare_digest(expected, v) for v in parts.get("v1", []))
