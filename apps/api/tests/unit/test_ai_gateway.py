"""AI gateway fallback matrix, circuit breaker, budgets, metering and secret hygiene.

All provider traffic goes through httpx.MockTransport; no real provider is called.
"""

import json
import logging
import traceback
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from app.ai.errors import (
    AllProvidersFailed,
    GatewayUnavailable,
    PermanentProviderFailure,
    UsageLimitExceeded,
)
from app.ai.health import ProviderHealth
from app.ai.manager import LLMManager, provider_status
from app.ai.registry import ModelRegistry
from app.ai.types import Message, ToolDefinition
from app.ai.usage import InMemoryUsageStore, UsageRecord
from app.shared.scope import WorkspaceScope

OPENAI_KEY = "sk-openai-SECRET-1111"
GEMINI_KEY = "gemini-SECRET-2222"
GROQ_KEY = "gsk-groq-SECRET-3333"
KEYS = (OPENAI_KEY, GEMINI_KEY, GROQ_KEY)
HOSTS = {
    "api.openai.com": "openai",
    "generativelanguage.googleapis.com": "gemini",
    "api.groq.com": "groq",
}


def configure(settings, retries=0):
    settings.openai_api_key = SecretStr(OPENAI_KEY)
    settings.gemini_api_key = SecretStr(GEMINI_KEY)
    settings.groq_api_key = SecretStr(GROQ_KEY)
    settings.openai_models = {"agent": "oa-model", "embed": "oa-embed", "transcribe": "oa-stt"}
    settings.gemini_models = {"agent": "gm-model", "embed": "gm-embed"}
    settings.groq_models = {"agent": "gq-model"}
    settings.llm_max_retries = retries
    return settings


