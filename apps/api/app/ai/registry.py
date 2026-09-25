"""Model aliases and provider construction.

This module is the ONE place with default model IDs and prices. Agents and modules
ask for a logical alias ("router", "agent", ...) and never hardcode model IDs.
Settings (``OPENAI_MODELS``/``GEMINI_MODELS``/``GROQ_MODELS``, ``AI_MODEL_PRICES``)
override every default; an empty string disables an alias for that provider.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx

from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.openai import OpenAICompatibleProvider

if TYPE_CHECKING:
    from app.core.config import Settings

KNOWN_PROVIDERS = ("openai", "gemini", "groq")
ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,19}$")  # ai_usage_events.alias is 20 chars

# Legacy/alternative alias names -> canonical alias.
ALIAS_SYNONYMS: dict[str, str] = {
    "fast": "router",
    "balanced": "agent",
    "embedding": "embed",
    "stt": "transcribe",
}

# Defaults: reasonable at the time of writing, NOT verified against live accounts.
# Operators should pin models explicitly via settings in production.
DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "openai": {
        "router": "gpt-4o-mini",
        "agent": "gpt-4o-mini",
        "summarize": "gpt-4o-mini",
        "vision": "gpt-4o-mini",
        "embed": "text-embedding-3-small",
        "transcribe": "whisper-1",
    },
    "gemini": {
        "router": "gemini-2.5-flash-lite",
        "agent": "gemini-2.5-flash",
        "summarize": "gemini-2.5-flash-lite",
        "vision": "gemini-2.5-flash",
        "embed": "gemini-embedding-001",
        "transcribe": "gemini-2.5-flash",
    },
    "groq": {
        "router": "llama-3.1-8b-instant",
        "agent": "llama-3.3-70b-versatile",
        "summarize": "llama-3.1-8b-instant",
        "vision": "meta-llama/llama-4-scout-17b-16e-instruct",
        "transcribe": "whisper-large-v3-turbo",
    },
}

# USD per 1M tokens (input, output). Approximate list prices; UNVERIFIED and subject
# to change. Override or extend with AI_MODEL_PRICES={"provider:model": {...}}.
DEFAULT_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "openai:gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "openai:text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
    "gemini:gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
    "gemini:gemini-2.5-flash-lite": (Decimal("0.10"), Decimal("0.40")),
    "groq:llama-3.1-8b-instant": (Decimal("0.05"), Decimal("0.08")),
    "groq:llama-3.3-70b-versatile": (Decimal("0.59"), Decimal("0.79")),
}


class InvalidAlias(ValueError):
    pass


def canonical_alias(alias: str) -> str:
    if not ALIAS_PATTERN.fullmatch(alias):
        raise InvalidAlias("Model alias must be 1-20 lowercase characters")
    return ALIAS_SYNONYMS.get(alias, alias)


class ModelRegistry:
    def __init__(
        self,
        overrides: Mapping[str, Mapping[str, str]],
        *,
        use_defaults: bool = True,
        defaults: Mapping[str, Mapping[str, str]] = DEFAULT_MODELS,
    ) -> None:
        self.overrides = overrides
        self.use_defaults = use_defaults
        self.defaults = defaults

    @classmethod
    def from_settings(cls, settings: Settings) -> ModelRegistry:
        return cls(
            {p: getattr(settings, f"{p}_models") for p in KNOWN_PROVIDERS},
            use_defaults=(
                settings.ai_use_default_models
                if settings.ai_use_default_models is not None
                else settings.app_env != "test"
            ),
        )

    def resolve(self, provider: str, alias: str) -> str | None:
        """Provider-specific model ID for ``alias`` or None when not available."""
        canonical = canonical_alias(alias)
        names = [alias, canonical] + [k for k, v in ALIAS_SYNONYMS.items() if v == canonical]
        configured = self.overrides.get(provider, {})
        for name in names:
            if name in configured:
                return configured[name] or None  # "" explicitly disables the alias
        if self.use_defaults:
            return self.defaults.get(provider, {}).get(canonical)
        return None

    def explicit(self, provider: str, alias: str) -> str | None:
        """Only an operator-configured model (no defaults)."""
        return ModelRegistry(self.overrides, use_defaults=False).resolve(provider, alias)

    def table(self) -> dict[str, dict[str, str]]:
        aliases = {a for m in self.defaults.values() for a in m} if self.use_defaults else set()
        for mapping in self.overrides.values():
            aliases.update(ALIAS_SYNONYMS.get(a, a) for a in mapping if ALIAS_PATTERN.fullmatch(a))
        out: dict[str, dict[str, str]] = {}
        for provider in KNOWN_PROVIDERS:
            resolved = {a: self.resolve(provider, a) for a in sorted(aliases)}
            out[provider] = {a: m for a, m in resolved.items() if m}
        return out


class PriceTable:
    def __init__(self, prices: Mapping[str, tuple[Decimal, Decimal]]) -> None:
        self.prices = dict(prices)

    @classmethod
    def from_settings(cls, settings: Settings) -> PriceTable:
        prices = dict(DEFAULT_PRICES)
        for key, value in settings.ai_model_prices.items():
            prices[key] = (
                Decimal(str(value.get("input", 0))),
                Decimal(str(value.get("output", 0))),
            )
        return cls(prices)

    def estimate(
        self, provider: str, model: str, input_tokens: int | None, output_tokens: int | None
    ) -> Decimal | None:
        price = self.prices.get(f"{provider}:{model}")
        if price is None or (input_tokens is None and output_tokens is None):
            return None
        cost = (Decimal(input_tokens or 0) * price[0] + Decimal(output_tokens or 0) * price[1]) / (
            Decimal(1_000_000)
        )
        return cost.quantize(Decimal("0.000001"))


class ProviderRegistry:
    """Active providers only: a provider without an API key is never constructed."""

    def __init__(self, providers: Mapping[str, Any]) -> None:
        self.providers = dict(providers)

    @classmethod
    def from_settings(cls, settings: Settings, http: httpx.AsyncClient) -> ProviderRegistry:
        providers: dict[str, Any] = {}
        if settings.openai_api_key:
            providers["openai"] = OpenAICompatibleProvider(
                "openai", http, settings.openai_base_url, settings.openai_api_key
            )
        if settings.gemini_api_key:
            providers["gemini"] = GeminiProvider(
                http, settings.gemini_base_url, settings.gemini_api_key
            )
        if settings.groq_api_key:
            providers["groq"] = OpenAICompatibleProvider(
                "groq",
                http,
                settings.groq_base_url,
                settings.groq_api_key,
                capabilities=frozenset({"chat", "vision", "transcribe"}),
                structured_mode=settings.groq_structured_output,
            )
        return cls(providers)

    def get(self, name: str) -> Any | None:
        return self.providers.get(name)

    def supports(self, name: str, capability: str) -> bool:
        provider = self.providers.get(name)
        capabilities = getattr(provider, "capabilities", None)
        return provider is not None and (capabilities is None or capability in capabilities)

    @property
    def names(self) -> list[str]:
        return list(self.providers)
