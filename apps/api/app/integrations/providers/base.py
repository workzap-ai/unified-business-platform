"""Small helpers shared by adapters."""

import hashlib
import hmac
import re
import time
from collections.abc import Mapping
from typing import Any

from app.integrations.errors import IntegrationError
from app.integrations.registry import ConfigurationInvalid, HealthResult

EMAIL = re.compile(r"^[^@\s<>\"',;]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")


def credential(credentials: Mapping[str, str], key: str) -> str:
    value = credentials.get(key)
    if not value:
        raise IntegrationError(
            "CREDENTIALS_MISSING", "Required credentials are missing", kind="configuration"
        )
    return str(value)


def require_field(values: Mapping[str, Any], key: str, label: str) -> str:
    value = values.get(key)
    if value is None or not str(value).strip():
        raise ConfigurationInvalid(f"{label} is required", key)
    return str(value).strip()


def safe_email(address: str) -> str:
    address = address.strip()
    if not EMAIL.fullmatch(address):
        raise ConfigurationInvalid("Enter a valid email address")
    return address


def no_header_injection(*values: str | None) -> None:
    for value in values:
        if value is not None and ("\r" in value or "\n" in value or "\0" in value):
            raise ConfigurationInvalid("Header values cannot contain line breaks")


def ok(message: str, latency_ms: int | None = None, **details: Any) -> HealthResult:
    return HealthResult(True, message, latency_ms, details)


def hmac_sha256_hex(secret: str | bytes, message: bytes) -> str:
    key = secret.encode() if isinstance(secret, str) else secret
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def within_window(timestamp: str | int | None, now: float, window: int) -> bool:
    try:
        ts = int(str(timestamp))
    except (TypeError, ValueError):
        return False
    return abs(now - ts) <= window


def now() -> float:
    return time.time()