def openai_ok(text="Hello from OpenAI", **message):
    return httpx.Response(
        200,
        json={
            "model": "oa-model",
            "choices": [{"message": {"content": text, **message}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def gemini_ok(text="Hello from Gemini", parts=None):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"content": {"parts": parts or [{"text": text}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        },
    )


class Router:
    """Per-provider scripted responses; records every request."""

    def __init__(self, **handlers):
        self.handlers = handlers
        self.calls: list[tuple[str, httpx.Request]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        provider = HOSTS[request.url.host]
        self.calls.append((provider, request))
        handler = self.handlers.get(provider)
        if handler is None:
            return httpx.Response(500)
        if isinstance(handler, list):
            handler = handler.pop(0) if len(handler) > 1 else handler[0]
        if isinstance(handler, Exception):
            raise handler
        return handler(request) if callable(handler) else handler

    @property
    def providers(self):
        return [p for p, _ in self.calls]


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def scope():
    return WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test", request_id="req-1")


@pytest.fixture
def store():
    return InMemoryUsageStore()


def manager_for(settings, router, store=None, health=None, sleeps=None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(router))

    async def sleep(seconds):
        if sleeps is not None:
            sleeps.append(seconds)

    return LLMManager(
        settings,
        client,
        usage=store,
        health=health or ProviderHealth(3, 30, clock=FakeClock()),
        sleep=sleep,
    )


async def ask(manager, scope, **kwargs):
    return await manager.complete(
        scope,
        alias=kwargs.pop("alias", "agent"),
        purpose=kwargs.pop("purpose", "reply"),
        messages=kwargs.pop("messages", [Message.system("Be brief."), Message.user("Hi")]),
        **kwargs,
    )


# -- fallback matrix -------------------------------------------------------------------


async def test_openai_success(settings, scope, store):
    router = Router(openai=openai_ok())
    response = await ask(manager_for(configure(settings), router, store), scope)
    assert (response.provider, response.text, response.fallback_used) == (
        "openai",
        "Hello from OpenAI",
        False,
    )
    assert response.usage.input_tokens == 10 and response.usage.output_tokens == 5
    request = router.calls[0][1]
    assert request.url.path == "/v1/chat/completions"
    body = json.loads(request.content)
    assert body["model"] == "oa-model" and body["messages"][0]["role"] == "system"
    assert request.headers["authorization"] == f"Bearer {OPENAI_KEY}"


@pytest.mark.parametrize(
    "failure,kind",
    [
        (httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}), "rate_limit"),
        (
            httpx.Response(
                429, json={"error": {"type": "insufficient_quota", "code": "insufficient_quota"}}
            ),
            "quota",
        ),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("refused"), "connection"),
        (httpx.Response(404, json={"error": {"code": "model_not_found"}}), "model_unavailable"),
    ],
)
async def test_openai_transient_failures_fall_back_to_gemini(settings, scope, failure, kind):
    router = Router(openai=failure, gemini=gemini_ok())
    response = await ask(manager_for(configure(settings), router), scope)
    assert response.provider == "gemini" and response.fallback_used
    assert router.providers == ["openai", "gemini"]
    assert [(a.provider, a.status, a.error_kind, a.fallback) for a in response.attempts] == [
        ("openai", "failed", kind, False),
        ("gemini", "success", None, True),
    ]


async def test_gemini_5xx_falls_back_to_groq(settings, scope):
    router = Router(
        openai=httpx.Response(500), gemini=httpx.Response(503), groq=openai_ok("From Groq")
    )
    response = await ask(manager_for(configure(settings), router), scope)
    assert response.provider == "groq" and response.text == "From Groq"
    assert router.providers == ["openai", "gemini", "groq"]
    assert router.calls[2][1].url.path == "/openai/v1/chat/completions"
    assert router.calls[2][1].headers["authorization"] == f"Bearer {GROQ_KEY}"
    assert [a.attempt for a in response.attempts] == [1, 2, 3]


async def test_all_providers_failing_raises_handoff_signal(settings, scope):
    router = Router(
        openai=httpx.Response(429),
        gemini=httpx.Response(503),
        groq=httpx.ConnectError("down"),
    )
    with pytest.raises(AllProvidersFailed) as caught:
        await ask(manager_for(configure(settings), router), scope)
    error = caught.value
    assert isinstance(error, GatewayUnavailable)  # existing PI handlers catch this
    assert error.safe_summary == (
        "All AI providers failed: openai=rate_limit, gemini=unavailable, groq=connection"
    )
    assert len(error.attempts) == 3
    assert error.public_message.startswith("AI assistance is unavailable")


@pytest.mark.parametrize(
    "status,body,kind",
    [
        (401, {"error": {"code": "invalid_api_key"}}, "auth"),
        (400, {"error": {"code": "invalid_value"}}, "invalid_request"),
        (400, {"error": {"code": "content_policy_violation"}}, "content_policy"),
    ],
)
async def test_permanent_errors_stop_without_retries_or_fallback(
    settings, scope, store, status, body, kind
):
    router = Router(openai=httpx.Response(status, json=body), gemini=gemini_ok())
    manager = manager_for(configure(settings, retries=3), router, store)
    with pytest.raises(PermanentProviderFailure) as caught:
        await ask(manager, scope)
    assert caught.value.kind == kind and isinstance(caught.value, GatewayUnavailable)
    assert router.providers == ["openai"]  # no retry storm, no cascade
    assert [r.error_kind for _, r in store.records] == [kind]


async def test_transient_retry_is_bounded_and_backs_off(settings, scope):
    sleeps: list[float] = []
    router = Router(openai=httpx.ReadTimeout("slow"), gemini=gemini_ok())
    response = await ask(manager_for(configure(settings, retries=2), router, sleeps=sleeps), scope)
    assert router.providers == ["openai", "openai", "openai", "gemini"]
    assert sleeps == [0.25, 0.5]
    assert response.provider == "gemini"


async def test_retry_after_is_honoured_when_short_and_skipped_when_long(settings, scope):
    sleeps: list[float] = []
    router = Router(openai=[httpx.Response(429, headers={"retry-after": "1"}), openai_ok()])
    response = await ask(manager_for(configure(settings, retries=1), router, sleeps=sleeps), scope)
    assert response.provider == "openai" and sleeps == [1.0]

    sleeps.clear()
    router = Router(openai=httpx.Response(429, headers={"retry-after": "60"}), gemini=gemini_ok())
    response = await ask(manager_for(configure(settings, retries=1), router, sleeps=sleeps), scope)
    assert router.providers == ["openai", "gemini"] and sleeps == []


async def test_provider_order_comes_from_settings(settings, scope):
    configure(settings)
    settings.primary_llm_provider = "groq"
    settings.fallback_llm_provider = "openai"
    settings.secondary_fallback_llm_provider = ""
    router = Router(groq=httpx.Response(503), openai=openai_ok(), gemini=gemini_ok())
    response = await ask(manager_for(settings, router), scope)
    assert router.providers == ["groq", "openai"] and response.provider == "openai"


async def test_unconfigured_providers_are_inactive(settings, scope):
    configure(settings)
    settings.openai_api_key = None
    router = Router(gemini=gemini_ok())
    response = await ask(manager_for(settings, router), scope)
    assert router.providers == ["gemini"] and not response.fallback_used


async def test_no_configured_provider_is_a_handoff(settings, scope):
    # apps/api/.env may define keys; clear them so nothing is configured.
    settings.openai_api_key = settings.gemini_api_key = settings.groq_api_key = None
    with pytest.raises(AllProvidersFailed) as caught:
        await ask(manager_for(settings, Router()), scope)
    assert "not_configured" in caught.value.safe_summary


# -- circuit breaker -------------------------------------------------------------------


async def test_circuit_opens_after_threshold_and_half_opens_after_cooldown(settings, scope):
    clock = FakeClock()
    health = ProviderHealth(failure_threshold=2, cooldown_seconds=30, clock=clock)
    router = Router(openai=httpx.Response(503), gemini=gemini_ok())
    manager = manager_for(configure(settings), router, health=health)

    await ask(manager, scope)
    await ask(manager, scope)
    assert health.state("openai") == "open"
    router.calls.clear()
    response = await ask(manager, scope)
    assert router.providers == ["gemini"]  # open provider skipped
    assert not response.fallback_used  # gemini was the first attempted provider

    clock.now += 31
    assert health.state("openai") == "half_open"
    router.calls.clear()
    await ask(manager, scope)  # probe fails -> open again
    assert router.providers == ["openai", "gemini"]
    assert health.state("openai") == "open"

    clock.now += 31
    router.handlers["openai"] = openai_ok()
    router.calls.clear()
    response = await ask(manager, scope)  # probe succeeds -> closed
    assert response.provider == "openai" and health.state("openai") == "closed"


def test_half_open_allows_a_single_probe():
    clock = FakeClock()
    health = ProviderHealth(1, 10, clock=clock)
    health.record_failure("openai")
    assert not health.allow("openai")
    clock.now += 10
    assert health.allow("openai") and not health.allow("openai")
    health.release("openai")
    assert health.allow("openai")


async def test_permanent_and_output_errors_do_not_open_the_circuit(settings, scope):
    health = ProviderHealth(1, 30, clock=FakeClock())
    router = Router(openai=httpx.Response(400), gemini=gemini_ok())
    with pytest.raises(PermanentProviderFailure):
        await ask(manager_for(configure(settings), router, health=health), scope)
    assert health.state("openai") == "closed"


# -- model aliases ---------------------------------------------------------------------


def test_model_alias_resolution(settings):
    configure(settings)
    settings.openai_models = {"fast": "oa-fast", "vision": ""}
    settings.ai_use_default_models = True
    registry = ModelRegistry.from_settings(settings)
    assert registry.resolve("openai", "router") == "oa-fast"  # legacy synonym
    assert registry.resolve("openai", "fast") == "oa-fast"
    assert registry.resolve("openai", "vision") is None  # explicitly disabled
    assert registry.resolve("openai", "embed") == "text-embedding-3-small"  # default
    assert registry.resolve("groq", "embed") is None  # no default: unsupported
    assert registry.resolve("openai", "custom") is None
    settings.ai_use_default_models = False
    assert ModelRegistry.from_settings(settings).resolve("openai", "embed") is None
    assert registry.explicit("openai", "embed") is None


async def test_provider_without_alias_is_skipped(settings, scope):
    configure(settings)
    settings.openai_models = {}
    settings.ai_use_default_models = False
    router = Router(gemini=gemini_ok())
    response = await ask(manager_for(settings, router), scope)
    assert router.providers == ["gemini"] and response.model == "gm-model"


async def test_invalid_alias_is_a_handoff_not_a_crash(settings, scope):
    with pytest.raises(AllProvidersFailed) as caught:
        await ask(manager_for(configure(settings), Router()), scope, alias="Not Valid!")
    assert caught.value.reason == "invalid_alias"


# -- structured output and tools ---------------------------------------------------------


class Decision(BaseModel):
    intent: str
    confidence: float


async def test_structured_output_is_parsed_and_validated(settings, scope):
    router = Router(openai=openai_ok('{"intent": "quote", "confidence": 0.9}'))
    manager = manager_for(configure(settings), router)
    result = await manager.complete_structured(
        scope, Decision, alias="agent", purpose="routing", messages=[Message.user("price?")]
    )
    assert result.value == Decision(intent="quote", confidence=0.9)
    assert result.response.parsed == {"intent": "quote", "confidence": 0.9}
    body = json.loads(router.calls[0][1].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["required"] == [
        "intent",
        "confidence",
    ]


async def test_invalid_json_falls_back_then_fails_safely(settings, scope):
    router = Router(
        openai=openai_ok("not json"), gemini=gemini_ok('{"intent": "order", "confidence": 1}')
    )
    response = await ask(manager_for(configure(settings), router), scope, schema=Decision)
    assert response.provider == "gemini" and response.output == Decision(
        intent="order", confidence=1
    )
    assert response.attempts[0].error_kind == "invalid_output"
    gemini_body = json.loads(router.calls[1][1].content)
    config = gemini_body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"]["type"] == "OBJECT"
    assert "title" not in json.dumps(config["responseSchema"])

    router = Router(
        openai=openai_ok('{"intent": 1}'),
        gemini=gemini_ok("{broken"),
        groq=openai_ok('{"wrong": true}'),
    )
    with pytest.raises(AllProvidersFailed) as caught:
        await ask(manager_for(configure(settings), router), scope, schema=Decision)
    assert [s.error_kind for s in caught.value.summary] == ["invalid_output"] * 3


async def test_openai_tool_calls_are_parsed(settings, scope):
    tool = ToolDefinition(
        "search_catalog",
        "Search services",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    )
    router = Router(
        openai=openai_ok(
            None,
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search_catalog", "arguments": '{"query": "website"}'},
                }
            ],
        )
    )
    response = await ask(
        manager_for(configure(settings), router), scope, tools=[tool], tool_choice="auto"
    )
    assert response.text == ""
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("call_1", "search_catalog", {"query": "website"})
    ]
    body = json.loads(router.calls[0][1].content)
    assert body["tools"][0]["function"]["name"] == "search_catalog"
    assert body["tool_choice"] == "auto"


