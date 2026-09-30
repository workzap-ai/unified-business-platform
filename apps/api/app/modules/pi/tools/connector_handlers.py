"""Controlled tools backed by business-authorized connections: calendar-aware booking
changes, Shopify order status and booking confirmation emails.

The customer is always the conversation's verified customer: phone/email come from the
CRM record, never from model arguments, so a customer can only reach their own data.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import Field

from app.integrations.errors import IntegrationError
from app.modules.customers.models import Customer
from app.modules.pi.tools.base import ToolContext, ToolInput, ToolOutput, ToolRefused
from app.modules.pi.tools.work_handlers import BookingOut, _booking_out, calendar_busy
from app.modules.pi_saas import work
from app.modules.pi_saas.models import PiBookableService, PiBooking
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository


def _refuse(exc: BusinessRuleViolation) -> ToolRefused:
    return ToolRefused(exc.code, exc.message, "error")


class RescheduleInput(ToolInput):
    booking_id: UUID
    start: datetime


async def reschedule_booking(ctx: ToolContext, data: RescheduleInput) -> BookingOut:
    from app.modules.pi.configuration import settings_row  # avoids an import cycle

    policy = await settings_row(ctx.session, ctx.scope)
    booking = await WorkspaceRepository(ctx.session, PiBooking, ctx.scope).find(
        PiBooking.id == data.booking_id,
        PiBooking.customer_id == ctx.conversation.customer_id,
    )
    if booking is None:
        raise ToolRefused("RESOURCE_NOT_FOUND", "The requested record was not found", "error")
    service = await WorkspaceRepository(ctx.session, PiBookableService, ctx.scope).get(
        booking.service_id
    )
    start = data.start.astimezone(UTC)
    busy, linked = await calendar_busy(
        ctx, service, start - timedelta(hours=12), start + timedelta(hours=12)
    )
    if linked and booking.external_event_id:
        # The booking's own current event is busy at the old time; ignore exactly it.
        busy = [(s, e) for s, e in busy if not (s == booking.starts_at and e == booking.ends_at)]
    try:
        moved = await work.reschedule(
            ctx.session,
            ctx.scope,
            booking.id,
            ctx.conversation.customer_id,
            start,
            policy.timezone,
            busy=busy,
            calendar=linked,
        )
    except BusinessRuleViolation as exc:
        raise _refuse(exc) from None
    return _booking_out(moved)


class StoreOrder(ToolOutput):
    name: str
    created_at: str
    payment_status: str
    fulfillment_status: str
    cancelled: bool
    total: str
    currency: str
    items: list[dict[str, Any]]


class StoreOrdersOutput(ToolOutput):
    connected: bool
    orders: list[StoreOrder]


async def get_store_orders(ctx: ToolContext, data: ToolInput) -> StoreOrdersOutput:
    """The current customer's recent Shopify orders (matched by their verified WhatsApp
    phone, then CRM email). No match returns an empty list, never someone else's order."""
    from app.integrations.http import OutboundClient
    from app.integrations.providers.shopify import ShopifyProvider
    from app.integrations.runtime import ConnectionRuntime
    from app.modules.pi_saas import connectors

    connection = await connectors.usable(ctx.session, ctx.scope, "shopify")
    if connection is None:
        return StoreOrdersOutput(connected=False, orders=[])
    if ctx.http is None:
        raise ToolRefused("STORE_UNAVAILABLE", "The store can't be checked right now", "error")
    customer = await WorkspaceRepository(ctx.session, Customer, ctx.scope).get(
        ctx.conversation.customer_id
    )
    settings, client = ctx.http
    outbound = client if isinstance(client, OutboundClient) else OutboundClient(settings, client)
    provider = ShopifyProvider()
    try:
        await connectors.fresh(ctx.session, settings, outbound, connection)
        orders, _ = await ConnectionRuntime(ctx.session, settings, outbound).call(
            connection,
            lambda pctx: provider.customer_orders(
                pctx, phone=customer.phone, email=customer.email, limit=5
            ),
            kind="store_orders",
        )
    except IntegrationError:
        raise ToolRefused(
            "STORE_UNAVAILABLE", "The store can't be checked right now", "error"
        ) from None
    return StoreOrdersOutput(connected=True, orders=[StoreOrder(**o) for o in orders])


class BookingEmailInput(ToolInput):
    booking_id: UUID


class BookingEmailOut(ToolOutput):
    status: str
    recipient: str = Field(description="Masked address the confirmation goes to")


def mask(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}"


async def email_booking_confirmation(ctx: ToolContext, data: BookingEmailInput) -> BookingEmailOut:
    """Queue a booking confirmation email to the customer's own CRM address. Delivered
    after commit by the integration outbox; one email per booking time and status."""
    from app.integrations import business
    from app.integrations.email import EMAIL_KEYS
    from app.integrations.providers.base import EMAIL
    from app.modules.pi.configuration import settings_row
    from app.modules.pi_saas import calendar_invite
    from app.modules.tenants.models import Tenant

    booking = await WorkspaceRepository(ctx.session, PiBooking, ctx.scope).find(
        PiBooking.id == data.booking_id,
        PiBooking.customer_id == ctx.conversation.customer_id,
    )
    if booking is None:
        raise ToolRefused("RESOURCE_NOT_FOUND", "The requested record was not found", "error")
    if booking.status not in work.ACTIVE:
        raise ToolRefused("BOOKING_NOT_ACTIVE", "Only active bookings can be confirmed", "error")
    customer = await WorkspaceRepository(ctx.session, Customer, ctx.scope).get(booking.customer_id)
    address = (customer.email or "").strip()
    if not EMAIL.fullmatch(address):
        raise ToolRefused(
            "CUSTOMER_EMAIL_REQUIRED", "This customer has no email address on file", "error"
        )
    try:
        connection = await business.connection_for(ctx.session, ctx.scope, EMAIL_KEYS)
    except BusinessRuleViolation:
        raise ToolRefused(
            "EMAIL_NOT_CONNECTED", "Email isn't connected for this business", "error"
        ) from None
    service = await WorkspaceRepository(ctx.session, PiBookableService, ctx.scope).get(
        booking.service_id
    )
    tenant = await ctx.session.get(Tenant, ctx.scope.tenant_id)
    policy = await settings_row(ctx.session, ctx.scope)
    name = (tenant.name if tenant else "") or "our team"
    when = work.label(booking.starts_at, booking.timezone)
    op = await business.operation(
        ctx.session,
        ctx.scope,
        connection,
        "notification",
        f"pi-booking-email:{booking.id}:{booking.starts_at.isoformat()}"[:200],
        "customer",
        customer.id,
        {
            "recipient": address,
            "template": "customer_notice",
            "name": customer.name,
            "business": name,
            "title": f"Booking confirmed: {service.name}",
            "message": (
                f"{service.name} on {when} ({booking.timezone or policy.timezone}). "
                "Open the attached calendar file to add it to your calendar. "
                "Reply on WhatsApp if you need to change or cancel it."
            ),
            # Calendar invitation: the same UID updates the entry if the time changes.
            "attachments": [
                calendar_invite.attachment(
                    calendar_invite.booking_ics(
                        booking.id,
                        booking.starts_at,
                        booking.ends_at,
                        f"{service.name} with {name}",
                        f"{service.name} with {name}. Reply on WhatsApp to change or cancel.",
                        sequence=int(datetime.now(UTC).timestamp()) // 60,
                    )
                )
            ],
        },
    )
    return BookingEmailOut(
        status="queued" if op.status in ("pending", "running") else op.status,
        recipient=mask(address),
    )
