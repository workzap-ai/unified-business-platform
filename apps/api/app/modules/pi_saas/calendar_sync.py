"""Google Calendar for native bookings: busy times for availability, and event sync.

Availability: when the business connected a calendar, its busy times are removed from
the offered slots and re-checked when booking. If the calendar is connected but cannot be
read, availability is refused (CALENDAR_UNAVAILABLE) instead of guessing it is free.

Sync is convergent and runs after the booking commits (sweep job), never inside the
customer's run transaction, so a rolled-back run can't leave a stray event. The event id
is derived from the booking id: a retry after an uncertain outcome gets 409 for the event
that already exists instead of creating a second one. A cancelled booking deletes it; a
rescheduled booking patches it. States on the booking: pending -> synced | failed.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.providers.base import EMAIL
from app.integrations.providers.google_calendar import GoogleCalendarProvider, event_id
from app.integrations.runtime import ConnectionRuntime
from app.modules.customers.models import Customer
from app.modules.integrations.models import IntegrationConnection
from app.modules.pi_saas import connectors
from app.modules.pi_saas.models import PiBookableService, PiBooking
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
PROVIDER = GoogleCalendarProvider()
Interval = tuple[datetime, datetime]


def _unavailable() -> BusinessRuleViolation:
    return BusinessRuleViolation(
        "CALENDAR_UNAVAILABLE",
        "The business calendar can't be checked right now; a team member will confirm",
        503,
    )


async def calendar_for(
    session: AsyncSession, scope: WorkspaceScope, service: PiBookableService
) -> IntegrationConnection | None:
    """The calendar that governs this service, None when the business has none. A linked
    but broken calendar raises: availability must not be offered without it."""
    repo = WorkspaceRepository(session, IntegrationConnection, scope)
    if service.calendar_connection_id is not None:
        row = await repo.find(IntegrationConnection.id == service.calendar_connection_id)
    else:
        row = await connectors.current(session, scope, "google_calendar")
    if row is None or (service.calendar_connection_id is None and row.status == "draft"):
        return None  # Never finished connecting: bookings work from working hours alone.
    if row.integration_key != "google_calendar" or row.status not in connectors.USABLE:
        raise _unavailable()
    return row


async def busy(
    session: AsyncSession,
    settings: Settings | None,
    http: Any,
    scope: WorkspaceScope,
    service: PiBookableService,
    start: datetime,
    end: datetime,
) -> tuple[list[Interval], bool]:
    """(busy intervals, calendar linked?)."""
    connection = await calendar_for(session, scope, service)
    if connection is None:
        return [], False
    if http is None or settings is None:
        raise _unavailable()
    outbound = http if isinstance(http, OutboundClient) else OutboundClient(settings, http)
    runtime = ConnectionRuntime(session, settings, outbound)
    try:
        await connectors.fresh(session, settings, outbound, connection)
        intervals, _ = await runtime.call(
            connection, lambda ctx: PROVIDER.busy(ctx, start, end), kind="calendar_busy"
        )
    except IntegrationError:
        raise _unavailable() from None
    return intervals, True


def _event(
    booking: PiBooking, service: PiBookableService, customer: Customer | None
) -> dict[str, Any]:
    name = (customer.name if customer else "") or "WhatsApp customer"
    body: dict[str, Any] = {
        "id": event_id(booking.id),
        "summary": f"{service.name} · {name}"[:200],
        "description": (
            (booking.notes + "\n\n" if booking.notes else "") + "Booked through Pi on WhatsApp."
        )[:4000],
        "start": {"dateTime": booking.starts_at.isoformat(), "timeZone": booking.timezone},
        "end": {"dateTime": booking.ends_at.isoformat(), "timeZone": booking.timezone},
        "extendedProperties": {"private": {"pi_booking_id": str(booking.id)}},
    }
    email = (customer.email or "").strip() if customer else ""
    if email and EMAIL.fullmatch(email):
        # Google emails the invitation; only a verified CRM address is ever invited.
        body["attendees"] = [{"email": email, "displayName": name[:100]}]
    return body


def _same_time(event: Any, booking: PiBooking) -> bool:
    try:
        start = datetime.fromisoformat(str(event["start"]["dateTime"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(event["end"]["dateTime"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    return start == booking.starts_at and end == booking.ends_at


async def sync_booking(
    session: AsyncSession, settings: Settings, http: Any, booking_id: UUID
) -> str:
    booking = await session.scalar(
        select(PiBooking)
        .where(PiBooking.id == booking_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if booking is None or booking.external_sync != "pending":
        return "skipped"
    scope = WorkspaceScope.system(
        booking.tenant_id, booking.environment_id, frozenset(), "Calendar sync"
    )
    service = await WorkspaceRepository(session, PiBookableService, scope).get(booking.service_id)
    try:
        connection = await calendar_for(session, scope, service)
    except BusinessRuleViolation:
        connection = None
        booking.external_sync = "failed"  # Linked calendar broken: staff must reconnect.
        await session.commit()
        return booking.external_sync
    if connection is None:
        booking.external_sync = "none" if booking.external_event_id is None else "failed"
        await session.commit()
        return booking.external_sync
    customer = await WorkspaceRepository(session, Customer, scope).find(
        Customer.id == booking.customer_id
    )
    outbound = http if isinstance(http, OutboundClient) else OutboundClient(settings, http)
    runtime = ConnectionRuntime(session, settings, outbound)
    wanted = event_id(booking.id)
    cancelled = booking.status not in ("pending", "confirmed")

    async def apply(ctx: Any) -> str | None:
        if cancelled:
            if booking.external_event_id:
                await PROVIDER.delete_event(ctx, booking.external_event_id, notify=True)
            return booking.external_event_id
        event = await PROVIDER.create_event(ctx, _event(booking, service, customer))
        if not _same_time(event, booking):  # Existing event from before a reschedule.
            body = _event(booking, service, customer)
            changes = {"start": body["start"], "end": body["end"]}
            if await PROVIDER.update_event(ctx, wanted, changes, notify=True) is None:
                raise IntegrationError("EVENT_MISSING", "The calendar event disappeared")
        return wanted

    try:
        await connectors.fresh(session, settings, outbound, connection)
        external, _ = await runtime.call(connection, apply, kind="calendar_sync")
    except IntegrationError as error:
        # Retryable outcomes stay pending: the deterministic id makes a retry safe.
        booking.external_sync = (
            "pending" if error.retryable or error.kind == "ambiguous" else ("failed")
        )
        booking.updated_at = datetime.now(UTC)
        await session.commit()
        return booking.external_sync
    booking.external_event_id = external
    booking.external_sync = "synced"
    await session.commit()
    return booking.external_sync


async def due(session: AsyncSession, *, limit: int = 50) -> list[UUID]:
    # Retries stop once the appointment is over: a stale pending row stays visible to
    # staff as "not in calendar" instead of looping forever.
    now = datetime.now(UTC)
    return list(
        await session.scalars(
            select(PiBooking.id)
            .where(
                PiBooking.external_sync == "pending",
                PiBooking.updated_at < now - timedelta(seconds=15),
                PiBooking.ends_at > now,
            )
            .order_by(PiBooking.updated_at)
            .limit(limit)
        )
    )


async def sweep_pi_calendar(ctx: dict[str, Any]) -> int:
    async with ctx["sessions"]() as session:
        ids = await due(session)
    done = 0
    for booking_id in ids:
        async with ctx["sessions"]() as session:
            try:
                await sync_booking(session, ctx["settings"], ctx["http"], booking_id)
                done += 1
            except Exception:  # noqa: BLE001 - one booking never stops the sweep
                await session.rollback()
                logger.warning("pi_calendar_sync_failed")
    return done


JOBS = {"sweep_pi_calendar": sweep_pi_calendar}
