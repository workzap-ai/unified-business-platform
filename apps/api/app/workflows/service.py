import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text

from app.modules.audit.service import record
from app.modules.notifications.service import notify
from app.shared.errors import BusinessRuleViolation, PermissionDenied, ResourceNotFound
from app.shared.workspace_repository import WorkspaceRepository
from app.workflows.models import WorkflowRun
from app.workflows.tools import TOOLS, Tool, ToolContext


class WorkflowService:
    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self.runs = WorkspaceRepository(context.session, WorkflowRun, context.scope)

    def tool(self, key: str) -> Tool:
        tool = TOOLS.get(key)
        if tool is None:
            raise BusinessRuleViolation("UNKNOWN_TOOL", "This workflow is unavailable")
        for permission in (tool.permission, *tool.additional_permissions):
            self.context.scope.require(permission)
        if self.context.allowed_tools is not None and key not in self.context.allowed_tools:
            raise PermissionDenied
        if self.context.customer_id is not None and not tool.customer_safe:
            raise PermissionDenied
        return tool

    async def start(self, key: str, arguments: dict[str, Any], idempotency_key: str) -> WorkflowRun:
        tool = self.tool(key)
        try:
            data = tool.schema.model_validate(arguments)
        except ValidationError:
            raise BusinessRuleViolation(
                "INVALID_TOOL_INPUT", "The workflow input is invalid"
            ) from None
        normalized = data.model_dump(mode="json")
        lock = hashlib.sha256(
            f"{self.context.scope.tenant_id}:{self.context.scope.environment_id}:{idempotency_key}".encode()
        ).digest()[:8]
        await self.context.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int.from_bytes(lock, "big", signed=True)},
        )
        existing = await self.runs.find(WorkflowRun.idempotency_key == idempotency_key)
        if existing:
            if (
                existing.tool_key != key
                or existing.arguments != normalized
                or existing.customer_id != self.context.customer_id
                or existing.requested_by != self.context.scope.user_id
            ):
                raise BusinessRuleViolation(
                    "IDEMPOTENCY_CONFLICT", "This request key has already been used", 409
                )
            return existing
        run = await self.runs.add(
            self.runs.new(
                tool_key=key,
                action_class=tool.action_class,
                status="pending_approval",
                idempotency_key=idempotency_key,
                requested_by=self.context.scope.user_id,
                customer_id=self.context.customer_id,
                arguments=normalized,
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
        )
        if not tool.approval_required:
            await self._execute(run, tool)
        elif tool.preview:
            run.result = await tool.preview(self.context, data)
            action = key.split(".", 1)[1]
            expected_action = "convert_to_order" if action == "convert" else action
            if expected_action not in run.result.get("next_actions", []):
                raise BusinessRuleViolation(
                    "INVALID_TRANSITION", "This action is not available for the current record"
                )
        if tool.approval_required and run.requested_by is not None:
            await notify(
                self.context.session,
                self.context.scope,
                "workflow.approval",
                "A workflow is ready for review",
                key.replace(".", " "),
                link=f"/workflows?run={run.id}",
                recipient_user_id=run.requested_by,
                dedupe_key=f"workflow:{run.id}:proposed",
            )
        await record(
            self.context.session,
            "workflow.proposed",
            scope=self.context.scope,
            entity_type="workflow",
            entity_id=run.id,
            details={"tool": key, "class": tool.action_class, "status": run.status},
        )
        return run

    async def approve(self, run_id: UUID) -> WorkflowRun:
        if self.context.scope.user_id is None:
            raise PermissionDenied
        run = await self.runs.get(run_id, for_update=True)
        tool = self.tool(run.tool_key)
        if run.requested_by != self.context.scope.user_id:
            # Customer proposals must go through PI's delivered-summary confirmation.
            raise PermissionDenied
        if run.status == "completed":
            return run
        if run.status != "pending_approval" or run.expires_at <= datetime.now(UTC):
            raise BusinessRuleViolation("APPROVAL_EXPIRED", "This proposal is no longer actionable")
        if tool.preview:
            current = await tool.preview(self.context, tool.schema.model_validate(run.arguments))
            if current != run.result:
                raise BusinessRuleViolation(
                    "PROPOSAL_CHANGED",
                    "The record changed. Reject this proposal and request a fresh review.",
                    409,
                )
        run.approved_by = self.context.scope.user_id
        await self._execute(run, tool)
        await record(
            self.context.session,
            "workflow.approved",
            scope=self.context.scope,
            entity_type="workflow",
            entity_id=run.id,
            details={"tool": tool.key, "status": run.status},
        )
        return run

    async def reject(self, run_id: UUID) -> WorkflowRun:
        run = await self.runs.get(run_id, for_update=True)
        self.tool(run.tool_key)
        if run.requested_by != self.context.scope.user_id or self.context.scope.user_id is None:
            raise PermissionDenied
        if run.status == "rejected":
            return run
        if run.status != "pending_approval":
            raise BusinessRuleViolation(
                "WORKFLOW_FINISHED", "Only pending proposals can be rejected"
            )
        run.status = "rejected"
        await record(
            self.context.session,
            "workflow.rejected",
            scope=self.context.scope,
            entity_type="workflow",
            entity_id=run.id,
            details={"tool": run.tool_key},
        )
        return run

    async def _execute(self, run: WorkflowRun, tool: Tool) -> None:
        self.context.scope.require(tool.permission)
        try:
            async with self.context.session.begin_nested():
                context = ToolContext(self.context.session, self.context.scope, run.customer_id)
                result = await tool.handler(context, tool.schema.model_validate(run.arguments))
                # Persist JSON-safe outputs only. Neither prompts nor credentials are audit details.
                run.result = json.loads(json.dumps(result))
                run.status = "completed"
                await self.context.session.flush()
        except (BusinessRuleViolation, PermissionDenied, ResourceNotFound) as exc:
            run.status = "failed"
            run.error_code = (
                exc.code
                if isinstance(exc, BusinessRuleViolation)
                else "RESOURCE_NOT_FOUND"
                if isinstance(exc, ResourceNotFound)
                else "PERMISSION_DENIED"
            )
        await record(
            self.context.session,
            "workflow.executed",
            scope=self.context.scope,
            entity_type="workflow",
            entity_id=run.id,
            details={"tool": tool.key, "status": run.status},
        )

    async def execute_customer_confirmation(self, run: WorkflowRun, message_id: UUID) -> None:
        # Internal entrypoint after PI verifies summary delivery, snapshot and identity.
        if (
            self.context.scope.user_id is not None
            or self.context.customer_id is None
            or run.customer_id != self.context.customer_id
            or run.status != "pending_approval"
            or run.expires_at <= datetime.now(UTC)
            or run.tool_key != "orders.confirm"
        ):
            raise PermissionDenied
        await self._execute(run, self.tool(run.tool_key))
        await record(
            self.context.session,
            "workflow.customer_confirmed",
            scope=self.context.scope,
            entity_type="workflow",
            entity_id=run.id,
            details={"message_id": str(message_id), "status": run.status},
        )
