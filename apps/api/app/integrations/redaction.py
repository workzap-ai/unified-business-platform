"""Redaction for logs, stored payloads and audit details."""

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_NAME = re.compile(
    r"pass(word)?|secret|token|api[_-]?key|apikey|authorization|auth|cookie|credential|"
    r"signature|private[_-]?key|access[_-]?key|session|bearer|x-amz-security-token|"
    r"client[_-]?secret|refresh|code[_-]?verifier|hub\.verify_token",
    re.IGNORECASE,
)
SENSITIVE_VALUE = re.compile(
    # Bearer tokens, Stripe/Resend/SendGrid/Slack style keys, AWS access key ids, JWTs.
    r"(?i)\bbearer\s+[a-z0-9._~+/=-]+|"
    r"\b(sk|rk|pk)_(live|test)_[a-z0-9]{8,}|"
    r"\bre_[a-z0-9_]{12,}|\bSG\.[a-z0-9_.-]{16,}|\bxox[abprs]-[a-z0-9-]{8,}|"
    r"\bAKIA[0-9A-Z]{16}\b|\beyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}|"
    r"hooks\.slack\.com/services/[a-z0-9/]+"
)
MASK = "[redacted]"


def is_sensitive(name: str) -> bool:
    return bool(SENSITIVE_NAME.search(name))


def redact_text(value: str, limit: int = 300) -> str:
    cleaned = SENSITIVE_VALUE.sub(MASK, value)
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def redact_headers(headers: Any) -> dict[str, str]:
    items = headers.items() if hasattr(headers, "items") else headers
    return {
        str(k).lower(): MASK if is_sensitive(str(k)) else redact_text(str(v), 200) for k, v in items
    }


def redact_url(url: str) -> str:
    """Drop userinfo and mask sensitive query parameters (e.g. ?access_token=)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return MASK
    host = parts.hostname or ""
    netloc = host + (f":{parts.port}" if parts.port else "")
    query = urlencode(
        [(k, MASK if is_sensitive(k) else v) for k, v in parse_qsl(parts.query, True)]
    )
    path = parts.path
    if "hooks.slack.com" in host:
        path = "/services/" + MASK
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def redact_data(value: Any, depth: int = 0, *, text_limit: int = 1000) -> Any:
    """Structure-preserving redaction for stored webhook payloads and audit details."""
    if depth > 8:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(k)[:100]: MASK
            if is_sensitive(str(k))
            else redact_data(v, depth + 1, text_limit=text_limit)
            for k, v in list(value.items())[:200]
        }
    if isinstance(value, list | tuple):
        return [redact_data(v, depth + 1, text_limit=text_limit) for v in list(value)[:200]]
    if isinstance(value, str):
        return redact_text(value, text_limit)
    if isinstance(value, bool | int | float) or value is None:
        return value
    return redact_text(str(value), text_limit)
