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
import re
import secrets
from datetime import datetime, timedelta
from types import SimpleNamespace
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
    # google_meet: from the connected calendar; video: a link pi makes itself (Jitsi Meet,
    # no account needed); link: their own Zoom / Teams link; in_person: a place.
    how: Literal["google_meet", "video", "link", "in_person"] = "google_meet"
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
        logger.warning(
            "pi_meet_failed", extra={"code": error.code, "kind": error.kind}, exc_info=True
        )
        if error.kind in ("auth", "configuration"):
            raise BusinessRuleViolation(
                "CALENDAR_RECONNECT",
                "Google Calendar needs to be connected again (its sign-in expired). Open "
                'My pi → Tools → Google Calendar and reconnect, or choose "My own link" '
                "and paste a Zoom / Meet link.",
                409,
            ) from None
        # 409, not 502: the team must see Google's reason, not "temporarily unavailable".
        raise BusinessRuleViolation(
            "MEET_FAILED",
            f"Google Calendar didn't create the meeting: {error.message}. Try again, or "
            'choose "My own link" and paste a Zoom / Meet link.',
            409,
        ) from None
    link = str(event.get("hangoutLink") or "")
    if not link:
        for entry in (event.get("conferenceData") or {}).get("entryPoints") or []:
            if isinstance(entry, dict) and entry.get("entryPointType") == "video":
                link = str(entry.get("uri") or "")
                break
    if not link:
        raise BusinessRuleViolation(
            "MEET_FAILED",
            "The event was created in Google Calendar but Google gave no Meet link. Turn on "
            "Google Meet for the calendar's account, or paste a link.",
            409,
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
    any_kind: bool = False,
) -> PiStaffRequest:
    """Book the meeting and answer the request with its time and link; the caller queues
    pi's reply to the customer."""
    from app.modules.pi_saas.requests import answer

    scope.require("pi.inbox.reply")
    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id)
    if row.kind != "meeting" and not any_kind:
        raise BusinessRuleViolation("NOT_A_MEETING", "This request isn't a meeting", 422)
    if row.status != "open":
        raise BusinessRuleViolation("REQUEST_CLOSED", "This request was already answered")
    settings_row = await WorkspaceRepository(session, PiSettings, scope).find()
    zone = settings_row.timezone if settings_row else "UTC"
    start = _local(data.starts_at, zone)
    if start < datetime.now(start.tzinfo) - timedelta(minutes=5):
        raise BusinessRuleViolation(
            "MEETING_IN_PAST", f"That time has already passed ({zone}). Pick a later time."
        )
    end = start + timedelta(minutes=data.duration_minutes)
    customer = await WorkspaceRepository(session, Customer, scope).find(
        Customer.id == row.customer_id
    )
    when = f"{start:%A %d %B, %I:%M %p} ({zone}), {data.duration_minutes} minutes"
    how = data.how
    joined = ""  # the link the customer joins with
    if how == "google_meet":
        try:
            link, _ = await _google_meet(session, scope, runtime, row, customer, start, end, zone)
            where, joined = f"on Google Meet: {link}", link
        except BusinessRuleViolation as error:
            if error.code not in CALENDAR_PROBLEMS:
                raise
            # Never stuck on the calendar: pi makes a video-call link itself instead.
            logger.warning("pi_meet_fell_back_to_video", extra={"code": error.code})
            if error.code == "CALENDAR_RECONNECT":
                await _expire_calendar(session, scope)
            how = "video"
    if how == "video":
        joined = video_link()
        where = f"on a video call (opens in the browser, no sign-up): {joined}"
    elif how == "link":
        if not data.link.startswith(("https://", "http://")):
            raise BusinessRuleViolation("LINK_INVALID", "Paste the meeting link (https://…)")
        where, joined = f"online: {data.link}", data.link
    elif how == "in_person":
        if not data.place:
            raise BusinessRuleViolation("PLACE_REQUIRED", "Say where you'll meet")
        where = f"in person at {data.place}"
    text = f"Meeting confirmed by the team: {when}, {where}."
    if data.note:
        text += f" {data.note}"
    if customer is not None and customer.email and how == "google_meet":
        text += " A calendar invitation was also emailed to them."
    await _remember_meeting(
        session,
        scope,
        row.conversation_id,
        {
            "starts_at": data.starts_at,
            "how": how,
            "booked": data.starts_at,
            "label": f"{start:%A %d %B, %I:%M %p}",
            "zone": zone,
            "minutes": data.duration_minutes,
            "link": joined,
            "place": data.place if how == "in_person" else "",
            "note": data.note,
        },
    )
    return await answer(session, scope, row.id, text, save_as_knowledge=False, max_bytes=max_bytes)


