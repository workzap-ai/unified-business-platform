from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Scope, Session
from app.shared.errors import PermissionDenied
from app.workflows.models import WorkflowRun
from app.workflows.service import WorkflowService
from app.workflows.tools import TOOLS, ToolContext

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=120)


class WorkflowView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tool_key: str
    action_class: str
    status: str
    result: dict[str, Any]
    error_code: str | None
    expires_at: datetime
    created_at: datetime
    arguments: dict[str, Any]


@router.get("/tools")
async def definitions(scope: Scope) -> list[dict[str, Any]]:
    return [
        {
            "key": t.key,
            "permission": t.permission,
            "action_class": t.action_class,
            "approval_required": t.approval_required,
            "input_schema": t.schema.model_json_schema(),
        }
        for t in TOOLS.values()
        if t.available(scope)
    ]


@router.get("", response_model=Page[WorkflowView])
async def history(
    scope: Scope,
    session: Session,
    pagination: Annotated[Pagination, Depends()],
    status: Annotated[
        Literal["pending_approval", "completed", "failed", "rejected"] | None, Query()
    ] = None,
) -> Page[WorkflowView]:
    service = WorkflowService(ToolContext(session, scope))
    statement = service.runs.select().where(
        WorkflowRun.requested_by == scope.user_id,
        WorkflowRun.tool_key.in_([t.key for t in TOOLS.values() if t.available(scope)]),
    )
    if status:
        statement = statement.where(WorkflowRun.status == status)
    rows, total = await service.runs.page(
        statement.order_by(WorkflowRun.created_at.desc(), WorkflowRun.id), pagination
    )
    return Page(
        items=[WorkflowView.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=WorkflowView)
async def start(data: WorkflowInput, scope: Scope, session: Session) -> WorkflowView:
    run = await WorkflowService(ToolContext(session, scope)).start(
        data.tool, data.arguments, data.idempotency_key
    )
    await session.commit()
    return WorkflowView.model_validate(run)


@router.post("/{run_id}/approve", response_model=WorkflowView)
async def approve(run_id: UUID, scope: Scope, session: Session) -> WorkflowView:
    run = await WorkflowService(ToolContext(session, scope)).approve(run_id)
    await session.commit()
    return WorkflowView.model_validate(run)


@router.get("/{run_id}", response_model=WorkflowView)
async def get(run_id: UUID, scope: Scope, session: Session) -> WorkflowView:
    service = WorkflowService(ToolContext(session, scope))
    run = await service.runs.get(run_id)
    service.tool(run.tool_key)
    if run.requested_by is not None and run.requested_by != scope.user_id:
        raise PermissionDenied
    return WorkflowView.model_validate(run)


@router.post("/{run_id}/reject", response_model=WorkflowView)
async def reject(run_id: UUID, scope: Scope, session: Session) -> WorkflowView:
    run = await WorkflowService(ToolContext(session, scope)).reject(run_id)
    await session.commit()
    return WorkflowView.model_validate(run)
