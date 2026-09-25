# AI gateway

`apps/api/app/ai/` is the platform's AI gateway. It is shared by every product, not
built for PI alone. It covers chat completion (with JSON-schema structured output and
tool calls), vision, embeddings and speech-to-text over OpenAI, Gemini and Groq. Around
those calls it handles model aliases, provider fallback, a circuit breaker, per-tenant
budgets, usage metering in `ai_usage_events`, and structured tracing.

> **Unverified:** no real provider has been called. Every test uses `httpx.MockTransport`
> with request/response shapes taken from the public API docs. Real keys may reveal
> differences: exact error codes, Gemini schema limits, Groq structured-output support
> per model, and whether the default model IDs exist on your account. Check each provider
> with real keys before production and pin model IDs in settings.

## Layout

| Module | Responsibility |
| --- | --- |
| `types.py` | `Message`, `TextPart`/`ImagePart`, `ToolDefinition`, `ToolCall`, `OutputSchema`, `LLMRequest`/`LLMResponse`, embedding/transcription types, `Attempt` |
| `errors.py` | `ErrorKind` taxonomy, `ProviderError`, terminal errors (all subclass `GatewayUnavailable`) |
| `providers/base.py` | Protocols `LLMProvider`, `VisionProvider`, `EmbeddingProvider`, `SpeechToTextProvider`; HTTP execution, Retry-After parsing |
| `providers/openai.py` | OpenAI Chat Completions, `/embeddings` and `/audio/transcriptions`. Groq reuses this adapter |
| `providers/gemini.py` | Gemini `generateContent`, `batchEmbedContents` and audio transcription through multimodal input |
| `registry.py` | `ModelRegistry` (aliases), `PriceTable`, `ProviderRegistry`. This is the only place that holds default model IDs and prices |
| `health.py` | `ProviderHealth` circuit breaker; `health_for(settings)` gives the per-process instance |
| `usage.py` | `UsageTracker`, `SqlUsageStore` / `InMemoryUsageStore` / `NullUsageStore`, `BudgetGuard` |
| `tracing.py` | `ai_span(...)`: an OpenTelemetry span if the package is installed, otherwise a no-op |
| `manager.py` | `LLMManager`, `FallbackPolicy`, `build_llm_manager`, `provider_status` |
| `media.py` | MIME allowlist, magic-byte and size validation, plus the legacy `understand_media` |
| `gateway.py`, `embeddings.py` | Legacy facades (`Gateway.generate`, `embed`) implemented over `LLMManager` |

No vendor SDKs and no new dependencies: everything uses `httpx`.

## Public API

```python
from app.ai.manager import LLMManager, build_llm_manager, provider_status
from app.ai.types import Message, ToolDefinition
from app.ai.errors import GatewayUnavailable  # the handoff signal

manager = build_llm_manager(settings, http_client, sessions)  # sessions: async_sessionmaker

response = await manager.complete(
    scope, alias="agent", purpose="reply",
    messages=[Message.system("..."), Message.user(text)],
    schema=MyModel | {json schema} | None, tools=[ToolDefinition(...)], tool_choice="auto",
    temperature=None, max_tokens=None, conversation_id=..., run_id=...,
)   # -> LLMResponse(text, tool_calls, parsed, output, usage, provider, model,
    #                 alias, fallback_used, attempts)
result = await manager.complete_structured(scope, MyModel, alias="router", purpose="routing",
                                           messages=[...])       # result.value: MyModel
vision = await manager.vision(scope, "Describe", [(image_bytes, "image/jpeg")])
stt = await manager.transcribe(scope, audio_bytes, "audio/ogg", language="ur")
emb = await manager.embed(scope, ["text"], alias="embed", expected_dimensions=1536)
status = provider_status(settings)   # order, configured/active providers, circuit state, models
```

`scope` is the trusted `WorkspaceScope`. It supplies the tenant and environment for
usage rows and budgets, and it never comes from request input. Passing `scope=None`
turns off budgets and metering. Only the legacy facades do that.

Every terminal failure is a `GatewayUnavailable`, so a caller only has to catch one type
to hand off to a human:

- `AllProvidersFailed`: every eligible provider failed with a transient error or was skipped. It carries `.summary` and `.safe_summary`, for example `"All AI providers failed: openai=rate_limit, gemini=unavailable, groq=timeout"`.
- `PermanentProviderFailure`: an auth, invalid-request or content-policy error stopped the chain. It carries `.kind`.
- `UsageLimitExceeded`: the tenant's daily budget is spent. No provider was called.
- `MediaValidationError`: the media was rejected before any call. It is also a `ValueError`.

