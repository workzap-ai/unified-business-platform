"""ToolRegistry: the single, audited entry point for PI tool execution.

Checks, in order: known tool -> conversation in scope -> not under human takeover ->
permission (PI runtime grants and the caller's scope) -> tool enabled for the workspace and
the agent -> product feature -> argument validation -> confirmation presence. The handler
runs inside a savepoint; any refusal or business error rolls its writes back. Every call is
persisted as a PiToolCall when a run is present; mutations are also audited.
"""

import time
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import PiAgent, PiAgentRun, PiAgentTool, PiConversation, PiToolCall
from app.modules.pi.tools.base import (
    PI_RUNTIME_PERMISSIONS,
    ToolContext,
    ToolRefused,
    ToolResult,
    ToolSpec,
)
from app.modules.pi.tools.catalog import TOOL_CATALOG
from app.modules.products.service import enabled_products
from app.shared.errors import BusinessRuleViolation, PermissionDenied, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

SAFE_MESSAGES = {
    "UNKNOWN_TOOL": "This tool is not available",
    "CONVERSATION_NOT_FOUND": "Conversation was not found",
    "HUMAN_TAKEOVER": "A team member is handling this conversation",
    "PERMISSION_DENIED": "PI is not permitted to use this tool",
    "TOOL_DISABLED": "This tool is disabled for this workspace or agent",
    "PI_FEATURE_DISABLED": "This PI feature is not enabled",
    "INVALID_ARGUMENTS": "The tool arguments are invalid",
    "CONFIRMATION_REQUIRED": "This action needs the customer's explicit confirmation",
    "RESOURCE_NOT_FOUND": "The requested record was not found",
}


class ToolRegistry:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def catalog() -> dict[str, ToolSpec]:
        return TOOL_CATALOG

    async def enabled_tools(self, scope: WorkspaceScope, agent_key: str | None) -> frozenset[str]:
        policy = await settings_row(self.session, scope)
        enabled = {
            name for name in TOOL_CATALOG if policy.tool_permissions.get(name, True) is not False
        }
        if agent_key:
            agent = await WorkspaceRepository(self.session, PiAgent, scope).find(
                PiAgent.key == agent_key
            )
            if agent is not None:
                disabled = set(
                    await self.session.scalars(
                        select(PiAgentTool.tool_key).where(
                            WorkspaceRepository(self.session, PiAgentTool, scope).predicate(),
                            PiAgentTool.agent_id == agent.id,
                            PiAgentTool.enabled.is_(False),
                        )
                    )
                )
                enabled -= disabled
        return frozenset(enabled)

    async def execute(
        self,
        scope: WorkspaceScope,
        conversation: PiConversation,
        tool_name: str,
        raw_args: Any,
        confirmation: str | None = None,
        *,
        run: PiAgentRun | None = None,
        agent_key: str = "router",
    ) -> ToolResult:
        started = time.monotonic()
        spec = TOOL_CATALOG.get(tool_name)
        args: dict[str, Any] = {}
        try:
            if spec is None:
                raise ToolRefused("UNKNOWN_TOOL", SAFE_MESSAGES["UNKNOWN_TOOL"], "invalid")
            try:
                current = await WorkspaceRepository(self.session, PiConversation, scope).get(
                    conversation.id
                )
            except ResourceNotFound:
                raise ToolRefused(
                    "CONVERSATION_NOT_FOUND", SAFE_MESSAGES["CONVERSATION_NOT_FOUND"]
                ) from None
            await self.session.refresh(current, ["mode", "status"])
            if current.mode != "ai" or current.status != "open":
                raise ToolRefused("HUMAN_TAKEOVER", SAFE_MESSAGES["HUMAN_TAKEOVER"])
            if spec.permission not in PI_RUNTIME_PERMISSIONS or not scope.can(spec.permission):
                raise ToolRefused("PERMISSION_DENIED", SAFE_MESSAGES["PERMISSION_DENIED"])
            if tool_name not in await self.enabled_tools(scope, agent_key):
                raise ToolRefused("TOOL_DISABLED", SAFE_MESSAGES["TOOL_DISABLED"])
            if spec.feature:
                features = (await enabled_products(self.session, scope)).get("pi", set())
                if spec.feature not in features:
                    raise ToolRefused("PI_FEATURE_DISABLED", SAFE_MESSAGES["PI_FEATURE_DISABLED"])
            try:
                data = spec.input_model.model_validate(raw_args)
            except ValidationError:
                raise ToolRefused(
                    "INVALID_ARGUMENTS", SAFE_MESSAGES["INVALID_ARGUMENTS"], "invalid"
                ) from None
            args = data.model_dump(mode="json")
            if spec.requires_confirmation and not confirmation:
                raise ToolRefused(
                    "CONFIRMATION_REQUIRED",
                    SAFE_MESSAGES["CONFIRMATION_REQUIRED"],
                    "confirmation_required",
                )
            context = ToolContext(self.session, scope, current, run, agent_key, confirmation)
            async with self.session.begin_nested():
                output = await spec.handler(context, data)
            result = ToolResult(
                tool=tool_name,
                ok=True,
                status="success",
                data=spec.output_model.model_validate(output).model_dump(mode="json"),
            )
        except ToolRefused as exc:
            result = ToolResult(
                tool=tool_name,
                ok=False,
                status=exc.status,
                error_code=exc.code,
                message=exc.message,
            )
        except BusinessRuleViolation as exc:
            result = ToolResult(
                tool=tool_name, ok=False, status="error", error_code=exc.code, message=exc.message
            )
        except PermissionDenied:
            result = ToolResult(
                tool=tool_name,
                ok=False,
                status="denied",
                error_code="PERMISSION_DENIED",
                message=SAFE_MESSAGES["PERMISSION_DENIED"],
            )
        except ResourceNotFound:
            result = ToolResult(
                tool=tool_name,
                ok=False,
                status="error",
                error_code="RESOURCE_NOT_FOUND",
                message=SAFE_MESSAGES["RESOURCE_NOT_FOUND"],
            )
        await self._persist(scope, conversation, spec, result, args, run, agent_key, started)
        return result

    async def _persist(
        self,
        scope: WorkspaceScope,
        conversation: PiConversation,
        spec: ToolSpec | None,
        result: ToolResult,
        args: dict[str, Any],
        run: PiAgentRun | None,
        agent_key: str,
        started: float,
    ) -> None:
        if run is not None:
            self.session.add(
                PiToolCall(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    run_id=run.id,
                    agent_key=agent_key,
                    tool_key=result.tool[:60],
                    status=result.status,
                    input=args,
                    output=result.data or {},
                    latency_ms=int((time.monotonic() - started) * 1000),
                    error_code=result.error_code,
                )
            )
        if spec is not None and (spec.mutation or result.status == "denied"):
            await record(
                self.session,
                f"pi.tool.{spec.name}",
                scope=scope,
                entity_type="pi_conversation",
                entity_id=conversation.id,
                outcome="success"
                if result.ok
                else "denied"
                if result.status == "denied"
                else "failure",
                details={"status": result.status, "error_code": result.error_code},
            )
        await self.session.flush()
