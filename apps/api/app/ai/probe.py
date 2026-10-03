"""Live check of one AI provider: a real, tiny completion per configured chat model.

A models-list call succeeds even when the account has no credits left, so the
dashboard's "Test" button uses this instead. It talks to the adapter directly
(no fallback, no circuit breaker), so a new key is always really tried, and a
passing test clears that provider's pause. Results are fixed, secret-free strings.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from app.ai.errors import ErrorKind, ProviderError
from app.ai.health import health_for
from app.ai.manager import key_fingerprint
from app.ai.registry import ModelRegistry, ProviderRegistry
from app.ai.types import LLMRequest, Message

if TYPE_CHECKING:
    from app.core.config import Settings

CHAT_ALIASES = ("router", "agent", "summarize")
PROMPT = [Message.system("Reply with the single word: ok"), Message.user("ping")]
# Room for models that think before answering (Gemini 3.x): with only a few tokens
# they spend them all thinking, return no text and the test wrongly reports a failure.
# The answer itself is still one word.
MAX_TOKENS = 256

STATUS: dict[ErrorKind, tuple[str, str]] = {
    ErrorKind.AUTH: ("bad_key", "The key was refused. Paste a valid key and save again."),
    ErrorKind.QUOTA: (
        "no_credits",
        "No credits or quota left on this account. Add credits or raise the limit; "
        "requests use the backup provider meanwhile.",
    ),
    ErrorKind.RATE_LIMIT: ("rate_limited", "The key works but is rate limited right now."),
    ErrorKind.MODEL_UNAVAILABLE: (
        "model_missing",
        "This model isn't available to the account. Choose another model.",
    ),
    ErrorKind.TIMEOUT: ("unreachable", "The provider didn't answer in time."),
    ErrorKind.CONNECTION: ("unreachable", "Couldn't reach the provider."),
    ErrorKind.UNAVAILABLE: ("unreachable", "The provider is having problems right now."),
}


def _models(settings: Settings, provider: str) -> list[tuple[str, str]]:
    registry, seen, out = ModelRegistry.from_settings(settings), set(), []
    for alias in CHAT_ALIASES:
        model = registry.resolve(provider, alias)
        if model and model not in seen:
            seen.add(model)
            out.append((alias, model))
    return out


async def _one(adapter: Any, model: str, seconds: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        await adapter.complete(
            LLMRequest(model=model, messages=PROMPT, max_tokens=MAX_TOKENS, timeout=seconds)
        )
        status, message = "ok", "Working"
    except ProviderError as exc:
        status, message = STATUS.get(exc.kind, ("error", f"Failed ({exc.kind.value})"))
    except Exception:  # noqa: BLE001 - adapter bug: report, never raise details
        status, message = "error", "Failed (adapter_error)"
    return {
        "model": model,
        "status": status,
        "message": message,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


async def probe(settings: Settings, http: httpx.AsyncClient, provider: str) -> dict[str, Any]:
    """``{"ok", "status", "message", "model", "latency_ms", "models": [...]}``."""
    adapter = ProviderRegistry.from_settings(settings, http).get(provider)
    if adapter is None:
        return {"ok": False, "status": "not_set", "message": "Add an API key first"}
    models = _models(settings, provider)
    if not models:
        return {"ok": False, "status": "no_model", "message": "Choose at least one model"}
    timeout = min(settings.llm_timeout_seconds, 20)
    results = []
    for alias, model in models:
        result = await _one(adapter, model, timeout)
        results.append({"alias": alias, **result})
        if result["status"] in {"bad_key", "no_credits"}:
            break  # account-level: the other models would fail the same way
    failed = next((r for r in results if r["status"] != "ok"), None)
    health = health_for(settings)
    health.credential(provider, key_fingerprint(settings, provider))
    if failed is None:
        health.record_success(provider)  # a fixed key/top-up is usable right away
        names = ", ".join(r["model"] for r in results)
        return {
            "ok": True,
            "status": "ok",
            "message": f"Working · {names}",
            "model": results[0]["model"],
            "latency_ms": max(r["latency_ms"] for r in results),
            "models": results,
        }
    if failed["status"] in {"bad_key", "no_credits"}:
        health.disable(provider, "auth" if failed["status"] == "bad_key" else "quota")
    return {
        "ok": False,
        "status": failed["status"],
        "message": failed["message"]
        + ("" if len(results) == 1 else f" ({failed['alias']}: {failed['model']})"),
        "model": failed["model"],
        "latency_ms": failed["latency_ms"],
        "models": results,
    }
