"""Anthropic Messages API adapter (Claude). Chat, tools and vision; no embeddings or
speech-to-text (those aliases stay on OpenAI/Gemini)."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from pydantic import SecretStr

from app.ai.errors import ErrorKind, ProviderError
from app.ai.providers.base import HttpAdapter, classify_status, error_body, optional_int
from app.ai.providers.base import parse_retry_after as _retry_after
from app.ai.types import (
    ImagePart,
    LLMRequest,
    LLMResponse,
    Message,
    TextPart,
    ToolCall,
    Usage,
)

API_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
ERROR_KINDS = {
    "authentication_error": ErrorKind.AUTH,
    "permission_error": ErrorKind.AUTH,
    "billing_error": ErrorKind.QUOTA,
    "rate_limit_error": ErrorKind.RATE_LIMIT,
    "overloaded_error": ErrorKind.UNAVAILABLE,
    "api_error": ErrorKind.UNAVAILABLE,
    "not_found_error": ErrorKind.MODEL_UNAVAILABLE,
    "request_too_large": ErrorKind.INVALID_REQUEST,
    "invalid_request_error": ErrorKind.INVALID_REQUEST,
}


# Claude 5 models answer 400 "`temperature` is deprecated for this model" (live 2026-10-26: every pi
# reply failed on it and, because an invalid request stops the chain, no fallback ran). They are
# never sent one; any other model that refuses it is retried once without it and remembered.
NO_TEMPERATURE = re.compile(r"^claude-(?:sonnet|opus|haiku|fable)-5")
# Claude 5 models always think, and at their default effort the thinking alone can use the whole
# `max_tokens` (live 2026-10-27: a 4096 budget ended mid-JSON, so pi answered "pi mein abhi
# masla hai"; the same prompt at medium effort ends in about a thousand tokens). Medium keeps the
# quality of a structured reply and leaves room for the answer. A model that refuses the setting
# is retried once without it and remembered.
EFFORT = "medium"


class AnthropicProvider(HttpAdapter):
    """Implements LLMProvider and VisionProvider."""

    vision_mime_types = IMAGE_TYPES
    capabilities = frozenset({"chat", "vision"})

    def __init__(self, http: httpx.AsyncClient, base_url: str, api_key: SecretStr) -> None:
        super().__init__("anthropic", http, base_url)
        self._key = api_key
        self._no_temperature: set[str] = set()
        self._no_effort: set[str] = set()

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._key.get_secret_value(), "anthropic-version": API_VERSION}

    def classify(self, response: httpx.Response) -> ProviderError:
        status = response.status_code
        error = error_body(response)
        code = str(error.get("type") or "")
        kind = ERROR_KINDS.get(code, classify_status(status))
        if status == 529:
            kind = ErrorKind.UNAVAILABLE
        # An empty balance comes back as a 400 invalid_request_error; read (never keep)
        # the message so it falls back to another provider instead of stopping.
        elif "credit balance" in str(error.get("message") or "").lower():
            kind = ErrorKind.QUOTA
        return ProviderError(
            self.name,
            kind,
            status_code=status,
            code=code or None,
            retry_after=_retry_after(response.headers),
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        system, messages = self._messages(request)
        body: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens or DEFAULT_MAX_TOKENS,
            "messages": messages,
        }
        if system:
            body["system"] = system
        sends_temperature = (
            request.temperature is not None
            and not NO_TEMPERATURE.match(request.model)
            and request.model not in self._no_temperature
        )
        if sends_temperature:
            body["temperature"] = request.temperature
        sends_effort = bool(NO_TEMPERATURE.match(request.model)) and (
            request.model not in self._no_effort
        )
        if sends_effort:
            body["output_config"] = {"effort": EFFORT}
        if request.tools:
            body["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": dict(t.parameters)}
                for t in request.tools
            ]
            choice = request.tool_choice
            if choice == "required":
                body["tool_choice"] = {"type": "any"}
            elif choice in ("auto", "none"):
                body["tool_choice"] = {"type": choice}
            elif choice:
                body["tool_choice"] = {"type": "tool", "name": choice}
        try:
            data = await self.post(
                "messages",
                headers=self._headers(),
                json_body=body,
                request_timeout=request.timeout,
            )
        except ProviderError as error:
            if error.kind != ErrorKind.INVALID_REQUEST or not (sends_temperature or sends_effort):
                raise
            if sends_temperature:
                self._no_temperature.add(request.model)
                body.pop("temperature", None)
            if sends_effort:
                self._no_effort.add(request.model)
                body.pop("output_config", None)
            data = await self.post(
                "messages",
                headers=self._headers(),
                json_body=body,
                request_timeout=request.timeout,
            )
        return self._parse(data, request.model)

    async def analyze(self, request: LLMRequest) -> LLMResponse:
        return await self.complete(request)

    def _messages(self, request: LLMRequest) -> tuple[str, list[dict[str, Any]]]:
        system: list[str] = []
        out: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                system.append(message.text())
                continue
            role, blocks = self._blocks(message)
            if out and out[-1]["role"] == role:
                out[-1]["content"].extend(blocks)  # the API expects alternating turns
            else:
                out.append({"role": role, "content": blocks})
        if request.schema is not None:
            system.append(
                "Respond only with a JSON object matching this JSON schema, with no other "
                "text: " + json.dumps(dict(request.schema.schema))
            )
        return "\n\n".join(s for s in system if s), out

    @staticmethod
    def _blocks(message: Message) -> tuple[str, list[dict[str, Any]]]:
        if message.role == "tool":
            return "user", [
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "",
                    "content": message.text(),
                }
            ]
        blocks: list[dict[str, Any]] = []
        for part in message.parts():
            if isinstance(part, TextPart) and part.text:
                blocks.append({"type": "text", "text": part.text})
            elif isinstance(part, ImagePart):
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": part.mime_type,
                            "data": base64.b64encode(part.data).decode(),
                        },
                    }
                )
        if message.role == "assistant":
            blocks.extend(
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                for c in message.tool_calls
            )
            return "assistant", blocks or [{"type": "text", "text": " "}]
        return "user", blocks or [{"type": "text", "text": " "}]

    def _parse(self, data: dict[str, Any], requested_model: str) -> LLMResponse:
        content = data.get("content")
        if not isinstance(content, list):
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="no_content")
        text = ""
        calls: list[ToolCall] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text += block["text"]
            elif block.get("type") == "tool_use":
                arguments = block.get("input")
                if not isinstance(arguments, dict) or not isinstance(block.get("name"), str):
                    raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="bad_tool_call")
                calls.append(
                    ToolCall(id=str(block.get("id") or ""), name=block["name"], arguments=arguments)
                )
        stop = data.get("stop_reason")
        if stop == "refusal":
            raise ProviderError(self.name, ErrorKind.CONTENT_POLICY, code="refusal")
        if not text.strip() and not calls:
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="empty")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or requested_model),
            usage=Usage(
                optional_int(usage.get("input_tokens")), optional_int(usage.get("output_tokens"))
            ),
            tool_calls=calls,
            finish_reason=stop if isinstance(stop, str) else None,
        )
