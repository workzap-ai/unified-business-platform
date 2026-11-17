"""X-Workzap-Signature: sha256=<hex HMAC-SHA256 of the raw body>, the key WORKZAP_BRIDGE_SECRET."""

import hashlib
import hmac

PREFIX = "sha256="


def sign(secret: str, raw: bytes) -> str:
    return PREFIX + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def verify(secret: str, raw: bytes, header: str | None) -> bool:
    """Constant-time check of the header against the raw bytes. A missing or unprefixed header
    is false."""
    if not header or not header.strip().lower().startswith(PREFIX):
        return False
    return hmac.compare_digest(sign(secret, raw).encode(), header.strip().lower().encode())