async def test_gemini_tool_calls_are_parsed(settings, scope):
    configure(settings)
    settings.primary_llm_provider = "gemini"
    tool = ToolDefinition(
        "search_catalog",
        "Search services",
        {"type": "object", "properties": {"query": {"type": "string"}}},
    )
    router = Router(
        gemini=gemini_ok(
            parts=[{"functionCall": {"name": "search_catalog", "args": {"query": "chatbot"}}}]
        )
    )
    messages = [
        Message.system("Use tools."),
        Message.user("Need a chatbot"),
    ]
    response = await ask(
        manager_for(settings, router),
        scope,
        messages=messages,
        tools=[tool],
        tool_choice="search_catalog",
    )
    assert response.tool_calls[0].name == "search_catalog"
    assert response.tool_calls[0].arguments == {"query": "chatbot"}
    body = json.loads(router.calls[0][1].content)
    assert body["systemInstruction"] == {"parts": [{"text": "Use tools."}]}
    declaration = body["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "search_catalog"
    assert declaration["parameters"]["properties"]["query"]["type"] == "STRING"
    assert body["toolConfig"]["functionCallingConfig"] == {
        "mode": "ANY",
        "allowedFunctionNames": ["search_catalog"],
    }


async def test_malformed_tool_arguments_are_invalid_output(settings, scope):
    bad = openai_ok(
        None,
        tool_calls=[{"id": "c", "function": {"name": "x", "arguments": "{not json"}}],
    )
    router = Router(openai=bad, gemini=gemini_ok())
    response = await ask(manager_for(configure(settings), router), scope)
    assert response.attempts[0].error_kind == "invalid_output"


# -- secrets ----------------------------------------------------------------------------


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


async def test_api_keys_never_appear_in_errors_or_logs(settings, scope):
    capture = Capture()
    ai_logger = logging.getLogger("platform.ai")
    ai_logger.addHandler(capture)
    previous = ai_logger.level
    ai_logger.setLevel(logging.DEBUG)
    echo = f"Incorrect API key provided: {OPENAI_KEY} {GEMINI_KEY} {GROQ_KEY}"
    try:
        configure(settings)
        router = Router(
            openai=httpx.Response(429, json={"error": {"message": echo}}),
            gemini=httpx.Response(503, json={"error": {"message": echo}}),
            groq=httpx.ConnectError(echo),
        )
        with pytest.raises(AllProvidersFailed) as failed:
            await ask(manager_for(settings, router), scope)
        router = Router(openai=httpx.Response(401, json={"error": {"message": echo}}))
        with pytest.raises(PermanentProviderFailure) as permanent:
            await ask(manager_for(settings, router), scope)
    finally:
        ai_logger.removeHandler(capture)
        ai_logger.setLevel(previous)
    texts = [
        str(failed.value),
        repr(failed.value),
        str(permanent.value),
        repr(permanent.value.error),
        "".join(traceback.format_exception(failed.value)),
        "".join(traceback.format_exception(permanent.value)),
        json.dumps([a.model_dump(mode="json") for a in failed.value.attempts]),
    ]
    texts += [r.getMessage() + json.dumps(r.__dict__, default=str) for r in capture.records]
    assert capture.records  # attempts were logged
    for text in texts:
        for key in KEYS:
            assert key not in text
    assert capture.records[0].provider == "openai" and capture.records[0].request_id == "req-1"


async def test_gemini_key_travels_in_header_not_url(settings, scope):
    configure(settings)
    settings.primary_llm_provider = "gemini"
    router = Router(gemini=gemini_ok())
    await ask(manager_for(settings, router), scope)
    request = router.calls[0][1]
    assert GEMINI_KEY not in str(request.url)
    assert request.headers["x-goog-api-key"] == GEMINI_KEY
    assert request.url.path == "/v1beta/models/gm-model:generateContent"


# -- usage metering and budgets --------------------------------------------------------


async def test_usage_rows_recorded_per_attempt(settings, scope, store):
    configure(settings)
    settings.ai_model_prices = {"gemini:gm-model": {"input": Decimal("1"), "output": Decimal("2")}}
    run_id, conversation_id = uuid4(), uuid4()
    router = Router(openai=httpx.Response(503), gemini=gemini_ok())
    await ask(
        manager_for(settings, router, store),
        scope,
        purpose="routing",
        run_id=run_id,
        conversation_id=conversation_id,
    )
    rows: list[UsageRecord] = [r for _, r in store.records]
    assert [(r.provider, r.model, r.status, r.fallback, r.attempt, r.error_kind) for r in rows] == [
        ("openai", "oa-model", "failed", False, 1, "unavailable"),
        ("gemini", "gm-model", "success", True, 2, None),
    ]
    for row in rows:
        assert (row.tenant_id, row.environment_id) == (scope.tenant_id, scope.environment_id)
        assert (row.alias, row.purpose, row.run_id, row.conversation_id) == (
            "agent",
            "routing",
            run_id,
            conversation_id,
        )
        assert row.latency_ms >= 0
    assert rows[0].estimated_cost is None and rows[0].input_tokens is None
    assert (rows[1].input_tokens, rows[1].output_tokens) == (10, 5)
    assert rows[1].estimated_cost == Decimal("0.000020")
    assert not hasattr(rows[1], "prompt")


async def test_no_scope_means_no_metering(settings, store):
    router = Router(openai=openai_ok())
    await ask(manager_for(configure(settings), router, store), None)
    assert store.records == []


async def test_daily_token_and_cost_budgets(settings, scope, store):
    configure(settings)
    settings.ai_tenant_daily_token_limit = 20
    router = Router(openai=openai_ok())
    manager = manager_for(settings, router, store)
    await ask(manager, scope)  # 15 tokens used
    await ask(manager, scope)  # 15 < 20: allowed, now 30
    with pytest.raises(UsageLimitExceeded) as caught:
        await ask(manager, scope)
    assert caught.value.limit == "token" and isinstance(caught.value, GatewayUnavailable)
    assert len(router.calls) == 2  # refused before any provider call
    other = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "other")
    await ask(manager, other)  # budgets are per tenant

    settings.ai_tenant_daily_token_limit = None
    settings.ai_tenant_daily_cost_limit = Decimal("0.000001")
    settings.ai_model_prices = {"openai:oa-model": {"input": Decimal("1"), "output": Decimal("1")}}
    fresh = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "fresh")
    await ask(manager, fresh)
    with pytest.raises(UsageLimitExceeded) as caught:
        await ask(manager, fresh)
    assert caught.value.limit == "cost"