async def _remember_meeting(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, meeting: dict[str, Any]
) -> None:
    """The arranged meeting on the chat's brief: pi repeats its exact time and link."""
    from app.modules.pi.models import PiConversation

    conversation = await WorkspaceRepository(session, PiConversation, scope).get(conversation_id)
    conversation.service_brief = {**(conversation.service_brief or {}), "meeting": meeting}


ZONE_NAMES = {"Asia/Karachi": "Pakistan time", "Asia/Dubai": "UAE time"}


def meeting_message(meeting: dict[str, Any], language: str) -> str:
    """The arranged meeting, told to the customer word for word (never through the
    model, so the time and link can't be dropped or changed)."""
    label = str(meeting.get("label") or "")
    zone = ZONE_NAMES.get(str(meeting.get("zone") or ""), str(meeting.get("zone") or ""))
    minutes = meeting.get("minutes") or 30
    link, place = str(meeting.get("link") or ""), str(meeting.get("place") or "")
    note = str(meeting.get("note") or "")
    if language == "roman_ur":
        text = f"Aap ki meeting confirm ho gayi hai: *{label}* ({zone}), {minutes} minute."
        if link:
            text += f"\nJoin karne ka link:\n{link}"
        elif place:
            text += f"\nJagah: {place}"
        text += "\nWaqt par link khol lein, browser ya phone dono par chal jata hai."
    else:
        text = f"Your meeting is confirmed: *{label}* ({zone}), {minutes} minutes."
        if link:
            text += f"\nJoin here:\n{link}"
        elif place:
            text += f"\nPlace: {place}"
        text += "\nOpen the link at that time; it works in a browser or on your phone."
    if note:
        text += f"\n{note}"
    return text


APPROVAL = re.compile(
    r"\b(?:yes|yep|yeah|ok(?:ay)?|sure|confirm\w*|approve\w*|schedul\w*|book|arrange|"
    r"go ahead|do it|fine|haan|han|ji|theek|thik|kar ?do|done)\b",
    re.IGNORECASE,
)
LINK = re.compile(r"https?://\S+")
MEETING_TALK = re.compile(r"\b(?:meeting|meet|call|zoom|demo|appointment|mulaqat)\b", re.I)


async def auto_arrange(
    session: AsyncSession,
    scope: WorkspaceScope,
    runtime: Any,
    row: PiStaffRequest,
    text: str,
    *,
    max_bytes: int,
) -> PiStaffRequest | None:
    """The team answered a meeting request in words ("yes, confirmed", "do schedule it",
    or a pasted Zoom link). When the customer already gave a time, the meeting is made
    for real: a Google Meet from the connected calendar, or the link they pasted. None
    when the answer isn't an approval or no time is known (it's then a plain answer).
    Never a confirmation without a link: without a calendar it asks for one."""
    from app.modules.pi.models import PiConversation

    if row.kind != "meeting" and not MEETING_TALK.search(row.question or ""):
        return None
    link = LINK.search(text)
    if not (link or APPROVAL.search(text)):
        return None
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        row.conversation_id
    )
    meeting = (conversation.service_brief or {}).get("meeting") or {}
    # A change they asked for after a meeting was arranged is the time to arrange now.
    starts_at = str(meeting.get("change_to") or meeting.get("starts_at") or "")
    settings_row = await WorkspaceRepository(session, PiSettings, scope).find()
    zone = settings_row.timezone if settings_row else "UTC"
    try:
        start = _local(starts_at, zone)
    except ValueError:
        return None
    if start < datetime.now(start.tzinfo) - timedelta(minutes=30):
        return None  # An old time: the team should pick one in the meeting dialog.
    data = MeetingInput(
        starts_at=starts_at,
        how="link" if link else "google_meet",  # falls back to pi's own video link
        link=link.group(0).rstrip(".,)") if link else "",
        note="" if link else LINK.sub("", text).strip()[:300],
    )
    return await arrange(session, scope, runtime, row.id, data, max_bytes=max_bytes, any_kind=True)


CALENDAR_PROBLEMS = {"CALENDAR_NOT_CONNECTED", "CALENDAR_RECONNECT", "MEET_FAILED"}


def video_link() -> str:
    """A private video-call room pi makes itself (Jitsi Meet: free, opens in the browser,
    no account). Unguessable, so only people with the link can join."""
    return f"https://meet.jit.si/pi-meeting-{secrets.token_hex(8)}"


