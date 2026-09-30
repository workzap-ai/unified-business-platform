"""Native bookings, tasks and support tickets (the bounded domains PI can act on).

Bookings: availability comes from each bookable service's working hours (in the
business timezone), duration and buffer, minus existing active bookings. Creation takes
a transaction advisory lock per service and re-checks the slot inside it, so two
concurrent requests for one slot cannot both succeed; an idempotency key per customer
message makes retries return the same booking. External calendars are applied by the
callers: busy times arrive as `busy` intervals, and a calendar-linked booking is marked
`external_sync="pending"` for the after-commit sync (app.modules.pi_saas.calendar_sync).
"""

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi.policy import zone
from app.modules.pi_saas.models import PiBookableService, PiBooking, PiTask, PiTicket
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ACTIVE = ("pending", "confirmed")
MIN_NOTICE = timedelta(hours=1)
RESPONSE_TARGET = {
    "urgent": timedelta(hours=1),
    "high": timedelta(hours=4),
    "normal": timedelta(hours=24),
    "low": timedelta(hours=72),
}


def validate_hours(hours: dict[str, Any]) -> dict[str, list[list[str]]]:
    """{"mon": [["09:00","17:00"]], ...}; ranges must be ordered and not overlap."""
    clean: dict[str, list[list[str]]] = {}
    for day, ranges in hours.items():
        if day not in DAY_KEYS or not isinstance(ranges, list) or len(ranges) > 4:
            raise BusinessRuleViolation("INVALID_HOURS", "Invalid working hours")
        parsed = []
        for item in ranges:
            try:
                start, end = time.fromisoformat(item[0]), time.fromisoformat(item[1])
            except (TypeError, ValueError, IndexError):
                raise BusinessRuleViolation("INVALID_HOURS", "Invalid working hours") from None
            if start >= end:
                raise BusinessRuleViolation("INVALID_HOURS", "A day must end after it starts")
            parsed.append((start, end))
        parsed.sort()
        if any(a[1] > b[0] for a, b in zip(parsed, parsed[1:], strict=False)):
            raise BusinessRuleViolation("INVALID_HOURS", "Working hours overlap")
        clean[day] = [[s.strftime("%H:%M"), e.strftime("%H:%M")] for s, e in parsed]
    return clean


def label(at: datetime, timezone: str) -> str:
    local = at.astimezone(zone(timezone))
    return local.strftime("%a %d %b, %H:%M")


