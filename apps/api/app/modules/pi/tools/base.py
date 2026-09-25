"""Shared types for PI controlled tools.

A tool is a typed, tenant-scoped function over existing business services. Language model
output can only *select* a tool and supply arguments; every argument is validated, every
record is re-read under the trusted scope, and the conversation's customer binds identity.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.permissions import PI_SYSTEM_PERMISSIONS
from app.modules.pi.models import PiAgentRun, PiConversation
from app.shared.scope import WorkspaceScope

# PI's system actor grants (access/permissions.py) plus the PI-internal grants the
# runtime needs to queue replies, open handoffs and read memory for the bound customer.
PI_RUNTIME_PERMISSIONS = PI_SYSTEM_PERMISSIONS | frozenset(
    {"pi.inbox.reply", "pi.handoffs.manage", "pi.memory.read"}
)

ToolStatus = Literal["success", "denied", "invalid", "error", "confirmation_required"]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolRefused(Exception):
    """A business-safe refusal. ``code`` is stable; ``message`` is safe for operators."""

    def __init__(self, code: str, message: str, status: ToolStatus = "denied") -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    scope: WorkspaceScope
    conversation: PiConversation
    run: PiAgentRun | None
    agent_key: str
    confirmation: str | None = None


Handler = Callable[[ToolContext, Any], Awaitable[ToolOutput]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[ToolInput]
    output_model: type[ToolOutput]
    handler: Handler
    permission: str
    mutation: bool = False
    requires_confirmation: bool = False
    feature: str | None = None

    @property
    def capability(self) -> Literal["read", "draft", "mutation", "communication"]:
        if self.name == "send_whatsapp_message":
            return "communication"
        if self.name.endswith("_draft"):
            return "draft"
        return "mutation" if self.mutation else "read"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "mutation": self.mutation,
            "requires_confirmation": self.requires_confirmation,
            "permission": self.permission,
            "feature": self.feature,
        }


class ToolResult(BaseModel):
    """Typed outcome returned to the runtime. Errors never carry internal details."""

    tool: str
    ok: bool
    status: ToolStatus
    data: dict[str, Any] | None = None
    error_code: str | None = None
    message: str = ""