`GatewayUnavailable.public_message` is the text that is safe to show customers.

### Legacy compatibility

`Gateway(settings, http).generate(system, user, alias="fast") -> Generation`,
`Gateway.attempts`, `understand_media(...)` and `embed(settings, http, texts)` keep their
signatures and still raise `GatewayUnavailable`. They now run through `LLMManager`.

- **Usage rows:** the facades do not write usage rows. PI writes `AIUsageEvent(**attempt.model_dump(), alias=..., purpose=...)` itself. For that reason `Attempt` must only contain columns of `ai_usage_events`. It now includes `estimated_cost`.
- **Skipped providers:** these no longer appear as `error_kind="unconfigured"` attempts. They are listed in the exception summary instead.
- **Legacy embeddings:** `embed()` still requires an explicitly configured OpenAI `embedding`/`embed` model. PI stores that model ID next to the vectors.

## Providers and aliases

The provider order comes from `Settings.provider_order()`: `PRIMARY_LLM_PROVIDER`, then
`FALLBACK_LLM_PROVIDER`, then `SECONDARY_FALLBACK_LLM_PROVIDER`. The default is
OpenAI → Gemini → Groq. A provider without an API key is never built.

Agents ask for an alias and never a model ID. `ModelRegistry.resolve(provider, alias)` resolves it in this order:

1. `*_MODELS[alias]`, then the canonical name and its synonyms. The legacy synonyms are `fast→router`, `balanced→agent`, `embedding→embed` and `stt→transcribe`.
2. An empty string means the alias is disabled for that provider, and the provider is skipped.
3. Otherwise the registry default applies. `AI_USE_DEFAULT_MODELS` controls this: when it
   is unset, defaults are on except with `APP_ENV=test`. That way test settings that inherit
   real keys from a local `.env` can never reach a provider through a default model.

| alias | openai | gemini | groq |
| --- | --- | --- | --- |
| router | gpt-4o-mini | gemini-2.5-flash-lite | llama-3.1-8b-instant |
| agent | gpt-4o-mini | gemini-2.5-flash | llama-3.3-70b-versatile |
| summarize | gpt-4o-mini | gemini-2.5-flash-lite | llama-3.1-8b-instant |
| vision | gpt-4o-mini | gemini-2.5-flash | meta-llama/llama-4-scout-17b-16e-instruct |
| embed | text-embedding-3-small | gemini-embedding-001 | (none) |
| transcribe | whisper-1 | gemini-2.5-flash (multimodal) | whisper-large-v3-turbo |

These defaults are unverified. Pin models in production.

Adapter notes:

- **OpenAI:** structured output uses `response_format: json_schema`. Tools use `tools`/`tool_choice`. Max tokens are sent as `max_completion_tokens`.
- **Groq:** uses the same adapter with a different base URL and key. Structured output defaults to `json_object` plus a schema instruction (`GROQ_STRUCTURED_OUTPUT`), because `json_schema` is only available on some Groq models. Groq has no embeddings.
- **Gemini:**
  - The system prompt is sent as `systemInstruction`, and assistant messages use the `model` role.
  - Tool calls go out as `functionDeclarations` and `toolConfig`, and tool results come back as `functionResponse`.
  - Structured output uses `responseMimeType` plus `responseSchema`. JSON Schema is converted to Gemini's OpenAPI subset: `$ref` is inlined, null unions become `nullable`, and `title`/`additionalProperties` are dropped.
  - The key travels only in the `x-goog-api-key` header, never in the URL.
  - Model IDs are checked against `^[A-Za-z0-9._-]+$` to prevent path injection.
- **Structured output (all providers):** the manager parses the JSON (tolerating a single code fence) and validates it against the Pydantic model when one was given. Invalid JSON or a schema mismatch counts as `invalid_output`.

## Fallback rules and error taxonomy

