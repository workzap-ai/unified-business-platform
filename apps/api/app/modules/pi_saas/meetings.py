"""A meeting the customer asked for, arranged by the team in one step.

From the meeting request on the desk, the team picks a time and how to meet:
- a Google Meet link, made by the business's connected Google Calendar (the event goes in
  their calendar; the customer is invited by email when their address is known), or
- their own link (Zoom, Teams...), or an in-person place.
The request is answered with the time and link, and pi tells the customer on WhatsApp in
their language (the same path as any team answer). pi never invents a time or a link:
the reply guard only lets through links the team gave it.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.providers.base import EMAIL
from app.integrations.providers.google_calendar import GoogleCalendarProvider
from app.integrations.runtime import ConnectionRuntime
from app.modules.customers.models import Customer
from app.modules.pi.models import PiSettings
from app.modules.pi_saas import connectors
from app.modules.pi_saas.models import PiStaffRequest
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
PROVIDER = GoogleCalendarProvider()


class MeetingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # Local date and time at the business ("2026-10-12T17:00").
    starts_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    duration_minutes: int = Field(default=30, ge=10, le=480)
    how: Literal["google_meet", "link", "in_person"] = "google_meet"
    link: str = Field(default="", max_length=500)  # their own Zoom / Teams link
    place: str = Field(default="", max_length=300)  # for in person
    note: str = Field(default="", max_length=1000)  # anything else pi should tell them


def _local(starts_at: str, zone: str) -> datetime:
    try:
        tz = ZoneInfo(zone or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return datetime.fromisoformat(starts_at).replace(tzinfo=tz)


async def _google_meet(
    session: AsyncSession,
    scope: WorkspaceScope,
    runtime: Any,
    request_row: PiStaffRequest,
    customer: Customer | None,
    start: datetime,
    end: datetime,
    zone: str,
) -> tuple[str, str]:
    """(Meet link, calendar event id) from the business's Google Calendar."""
    connection = await connectors.current(session, scope, "google_calendar")
    if connection is None or connection.status not in connectors.USABLE:
        raise BusinessRuleViolation(
            "CALENDAR_NOT_CONNECTED",
            "Connect Google Calendar (My pi → Tools) to create Meet links, or paste a link.",
            409,
        )
    name = (customer.name if customer else "") or "WhatsApp customer"
    body: dict[str, Any] = {
        "summary": f"Meeting with {name}"[:200],
        "description": (request_row.question or "")[:3000] + "\n\nArranged through pi.",
        "start": {"dateTime": start.isoformat(), "timeZone": zone},
        "end": {"dateTime": end.isoformat(), "timeZone": zone},
        "conferenceData": {
            "createRequest": {
                "requestId": f"pi-{request_row.id}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    email = (customer.email or "").strip() if customer else ""
    if email and EMAIL.fullmatch(email):
        body["attendees"] = [{"email": email, "displayName": name[:100]}]

    async def create(ctx: Any) -> Any:
        response = await ctx.http.request(
            "POST",
            PROVIDER._events_url(ctx),
            headers=PROVIDER._headers(ctx),
            params={
                "conferenceDataVersion": "1",
                "sendUpdates": "all" if body.get("attendees") else "none",
            },
            json_body=body,
            context=ctx.call,
        )
        return response.ensure_success().json_object()

    outbound = runtime.http
    try:
        await connectors.fresh(session, runtime.settings, outbound, connection)
        event, _ = await ConnectionRuntime(session, runtime.settings, outbound).call(
            connection, create, kind="calendar_meet"
        )
    except IntegrationError as error:
        logger.warning("pi_meet_failed", exc_info=True)
        raise BusinessRuleViolation(
            "MEET_FAILED",
            f"Google Calendar didn't create the meeting ({error.message}). Try again or "
            "paste a link.",
            502,
        ) from None
    link = str(event.get("hangoutLink") or "")
    if not link:
        for entry in (event.get("conferenceData") or {}).get("entryPoints") or []:
            if isinstance(entry, dict) and entry.get("entryPointType") == "video":
                link = str(entry.get("uri") or "")
                break
    if not link:
        raise BusinessRuleViolation(
            "MEET_FAILED", "The event was created but Google gave no Meet link.", 502
        )
    return link, str(event.get("id") or "")


async def arrange(
    session: AsyncSession,
    scope: WorkspaceScope,
    runtime: Any,
    request_id: UUID,
    data: MeetingInput,
    *,
    max_bytes: int,
) -> PiStaffRequest:
    """Book the meeting and answer the request with its time and link; the caller queues
    pi's reply to the customer."""
    from app.modules.pi_saas.requests import answer

    scope.require("pi.inbox.reply")
    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id)
    if row.kind != "meeting":
        raise BusinessRuleViolation("NOT_A_MEETING", "This request isn't a meeting", 422)
    if row.status != "open":
        raise BusinessRuleViolation("REQUEST_CLOSED", "This request was already answered")
    settings_row = await WorkspaceRepository(session, PiSettings, scope).find()
    zone = settings_row.timezone if settings_row else "UTC"
    start = _local(data.starts_at, zone)
    end = start + timedelta(minutes=data.duration_minutes)
    customer = await WorkspaceRepository(session, Customer, scope).find(
        Customer.id == row.customer_id
    )
    when = f"{start:%A %d %B, %I:%M %p} ({zone}), {data.duration_minutes} minutes"
    if data.how == "google_meet":
        link, _ = await _google_meet(session, scope, runtime, row, customer, start, end, zone)
        where = f"on Google Meet: {link}"
    elif data.how == "link":
        if not data.link.startswith(("https://", "http://")):
            raise BusinessRuleViolation("LINK_INVALID", "Paste the meeting link (https://…)")
        where = f"online: {data.link}"
    else:
        if not data.place:
            raise BusinessRuleViolation("PLACE_REQUIRED", "Say where you'll meet")
        where = f"in person at {data.place}"
    text = f"Meeting confirmed by the team: {when}, {where}."
    if data.note:
        text += f" {data.note}"
    if customer is not None and customer.email and data.how == "google_meet":
        text += " A calendar invitation was also emailed to them."
    return await answer(session, scope, row.id, text, save_as_knowledge=False, max_bytes=max_bytes)


def runtime_for(request: Any) -> Any:
    """What the calendar call needs from the app (settings + outbound HTTP)."""
    state = request.app.state

    class _Runtime:
        settings = state.settings
        http = OutboundClient(
            state.settings, state.http, resolver=getattr(state, "integration_resolver", None)
        )

    return _Runtime()


__all__ = ["MeetingInput", "arrange", "runtime_for"]
