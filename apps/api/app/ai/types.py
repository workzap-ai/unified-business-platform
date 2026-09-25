"""Provider-neutral request/response types for the AI gateway."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

Role = Literal["system", "user", "assistant", "tool"]
ToolChoice = Literal["auto", "none", "required"] | str  # a tool name forces that tool


class Attempt(BaseModel):
    """One provider attempt. Fields are a strict subset of ai_usage_events columns
    (callers may splat ``model_dump()`` into AIUsageEvent), so never add others."""

    provider: str
    model: str
    status: str  # success | failed
    error_kind: str | None = None
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempt: int
    fallback: bool
    estimated_cost: Decimal | None = None


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str


@dataclass(frozen=True, slots=True)
class ImagePart:
    """Inline image bytes (validated by app.ai.media before any provider call)."""

    data: bytes
    mime_type: str

    def __repr__(self) -> str:  # never dump raw bytes into logs or reprs
        return f"ImagePart(mime_type={self.mime_type!r}, bytes={len(self.data)})"


ContentPart = TextPart | ImagePart


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str | Sequence[ContentPart] = ""
    name: str | None = None  # tool name for role="tool"
    tool_call_id: str | None = None  # for role="tool"
    tool_calls: Sequence[ToolCall] = ()  # for role="assistant"

    @classmethod
    def system(cls, text: str) -> Message:
        return cls("system", text)

    @classmethod
    def user(cls, content: str | Sequence[ContentPart]) -> Message:
        return cls("user", content)

    @classmethod
    def assistant(cls, text: str = "", tool_calls: Sequence[ToolCall] = ()) -> Message:
        return cls("assistant", text, tool_calls=tool_calls)

    @classmethod
    def tool(cls, tool_call_id: str, name: str, result: Any) -> Message:
        body = result if isinstance(result, str) else json.dumps(result, default=str)
        return cls("tool", body, name=name, tool_call_id=tool_call_id)

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "".join(p.text for p in self.content if isinstance(p, TextPart))

    def parts(self) -> list[ContentPart]:
        if isinstance(self.content, str):
            return [TextPart(self.content)] if self.content else []
        return list(self.content)

    def images(self) -> list[ImagePart]:
        return [p for p in self.parts() if isinstance(p, ImagePart)]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: Mapping[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )


@dataclass(frozen=True, slots=True)
class OutputSchema:
    """JSON-schema structured output request."""

    name: str
    schema: Mapping[str, Any]
    strict: bool = False
    model: type[BaseModel] | None = None  # validated after parsing when present

    @classmethod
    def of(
        cls, schema: type[BaseModel] | Mapping[str, Any], name: str = "response"
    ) -> OutputSchema:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return cls(name=name, schema=schema.model_json_schema(), model=schema)
        return cls(name=name, schema=dict(schema))


@dataclass(frozen=True, slots=True)
class LLMRequest:
    model: str
    messages: Sequence[Message]
    schema: OutputSchema | None = None
    tools: Sequence[ToolDefinition] = ()
    tool_choice: ToolChoice | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float = 20.0


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    parsed: Any = None  # JSON value when a schema was requested
    output: BaseModel | None = None  # validated model when OutputSchema.model was given
    alias: str = ""
    fallback_used: bool = False
    attempts: list[Attempt] = field(default_factory=list)

    def parse_as[M: BaseModel](self, model: type[M]) -> M:
        if isinstance(self.output, model):
            return self.output
        if self.parsed is not None:
            return model.model_validate(self.parsed)
        return model.model_validate_json(self.text)


@dataclass(frozen=True, slots=True)
class EmbeddingRequest:
    model: str
    texts: Sequence[str]
    timeout: float = 20.0
    dimensions: int | None = None


@dataclass(slots=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    attempts: list[Attempt] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    model: str
    audio: bytes
    mime_type: str
    language: str | None = None
    prompt: str | None = None
    timeout: float = 20.0

    def __repr__(self) -> str:
        return (
            f"TranscriptionRequest(model={self.model!r}, mime_type={self.mime_type!r}, "
            f"bytes={len(self.audio)})"
        )


@dataclass(slots=True)
class TranscriptionResponse:
    text: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    language: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
