"""Adapter details, error classification, STT/vision validation and legacy facade shape."""

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from app.ai.errors import AllProvidersFailed, ErrorKind, MediaValidationError, ProviderError
from app.ai.gateway import Gateway
from app.ai.health import ProviderHealth
from app.ai.manager import LLMManager
from app.ai.media import validate_audio, validate_image, validate_media
from app.ai.models import AIUsageEvent
from app.ai.providers.base import parse_retry_after
from app.ai.providers.gemini import GeminiProvider, to_gemini_schema
from app.ai.providers.openai import OpenAICompatibleProvider
from app.ai.types import LLMRequest, Message, ToolCall
from app.shared.scope import WorkspaceScope

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
OGG = b"OggS" + b"\x00" * 32
AAC = b"\xff\xf1" + b"\x00" * 32


def scope():
    return WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")


def configure(settings):
    settings.openai_api_key = SecretStr("sk-openai-test")
    settings.gemini_api_key = SecretStr("gemini-test")
    settings.groq_api_key = SecretStr("gsk-groq-test")
    settings.openai_models = {}
    settings.gemini_models = {}
    settings.groq_models = {}
    settings.llm_max_retries = 0
    settings.ai_use_default_models = True  # use registry default models
    return settings


def manager(settings, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMManager(settings, client, health=ProviderHealth(5, 30))


# -- media validation ------------------------------------------------------------------


def test_media_validation_checks_type_signature_and_size():
    assert validate_image(PNG, "image/png", 1024) == "image/png"
    assert validate_image(JPEG, "image/jpg", 1024) == "image/jpeg"
    assert validate_audio(OGG, "audio/ogg; codecs=opus", 1024) == "audio/ogg"
    cases = [
        (lambda: validate_image(b"<script>", "image/png", 1024), "content_mismatch"),
        (lambda: validate_image(PNG, "image/png", 8), "too_large"),
        (lambda: validate_image(OGG, "audio/ogg", 1024), "unsupported_type"),
        (lambda: validate_audio(PNG, "image/png", 1024), "unsupported_type"),
        (lambda: validate_media(PNG, "application/pdf", 1024), "unsupported_type"),
        (lambda: validate_media(b"", "image/png", 1024), "empty"),
    ]
    for call, reason in cases:
        with pytest.raises(MediaValidationError) as caught:
            call()
        assert caught.value.reason == reason


async def test_transcribe_validates_before_any_provider_call(settings):
    configure(settings)
    settings.media_max_bytes = 16
    calls = []
    m = manager(settings, lambda r: calls.append(r) or httpx.Response(500))
    with pytest.raises(MediaValidationError):
        await m.transcribe(scope(), OGG, "audio/ogg")
    with pytest.raises(MediaValidationError):
        await m.vision(scope(), "Describe", [(PNG, "image/png")])
    settings.media_max_bytes = 1024
    with pytest.raises(MediaValidationError):
        await m.vision(scope(), "Describe", [(OGG, "audio/ogg")])
    with pytest.raises(MediaValidationError):
        await m.vision(scope(), "Describe", [])
    assert calls == []


# -- speech to text --------------------------------------------------------------------


async def test_openai_transcription_multipart_and_groq_fallback(settings):
    configure(settings)
    settings.fallback_llm_provider = "groq"
    settings.secondary_fallback_llm_provider = "gemini"
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "api.openai.com":
            return httpx.Response(503)
        return httpx.Response(200, json={"text": "Mujhe website chahiye", "language": "hi"})

    result = await manager(settings, handler).transcribe(scope(), OGG, "audio/ogg")
    assert (result.provider, result.model, result.text) == (
        "groq",
        "whisper-large-v3-turbo",
        "Mujhe website chahiye",
    )
    assert [r.url.path for r in seen] == [
        "/v1/audio/transcriptions",
        "/openai/v1/audio/transcriptions",
    ]
    body = seen[1].content
    assert b'name="model"' in body and b"whisper-large-v3-turbo" in body
    assert b'filename="audio.ogg"' in body and b"OggS" in body
    assert [a.fallback for a in result.attempts] == [False, True]


async def test_unsupported_audio_type_skips_to_capable_provider(settings):
    configure(settings)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
        )

    result = await manager(settings, handler).transcribe(scope(), AAC, "audio/aac")
    assert result.provider == "gemini" and result.text == "hello"
    assert hosts == ["generativelanguage.googleapis.com"]  # OpenAI cannot take AAC
    assert result.attempts[0].provider == "openai"
    assert result.attempts[0].error_kind == "unsupported"


# -- vision ------------------------------------------------------------------------------


async def test_vision_sends_inline_image_to_openai_and_gemini(settings):
    configure(settings)
    bodies = []

    def handler(request):
        bodies.append((request.url.host, json.loads(request.content)))
        if request.url.host == "api.openai.com":
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "A red logo"}]}}]}
        )

    result = await manager(settings, handler).vision(scope(), "Describe", [(PNG, "image/png")])
    assert result.text == "A red logo" and result.alias == "vision"
    openai_parts = bodies[0][1]["messages"][0]["content"]
    assert openai_parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    gemini_parts = bodies[1][1]["contents"][0]["parts"]
    assert gemini_parts[1]["inlineData"]["mimeType"] == "image/png"


# -- adapter details ---------------------------------------------------------------------


def test_retry_after_parsing():
    assert parse_retry_after(httpx.Headers({"retry-after": "3"})) == 3.0
    assert parse_retry_after(httpx.Headers({"retry-after-ms": "1500"})) == 1.5
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    value = parse_retry_after(httpx.Headers({"retry-after": future}))
    assert value is not None and 25 <= value <= 31
    assert parse_retry_after(httpx.Headers({"retry-after": "soon"})) is None
    assert parse_retry_after(httpx.Headers({})) is None