async def _lock(session: AsyncSession, scope: WorkspaceScope, service_id: UUID) -> None:
    key = int.from_bytes(
        hashlib.sha256(
            f"booking:{scope.tenant_id}:{scope.environment_id}:{service_id}".encode()
        ).digest()[:8],
        "big",
        signed=True,
    )
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _overlaps(busy: Sequence[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    return any(s < end and e > start for s, e in busy)


async def _existing(
    session: AsyncSession, scope: WorkspaceScope, service_id: UUID, start: datetime, end: datetime
) -> list[PiBooking]:
    return list(
        await session.scalars(
            WorkspaceRepository(session, PiBooking, scope)
            .select()
            .where(
                PiBooking.service_id == service_id,
                PiBooking.status.in_(ACTIVE),
                PiBooking.starts_at < end,
                PiBooking.ends_at > start,
            )
        )
    )


def _windows(
    service: PiBookableService, day: date, timezone: str
) -> list[tuple[datetime, datetime]]:
    tz = zone(timezone)
    key = DAY_KEYS[day.weekday()]
    return [
        (
            datetime.combine(day, time.fromisoformat(a), tz).astimezone(UTC),
            datetime.combine(day, time.fromisoformat(b), tz).astimezone(UTC),
        )
        for a, b in service.working_hours.get(key, [])
    ]


async def available_slots(
    session: AsyncSession,
    scope: WorkspaceScope,
    service: PiBookableService,
    timezone: str,
    *,
    days: int = 7,
    limit: int = 12,
    now: datetime | None = None,
    busy: Sequence[tuple[datetime, datetime]] = (),
) -> list[dict[str, str]]:
    now = now or datetime.now(UTC)
    duration = timedelta(minutes=service.duration_minutes)
    buffer = timedelta(minutes=service.buffer_minutes)
    horizon = now + timedelta(days=days + 1)
    taken = [
        (b.starts_at, b.ends_at) for b in await _existing(session, scope, service.id, now, horizon)
    ] + list(busy)
    slots: list[dict[str, str]] = []
    today = now.astimezone(zone(timezone)).date()
    for offset in range(days + 1):
        for start, end in _windows(service, today + timedelta(days=offset), timezone):
            cursor = start
            while cursor + duration <= end and len(slots) < limit:
                slot_end = cursor + duration
                clash = any(s < slot_end + buffer and e + buffer > cursor for s, e in taken)
                if cursor >= now + MIN_NOTICE and not clash:
                    slots.append({"start": cursor.isoformat(), "label": label(cursor, timezone)})
                cursor = slot_end + buffer
    return slots


async def book(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    service_id: UUID,
    customer_id: UUID,
    conversation_id: UUID | None,
    starts_at: datetime,
    timezone: str,
    idempotency_key: str,
    notes: str = "",
    busy: Sequence[tuple[datetime, datetime]] = (),
    calendar: bool = False,
) -> PiBooking:
    """`busy`: external calendar busy times re-read just before booking; `calendar`:
    the service has a linked calendar, so the booking is queued for event sync."""
    scope.require("pi.bookings.manage")
    repo = WorkspaceRepository(session, PiBooking, scope)
    await _lock(session, scope, service_id)
    existing = await repo.find(PiBooking.idempotency_key == idempotency_key[:200])
    if existing is not None:
        return existing  # A retry of the same request: never a second booking.
    service = await WorkspaceRepository(session, PiBookableService, scope).get(service_id)
    if service.status != "active":
        raise BusinessRuleViolation("SERVICE_UNAVAILABLE", "This service can't be booked")
    starts_at = starts_at.astimezone(UTC)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    buffer = timedelta(minutes=service.buffer_minutes)
    if starts_at < datetime.now(UTC) + MIN_NOTICE:
        raise BusinessRuleViolation("SLOT_UNAVAILABLE", "That time is too soon", 409)
    inside = any(
        start <= starts_at and ends_at <= end
        for start, end in _windows(service, starts_at.astimezone(zone(timezone)).date(), timezone)
    )
    if (
        not inside
        or _overlaps(busy, starts_at - buffer, ends_at + buffer)
        or await _existing(session, scope, service.id, starts_at - buffer, ends_at + buffer)
    ):
        raise BusinessRuleViolation("SLOT_UNAVAILABLE", "That time is no longer available", 409)
    booking = await repo.add(
        repo.new(
            service_id=service.id,
            customer_id=customer_id,
            conversation_id=conversation_id,
            starts_at=starts_at,
            ends_at=ends_at,
            timezone=timezone,
            status="confirmed",
            notes=notes[:2000],
            idempotency_key=idempotency_key[:200],
            created_by_label=scope.actor_label,
            external_sync="pending" if calendar else "none",
        )
    )
    await record(
        session, "pi.booking_created", scope=scope, entity_type="pi_booking", entity_id=booking.id
    )
    return booking


async def cancel_booking(
    session: AsyncSession, scope: WorkspaceScope, booking_id: UUID, customer_id: UUID | None
) -> PiBooking:
    scope.require("pi.bookings.manage")
    booking = await WorkspaceRepository(session, PiBooking, scope).get(booking_id, for_update=True)
    if customer_id is not None and booking.customer_id != customer_id:
        raise ResourceNotFound  # Customers can only cancel their own bookings.
    if booking.status in ACTIVE:
        booking.status = "cancelled"
        if booking.external_event_id or booking.external_sync != "none":
            booking.external_sync = "pending"  # Remove the calendar event after commit.
        await record(
            session,
            "pi.booking_cancelled",
            scope=scope,
            entity_type="pi_booking",
            entity_id=booking.id,
        )
    return booking


async def reschedule(
    session: AsyncSession,
    scope: WorkspaceScope,
    booking_id: UUID,
    customer_id: UUID | None,
    starts_at: datetime,
    timezone: str,
    *,
    busy: Sequence[tuple[datetime, datetime]] = (),
    calendar: bool = False,
) -> PiBooking:
    """Move an active booking to a new free time (same checks as booking, excluding the
    booking itself). Repeating the same move is a no-op."""
    scope.require("pi.bookings.manage")
    current = await WorkspaceRepository(session, PiBooking, scope).get(booking_id)
    if customer_id is not None and current.customer_id != customer_id:
        raise ResourceNotFound  # Customers can only move their own bookings.
    await _lock(session, scope, current.service_id)
    booking = await WorkspaceRepository(session, PiBooking, scope).get(booking_id, for_update=True)
    if booking.status not in ACTIVE:
        raise BusinessRuleViolation("BOOKING_NOT_ACTIVE", "This booking can't be changed", 409)
    starts_at = starts_at.astimezone(UTC)
    if starts_at == booking.starts_at:
        return booking
    service = await WorkspaceRepository(session, PiBookableService, scope).get(booking.service_id)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    buffer = timedelta(minutes=service.buffer_minutes)
    if starts_at < datetime.now(UTC) + MIN_NOTICE:
        raise BusinessRuleViolation("SLOT_UNAVAILABLE", "That time is too soon", 409)
    inside = any(
        start <= starts_at and ends_at <= end
        for start, end in _windows(service, starts_at.astimezone(zone(timezone)).date(), timezone)
    )
    others = [
        b
        for b in await _existing(session, scope, service.id, starts_at - buffer, ends_at + buffer)
        if b.id != booking.id
    ]
    if not inside or others or _overlaps(busy, starts_at - buffer, ends_at + buffer):
        raise BusinessRuleViolation("SLOT_UNAVAILABLE", "That time is no longer available", 409)
    booking.starts_at, booking.ends_at, booking.timezone = starts_at, ends_at, timezone
    if calendar or booking.external_event_id:
        booking.external_sync = "pending"
    await record(
        session,
        "pi.booking_rescheduled",
        scope=scope,
        entity_type="pi_booking",
        entity_id=booking.id,
    )
    return booking


async def create_task(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    title: str,
    description: str,
    customer_id: UUID | None,
    conversation_id: UUID | None,
    idempotency_key: str | None,
    assignee_user_id: UUID | None = None,
    due_at: datetime | None = None,
    priority: str = "normal",
) -> PiTask:
    scope.require("pi.work.manage")
    repo = WorkspaceRepository(session, PiTask, scope)
    if idempotency_key:
        existing = await repo.find(PiTask.idempotency_key == idempotency_key[:200])
        if existing is not None:
            return existing
    task = await repo.add(
        repo.new(
            title=title[:200],
            description=description[:8000],
            customer_id=customer_id,
            conversation_id=conversation_id,
            assignee_user_id=assignee_user_id,
            created_by_user_id=scope.user_id,
            created_by_label=scope.actor_label,
            priority=priority if priority in RESPONSE_TARGET else "normal",
            due_at=due_at,
            idempotency_key=idempotency_key[:200] if idempotency_key else None,
        )
    )
    await record(session, "pi.task_created", scope=scope, entity_type="pi_task", entity_id=task.id)
    return task


async def create_ticket(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    subject: str,
    summary: str,
    customer_id: UUID,
    conversation_id: UUID | None,
    priority: str,
    idempotency_key: str | None,
) -> PiTicket:
    scope.require("pi.work.manage")
    repo = WorkspaceRepository(session, PiTicket, scope)
    if idempotency_key:
        existing = await repo.find(PiTicket.idempotency_key == idempotency_key[:200])
        if existing is not None:
            return existing
    priority = priority if priority in RESPONSE_TARGET else "normal"
    ticket = await repo.add(
        repo.new(
            subject=subject[:200],
            summary=summary[:8000],
            customer_id=customer_id,
            conversation_id=conversation_id,
            priority=priority,
            first_response_due_at=datetime.now(UTC) + RESPONSE_TARGET[priority],
            idempotency_key=idempotency_key[:200] if idempotency_key else None,
        )
    )
    await record(
        session, "pi.ticket_created", scope=scope, entity_type="pi_ticket", entity_id=ticket.id
    )
    return ticket