| Kind | Class | Behaviour |
| --- | --- | --- |
| `rate_limit`, `timeout`, `connection`, `unavailable` (5xx/408/409) | transient | Retried on the same provider up to `LLM_MAX_RETRIES` times with backoff 0.25s, 0.5s, and so on (capped at 2s). A 429 is retried only when `Retry-After` is at most `LLM_RETRY_AFTER_MAX_SECONDS`. After that, fall back. Counts toward the circuit breaker. |
| `quota` (e.g. `insufficient_quota`, Gemini per-day quota) | transient | Falls back immediately. Counts toward the circuit breaker. |
| `model_unavailable` (404, `model_not_found`/`decommissioned`) | transient | Falls back. |
| `invalid_output` (bad JSON/schema, empty reply, malformed tool call) | transient | Falls back. Does not count toward the circuit breaker. |
| `unsupported` (capability or MIME type not supported) | transient | Skips to the next provider. |
| `auth`, `invalid_request`, `content_policy`, `permanent` | permanent | Stops at once with `PermanentProviderFailure`. No retry and no cascade. |

- **Retry-After:** both delta-seconds and HTTP-date forms are honoured, as are `retry-after-ms` and Gemini's `RetryInfo.retryDelay`.
- **Media:** transcription never retries on the same provider, because the payloads are large.
- **Embeddings:** these never fall back across providers by default, because vector spaces differ between providers. Opt in with `allow_fallback=True` and store `response.provider`/`response.model`.

## Circuit breaker

`ProviderHealth` keeps one circuit per provider, per process, bound to a Settings
instance:

- **Closed → open:** after `LLM_CIRCUIT_FAILURE_THRESHOLD` consecutive circuit-counting failures (default 3), the circuit opens and the provider is skipped (`circuit_open`).
- **Open → half-open:** after `LLM_CIRCUIT_COOLDOWN_SECONDS` (default 30s), one probe request is allowed.
- **Half-open → closed or open:** if the probe succeeds the circuit closes; if it fails the circuit opens again.

State is not shared through Redis, so each API or worker process learns on its own.

## Cost tracking and limits

- **Usage rows:** each provider attempt writes one `ai_usage_events` row: provider, model, alias, purpose, status, fallback, attempt number, error_kind, latency_ms, input/output tokens, `estimated_cost` (Decimal), conversation_id and run_id. Tenant and environment come from the scope. Prompts, outputs, media and keys are never stored.
- **Transactions:** `SqlUsageStore` writes each call's rows in its own short transaction, outside business transactions. A metering failure is logged and never fails the AI call.
- **Prices:** these are USD per 1M tokens, from `DEFAULT_PRICES` in `registry.py` (approximate and unverified). Override them with `AI_MODEL_PRICES={"provider:model": {"input": "...", "output": "..."}}`. An unknown model gets `estimated_cost = NULL`. Transcription is billed per minute by providers and is not priced.
- **Budgets:** `AI_TENANT_DAILY_TOKEN_LIMIT` and `AI_TENANT_DAILY_COST_LIMIT` are per tenant, per UTC day, summed from `ai_usage_events`. They are checked before every call and raise `UsageLimitExceeded`. One in-flight call can overshoot the limit by its own usage.

## Media

- **Images:** jpeg, png and webp.
- **Audio:** ogg (WhatsApp voice notes), mpeg, mp4/m4a, wav, webm, flac, aac.
- **Checks:** MIME parameters are stripped and aliases normalized. The magic bytes must match the MIME type. Size is limited by `MEDIA_MAX_BYTES`, and audio is also capped at 25 MB, the OpenAI/Groq upload limit.
- **AAC:** OpenAI and Groq do not accept AAC, so AAC goes to Gemini.
- **Vision:** at most 8 images per call.

## Tracing and logs

- **Logs:** each attempt logs `ai.attempt` to the `platform.ai` logger. The message and `extra` fields contain provider, model, alias, purpose, status, latency_ms, fallback, attempt, error_kind and request_id.
- **JSON formatter:** the core `JsonFormatter` only emits allowlisted extra fields. That is why the key fields are also in the message text. To get them as JSON fields, the core logging owner can add them to the allowlist.
- **Spans:** `ai_span("ai.attempt", ...)` produces an OpenTelemetry span when `opentelemetry` is importable (it is not a dependency). Otherwise it does nothing.
- **Secret hygiene:** API keys, provider response bodies and URLs never appear in exceptions or logs. Adapters raise `from None` and keep only a sanitized provider error code. Tests assert this for OpenAI, Gemini and Groq.

## Not done / follow-ups

- **Admin endpoint:** a read-only admin endpoint for `provider_status()` belongs to the integration owner.
- **PI wiring:** PI still uses the legacy facade. To get budgets and direct metering, move it to `LLMManager.complete(scope, ...)`, and stop writing rows from `Gateway.attempts` at the same time so nothing is counted twice.
- **Not implemented:** streaming, and shared circuit state across processes.
- **Real provider calls:** unverified (see the note at the top).