def gemini():
    return GeminiProvider(httpx.AsyncClient(), "https://g.test/v1beta", SecretStr("k"))


def response(status, body, headers=None):
    return httpx.Response(status, json=body, headers=headers)


def test_gemini_error_classification():
    g = gemini()
    per_day = {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {"@type": "QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerDay"}]},
                {"@type": "RetryInfo", "retryDelay": "30s"},
            ],
        }
    }
    quota = g.classify(response(429, per_day))
    assert quota.kind == ErrorKind.QUOTA and quota.retry_after == 30.0
    assert g.classify(response(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})).kind == (
        ErrorKind.RATE_LIMIT
    )
    bad_key = {"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}
    assert g.classify(response(400, bad_key)).kind == ErrorKind.AUTH
    assert g.classify(response(400, {"error": {"status": "INVALID_ARGUMENT"}})).kind == (
        ErrorKind.INVALID_REQUEST
    )
    assert g.classify(response(404, {"error": {"status": "NOT_FOUND"}})).kind == (
        ErrorKind.MODEL_UNAVAILABLE
    )
    assert g.classify(response(503, {})).kind == ErrorKind.UNAVAILABLE


def test_openai_error_classification():
    o = OpenAICompatibleProvider("openai", httpx.AsyncClient(), "https://o.test", SecretStr("k"))
    assert o.classify(response(429, {"error": {"code": "insufficient_quota"}})).kind == "quota"
    assert o.classify(response(429, {})).kind == "rate_limit"
    assert o.classify(response(401, {})).kind == "auth"
    assert o.classify(response(400, {"error": {"code": "model_decommissioned"}})).kind == (
        "model_unavailable"
    )
    assert o.classify(response(502, {})).kind == "unavailable"
    assert o.classify(response(429, {}, {"retry-after": "2"})).retry_after == 2.0


class Inner(BaseModel):
    name: str


class Outer(BaseModel):
    inner: Inner
    note: str | None = None
    tags: list[str] = []


def test_gemini_schema_conversion_inlines_refs_and_nullables():
    converted = to_gemini_schema(Outer.model_json_schema())
    dumped = json.dumps(converted)
    assert "$ref" not in dumped and "$defs" not in dumped and "title" not in dumped
    assert converted["properties"]["inner"]["properties"]["name"]["type"] == "STRING"
    assert converted["properties"]["note"] == {"nullable": True, "type": "STRING"}
    assert converted["properties"]["tags"]["items"]["type"] == "STRING"


async def test_gemini_maps_roles_tool_results_and_blocks():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    g = GeminiProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), "https://g.test", SecretStr("k")
    )
    messages = [
        Message.system("sys"),
        Message.user("find"),
        Message.assistant(tool_calls=[ToolCall("c1", "search", {"q": "x"})]),
        Message.tool("c1", "search", {"items": []}),
    ]
    with pytest.raises(ProviderError) as caught:
        await g.complete(LLMRequest(model="models/gm", messages=messages))
    assert caught.value.kind == ErrorKind.CONTENT_POLICY
    contents = seen[0]["contents"]
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[1]["parts"][0]["functionCall"] == {"name": "search", "args": {"q": "x"}}
    assert contents[2]["parts"][0]["functionResponse"] == {
        "name": "search",
        "response": {"items": []},
    }


async def test_gemini_rejects_path_injection_in_model_id():
    g = gemini()
    with pytest.raises(ProviderError) as caught:
        await g.complete(LLMRequest(model="../../x?key=1", messages=[Message.user("hi")]))
    assert caught.value.kind == ErrorKind.PERMANENT


async def test_openai_refusal_is_content_policy():
    body = {"choices": [{"message": {"content": None, "refusal": "no"}, "finish_reason": "stop"}]}
    o = OpenAICompatibleProvider(
        "openai",
        httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))),
        "https://o.test",
        SecretStr("k"),
    )
    with pytest.raises(ProviderError) as caught:
        await o.complete(LLMRequest(model="m", messages=[Message.user("hi")]))
    assert caught.value.kind == ErrorKind.CONTENT_POLICY


async def test_groq_uses_json_object_mode_with_schema_instruction(settings):
    configure(settings)
    settings.primary_llm_provider = "groq"
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name": "a"}'}}]})

    result = await manager(settings, handler).complete(
        scope(), alias="agent", purpose="test", messages=[Message.user("x")], schema=Inner
    )
    assert result.output == Inner(name="a")
    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert "JSON schema" in bodies[0]["messages"][0]["content"]


# -- legacy facade -----------------------------------------------------------------------


async def test_legacy_attempts_splat_into_usage_rows(settings):
    configure(settings)
    settings.openai_models = {"fast": "oa-fast"}

    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(503)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
        )

    gateway = Gateway(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await gateway.generate("System", "Customer")
    assert result.provider == "gemini" and gateway.attempts == result.attempts
    # PI writes AIUsageEvent(**attempt.model_dump(), alias=..., purpose=...).
    for attempt in gateway.attempts:
        row = AIUsageEvent(alias="fast", purpose="routing", **attempt.model_dump())
        assert row.provider == attempt.provider


async def test_legacy_attempts_are_kept_on_failure(settings):
    configure(settings)
    gateway = Gateway(
        settings, httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    )
    with pytest.raises(AllProvidersFailed):
        await gateway.generate("System", "Customer")
    assert [a.provider for a in gateway.attempts] == ["openai", "gemini", "groq"]
