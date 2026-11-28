"""OpenAI Chat Completions adapter; Groq reuses it (OpenAI-compatible API)."""

from __future__ import annotations

import base64
import json
from typing import Any, Literal

import httpx
from pydantic import SecretStr

from app.ai.errors import ErrorKind, ProviderError
from app.ai.providers.base import HttpAdapter, classify_status, error_body, optional_int
from app.ai.providers.base import parse_retry_after as _retry_after
from app.ai.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    ImagePart,
    LLMRequest,
    LLMResponse,
    Message,
    SpeechRequest,
    SpeechResponse,
    TextPart,
    ToolCall,
    TranscriptionRequest,
    TranscriptionResponse,
    Usage,
    Word,
)

AUDIO_EXTENSIONS = {
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/wav": "wav",
    "audio/webm": "webm",
    "audio/flac": "flac",
}
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
Capability = Literal["chat", "vision", "embed", "transcribe", "speak"]
SPEECH_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "opus": "audio/opus", "pcm": "audio/pcm"}
StructuredMode = Literal["json_schema", "json_object"]


class OpenAICompatibleProvider(HttpAdapter):
    """Implements LLMProvider, VisionProvider, EmbeddingProvider, SpeechToTextProvider."""

    transcription_mime_types = frozenset(AUDIO_EXTENSIONS)
    vision_mime_types = IMAGE_TYPES

    def __init__(
        self,
        name: str,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: SecretStr,
        *,
        capabilities: frozenset[Capability] = frozenset(
            {"chat", "vision", "embed", "transcribe", "speak"}
        ),
        structured_mode: StructuredMode = "json_schema",
    ) -> None:
        super().__init__(name, http, base_url)
        self._key = api_key
        self.capabilities = capabilities
        self.structured_mode = structured_mode

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key.get_secret_value()}"}

    def classify(self, response: httpx.Response) -> ProviderError:
        status = response.status_code
        error = error_body(response)
        code = str(error.get("code") or error.get("type") or "")
        kind = classify_status(status)
        if status == 413:
            # A size limit of THIS provider or tier (Groq's free tier answers 413 above 8,000
            # tokens a request), not a broken request: the next provider may take it.
            kind = ErrorKind.REQUEST_TOO_LARGE
        if code in {"insufficient_quota", "billing_hard_limit_reached", "credit_balance_exhausted"}:
            kind = ErrorKind.QUOTA
        elif code in {"content_policy_violation", "content_filter"}:
            kind = ErrorKind.CONTENT_POLICY
        elif code in {"model_not_found", "model_decommissioned"}:
            kind = ErrorKind.MODEL_UNAVAILABLE
        elif code in {"invalid_api_key", "invalid_authentication"}:
            kind = ErrorKind.AUTH
        return ProviderError(
            self.name,
            kind,
            status_code=status,
            code=code or None,
            retry_after=_retry_after(response.headers),
        )

    def _unsupported(self, capability: Capability) -> None:
        if capability not in self.capabilities:
            raise ProviderError(self.name, ErrorKind.UNSUPPORTED, code=capability)

    # -- chat -----------------------------------------------------------------------------

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self._unsupported("chat")
        if any(m.images() for m in request.messages):
            self._unsupported("vision")
        body: dict[str, Any] = {
            "model": request.model,
            "messages": self._messages(request),
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_completion_tokens"] = request.max_tokens
        if request.schema is not None:
            if self.structured_mode == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema.name,
                        "schema": dict(request.schema.schema),
                        "strict": request.schema.strict,
                    },
                }
            else:
                body["response_format"] = {"type": "json_object"}
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": dict(t.parameters),
                    },
                }
                for t in request.tools
            ]
            if request.tool_choice in ("auto", "none", "required"):
                body["tool_choice"] = request.tool_choice
            elif request.tool_choice:
                body["tool_choice"] = {
                    "type": "function",
                    "function": {"name": request.tool_choice},
                }
        data = await self.post(
            "chat/completions",
            headers=self._headers(),
            json_body=body,
            request_timeout=request.timeout,
        )
        return self._parse_chat(data, request.model)

    async def analyze(self, request: LLMRequest) -> LLMResponse:
        self._unsupported("vision")
        return await self.complete(request)

    def _messages(self, request: LLMRequest) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if request.schema is not None and self.structured_mode == "json_object":
            out.append(
                {
                    "role": "system",
                    "content": "Respond only with a JSON object matching this JSON schema: "
                    + json.dumps(dict(request.schema.schema)),
                }
            )
        for message in request.messages:
            out.append(self._message(message))
        return out

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        if message.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id or "",
                "content": message.text(),
            }
        if message.role == "assistant":
            item: dict[str, Any] = {"role": "assistant", "content": message.text() or None}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in message.tool_calls
                ]
            return item
        if isinstance(message.content, str):
            return {"role": message.role, "content": message.content}
        parts: list[dict[str, Any]] = []
        for part in message.content:
            if isinstance(part, TextPart):
                parts.append({"type": "text", "text": part.text})
            elif isinstance(part, ImagePart):
                encoded = base64.b64encode(part.data).decode()
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{part.mime_type};base64,{encoded}"},
                    }
                )
        return {"role": message.role, "content": parts}

    def _parse_chat(self, data: dict[str, Any], requested_model: str) -> LLMResponse:
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="no_choice") from None
        finish = choice.get("finish_reason") if isinstance(choice, dict) else None
        if finish == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
            raise ProviderError(self.name, ErrorKind.CONTENT_POLICY, code="refusal")
        if not isinstance(message, dict):
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="no_message")
        content = message.get("content")
        text = content if isinstance(content, str) else ""
        calls: list[ToolCall] = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            try:
                function = raw["function"]
                arguments = json.loads(function.get("arguments") or "{}")
                name = function["name"]
            except (KeyError, TypeError, ValueError):
                raise ProviderError(
                    self.name, ErrorKind.INVALID_OUTPUT, code="bad_tool_call"
                ) from None
            if not isinstance(arguments, dict) or not isinstance(name, str):
                raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="bad_tool_call")
            calls.append(
                ToolCall(id=str(raw.get("id") or f"call_{index}"), name=name, arguments=arguments)
            )
        if not text.strip() and not calls:
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="empty")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or requested_model),
            usage=Usage(
                optional_int(usage.get("prompt_tokens")),
                optional_int(usage.get("completion_tokens")),
            ),
            tool_calls=calls,
            finish_reason=finish if isinstance(finish, str) else None,
        )

    # -- embeddings -----------------------------------------------------------------------

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self._unsupported("embed")
        body: dict[str, Any] = {
            "model": request.model,
            "input": list(request.texts),
            "encoding_format": "float",
        }
        if request.dimensions:
            body["dimensions"] = request.dimensions
        data = await self.post(
            "embeddings", headers=self._headers(), json_body=body, request_timeout=request.timeout
        )
        try:
            rows = sorted(data["data"], key=lambda x: x["index"])
            if [r["index"] for r in rows] != list(range(len(request.texts))):
                raise ValueError
            vectors = [[float(v) for v in row["embedding"]] for row in rows]
        except (KeyError, TypeError, ValueError):
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="bad_embedding") from None
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        return EmbeddingResponse(
            vectors=vectors,
            provider=self.name,
            model=request.model,
            usage=Usage(optional_int(usage.get("prompt_tokens")), 0),
        )

    # -- text to speech -------------------------------------------------------------------

    async def synthesize(self, request: SpeechRequest) -> SpeechResponse:
        self._unsupported("speak")
        mime = SPEECH_MIME.get(request.format)
        if mime is None:
            raise ProviderError(self.name, ErrorKind.UNSUPPORTED, code="format")
        body: dict[str, Any] = {
            "model": request.model,
            "input": request.text,
            "voice": request.voice,
            "response_format": request.format,
        }
        if request.instructions and request.model.startswith("gpt-4o"):
            body["instructions"] = (
                request.instructions
            )  # tone, pace and accent (older models refuse it)
        audio = await self.post_bytes(
            "audio/speech",
            headers=self._headers(),
            json_body=body,
            request_timeout=request.timeout,
        )
        return SpeechResponse(
            audio=audio,
            mime_type=mime,
            provider=self.name,
            model=request.model,
            usage=Usage(len(request.text), 0),  # the price of speech follows its characters
        )

    # -- speech to text -------------------------------------------------------------------

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResponse:
        self._unsupported("transcribe")
        extension = AUDIO_EXTENSIONS.get(request.mime_type)
        if extension is None:
            raise ProviderError(self.name, ErrorKind.UNSUPPORTED, code="mime")
        form: dict[str, Any] = {"model": request.model, "response_format": "json"}
        if request.timestamps:
            form["response_format"] = "verbose_json"
            form["timestamp_granularities[]"] = ["word"]
        if request.language:
            form["language"] = request.language
        if request.prompt:
            form["prompt"] = request.prompt
        data = await self.post(
            "audio/transcriptions",
            headers=self._headers(),
            data=form,
            files={"file": (f"audio.{extension}", request.audio, request.mime_type)},
            request_timeout=request.timeout,
        )
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(self.name, ErrorKind.INVALID_OUTPUT, code="empty")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        language = data.get("language")
        return TranscriptionResponse(
            text=text,
            provider=self.name,
            model=request.model,
            usage=Usage(
                optional_int(usage.get("input_tokens")), optional_int(usage.get("output_tokens"))
            ),
            language=language if isinstance(language, str) else None,
            words=_words(data) if request.timestamps else [],
        )


def _words(data: dict[str, Any]) -> list[Word]:
    """The timed words of a verbose transcription; anything malformed is left out."""
    out: list[Word] = []
    for item in data.get("words") or []:
        if not isinstance(item, dict):
            continue
        text, start, end = item.get("word"), item.get("start"), item.get("end")
        if (
            isinstance(text, str)
            and text.strip()
            and isinstance(start, int | float)
            and isinstance(end, int | float)
            and not isinstance(start, bool)
            and not isinstance(end, bool)
        ):
            out.append(Word(text.strip(), float(start), max(float(start), float(end))))
    return out
