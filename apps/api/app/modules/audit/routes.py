from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.audit.models import AuditEvent
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/audit", tags=["audit"])
Read = Annotated[WorkspaceScope, Depends(require("audit.read"))]
Paging = Annotated[Pagination, Query()]


class AuditView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_type: str
    actor_label: str
    action: str
    entity_type: str | None
    entity_id: UUID | None
    outcome: str
    request_id: str | None
    environment_id: UUID | None
    details: dict[str, Any]
    created_at: datetime


@router.get("/events", response_model=Page[AuditView])
async def events(
    scope: Read,
    session: Session,
    pagination: Paging,
    action: Annotated[str | None, Query(max_length=80)] = None,
    entity_type: Annotated[str | None, Query(max_length=60)] = None,
    entity_id: UUID | None = None,
    outcome: Annotated[str | None, Query(pattern="^(success|denied|failure)$")] = None,
) -> Page[AuditView]:
    # Tenant events for the current environment plus tenant-wide (environment-less) events.
    statement = select(AuditEvent).where(
        AuditEvent.tenant_id == scope.tenant_id,
        or_(
            AuditEvent.environment_id == scope.environment_id,
            AuditEvent.environment_id.is_(None),
        ),
    )
    if action:
        statement = statement.where(AuditEvent.action.startswith(action, autoescape=True))
    if entity_type:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditEvent.entity_id == entity_id)
    if outcome:
        statement = statement.where(AuditEvent.outcome == outcome)
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = await session.scalars(
        statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    return Page(
        items=[AuditView.model_validate(r) for r in rows],
        total=int(total or 0),
        page=pagination.page,
        page_size=pagination.page_size,
    )
