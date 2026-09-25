"""Centralized outbound HTTP client with SSRF protection.

Every provider adapter and outbound webhook delivery uses `OutboundClient`. Guarantees:

* Destination validation on *every* request (`validate_outbound_url`): https only (plain
  http only for hosts on the explicit dev/test allowlist, never in production), no
  userinfo, only port 443 (80 for allowlisted http) plus explicitly configured ports, no
  IP-literal encodings other than canonical dotted-quad/IPv6, and every DNS answer must be
  a public unicast address (private, loopback, link-local, CGNAT, multicast, reserved,
  unspecified, IPv6 ULA, IPv4-mapped/6to4/Teredo/NAT64-embedded private addresses and the
  cloud metadata endpoints 169.254.169.254 / fd00:ec2::254 are rejected).
* Redirects are never followed (a 3xx is returned to the caller, which treats it as an
  error), so a validated URL cannot bounce to an internal address.
* Connect/read/write/pool timeouts plus a total deadline; response bodies are streamed and
  capped; TLS verification is controlled by settings (always on in production).
* Request-id / correlation-id / W3C traceparent propagation; logs carry only method, host,
  redacted path, status and latency — never headers, bodies or secrets.

Residual risk (documented in docs/INTEGRATIONS.md): DNS rebinding. We resolve and check
the addresses, then httpx resolves again when connecting; a hostile DNS server with a very
short TTL could return a public address to the check and a private one to the connect.
Mitigations: deploy egress through a proxy / network policy that blocks private ranges;
optionally pin the resolved address (not enabled because it breaks SNI/TLS verification
with plain httpx).
"""

import asyncio
import email.utils
import ipaddress
import json
import logging
import re
import secrets
import socket
import time
import zlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.integrations.errors import IntegrationError, OutboundUrlRejected, error_for_status

logger = logging.getLogger("platform")

Resolver = Callable[[str, int], Awaitable[list[str]]]
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

METADATA_ADDRESSES = frozenset(
    {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("fd00:ec2::254")}
)
BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal", "metadata.goog"})
BLOCKED_SUFFIXES = (".localhost", ".localdomain", ".internal")
NAT64 = ipaddress.ip_network("64:ff9b::/96")
CGNAT = ipaddress.ip_network("100.64.0.0/10")
HOST_CHARS = re.compile(r"^[a-z0-9.-]+$")
NUMERIC_LABEL = re.compile(r"^(0x[0-9a-f]*|[0-9]+)$")
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})
MAX_URL_LENGTH = 2048


@dataclass(frozen=True, slots=True)
class ValidatedUrl:
    url: str
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def forbidden_reason(address: IPAddress) -> str | None:
    """Why an address may not be contacted, or None when it is public unicast."""
    if address in METADATA_ADDRESSES:
        return "cloud metadata address"
    if isinstance(address, ipaddress.IPv6Address):
        embedded: ipaddress.IPv4Address | None = address.ipv4_mapped or address.sixtofour
        if embedded is None and address.teredo:
            embedded = address.teredo[1]
        if embedded is None and address in NAT64:
            embedded = ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
        if embedded is not None:
            inner = forbidden_reason(embedded)
            if inner:
                return inner
    if address.is_loopback:
        return "loopback address"
    if address.is_link_local:
        return "link-local address"
    if address.is_multicast:
        return "multicast address"
    if address.is_unspecified:
        return "unspecified address"
    if isinstance(address, ipaddress.IPv4Address) and address in CGNAT:
        return "shared address space"
    if address.is_private:
        return "private address"
    if address.is_reserved:
        return "reserved address"
    if not address.is_global:
        return "non-public address"
    return None


def _literal_ip(host: str) -> IPAddress | None:
    candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _looks_numeric(host: str) -> bool:
    labels = host.rstrip(".").split(".")
    return bool(labels) and all(NUMERIC_LABEL.fullmatch(label) for label in labels if label)


