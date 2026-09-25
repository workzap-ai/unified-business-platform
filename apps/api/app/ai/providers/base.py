"""Provider protocols and shared HTTP plumbing (httpx only; no vendor SDKs)."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol, runtime_checkable

import httpx

from app.ai.errors import ErrorKind, ProviderError
from app.ai.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    TranscriptionRequest,
    TranscriptionResponse,
)


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


@runtime_checkable
class SpeechToTextProvider(Protocol):
    name: str
    transcription_mime_types: frozenset[str]

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResponse: ...


@runtime_checkable
class VisionProvider(Protocol):
    """Multimodal chat: ``request.messages`` carry ImagePart content."""

    name: str
    vision_mime_types: frozenset[str]

    async def analyze(self, request: LLMRequest) -> LLMResponse: ...


def parse_retry_after(headers: httpx.Headers) -> float | None:
    """Seconds from Retry-After (delta or HTTP date) or OpenAI's retry-after-ms."""
    raw_ms = headers.get("retry-after-ms")
    if raw_ms:
        try:
            value = float(raw_ms) / 1000
            if math.isfinite(value) and value >= 0:
                return value
        except ValueError:
            pass
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) and value >= 0 else None
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def error_body(response: httpx.Response) -> dict[str, Any]:
    """The provider's error object, used only to classify (never logged or raised)."""
    try:
        data = response.json()
    except (ValueError, UnicodeDecodeError):
        return {}
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]  # some Google endpoints wrap errors in a list
    if not isinstance(data, dict):
        return {}
    error = data.get("error")
    return error if isinstance(error, dict) else {}


def classify_status(status: int) -> ErrorKind:
    if status in (401, 403):
        return ErrorKind.AUTH
    if status == 429:
        return ErrorKind.RATE_LIMIT
    if status == 404:
        return ErrorKind.MODEL_UNAVAILABLE
    if status in (408, 504):
        return ErrorKind.TIMEOUT
    if status == 409 or status >= 500 or status == 498:
        return ErrorKind.UNAVAILABLE
    if status in (400, 413, 415, 422):
        return ErrorKind.INVALID_REQUEST
    return ErrorKind.PERMANENT


class HttpAdapter:
    """Common request execution: timeouts/transport errors become ProviderErrors.

    Exceptions are raised ``from None`` so httpx request objects (URLs, headers)
    are never chained into tracebacks.
    """

    name: str

    def __init__(self, name: str, http: httpx.AsyncClient, base_url: str) -> None:
        self.name, self.http, self.base_url = name, http, base_url.rstrip("/")

    def classify(self, response: httpx.Response) -> ProviderError:
        raise NotImplementedError

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str],
        request_timeout: float,
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self.http.post(
                f"{self.base_url}/{path.lstrip('/')}",
                headers=headers,
                json=json_body,
                data=data,
                files=files,
                timeout=request_timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            raise ProviderError(self.name, ErrorKind.TIMEOUT) from None
        except httpx.TransportError:
            raise ProviderError(self.name, ErrorKind.CONNECTION) from None
        if response.status_code >= 400:
            raise self.classify(response) from None
        if 300 <= response.status_code < 400:
            raise ProviderError(
                self.name, ErrorKind.UNAVAILABLE, status_code=response.status_code
            ) from None
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError(
                self.name, ErrorKind.UNAVAILABLE, status_code=response.status_code, code="bad_body"
            ) from None
        if not isinstance(body, dict):
            raise ProviderError(self.name, ErrorKind.UNAVAILABLE, code="bad_body") from None
        return body


def optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def parse_json_text(provider: str, text: str) -> Any:
    """Parse structured output; tolerate a single ```json fence some models add."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        raise ProviderError(provider, ErrorKind.INVALID_OUTPUT, code="invalid_json") from None
