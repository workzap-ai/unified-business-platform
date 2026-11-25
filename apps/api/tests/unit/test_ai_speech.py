"""Text to speech through the AI gateway: the request, the answer, failure and who is skipped."""

import json
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.ai.errors import AllProvidersFailed
from app.ai.health import ProviderHealth
from app.ai.manager import MAX_SPEECH_CHARS, LLMManager
from app.shared.scope import WorkspaceScope

MP3 = b"ID3" + b"\x00" * 64


def scope():
    return WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")


def configure(settings, *, groq=False):
    settings.openai_api_key = SecretStr("sk-openai-test")
    settings.gemini_api_key = None
    settings.groq_api_key = SecretStr("gsk-groq-test") if groq else None
    settings.openai_models = {}
    settings.gemini_models = {}
    settings.groq_models = {}
    settings.llm_max_retries = 0
    settings.ai_use_default_models = True
    return settings


def manager(settings, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMManager(settings, client, health=ProviderHealth(5, 30))


async def test_speech_request_and_audio_answer(settings):
    configure(settings)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

    result = await manager(settings, handler).synthesize(
        scope(), "Hello,   I am pi, an AI.", voice="nova"
    )
    assert result.audio == MP3
    assert (result.provider, result.mime_type) == ("openai", "audio/mpeg")
    assert result.model == "gpt-4o-mini-tts"
    assert result.usage.input_tokens == len("Hello, I am pi, an AI.")
    assert [r.url.path for r in seen] == ["/v1/audio/speech"]
    body = json.loads(seen[0].content)
    assert body == {
        "model": "gpt-4o-mini-tts",
        "input": "Hello, I am pi, an AI.",
        "voice": "nova",
        "response_format": "mp3",
    }
    assert seen[0].headers["authorization"] == "Bearer sk-openai-test"


async def test_raw_pcm_is_asked_for_by_format(settings):
    configure(settings)

    def handler(request):
        assert json.loads(request.content)["response_format"] == "pcm"
        return httpx.Response(200, content=b"\x00\x01" * 100)

    result = await manager(settings, handler).synthesize(scope(), "hi", audio_format="pcm")
    assert result.mime_type == "audio/pcm"


@pytest.mark.parametrize("status", [401, 429, 503])
async def test_a_refused_request_is_a_failure_never_audio(settings, status):
    configure(settings)
    with pytest.raises(AllProvidersFailed):
        await manager(settings, lambda r: httpx.Response(status)).synthesize(scope(), "hi")


async def test_an_empty_body_is_a_failure(settings):
    configure(settings)
    with pytest.raises(AllProvidersFailed):
        await manager(settings, lambda r: httpx.Response(200, content=b"")).synthesize(
            scope(), "hi"
        )


async def test_a_provider_without_speech_is_skipped(settings):
    configure(settings, groq=True)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(503) if request.url.host == "api.openai.com" else httpx.Response(200)

    settings.fallback_llm_provider = "groq"
    with pytest.raises(AllProvidersFailed):
        await manager(settings, handler).synthesize(scope(), "hi")
    assert hosts == ["api.openai.com"]  # groq has no speech: never called


async def test_empty_or_long_text_is_refused_before_any_call(settings):
    configure(settings)
    calls = []
    m = manager(settings, lambda r: calls.append(r) or httpx.Response(200, content=MP3))
    with pytest.raises(ValueError):
        await m.synthesize(scope(), "   ")
    with pytest.raises(ValueError):
        await m.synthesize(scope(), "a" * (MAX_SPEECH_CHARS + 1))
    assert calls == []


def test_the_text_never_appears_in_a_repr():
    from app.ai.types import SpeechRequest

    assert "secret words" not in repr(SpeechRequest("m", "secret words", "alloy"))