async def validate_outbound_url(
    url: str,
    settings: Settings,
    *,
    resolver: Resolver | None = None,
) -> ValidatedUrl:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise OutboundUrlRejected("invalid URL")
    if any(ch in url for ch in ("\\", "\r", "\n", "\t", " ")):
        raise OutboundUrlRejected("invalid characters")
    try:
        parts = urlsplit(url)
        port_value = parts.port
    except ValueError:
        raise OutboundUrlRejected("invalid URL") from None
    scheme = parts.scheme.lower()
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise OutboundUrlRejected("credentials in URL")
    raw_host = (parts.hostname or "").lower()
    if not raw_host:
        raise OutboundUrlRejected("missing host")
    allowlisted = settings.app_env != "production" and raw_host.rstrip(".") in {
        h.lower() for h in settings.outbound_http_allowlist
    }
    if scheme == "http":
        if not allowlisted:
            raise OutboundUrlRejected("https is required")
    elif scheme != "https":
        raise OutboundUrlRejected("https is required")
    default_port = 443 if scheme == "https" else 80
    port = port_value or default_port
    if port != default_port and port not in settings.outbound_allowed_ports:
        raise OutboundUrlRejected("non-standard port")
    literal = _literal_ip(raw_host)
    host = raw_host.rstrip(".")
    if literal is None:
        if _looks_numeric(host):
            raise OutboundUrlRejected("numeric host encoding")
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            raise OutboundUrlRejected("invalid host") from None
        blocked = host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES)
        if blocked and not allowlisted:
            raise OutboundUrlRejected("internal host name")
        if not HOST_CHARS.fullmatch(host) or ("." not in host and not allowlisted):
            raise OutboundUrlRejected("invalid host")
    if allowlisted:
        # Explicit development/test allowlist: private destinations are permitted here only.
        return ValidatedUrl(url, scheme, host, port, ())
    if literal is not None:
        reason = forbidden_reason(literal)
        if reason:
            raise OutboundUrlRejected(reason)
        return ValidatedUrl(url, scheme, str(literal), port, (str(literal),))
    try:
        async with asyncio.timeout(settings.outbound_connect_timeout_seconds):
            answers = await (resolver or system_resolver)(host, port)
    except (OSError, TimeoutError, UnicodeError):
        raise OutboundUrlRejected("host could not be resolved") from None
    if not answers:
        raise OutboundUrlRejected("host could not be resolved")
    for answer in answers:
        try:
            address = ipaddress.ip_address(answer.split("%", 1)[0])
        except ValueError:
            raise OutboundUrlRejected("host could not be resolved") from None
        reason = forbidden_reason(address)
        if reason:
            # Any forbidden answer rejects the host (no "pick the public one" games).
            raise OutboundUrlRejected(f"host resolves to a {reason}")
    return ValidatedUrl(url, scheme, host, port, tuple(answers))


@dataclass(frozen=True, slots=True)
class CallContext:
    request_id: str | None = None
    correlation_id: str | None = None
    traceparent: str | None = None
    idempotent: bool | None = None  # None: infer from the HTTP method


TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def new_traceparent(parent: str | None = None) -> str:
    if parent and TRACEPARENT.fullmatch(parent):
        trace_id = parent.split("-")[1]
        return f"00-{trace_id}-{secrets.token_hex(8)}-01"
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def parse_retry_after(value: str | None, *, cap: float = 3600) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), cap)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, min((when - datetime.now(UTC)).total_seconds(), cap))


@dataclass(frozen=True, slots=True)
class OutboundResponse:
    status_code: int
    headers: httpx.Headers
    content: bytes
    elapsed_ms: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def retry_after(self) -> float | None:
        return parse_retry_after(self.headers.get("retry-after"))

    def json(self) -> Any:
        try:
            return json.loads(self.content) if self.content else None
        except (ValueError, UnicodeDecodeError):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "The provider returned a malformed response",
                kind="invalid_response",
                status=self.status_code,
            ) from None

    def json_object(self) -> dict[str, Any]:
        data = self.json()
        if not isinstance(data, dict):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "The provider returned an unexpected response",
                kind="invalid_response",
                status=self.status_code,
            )
        return data

    def ensure_success(self) -> "OutboundResponse":
        if 300 <= self.status_code < 400:
            raise IntegrationError(
                "UNEXPECTED_REDIRECT",
                "The destination answered with a redirect; redirects are not followed",
                status=self.status_code,
            )
        if self.status_code >= 400:
            raise error_for_status(self.status_code, self.retry_after())
        return self


