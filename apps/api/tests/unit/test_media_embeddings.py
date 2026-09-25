import httpx
import pytest
from pydantic import SecretStr

from app.ai.embeddings import embed
from app.ai.gateway import GatewayUnavailable
from app.ai.media import understand_media, validate_media


def test_media_validates_content_and_size():
    validate_media(b"OggSvoice", "audio/ogg", 1024)
    with pytest.raises(GatewayUnavailable):
        validate_media(b"<script>", "image/png", 1024)
    with pytest.raises(GatewayUnavailable):
        validate_media(b"OggSvoice", "audio/ogg", 4)


async def test_transcription_provider_fallback(settings):
    settings.openai_api_key = SecretStr("test-openai")
    settings.gemini_api_key = SecretStr("test-gemini")
    settings.openai_models = {"stt": "test-stt"}
    settings.gemini_models = {"stt": "test-stt"}
    calls = []

    def respond(request):
        calls.append(request.url.host)
        if request.url.host == "api.openai.com":
            return httpx.Response(503)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "Mujhe website chahiye"}]}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (
            await understand_media(settings, client, b"OggSvoice", "audio/ogg")
            == "Mujhe website chahiye"
        )
    assert calls == ["api.openai.com", "generativelanguage.googleapis.com"]


async def test_embeddings_validate_dimension_and_numeric_values(settings):
    settings.openai_api_key = SecretStr("test-key")
    settings.openai_models = {"embedding": "test-embedding"}
    settings.embedding_dimensions = 2
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        )
    ) as client:
        assert await embed(settings, client, ["Approved policy"]) == [[0.1, 0.2]]
        settings.embedding_dimensions = 3
        with pytest.raises(GatewayUnavailable):
            await embed(settings, client, ["Approved policy"])
