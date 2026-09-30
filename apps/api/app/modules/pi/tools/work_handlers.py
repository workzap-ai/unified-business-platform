"""Controlled tools for native bookings, tasks and support tickets.

Every tool is bound to the conversation's customer: a customer can only see or cancel
their own bookings and project status. Mutations use an idempotency key derived from the
inbound message, so a retried run never creates a second record.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.modules.pi.tools.base import ToolContext, ToolInput, ToolOutput, ToolRefused
from app.modules.pi_saas import work
from app.modules.pi_saas.models import PiBookableService, PiBooking, PiTask
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository


async def calendar_busy(
    ctx: ToolContext, service: PiBookableService, start: datetime, end: datetime
) -> tuple[list[tuple[datetime, datetime]], bool]:
    """Busy times of the business calendar governing `service`, and whether one is linked."""
    from app.modules.pi_saas import calendar_sync

    settings, client = ctx.http if ctx.http is not None else (None, None)
    try:
        return await calendar_sync.busy(
            ctx.session, settings, client, ctx.scope, service, start, end
        )
    except BusinessRuleViolation as exc:
        raise ToolRefused(exc.code, exc.message, "error") from None


def _key(ctx: ToolContext, kind: str) -> str:
    if ctx.run is None:
        raise ToolRefused("RUN_REQUIRED", "Only available for an inbound message")
    return f"pi:{ctx.run.message_id}:{kind}"


class Slot(ToolOutput):
    start: str
    label: str


class ServiceSlots(ToolOutput):
    service_id: UUID
    name: str
    duration_minutes: int
    slots: list[Slot]


class AvailabilityInput(ToolInput):
    service_id: UUID | None = None
    days: int = Field(default=7, ge=1, le=21)


class AvailabilityOutput(ToolOutput):
    timezone: str
    services: list[ServiceSlots]


async def check_availability(ctx: ToolContext, data: AvailabilityInput) -> AvailabilityOutput:
    from app.modules.pi.configuration import settings_row  # avoids an import cycle

    policy = await settings_row(ctx.session, ctx.scope)
    query = (
        WorkspaceRepository(ctx.session, PiBookableService, ctx.scope)
        .select()
        .where(PiBookableService.status == "active")
    )
    if data.service_id:
        query = query.where(PiBookableService.id == data.service_id)
    services = list(await ctx.session.scalars(query.order_by(PiBookableService.name).limit(10)))
    result = []
    now = datetime.now(UTC)
    for service in services:
        # The business calendar's busy times too; unreadable calendar -> refused.
        busy, _ = await calendar_busy(ctx, service, now, now + timedelta(days=data.days + 1))
        slots = await work.available_slots(
            ctx.session, ctx.scope, service, policy.timezone, days=data.days, limit=8, busy=busy
        )
        result.append(
            ServiceSlots(
                service_id=service.id,
                name=service.name,
                duration_minutes=service.duration_minutes,
                slots=[Slot(**s) for s in slots],
            )
        )
    return AvailabilityOutput(timezone=policy.timezone, services=result)


class BookingInput(ToolInput):
    service_id: UUID
    start: datetime
    notes: str = Field(default="", max_length=500)


BookingStatus = Literal["pending", "confirmed", "cancelled", "completed", "no_show"]


class BookingOut(ToolOutput):
    booking_id: UUID
    service_id: UUID
    status: BookingStatus
    starts_at: datetime
    label: str
    timezone: str


def _booking_out(booking: PiBooking) -> BookingOut:
    return BookingOut(
        booking_id=booking.id,
        service_id=booking.service_id,
        status=booking.status,
        starts_at=booking.starts_at,
        label=work.label(booking.starts_at, booking.timezone),
        timezone=booking.timezone,
    )


async def create_booking(ctx: ToolContext, data: BookingInput) -> BookingOut:
    from app.modules.pi.configuration import settings_row  # avoids an import cycle

    policy = await settings_row(ctx.session, ctx.scope)
    service = await WorkspaceRepository(ctx.session, PiBookableService, ctx.scope).find(
        PiBookableService.id == data.service_id
    )
    if service is None:
        raise ToolRefused("RESOURCE_NOT_FOUND", "The requested record was not found", "error")
    start = data.start.astimezone(UTC)
    # Re-read the calendar right before booking: the slot may have been taken meanwhile.
    busy, linked = await calendar_busy(
        ctx, service, start - timedelta(hours=12), start + timedelta(hours=12)
    )
    try:
        booking = await work.book(
            ctx.session,
            ctx.scope,
            service_id=data.service_id,
            customer_id=ctx.conversation.customer_id,
            conversation_id=ctx.conversation.id,
            starts_at=data.start,
            timezone=policy.timezone,
            idempotency_key=_key(ctx, "booking"),
            notes=data.notes,
            busy=busy,
            calendar=linked,
        )
    except BusinessRuleViolation as exc:
        raise ToolRefused(exc.code, exc.message, "error") from None
    return _booking_out(booking)


class BookingIdInput(ToolInput):
    booking_id: UUID


async def cancel_booking(ctx: ToolContext, data: BookingIdInput) -> BookingOut:
    booking = await work.cancel_booking(
        ctx.session, ctx.scope, data.booking_id, ctx.conversation.customer_id
    )
    return _booking_out(booking)


class BookingsOutput(ToolOutput):
    bookings: list[BookingOut]


async def get_bookings(ctx: ToolContext, data: ToolInput) -> BookingsOutput:
    rows = await ctx.session.scalars(
        WorkspaceRepository(ctx.session, PiBooking, ctx.scope)
        .select()
        .where(
            PiBooking.customer_id == ctx.conversation.customer_id,
            PiBooking.status.in_(work.ACTIVE),
            PiBooking.starts_at >= datetime.now(UTC),
        )
        .order_by(PiBooking.starts_at)
        .limit(10)
    )
    return BookingsOutput(bookings=[_booking_out(b) for b in rows])


class TaskInput(ToolInput):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class TaskOut(ToolOutput):
    task_id: UUID
    status: str


async def create_task(ctx: ToolContext, data: TaskInput) -> TaskOut:
    task = await work.create_task(
        ctx.session,
        ctx.scope,
        title=data.title,
        description=data.description,
        customer_id=ctx.conversation.customer_id,
        conversation_id=ctx.conversation.id,
        idempotency_key=_key(ctx, "task"),
    )
    return TaskOut(task_id=task.id, status=task.status)


class TicketInput(ToolInput):
    subject: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class TicketOut(ToolOutput):
    ticket_id: UUID
    status: str
    priority: str


async def create_ticket(ctx: ToolContext, data: TicketInput) -> TicketOut:
    ticket = await work.create_ticket(
        ctx.session,
        ctx.scope,
        subject=data.subject,
        summary=data.summary,
        customer_id=ctx.conversation.customer_id,
        conversation_id=ctx.conversation.id,
        priority=data.priority,
        idempotency_key=_key(ctx, "ticket"),
    )
    return TicketOut(ticket_id=ticket.id, status=ticket.status, priority=ticket.priority)


class ProjectStatus(ToolOutput):
    title: str
    status: str
    customer_visible_status: str


class ProjectStatusOutput(ToolOutput):
    projects: list[ProjectStatus]


async def get_project_status(ctx: ToolContext, data: ToolInput) -> ProjectStatusOutput:
    """Only what the team marked as customer-visible, for the current customer."""
    rows = await ctx.session.scalars(
        WorkspaceRepository(ctx.session, PiTask, ctx.scope)
        .select()
        .where(
            PiTask.customer_id == ctx.conversation.customer_id,
            PiTask.customer_visible_status != "",
        )
        .order_by(PiTask.updated_at.desc())
        .limit(10)
    )
    return ProjectStatusOutput(
        projects=[
            ProjectStatus(
                title=t.title, status=t.status, customer_visible_status=t.customer_visible_status
            )
            for t in rows
        ]
    )


class PaymentRequestInput(ToolInput):
    method: Literal["stripe", "bank_transfer", "mobile_wallet", "cash"]
    invoice_id: UUID | None = None


class PaymentRequestOut(ToolOutput):
    request_id: UUID
    status: str
    method: str
    amount: str
    currency: str
    reference: str
    message: str


async def request_payment(ctx: ToolContext, data: PaymentRequestInput) -> PaymentRequestOut:
    """Payment instructions for the CURRENT customer's own open invoice. The amount is the
    invoice balance; Stripe links use the business's own Stripe account."""
    from app.integrations import business
    from app.integrations.http import OutboundClient
    from app.modules.billing.models import Invoice
    from app.modules.pi_saas import customer_payments as cp

    invoice_id = data.invoice_id
    if invoice_id is None:
        invoice_id = await ctx.session.scalar(
            WorkspaceRepository(ctx.session, Invoice, ctx.scope)
            .select()
            .with_only_columns(Invoice.id)
            .where(
                Invoice.customer_id == ctx.conversation.customer_id,
                Invoice.status.in_(["issued", "partially_paid"]),
            )
            .order_by(Invoice.created_at.desc())
            .limit(1)
        )
        if invoice_id is None:
            raise ToolRefused("NOTHING_DUE", "There is no open invoice to pay", "error")
    checkout = None
    if data.method == "stripe" and ctx.http is not None:
        settings, http = ctx.http

        async def checkout(scope, invoice, request_key=""):  # type: ignore[no-untyped-def]
            return await business.checkout(
                ctx.session, settings, OutboundClient(settings, http), scope, invoice, request_key
            )

    try:
        row = await cp.create_request(
            ctx.session,
            ctx.scope,
            invoice_id=invoice_id,
            method=data.method,
            idempotency_key=_key(ctx, f"payment:{data.method}"),
            conversation_id=ctx.conversation.id,
            customer_id=ctx.conversation.customer_id,
            stripe_checkout=checkout,
        )
    except BusinessRuleViolation as exc:
        raise ToolRefused(exc.code, exc.message, "error") from None
    return PaymentRequestOut(
        request_id=row.id,
        status=row.status,
        method=row.method,
        amount=str(row.amount),
        currency=row.currency,
        reference=row.reference,
        message=cp.customer_message(row),
    )


class PaymentStatusOutput(ToolOutput):
    requests: list[PaymentRequestOut]


async def get_payment_status(ctx: ToolContext, data: ToolInput) -> PaymentStatusOutput:
    from app.modules.pi_saas import customer_payments as cp
    from app.modules.pi_saas.customer_payment_models import PiPaymentRequest

    rows = await ctx.session.scalars(
        WorkspaceRepository(ctx.session, PiPaymentRequest, ctx.scope)
        .select()
        .where(PiPaymentRequest.customer_id == ctx.conversation.customer_id)
        .order_by(PiPaymentRequest.created_at.desc())
        .limit(5)
    )
    items = []
    for row in rows:
        await cp.sync_stripe(ctx.session, ctx.scope, row)
        items.append(
            PaymentRequestOut(
                request_id=row.id,
                status=row.status,
                method=row.method,
                amount=str(row.amount),
                currency=row.currency,
                reference=row.reference,
                message="",
            )
        )
    return PaymentStatusOutput(requests=items)
