import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai.errors import ErrorKind, ProviderError
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.registry import ModelRegistry, ProviderRegistry
from app.ai.types import LLMRequest, Message, OutputSchema, ToolCall, ToolDefinition


def _provider(handler) -> AnthropicProvider:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AnthropicProvider(http, "https://api.anthropic.com/v1", SecretStr("sk-ant-test"))


async def test_messages_request_and_tool_call_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-sonnet-5-5",
                "content": [
                    {"type": "text", "text": "Checking."},
                    {"type": "tool_use", "id": "tu_1", "name": "lookup", "input": {"q": "x"}},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 12, "output_tokens": 5},
            },
        )

    response = await _provider(handler).complete(
        LLMRequest(
            model="claude-sonnet-5-5",
            messages=[
                Message.system("Be brief."),
                Message.user("hi"),
                Message.assistant("", [ToolCall("tu_0", "lookup", {"q": "a"})]),
                Message.tool("tu_0", "lookup", {"found": True}),
                Message.tool("tu_9", "lookup", "second"),
            ],
            tools=[ToolDefinition("lookup", "Look up")],
            tool_choice="required",
            schema=OutputSchema.of({"type": "object"}),
        )
    )
    body = seen["body"]
    assert seen["headers"]["x-api-key"] == "sk-ant-test"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert body["system"].startswith("Be brief.") and "JSON schema" in body["system"]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert len(body["messages"][2]["content"]) == 2  # tool results merged into one turn
    assert body["tool_choice"] == {"type": "any"} and body["max_tokens"] == 1024
    assert response.tool_calls[0].name == "lookup" and response.usage.total_tokens == 17
    assert response.provider == "anthropic"


@pytest.mark.parametrize(
    ("status", "error", "kind"),
    [
        (401, "authentication_error", ErrorKind.AUTH),
        (429, "rate_limit_error", ErrorKind.RATE_LIMIT),
        (529, "overloaded_error", ErrorKind.UNAVAILABLE),
    ],
)
async def test_errors_are_classified(status, error, kind):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"type": "error", "error": {"type": error}})

    with pytest.raises(ProviderError) as caught:
        await _provider(handler).complete(LLMRequest(model="m", messages=[Message.user("x")]))
    assert caught.value.kind == kind


def test_registry_builds_anthropic_with_defaults(settings):
    settings.anthropic_api_key = SecretStr("sk-ant-test")
    registry = ProviderRegistry.from_settings(settings, httpx.AsyncClient())
    assert "anthropic" in registry.names and registry.supports("anthropic", "chat")
    assert not registry.supports("anthropic", "embed")
    models = ModelRegistry({}, use_defaults=True)
    assert models.resolve("anthropic", "agent") == "claude-sonnet-5-5"
    assert models.resolve("anthropic", "embed") is None
