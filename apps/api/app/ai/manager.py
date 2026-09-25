"""LLMManager: the single entry point for AI calls (chat, structured, tools, vision,
embeddings, speech-to-text) with fallback, circuit breaking, budgets and metering."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import (
    CIRCUIT_KINDS,
    SAME_PROVIDER_RETRY_KINDS,
    AllProvidersFailed,
    AttemptSummary,
    ErrorKind,
    PermanentProviderFailure,
    ProviderError,
)
from app.ai.health import ProviderHealth, health_for
from app.ai.media import validate_audio, validate_image
from app.ai.providers.base import parse_json_text
from app.ai.registry import (
    KNOWN_PROVIDERS,
    InvalidAlias,
    ModelRegistry,
    PriceTable,
    ProviderRegistry,
    canonical_alias,
)
from app.ai.tracing import ai_span
from app.ai.types import (
    Attempt,
    EmbeddingRequest,
    EmbeddingResponse,
    ImagePart,
    LLMRequest,
    LLMResponse,
    Message,
    OutputSchema,
    TextPart,
    ToolChoice,
    ToolDefinition,
    TranscriptionRequest,
    TranscriptionResponse,
    Usage,
)
from app.ai.usage import (
    BudgetGuard,
    NullUsageStore,
    SqlUsageStore,
    UsageRecord,
    UsageStore,
    UsageTracker,
)
from app.core.config import Settings

if TYPE_CHECKING:
    from app.shared.scope import WorkspaceScope

logger = logging.getLogger("platform.ai")
PURPOSE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,19}$")  # ai_usage_events.purpose: 20 chars
MAX_EMBED_BATCH = 100


class FallbackPolicy:
    """Provider order from Settings.provider_order(); bounded same-provider retries.

    - transient error: retry the same provider (timeout/connection/5xx/429 with a short
      Retry-After) up to ``max_retries`` times, then move to the next provider;
    - permanent error (auth, invalid request, content policy): stop immediately;
    - every provider failed or skipped: AllProvidersFailed (human handoff signal).
    """

    def __init__(self, order: Sequence[str], max_retries: int, retry_after_max: float) -> None:
        self.order = [p for p in order if p in KNOWN_PROVIDERS]
        self.max_retries, self.retry_after_max = max_retries, retry_after_max

    @classmethod
    def from_settings(cls, settings: Settings) -> FallbackPolicy:
        return cls(
            settings.provider_order(),
            settings.llm_max_retries,
            settings.llm_retry_after_max_seconds,
        )

    def retry_delay(self, error: ProviderError, retry: int, max_retries: int) -> float | None:
        """Seconds to wait before retrying the same provider, or None to move on."""
        if retry >= max_retries or error.kind not in SAME_PROVIDER_RETRY_KINDS:
            return None
        if error.retry_after is not None:
            return error.retry_after if error.retry_after <= self.retry_after_max else None
        if error.kind == ErrorKind.RATE_LIMIT:
            return None  # no hint: another provider is the better bet
        return min(0.25 * 2.0**retry, 2.0)


@dataclass(slots=True)
class StructuredResult[M: BaseModel]:
    value: M
    response: LLMResponse


class LLMManager:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        *,
        usage: UsageStore | None = None,
        health: ProviderHealth | None = None,
        providers: ProviderRegistry | None = None,
        models: ModelRegistry | None = None,
        prices: PriceTable | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.settings, self.http = settings, http
        self.usage_store: UsageStore = usage or NullUsageStore()
        self.tracker = UsageTracker(self.usage_store)
        self.health = health or health_for(settings)
        self._providers, self._models, self._prices = providers, models, prices
        self.sleep, self.clock = sleep, clock

    # Built per call unless injected: settings may be reconfigured at runtime/tests.
    @property
    def providers(self) -> ProviderRegistry:
        return self._providers or ProviderRegistry.from_settings(self.settings, self.http)

    @property
    def models(self) -> ModelRegistry:
        return self._models or ModelRegistry.from_settings(self.settings)

    @property
    def prices(self) -> PriceTable:
        return self._prices or PriceTable.from_settings(self.settings)

    # -- public API -----------------------------------------------------------------------

    async def complete(
        self,
        scope: WorkspaceScope | None,
        *,
        alias: str,
        purpose: str,
        messages: Sequence[Message],
        schema: type[BaseModel] | Mapping[str, Any] | OutputSchema | None = None,
        tools: Sequence[ToolDefinition] = (),
        tool_choice: ToolChoice | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        conversation_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> LLMResponse:
        """Chat completion with fallback. ``scope`` None skips budgets and metering
        (legacy facade only); production callers pass the trusted WorkspaceScope."""
        output = (
            schema
            if isinstance(schema, OutputSchema) or schema is None
            else (OutputSchema.of(schema))
        )
        vision = any(m.images() for m in messages)

        async def call(provider: Any, name: str, model: str) -> LLMResponse:
            request = LLMRequest(
                model=model,
                messages=messages,
                schema=output,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.settings.llm_timeout_seconds,
            )
            response: LLMResponse = await (
                provider.analyze(request) if vision else provider.complete(request)
            )
            if output is not None and not (response.tool_calls and not response.text.strip()):
                self._parse_structured(name, response, output)
            return response

        response, attempts = await self._execute(
            scope,
            alias=alias,
            purpose=purpose,
            capability="vision" if vision else "chat",
            call=call,
            usage_of=lambda r: r.usage,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        response.alias, response.attempts = alias, attempts
        response.fallback_used = any(a.fallback for a in attempts)
        return response

    async def complete_structured[M: BaseModel](
        self,
        scope: WorkspaceScope | None,
        output: type[M],
        *,
        alias: str,
        purpose: str,
        messages: Sequence[Message],
        temperature: float | None = None,
        max_tokens: int | None = None,
        conversation_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> StructuredResult[M]:
        response = await self.complete(
            scope,
            alias=alias,
            purpose=purpose,
            messages=messages,
            schema=output,
            temperature=temperature,
            max_tokens=max_tokens,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        return StructuredResult(response.parse_as(output), response)

    async def vision(
        self,
        scope: WorkspaceScope | None,
        prompt: str,
        images: Sequence[tuple[bytes, str]],
        *,
        alias: str = "vision",
        purpose: str = "vision",
        system: str | None = None,
        schema: type[BaseModel] | Mapping[str, Any] | None = None,
        max_tokens: int | None = None,
        conversation_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> LLMResponse:
        if not images or len(images) > 8:
            from app.ai.errors import MediaValidationError

            raise MediaValidationError("image_count")
        parts: list[TextPart | ImagePart] = [TextPart(prompt)]
        for content, mime in images:
            normalized = validate_image(content, mime, self.settings.media_max_bytes)
            parts.append(ImagePart(content, normalized))
        messages = ([Message.system(system)] if system else []) + [Message.user(parts)]
        return await self.complete(
            scope,
            alias=alias,
            purpose=purpose,
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
            conversation_id=conversation_id,
            run_id=run_id,
        )

    async def transcribe(
        self,
        scope: WorkspaceScope | None,
        audio: bytes,
        mime_type: str,
        *,
        alias: str = "transcribe",
        purpose: str = "transcription",
        language: str | None = None,
        prompt: str | None = None,
        conversation_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> TranscriptionResponse:
        normalized = validate_audio(audio, mime_type, self.settings.media_max_bytes)

        async def call(provider: Any, name: str, model: str) -> TranscriptionResponse:
            if normalized not in getattr(provider, "transcription_mime_types", frozenset()):
                raise ProviderError(name, ErrorKind.UNSUPPORTED, code="mime")
            result: TranscriptionResponse = await provider.transcribe(
                TranscriptionRequest(
                    model=model,
                    audio=audio,
                    mime_type=normalized,
                    language=language,
                    prompt=prompt,
                    timeout=self.settings.llm_timeout_seconds,
                )
            )
            return result

        result, attempts = await self._execute(
            scope,
            alias=alias,
            purpose=purpose,
            capability="transcribe",
            call=call,
            usage_of=lambda r: r.usage,
            conversation_id=conversation_id,
            run_id=run_id,
            max_retries=0,  # large payloads: fall back instead of re-uploading
        )
        result.attempts = attempts
        return result

    async def embed(
        self,
        scope: WorkspaceScope | None,
        texts: Sequence[str],
        *,
        alias: str = "embed",
        purpose: str = "embedding",
        provider: str | None = None,
        dimensions: int | None = None,
        expected_dimensions: int | None = None,
        allow_fallback: bool = False,
        explicit_model_only: bool = False,
    ) -> EmbeddingResponse:
        """Embeddings from ONE vector space by default: the first capable provider in
        order (or ``provider``). Cross-provider fallback mixes incompatible spaces, so it
        is opt-in and callers must store ``response.provider``/``response.model``."""
        if not 1 <= len(texts) <= MAX_EMBED_BATCH or any(not t for t in texts):
            raise AllProvidersFailed([], reason="invalid_input")

        async def call(adapter: Any, name: str, model: str) -> EmbeddingResponse:
            result: EmbeddingResponse = await adapter.embed(
                EmbeddingRequest(
                    model=model,
                    texts=list(texts),
                    timeout=self.settings.llm_timeout_seconds,
                    dimensions=dimensions,
                )
            )
            width = expected_dimensions or (len(result.vectors[0]) if result.vectors else 0)
            if len(result.vectors) != len(texts) or any(
                len(v) != width or not v or not any(v) or not all(math.isfinite(x) for x in v)
                for v in result.vectors
            ):
                raise ProviderError(name, ErrorKind.INVALID_OUTPUT, code="bad_embedding")
            return result

        result, attempts = await self._execute(
            scope,
            alias=alias,
            purpose=purpose,
            capability="embed",
            call=call,
            usage_of=lambda r: r.usage,
            only=[provider] if provider else None,
            allow_fallback=allow_fallback,
            explicit_model_only=explicit_model_only,
        )
        result.attempts = attempts
        return result

    # -- engine ---------------------------------------------------------------------------

    @staticmethod
    def _parse_structured(name: str, response: LLMResponse, output: OutputSchema) -> None:
        response.parsed = parse_json_text(name, response.text)
        if output.model is not None:
            try:
                response.output = output.model.model_validate(response.parsed)
            except ValidationError:
                raise ProviderError(
                    name, ErrorKind.INVALID_OUTPUT, code="schema_mismatch"
                ) from None

    async def _execute[T](
        self,
        scope: WorkspaceScope | None,
        *,
        alias: str,
        purpose: str,
        capability: str,
        call: Callable[[Any, str, str], Awaitable[T]],
        usage_of: Callable[[T], Usage],
        conversation_id: UUID | None = None,
        run_id: UUID | None = None,
        max_retries: int | None = None,
        only: list[str] | None = None,
        allow_fallback: bool = True,
        explicit_model_only: bool = False,
    ) -> tuple[T, list[Attempt]]:
        try:
            canonical_alias(alias)
        except InvalidAlias:
            raise AllProvidersFailed([], reason="invalid_alias") from None
        if not PURPOSE_PATTERN.fullmatch(purpose):
            raise ValueError("purpose must be 1-20 lowercase characters")
        if scope is not None:
            await BudgetGuard.from_settings(self.settings, self.usage_store).check(scope.tenant_id)
        policy = FallbackPolicy.from_settings(self.settings)
        retries = policy.max_retries if max_retries is None else max_retries
        providers, models, prices = self.providers, self.models, self.prices
        order = [p for p in policy.order if only is None or p in only]
        summary: list[AttemptSummary] = []
        attempts: list[Attempt] = []
        records: list[UsageRecord] = []
        first: str | None = None
        request_id = scope.request_id if scope is not None else None

        async def finish() -> None:
            if scope is not None and records:
                await self.tracker.record(records)

        for name in order:
            adapter = providers.get(name)
            if adapter is None:
                summary.append(AttemptSummary(name, "", "skipped", "not_configured"))
                continue
            if not providers.supports(name, capability):
                summary.append(AttemptSummary(name, "", "skipped", "unsupported"))
                continue
            model = (
                models.explicit(name, alias) if explicit_model_only else models.resolve(name, alias)
            )
            if not model:
                summary.append(AttemptSummary(name, "", "skipped", "no_model"))
                continue
            if not self.health.allow(name):
                summary.append(AttemptSummary(name, model, "skipped", "circuit_open"))
                continue
            first = first or name
            for retry in range(retries + 1):
                if retry and not self.health.allow(name):
                    break
                number = len(attempts) + 1
                fallback = name != first
                started = self.clock()
                error: ProviderError | None = None
                result: T | None = None
                with ai_span(
                    "ai.attempt",
                    provider=name,
                    model=model,
                    alias=alias,
                    purpose=purpose,
                    attempt=number,
                    fallback=fallback,
                    request_id=request_id,
                ) as span:
                    try:
                        result = await call(adapter, name, model)
                    except ProviderError as exc:
                        error = exc
                    except Exception as exc:  # adapter bug: contain it, never leak details
                        logger.error(
                            "ai.adapter_error provider=%s type=%s", name, type(exc).__name__
                        )
                        error = ProviderError(name, ErrorKind.UNAVAILABLE, code="adapter_error")
                    if error is not None:
                        span.set_attribute("ai.error_kind", error.kind.value)
                latency = max(0, int((self.clock() - started) * 1000))
                usage = usage_of(result) if result is not None else Usage()
                cost = prices.estimate(name, model, usage.input_tokens, usage.output_tokens)
                attempt = Attempt(
                    provider=name,
                    model=model,
                    status="success" if error is None else "failed",
                    error_kind=error.kind.value if error else None,
                    latency_ms=latency,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    attempt=number,
                    fallback=fallback,
                    estimated_cost=cost,
                )
                attempts.append(attempt)
                summary.append(
                    AttemptSummary(name, model, attempt.status, attempt.error_kind, number)
                )
                if scope is not None:
                    records.append(
                        self.tracker.build(
                            scope,
                            alias=alias,
                            purpose=purpose,
                            conversation_id=conversation_id,
                            run_id=run_id,
                            **attempt.model_dump(),
                        )
                    )
                self._log(attempt, alias, purpose, request_id)
                if error is None:
                    self.health.record_success(name)
                    await finish()
                    assert result is not None
                    return result, attempts
                if error.kind in CIRCUIT_KINDS:
                    self.health.record_failure(name)
                else:
                    self.health.release(name)
                if error.permanent:
                    await finish()
                    raise PermanentProviderFailure(error, summary, attempts)
                delay = policy.retry_delay(error, retry, retries)
                if delay is None:
                    break
                await self.sleep(delay)
            if not allow_fallback and first is not None:
                break
        await finish()
        raise AllProvidersFailed(summary, attempts)

    @staticmethod
    def _log(attempt: Attempt, alias: str, purpose: str, request_id: str | None) -> None:
        fields = {
            "provider": attempt.provider,
            "model": attempt.model,
            "alias": alias,
            "purpose": purpose,
            "status": attempt.status,
            "latency_ms": attempt.latency_ms,
            "fallback": attempt.fallback,
            "attempt": attempt.attempt,
            "error_kind": attempt.error_kind,
            "request_id": request_id,
        }
        logger.log(
            logging.INFO if attempt.status == "success" else logging.WARNING,
            "ai.attempt",
            extra=fields,
        )


def build_llm_manager(
    settings: Settings,
    http: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession] | None = None,
) -> LLMManager:
    """Production wiring: usage rows go to ai_usage_events when a session factory is given."""
    return LLMManager(
        settings, http, usage=SqlUsageStore(sessions) if sessions is not None else None
    )


def provider_status(settings: Settings, health: ProviderHealth | None = None) -> dict[str, Any]:
    """Secret-free gateway status for admin/ops endpoints."""
    health = health or health_for(settings)
    order = FallbackPolicy.from_settings(settings).order
    models = ModelRegistry.from_settings(settings).table()
    providers = []
    for name in KNOWN_PROVIDERS:
        configured = getattr(settings, f"{name}_api_key") is not None
        snapshot = health.snapshot().get(name, {"state": "closed", "consecutive_failures": 0})
        providers.append(
            {
                "name": name,
                "configured": configured,
                "in_order": name in order,
                "active": configured and name in order,
                "circuit": health.state(name),
                "consecutive_failures": snapshot["consecutive_failures"],
                "models": models.get(name, {}),
            }
        )
    return {
        "order": order,
        "providers": providers,
        "limits": {
            "tenant_daily_tokens": settings.ai_tenant_daily_token_limit,
            "tenant_daily_cost": (
                str(settings.ai_tenant_daily_cost_limit)
                if settings.ai_tenant_daily_cost_limit is not None
                else None
            ),
        },
        "circuit": {
            "failure_threshold": health.failure_threshold,
            "cooldown_seconds": health.cooldown_seconds,
        },
    }
