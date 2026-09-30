"""Staff API for bookable services, bookings, tasks and support tickets (/pi/...).

Mounted for both the Owner OS workspace and the Pi app. Reads need the matching
``.read`` permission and changes the ``.manage`` one; every record is environment
scoped, and customer-facing tools only ever reach the current customer's records.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.service import require_pi
from app.modules.pi_saas import work
from app.modules.pi_saas.models import PiBookableService, PiBooking, PiTask, PiTicket
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-work"])


class ServiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    duration_minutes: int = Field(default=30, ge=5, le=720)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    working_hours: dict[str, list[list[str]]] = Field(default_factory=dict)


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    duration_minutes: int | None = Field(default=None, ge=5, le=720)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    working_hours: dict[str, list[list[str]]] | None = None
    status: Literal["active", "archived"] | None = None


def _service(row: PiBookableService) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "duration_minutes": row.duration_minutes,
        "buffer_minutes": row.buffer_minutes,
        "working_hours": row.working_hours,
        "status": row.status,
    }


@router.get("/bookable-services")
async def services(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await require_pi(session, scope, "pi.bookings.read")
    rows = await session.scalars(
        WorkspaceRepository(session, PiBookableService, scope)
        .select()
        .order_by(PiBookableService.name)
        .limit(100)
    )
    return [_service(r) for r in rows]


@router.post("/bookable-services", status_code=201)
async def add_service(data: ServiceInput, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.bookings.manage")
    repo = WorkspaceRepository(session, PiBookableService, scope)
    row = await repo.add(
        repo.new(
            name=data.name,
            duration_minutes=data.duration_minutes,
            buffer_minutes=data.buffer_minutes,
            working_hours=work.validate_hours(data.working_hours),
        )
    )
    await record(
        session,
        "pi.bookable_service_created",
        scope=scope,
        entity_type="pi_bookable_service",
        entity_id=row.id,
    )
    await session.commit()
    return _service(row)


@router.patch("/bookable-services/{service_id}")
async def edit_service(
    service_id: UUID, data: ServiceUpdate, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.bookings.manage")
    row = await WorkspaceRepository(session, PiBookableService, scope).get(
        service_id, for_update=True
    )
    values = data.model_dump(exclude_unset=True)
    if "working_hours" in values and values["working_hours"] is not None:
        values["working_hours"] = work.validate_hours(values["working_hours"])
    for field, value in values.items():
        if value is not None:
            setattr(row, field, value)
    await session.commit()
    return _service(row)


@router.get("/bookable-services/{service_id}/availability")
async def availability(
    service_id: UUID,
    request: Request,
    scope: Scope,
    session: Session,
    days: int = Query(7, ge=1, le=21),
) -> dict[str, Any]:
    from app.modules.pi_saas import calendar_sync

    await require_pi(session, scope, "pi.bookings.read")
    row = await WorkspaceRepository(session, PiBookableService, scope).get(service_id)
    policy = await settings_row(session, scope)
    now = datetime.now(UTC)
    # Busy times from the connected Google Calendar (refused if it can't be read).
    busy, linked = await calendar_sync.busy(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        row,
        now,
        now + timedelta(days=days + 1),
    )
    slots = await work.available_slots(
        session, scope, row, policy.timezone, days=days, limit=40, busy=busy
    )
    await session.commit()  # Keeps recorded calendar health/token refresh.
    return {"timezone": policy.timezone, "calendar": linked, "slots": slots}


def _booking(row: PiBooking) -> dict[str, Any]:
    return {
        "id": row.id,
        "service_id": row.service_id,
        "customer_id": row.customer_id,
        "conversation_id": row.conversation_id,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "label": work.label(row.starts_at, row.timezone),
        "timezone": row.timezone,
        "status": row.status,
        "created_by": row.created_by_label,
        "external_sync": row.external_sync,
    }


@router.get("/bookings")
async def bookings(
    scope: Scope, session: Session, upcoming: bool = True, limit: int = Query(50, ge=1, le=200)
) -> list[dict[str, Any]]:
    await require_pi(session, scope, "pi.bookings.read")
    query = WorkspaceRepository(session, PiBooking, scope).select()
    if upcoming:
        query = query.where(
            PiBooking.starts_at >= datetime.now(UTC) - timedelta(hours=1),
            PiBooking.status.in_(work.ACTIVE),
        ).order_by(PiBooking.starts_at)
    else:
        query = query.order_by(PiBooking.starts_at.desc())
    return [_booking(r) for r in await session.scalars(query.limit(limit))]


@router.post("/bookings/{booking_id}/cancel")
async def cancel(booking_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.bookings.manage")
    row = await work.cancel_booking(session, scope, booking_id, None)
    await session.commit()
    return _booking(row)


def _task(row: PiTask) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "customer_id": row.customer_id,
        "conversation_id": row.conversation_id,
        "status": row.status,
        "priority": row.priority,
        "due_at": row.due_at,
        "assignee_user_id": row.assignee_user_id,
        "customer_visible_status": row.customer_visible_status,
        "created_by": row.created_by_label,
        "created_at": row.created_at,
    }


@router.get("/tasks")
async def tasks(
    scope: Scope, session: Session, status: str | None = Query(None, max_length=16)
) -> list[dict[str, Any]]:
    await require_pi(session, scope, "pi.work.read")
    query = WorkspaceRepository(session, PiTask, scope).select()
    if status:
        query = query.where(PiTask.status == status)
    rows = await session.scalars(query.order_by(PiTask.created_at.desc()).limit(200))
    return [_task(r) for r in rows]


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["open", "in_progress", "blocked", "done", "cancelled"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assignee_user_id: UUID | None = None
    customer_visible_status: str | None = Field(default=None, max_length=300)


@router.patch("/tasks/{task_id}")
async def edit_task(
    task_id: UUID, data: TaskUpdate, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    row = await WorkspaceRepository(session, PiTask, scope).get(task_id, for_update=True)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await record(session, "pi.task_updated", scope=scope, entity_type="pi_task", entity_id=row.id)
    await session.commit()
    return _task(row)


def _ticket(row: PiTicket) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": row.id,
        "subject": row.subject,
        "summary": row.summary,
        "customer_id": row.customer_id,
        "conversation_id": row.conversation_id,
        "status": row.status,
        "priority": row.priority,
        "team": row.team,
        "first_response_due_at": row.first_response_due_at,
        "first_responded_at": row.first_responded_at,
        "overdue": row.first_responded_at is None
        and row.first_response_due_at is not None
        and row.first_response_due_at < now
        and row.status in {"open", "pending_customer"},
        "created_at": row.created_at,
    }


@router.get("/tickets")
async def tickets(
    scope: Scope, session: Session, status: str | None = Query(None, max_length=20)
) -> list[dict[str, Any]]:
    await require_pi(session, scope, "pi.work.read")
    query = WorkspaceRepository(session, PiTicket, scope).select()
    if status:
        query = query.where(PiTicket.status == status)
    rows = await session.scalars(query.order_by(PiTicket.created_at.desc()).limit(200))
    return [_ticket(r) for r in rows]


class TicketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "pending_customer", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    responded: bool | None = None


@router.patch("/tickets/{ticket_id}")
async def edit_ticket(
    ticket_id: UUID, data: TicketUpdate, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    row = await WorkspaceRepository(session, PiTicket, scope).get(ticket_id, for_update=True)
    if data.status:
        row.status = data.status
        if data.status in {"resolved", "closed"}:
            row.resolved_at = row.resolved_at or datetime.now(UTC)
    if data.priority:
        row.priority = data.priority
    if data.responded and row.first_responded_at is None:
        row.first_responded_at = datetime.now(UTC)
    await record(
        session, "pi.ticket_updated", scope=scope, entity_type="pi_ticket", entity_id=row.id
    )
    await session.commit()
    return _ticket(row)