async def _expire_calendar(session: AsyncSession, scope: WorkspaceScope) -> None:
    connection = await connectors.current(session, scope, "google_calendar")
    if connection is not None and connection.status in connectors.USABLE:
        connection.status, connection.health = "expired", "failing"
        connection.last_error = "Google sign-in expired; reconnect Google Calendar"
        connection.last_error_code = "RECONNECT_REQUIRED"


def runtime_for(request: Any) -> Any:
    """What the calendar call needs from the app (settings + outbound HTTP)."""
    state = request.app.state

    class _Runtime:
        settings = state.settings
        http = OutboundClient(
            state.settings, state.http, resolver=getattr(state, "integration_resolver", None)
        )

    return _Runtime()


__all__ = [
    "MeetingInput",
    "arrange",
    "auto_arrange",
    "book_for_customer",
    "calendar_ready",
    "runtime_for",
]


# ---- pi books the meeting itself -----------------------------------------------------

AHEAD = timedelta(minutes=5)
HORIZON = timedelta(days=90)


async def mark_reconnect(session: AsyncSession, scope: WorkspaceScope) -> None:
    """Google's sign-in expired: save that (after the failed attempt was rolled back), so
    Tools shows Reconnect and pi stops promising Meet links it can't make."""
    await session.rollback()
    connection = await connectors.current(session, scope, "google_calendar")
    if connection is not None and connection.status in connectors.USABLE:
        connection.status, connection.health = "expired", "failing"
        connection.last_error = "Google sign-in expired; reconnect Google Calendar"
        connection.last_error_code = "RECONNECT_REQUIRED"
        await session.commit()


async def calendar_ready(session: AsyncSession, scope: WorkspaceScope) -> bool:
    """The business's Google Calendar is connected, so pi can make Meet links itself."""
    connection = await connectors.current(session, scope, "google_calendar")
    return connection is not None and connection.status in connectors.USABLE


async def book_for_customer(ctx: dict[str, Any], conversation_id: str) -> str | None:
    """Job: the customer gave a day and time for a meeting. When the business's Google
    Calendar is connected (and pi books meetings), pi creates the Google Meet event at
    that time and sends the real link in the chat - nobody has to remember to do it.
    Otherwise the meeting request stays on the team's desk. Returns the request id."""
    from app.modules.pi.configuration import settings_row as pi_settings
    from app.modules.pi.models import PiConversation
    from app.modules.pi_saas.deals import system_scope_for
    from app.modules.pi_saas.requests import raise_request, reply_with_answer

    async with ctx["sessions"]() as session:
        conversation = await session.get(PiConversation, UUID(conversation_id))
        if conversation is None or conversation.customer_id is None:
            return None
        scope = await system_scope_for(session, conversation.tenant_id, conversation.environment_id)
        policy = await pi_settings(session, scope)
        if (policy.whatsapp_config or {}).get("auto_meetings", True) is False:
            return None
        meeting = dict((conversation.service_brief or {}).get("meeting") or {})
        starts_at, how = str(meeting.get("starts_at") or ""), str(meeting.get("how") or "")
        if (
            not starts_at
            or how in ("phone", "in_person")  # the team calls them or picks the place
            or meeting.get("booked") == starts_at
        ):
            return None
        try:
            start = _local(starts_at, policy.timezone)
        except ValueError:
            return None
        now = datetime.now(start.tzinfo)
        if not now + AHEAD <= start <= now + HORIZON:
            return None
        row = await raise_request(
            session,
            scope,
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            kind="meeting",
            question=f"The customer wants a meeting at {starts_at.replace('T', ' ')}.",
            priority="high",
        )
        runtime = SimpleNamespace(
            settings=ctx["settings"], http=OutboundClient(ctx["settings"], ctx["http"])
        )
        try:
            async with session.begin_nested():
                row = await arrange(
                    session,
                    scope,
                    runtime,
                    row.id,
                    MeetingInput(starts_at=starts_at, how="google_meet"),
                    max_bytes=ctx["settings"].knowledge_upload_max_bytes,
                    any_kind=True,
                )
        except BusinessRuleViolation as error:
            logger.warning("pi_auto_meeting_failed", exc_info=True)
            if error.code == "CALENDAR_RECONNECT":
                connection = await connectors.current(session, scope, "google_calendar")
                if connection is not None and connection.status in connectors.USABLE:
                    connection.status, connection.health = "expired", "failing"
            await session.commit()  # The request stays open on the desk for the team.
            return str(row.id)
        request_id = str(row.id)
        await session.commit()
    await reply_with_answer(ctx, request_id)  # pi sends the link in the customer's language
    return request_id
