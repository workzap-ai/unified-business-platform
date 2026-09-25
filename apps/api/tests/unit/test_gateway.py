import httpx
import pytest

from app.ai.gateway import Gateway, GatewayUnavailable


def configure(settings):
    from pydantic import SecretStr

    for provider in ("openai", "gemini", "groq"):
        setattr(settings, f"{provider}_api_key", SecretStr("test-provider-key"))
        setattr(settings, f"{provider}_models", {"fast": "test-model"})
    settings.llm_max_retries = 0
    return settings


@pytest.mark.parametrize(
    "failures,expected", [(0, "openai"), (1, "gemini"), (2, "groq"), (3, None)]
)
async def test_provider_fallback(settings, failures, expected):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if len(seen) <= failures:
            return httpx.Response(429, json={"error": "secret provider error"})
        if "googleapis" in request.url.host:
            return httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        gateway = Gateway(configure(settings), client)
        if expected:
            result = await gateway.generate("System", "Customer")
            assert result.provider == expected and len(result.attempts) == failures + 1
        else:
            with pytest.raises(GatewayUnavailable) as error:
                await gateway.generate("System", "Customer")
            assert "secret" not in str(error.value)
            assert len(error.value.attempts) == 3


async def test_permanent_error_is_not_retried_or_sent_to_other_providers(settings):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(400, json={"error": "bad input"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GatewayUnavailable):
            await Gateway(configure(settings), client).generate("System", "Customer")
    assert len(seen) == 1