class OutboundClient:
    """Wraps an httpx.AsyncClient (the pool) with policy. Inject MockTransport in tests."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient,
        *,
        resolver: Resolver | None = None,
    ) -> None:
        self.settings, self.client, self.resolver = settings, client, resolver

    def timeout(self, read: float | None = None) -> httpx.Timeout:
        s = self.settings
        return httpx.Timeout(
            connect=s.outbound_connect_timeout_seconds,
            read=read or s.outbound_read_timeout_seconds,
            write=s.outbound_read_timeout_seconds,
            pool=s.outbound_connect_timeout_seconds,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any = None,
        content: bytes | str | None = None,
        form: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        read_timeout: float | None = None,
        max_bytes: int | None = None,
        context: CallContext | None = None,
    ) -> OutboundResponse:
        method = method.upper()
        validated = await validate_outbound_url(url, self.settings, resolver=self.resolver)
        ctx = context or CallContext()
        outgoing: dict[str, str] = {
            "user-agent": "PlatformIntegrations/1.0",
            "accept-encoding": "gzip, identity",
        }
        if ctx.request_id:
            outgoing["x-request-id"] = ctx.request_id
        if ctx.correlation_id:
            outgoing["x-correlation-id"] = ctx.correlation_id
        outgoing["traceparent"] = new_traceparent(ctx.traceparent)
        outgoing.update(headers or {})
        limit = max_bytes or self.settings.outbound_max_response_bytes
        idempotent = ctx.idempotent if ctx.idempotent is not None else method in IDEMPOTENT_METHODS
        started = time.perf_counter()
        status = 0
        try:
            async with asyncio.timeout(self.settings.outbound_total_timeout_seconds):
                request = self.client.build_request(
                    method,
                    validated.url,
                    headers=outgoing,
                    json=json_body,
                    content=content,
                    data=dict(form) if form is not None else None,
                    params=dict(params) if params is not None else None,
                    timeout=self.timeout(read_timeout),
                )
                response = await self.client.send(request, stream=True, follow_redirects=False)
                try:
                    status = response.status_code
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > limit:
                        raise _too_large(status)
                    if response.is_stream_consumed:
                        # Already buffered (and decoded) by the transport, e.g. MockTransport.
                        data = response.content
                        if len(data) > limit:
                            raise _too_large(status)
                    else:
                        body = bytearray()
                        async for chunk in response.aiter_raw():
                            body.extend(chunk)
                            if len(body) > limit:
                                raise _too_large(status)
                        data = _decode(bytes(body), response.headers, limit, status)
                finally:
                    await response.aclose()
        except IntegrationError:
            self._log(method, url, status, started, "error")
            raise
        except httpx.ConnectTimeout:
            self._log(method, url, 0, started, "connect_timeout")
            raise IntegrationError(
                "PROVIDER_TIMEOUT", "Connection to the provider timed out", kind="retryable"
            ) from None
        except (httpx.TimeoutException, TimeoutError):
            self._log(method, url, status, started, "timeout")
            raise IntegrationError(
                "PROVIDER_TIMEOUT",
                "The provider did not respond in time",
                kind="retryable" if idempotent else "ambiguous",
            ) from None
        except httpx.ConnectError:
            self._log(method, url, 0, started, "connect_error")
            raise IntegrationError(
                "PROVIDER_UNREACHABLE", "The provider could not be reached", kind="retryable"
            ) from None
        except httpx.HTTPError:
            self._log(method, url, status, started, "transport_error")
            raise IntegrationError(
                "PROVIDER_UNREACHABLE",
                "The connection to the provider failed",
                kind="retryable" if idempotent else "ambiguous",
            ) from None
        elapsed = int((time.perf_counter() - started) * 1000)
        self._log(method, url, status, started, "ok")
        return OutboundResponse(status, response.headers, data, elapsed)

    def _log(self, method: str, url: str, status: int, started: float, outcome: str) -> None:
        # Structured and allowlisted (app.core.logging): host only, never path/query/body.
        try:
            host = urlsplit(url).hostname or "unknown"
        except ValueError:
            host = "invalid"
        logger.info(
            "integration_http",
            extra={
                "provider": host[:120],
                "operation": f"{method} {outcome}",
                "status_code": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )


def _decode(body: bytes, headers: httpx.Headers, limit: int, status: int) -> bytes:
    """Decode gzip/deflate with an output cap so compression bombs cannot bypass it."""
    encoding = headers.get("content-encoding", "identity").strip().lower()
    if encoding in ("", "identity"):
        return body
    if encoding not in ("gzip", "deflate"):
        raise IntegrationError(
            "INVALID_RESPONSE", "Unsupported response encoding", kind="invalid_response"
        )
    wbits = 16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
    try:
        decoder = zlib.decompressobj(wbits)
        data = decoder.decompress(body, limit + 1)
    except zlib.error:
        raise IntegrationError(
            "INVALID_RESPONSE",
            "The provider returned a malformed response",
            kind="invalid_response",
        ) from None
    if len(data) > limit or decoder.unconsumed_tail:
        raise _too_large(status)
    return data


def _too_large(status: int) -> IntegrationError:
    return IntegrationError(
        "RESPONSE_TOO_LARGE",
        "The provider response exceeded the size limit",
        kind="invalid_response",
        status=status,
    )
