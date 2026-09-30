"""Failover when a provider's key is refused or its credits run out, and the live probe.

All provider traffic goes through httpx.MockTransport; no real provider is called.
"""

from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from test_ai_gateway import (
    GEMINI_KEY,
    FakeClock,
    Router,
    ask,
    configure,
    gemini_ok,
    manager_for,
    openai_ok,
)

from app.ai.errors import AllProvidersFailed, ErrorKind, PermanentProviderFailure
from app.ai.health import ProviderHealth, health_for
from app.ai.manager import provider_status
from app.ai.probe import probe
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import classify_status
from app.shared.scope import WorkspaceScope

NO_CREDITS = httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
BAD_KEY = httpx.Response(401, json={"error": {"code": "invalid_api_key"}})


@pytest.fixture
def scope():
    return WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test", request_id="req-1")


@pytest.mark.parametrize("failure", [NO_CREDITS, BAD_KEY], ids=["no_credits", "bad_key"])
async def test_dead_account_falls_back_and_is_paused(settings, scope, failure):
    clock = FakeClock()
    health = ProviderHealth(3, 30, clock=clock, disable_seconds=600)
    router = Router(openai=failure, gemini=gemini_ok())
    manager = manager_for(configure(settings), router, health=health)
    first = await ask(manager, scope)
    assert first.provider == "gemini" and first.fallback_used
    assert router.providers == ["openai", "gemini"]  # no retry against a dead account
    # Paused well past the normal 30 s cooldown: later requests skip it entirely.
    clock.now += 300
    await ask(manager, scope)
    assert router.providers == ["openai", "gemini", "gemini"]
    reason = "quota" if failure is NO_CREDITS else "auth"
    assert health.snapshot()["openai"]["reason"] == reason
    # After the pause one probe request is allowed again.
    clock.now += 301
    await ask(manager, scope)
    assert router.providers[-2:] == ["openai", "gemini"]


async def test_saving_a_new_key_ends_the_pause_at_once(settings, scope):
    health = ProviderHealth(3, 30, clock=FakeClock(), disable_seconds=600)
    router = Router(openai=[NO_CREDITS, openai_ok()], gemini=gemini_ok())
    manager = manager_for(configure(settings), router, health=health)
    assert (await ask(manager, scope)).provider == "gemini"
    settings.openai_api_key = SecretStr("sk-openai-TOPPED-UP-9999")
    assert (await ask(manager, scope)).provider == "openai"


async def test_request_errors_still_stop_the_chain(settings, scope):
    router = Router(openai=httpx.Response(400, json={"error": {"code": "bad"}}))
    with pytest.raises(PermanentProviderFailure):
        await ask(manager_for(configure(settings), router), scope)
    assert router.providers == ["openai"]


async def test_every_account_dead_is_a_handoff_not_a_crash(settings, scope):
    router = Router(openai=BAD_KEY, gemini=httpx.Response(402), groq=NO_CREDITS)
    with pytest.raises(AllProvidersFailed) as failed:
        await ask(manager_for(configure(settings), router), scope)
    assert [s.error_kind for s in failed.value.summary] == ["auth", "quota", "quota"]


@pytest.mark.parametrize("enabled,expected", [(True, "gemini"), (False, None)])
async def test_last_resort_uses_any_provider_with_a_key(settings, scope, enabled, expected):
    configure(settings)
    settings.primary_llm_provider = settings.fallback_llm_provider = "openai"
    settings.secondary_fallback_llm_provider = "openai"
    settings.ai_failover_all_configured = enabled
    router = Router(openai=NO_CREDITS, gemini=gemini_ok())
    manager = manager_for(settings, router)
    if expected is None:
        with pytest.raises(AllProvidersFailed):
            await ask(manager, scope)
    else:
        assert (await ask(manager, scope)).provider == expected
    assert provider_status(settings)["order"][0] == "openai"


def json_error(status, body):
    return httpx.Response(status, json=body)


@pytest.mark.parametrize(
    "response,kind",
    [
        (
            json_error(
                400,
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Your credit balance is too low to access the API.",
                    }
                },
            ),
            ErrorKind.QUOTA,
        ),
        (json_error(402, {"error": {"type": "billing_error"}}), ErrorKind.QUOTA),
        (json_error(401, {"error": {"type": "authentication_error"}}), ErrorKind.AUTH),
        (json_error(400, {"error": {"type": "invalid_request_error"}}), ErrorKind.INVALID_REQUEST),
    ],
)
def test_anthropic_credit_errors_are_quota(response, kind):
    adapter = AnthropicProvider(httpx.AsyncClient(), "https://api.anthropic.com/v1", SecretStr("k"))
    assert adapter.classify(response).kind == kind


def test_payment_required_is_quota_for_every_provider():
    assert classify_status(402) == ErrorKind.QUOTA


def probe_settings(settings):
    configure(settings)
    settings.openai_models = {"router": "oa-small", "agent": "oa-model"}
    return settings


def mock(router):
    return httpx.AsyncClient(transport=httpx.MockTransport(router))


async def test_probe_really_calls_each_model_and_reports_working(settings):
    router = Router(openai=openai_ok("ok"))
    result = await probe(probe_settings(settings), mock(router), "openai")
    assert result["ok"] and result["status"] == "ok"
    assert [m["model"] for m in result["models"]] == ["oa-small", "oa-model"]
    assert router.providers == ["openai", "openai"]


async def test_probe_detects_finished_credits_and_pauses_provider(settings):
    settings = probe_settings(settings)
    router = Router(openai=NO_CREDITS)
    result = await probe(settings, mock(router), "openai")
    assert result == {**result, "ok": False, "status": "no_credits"}
    assert "credits" in result["message"]
    assert router.providers == ["openai"]  # stops after the account-level answer
    assert health_for(settings).state("openai") == "open"
    # Topping up and testing again un-pauses it straight away.
    fixed = await probe(settings, mock(Router(openai=openai_ok("ok"))), "openai")
    assert fixed["ok"] and health_for(settings).state("openai") == "closed"


@pytest.mark.parametrize(
    "response,status",
    [
        (BAD_KEY, "bad_key"),
        (httpx.Response(404, json={"error": {"code": "model_not_found"}}), "model_missing"),
        (httpx.Response(503), "unreachable"),
    ],
)
async def test_probe_statuses(settings, response, status):
    result = await probe(probe_settings(settings), mock(Router(openai=response)), "openai")
    assert not result["ok"] and result["status"] == status


async def test_probe_without_key_or_model(settings):
    assert (await probe(settings, mock(Router()), "openai"))["status"] == "not_set"
    configure(settings)
    settings.groq_models = {}
    settings.ai_use_default_models = False
    assert (await probe(settings, mock(Router()), "groq"))["status"] == "no_model"


async def test_probe_never_returns_the_key(settings):
    result = await probe(probe_settings(settings), mock(Router(openai=BAD_KEY)), "openai")
    assert GEMINI_KEY not in str(result) and "sk-openai" not in str(result)