# -- embeddings ------------------------------------------------------------------------


async def test_embeddings_use_one_vector_space_unless_fallback_is_allowed(settings, scope, store):
    configure(settings)
    router = Router(
        openai=httpx.Response(503),
        gemini=httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}]}),
    )
    manager = manager_for(settings, router, store)
    with pytest.raises(AllProvidersFailed):
        await manager.embed(scope, ["hello"])
    assert router.providers == ["openai"]

    response = await manager.embed(scope, ["hello"], allow_fallback=True)
    assert (response.provider, response.model, response.vectors) == (
        "gemini",
        "gm-embed",
        [[0.1, 0.2]],
    )
    assert router.calls[-1][1].url.path == "/v1beta/models/gm-embed:batchEmbedContents"

    router = Router(
        openai=httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.3, 0.4]}],
                "usage": {"prompt_tokens": 2},
            },
        )
    )
    response = await manager_for(settings, router, store).embed(
        scope, ["hi"], expected_dimensions=2
    )
    assert response.vectors == [[0.3, 0.4]] and response.usage.input_tokens == 2
    assert store.records[-1][1].purpose == "embedding"


async def test_groq_has_no_embeddings(settings, scope):
    configure(settings)
    settings.primary_llm_provider = "groq"
    settings.fallback_llm_provider = ""
    settings.secondary_fallback_llm_provider = ""
    with pytest.raises(AllProvidersFailed) as caught:
        await manager_for(settings, Router()).embed(scope, ["x"])
    assert caught.value.summary[0].error_kind == "unsupported"


# -- status ------------------------------------------------------------------------------


def test_provider_status_has_no_secrets(settings):
    configure(settings)
    settings.groq_api_key = None
    health = ProviderHealth(1, 30, clock=FakeClock())
    health.record_failure("gemini")
    status = provider_status(settings, health)
    assert status["order"] == ["openai", "gemini", "groq"]
    by_name = {p["name"]: p for p in status["providers"]}
    assert by_name["openai"]["active"] and not by_name["groq"]["active"]
    assert by_name["gemini"]["circuit"] == "open"
    assert by_name["openai"]["models"]["agent"] == "oa-model"
    dumped = json.dumps(status)
    assert all(key not in dumped for key in KEYS)
