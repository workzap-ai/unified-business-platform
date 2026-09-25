"""Minimal AWS Signature Version 4 signer (header and query/presigned forms).

Verified against AWS's published examples (tests/unit/test_integrations_sigv4.py): the
SigV4 test-suite `get-vanilla` family and the Amazon S3 documentation examples for a
header-signed GET Object and a presigned URL. S3 canonical URIs are encoded once;
other services encode path segments twice, as the specification requires.
"""

import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, urlsplit

ALGORITHM = "AWS4-HMAC-SHA256"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def canonical_uri(path: str, service: str) -> str:
    path = path or "/"
    if service == "s3":
        return quote(path, safe="/-_.~")
    segments = [quote(quote(seg, safe="-_.~"), safe="-_.~") for seg in path.split("/")]
    return "/".join(segments) or "/"


def canonical_query(query: str) -> str:
    pairs = [(quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in parse_qsl(query, True)]
    return "&".join(f"{k}={v}" for k, v in sorted(pairs))


def _canonical_headers(headers: Mapping[str, str]) -> tuple[str, str]:
    normalized: dict[str, str] = {}
    for name, value in headers.items():
        normalized[name.strip().lower()] = " ".join(str(value).strip().split())
    names = sorted(normalized)
    return "".join(f"{n}:{normalized[n]}\n" for n in names), ";".join(names)


def signing_key(secret_key: str, date: str, region: str, service: str) -> bytes:
    k_date = _hmac(("AWS4" + secret_key).encode(), date)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    return _hmac(k_service, "aws4_request")


def _signature(
    method: str,
    uri: str,
    query: str,
    headers: Mapping[str, str],
    payload_hash: str,
    secret_key: str,
    region: str,
    service: str,
    amz_date: str,
) -> tuple[str, str]:
    canonical_headers, signed_headers = _canonical_headers(headers)
    canonical_request = "\n".join(
        [method.upper(), uri, query, canonical_headers, signed_headers, payload_hash]
    )
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        [ALGORITHM, amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    key = signing_key(secret_key, date, region, service)
    return hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest(), signed_headers


def amz_timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def sign_headers(
    method: str,
    url: str,
    headers: Mapping[str, str],
    *,
    access_key: str,
    secret_key: str,
    region: str,
    service: str,
    payload_hash: str | None = None,
    now: datetime | None = None,
    session_token: str | None = None,
    include_content_sha256: bool | None = None,
) -> dict[str, str]:
    """Return headers including Authorization and X-Amz-Date for the request."""
    parts = urlsplit(url)
    amz_date = amz_timestamp(now)
    signed: dict[str, str] = {k: v for k, v in headers.items()}
    lower = {k.lower() for k in signed}
    if "host" not in lower:
        signed["host"] = parts.netloc
    signed["x-amz-date"] = amz_date
    body_hash = payload_hash or EMPTY_SHA256
    if include_content_sha256 if include_content_sha256 is not None else service == "s3":
        signed["x-amz-content-sha256"] = body_hash
    if session_token:
        signed["x-amz-security-token"] = session_token
    signature, signed_headers = _signature(
        method,
        canonical_uri(parts.path, service),
        canonical_query(parts.query),
        signed,
        body_hash,
        secret_key,
        region,
        service,
        amz_date,
    )
    scope = f"{amz_date[:8]}/{region}/{service}/aws4_request"
    signed["authorization"] = (
        f"{ALGORITHM} Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return signed


def presign_url(
    method: str,
    url: str,
    *,
    access_key: str,
    secret_key: str,
    region: str,
    service: str = "s3",
    expires: int = 900,
    now: datetime | None = None,
    session_token: str | None = None,
) -> str:
    if not 1 <= expires <= 604800:
        raise ValueError("Presigned URLs expire within 7 days")
    parts = urlsplit(url)
    amz_date = amz_timestamp(now)
    scope = f"{amz_date[:8]}/{region}/{service}/aws4_request"
    params = parse_qsl(parts.query, True) + [
        ("X-Amz-Algorithm", ALGORITHM),
        ("X-Amz-Credential", f"{access_key}/{scope}"),
        ("X-Amz-Date", amz_date),
        ("X-Amz-Expires", str(expires)),
        ("X-Amz-SignedHeaders", "host"),
    ]
    if session_token:
        params.append(("X-Amz-Security-Token", session_token))
    query = "&".join(
        f"{k}={v}"
        for k, v in sorted((quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in params)
    )
    signature, _ = _signature(
        method,
        canonical_uri(parts.path, service),
        query,
        {"host": parts.netloc},
        UNSIGNED_PAYLOAD,
        secret_key,
        region,
        service,
        amz_date,
    )
    base = f"{parts.scheme}://{parts.netloc}{canonical_uri(parts.path, service)}"
    return f"{base}?{query}&X-Amz-Signature={signature}"
