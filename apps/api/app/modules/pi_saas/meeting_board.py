"""The Meeting Board: every meeting pi and the team arranged, the free time to book new
ones, and the requests still waiting for a time, in one week view.

No table of its own. A chat's arranged meeting lives on its brief
(``service_brief["meeting"]``, written by ``meetings.arrange``); finished and cancelled
ones move to ``service_brief["meetings_past"]`` so the board keeps their history and
pi never sends an old link again. Bookings of bookable services come from
``pi_bookings``; busy time from the connected Google Calendar (free/busy only).

The team acts from the board: move a meeting (the Google event moves too, the customer
is told the new time word for word), accept the time the customer asked to change to,
cancel it, send a reminder with the link, and record how it went (done / no-show and a
note pi reads as a team note, so the next reply builds on it).
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.runtime import ConnectionRuntime
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.navigation.service import badge_provider
from app.modules.pi.models import PiConversation, PiSettings
from app.modules.pi.service import require_pi
from app.modules.pi_saas import connectors
from app.modules.pi_saas.meetings import PROVIDER, ZONE_NAMES, meeting_message
from app.modules.pi_saas.models import PiBooking, PiConversationNote, PiStaffRequest
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pi/meetings", tags=["pi-meetings"])

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Meeting hours when the business set none: Monday to Saturday, 9 to 6.
DEFAULT_HOURS = {d: {"open": d != "sun", "start": "09:00", "end": "18:00"} for d in DAYS}
SLOT = timedelta(minutes=30)
NOTICE = timedelta(minutes=30)  # a free slot starts at least this far ahead
WINDOW = timedelta(hours=24)  # WhatsApp: free-form messages only inside this window
PAST_KEEP = 20


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local(value: str, tz: ZoneInfo) -> datetime | None:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=tz)
    except (TypeError, ValueError):
        return None


def meeting_hours(settings: PiSettings | None) -> dict[str, dict[str, Any]]:
    """Opening hours per weekday from pi's business hours (whether or not pi uses them
    for out-of-hours replies), else Monday to Saturday 9 to 6."""
    days = ((settings.business_hours if settings else None) or {}).get("days") or {}
    hours: dict[str, dict[str, Any]] = {}
    for day in DAYS:
        given = days.get(day) if isinstance(days.get(day), dict) else None
        hours[day] = {**DEFAULT_HOURS[day], **(given or {})}
    return hours


def _status(meeting: dict[str, Any], tz: ZoneInfo, now: datetime) -> str:
    if meeting.get("status") in ("done", "no_show", "cancelled"):
        return str(meeting["status"])
    start = _local(str(meeting.get("starts_at") or ""), tz)
    if not meeting.get("link") and not meeting.get("place"):
        return "requested"  # a time they asked for, not arranged yet
    if start is not None:
        end = start + timedelta(minutes=int(meeting.get("minutes") or 30))
        if now >= end:
            return "awaiting_outcome"  # over: the team says how it went
        if now >= start:
            return "live"
    return "scheduled"


def _meeting_view(
    conversation: PiConversation,
    meeting: dict[str, Any],
    customer: Customer | None,
    tz: ZoneInfo,
    now: datetime,
    *,
    current: bool,
) -> dict[str, Any] | None:
    start = _local(str(meeting.get("starts_at") or ""), tz)
    if start is None:
        return None
    minutes = int(meeting.get("minutes") or 30)
    change = _local(str(meeting.get("change_to") or ""), tz) if current else None
    return {
        "id": str(conversation.id) if current else f"{conversation.id}:{meeting.get('starts_at')}",
        "conversation_id": conversation.id,
        "customer_id": conversation.customer_id,
        "customer_name": (customer.name if customer else "") or "WhatsApp customer",
        "phone": customer.phone if customer else None,
        "starts_at": start.astimezone(UTC).isoformat(),
        "ends_at": (start + timedelta(minutes=minutes)).astimezone(UTC).isoformat(),
        "local": str(meeting.get("starts_at")),
        "label": str(meeting.get("label") or f"{start:%A %d %B, %I:%M %p}"),
        "minutes": minutes,
        "how": str(meeting.get("how") or ""),
        "link": str(meeting.get("link") or ""),
        "place": str(meeting.get("place") or ""),
        "note": str(meeting.get("note") or ""),
        "status": _status(meeting, tz, now),
        "outcome": str(meeting.get("outcome") or ""),
        "change_to": change.astimezone(UTC).isoformat() if change else None,
        "change_label": f"{change:%A %d %B, %I:%M %p}" if change else None,
        "calendar_event": bool(meeting.get("event_id")),
        "actionable": current,
        "topic": _topic(conversation),
    }


def _topic(conversation: PiConversation) -> str:
    """What the meeting is about: the chat's newest project."""
    projects = [
        p for p in (conversation.service_brief or {}).get("projects") or [] if isinstance(p, dict)
    ]
    return str((projects[-1].get("title") if projects else "") or "")[:120]


async def _conversations_with_meetings(
    session: AsyncSession, scope: WorkspaceScope
) -> list[PiConversation]:
    from app.modules.pi.service import PiService

    service = PiService(session, scope)
    brief = PiConversation.service_brief
    query = (
        service.conversations.select()
        .where(brief.has_key("meeting") | brief.has_key("meetings_past"))
        .order_by(PiConversation.updated_at.desc())
        .limit(500)
    )
    return list(await session.scalars(query))


async def _calendar_busy(
    session: AsyncSession, request: Request, scope: WorkspaceScope, start: datetime, end: datetime
) -> tuple[list[tuple[datetime, datetime]], str]:
    """(busy intervals, calendar state: none | connected | error)."""
    connection = await connectors.current(session, scope, "google_calendar")
    if connection is None or connection.status == "draft":
        return [], "none"
    if connection.status not in connectors.USABLE:
        return [], "error"
    settings = request.app.state.settings
    outbound = OutboundClient(
        settings,
        request.app.state.http,
        resolver=getattr(request.app.state, "integration_resolver", None),
    )
    try:
        async with session.begin_nested():
            await connectors.fresh(session, settings, outbound, connection)
            intervals, _ = await ConnectionRuntime(session, settings, outbound).call(
                connection, lambda ctx: PROVIDER.busy(ctx, start, end), kind="calendar_busy"
            )
    except (IntegrationError, BusinessRuleViolation):
        logger.warning("pi_meeting_board_busy_failed", exc_info=True)
        return [], "error"
    return list(intervals), "connected"


def free_slots(
    hours: dict[str, dict[str, Any]],
    tz: ZoneInfo,
    first: date,
    days: int,
    taken: list[tuple[datetime, datetime]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Half-hour slots inside meeting hours that nothing takes (calendar, meetings,
    bookings) and that start at least NOTICE from now."""
    slots: list[dict[str, Any]] = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        rule = hours[DAYS[day.weekday()]]
        if not rule.get("open"):
            continue
        try:
            opens = datetime.combine(day, time.fromisoformat(str(rule["start"])), tz)
            closes = datetime.combine(day, time.fromisoformat(str(rule["end"])), tz)
        except (KeyError, ValueError):
            continue
        at = opens
        while at + SLOT <= closes:
            end = at + SLOT
            if at >= now + NOTICE and not any(s < end and at < e for s, e in taken):
                slots.append(
                    {
                        "starts_at": at.astimezone(UTC).isoformat(),
                        "local": f"{at:%Y-%m-%dT%H:%M}",
                        "label": f"{at:%a %d %b, %I:%M %p}",
                    }
                )
            at = end
    return slots


@router.get("")
async def board(
    request: Request,
    scope: Scope,
    session: Session,
    start: date | None = None,  # first day (business time); default today
    days: int = Query(7, ge=1, le=14),
) -> dict[str, Any]:
    """The week: meetings, bookings, busy time, free slots and waiting requests."""
    await require_pi(session, scope, "pi.read")
    settings = await WorkspaceRepository(session, PiSettings, scope).find()
    zone = settings.timezone if settings else "UTC"
    tz = _zone(zone)
    now = datetime.now(tz)
    first = start or now.date()
    begin = datetime.combine(first, time.min, tz)
    finish = begin + timedelta(days=days)

    conversations = await _conversations_with_meetings(session, scope)
    customers = {
        c.id: c
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope)
            .select()
            .where(Customer.id.in_([c.customer_id for c in conversations] or [None]))
        )
    }
    meetings: list[dict[str, Any]] = []
    for conversation in conversations:
        brief = conversation.service_brief or {}
        customer = customers.get(conversation.customer_id)
        items = [(brief.get("meeting") or {}, True)] + [
            (m, False) for m in brief.get("meetings_past") or [] if isinstance(m, dict)
        ]
        for meeting, current in items:
            view = _meeting_view(conversation, meeting, customer, tz, now, current=current)
            if view is not None and view["status"] != "requested":
                meetings.append(view)
    meetings.sort(key=lambda m: m["starts_at"])
    in_range = [
        m
        for m in meetings
        if begin.astimezone(UTC).isoformat() <= m["starts_at"] < finish.astimezone(UTC).isoformat()
    ]

    bookings = list(
        await session.scalars(
            WorkspaceRepository(session, PiBooking, scope)
            .select()
            .where(
                PiBooking.starts_at < finish,
                PiBooking.ends_at > begin,
                PiBooking.status.in_(["pending", "confirmed", "completed"]),
            )
            .order_by(PiBooking.starts_at)
            .limit(300)
        )
    )
    booking_names = {
        c.id: c.name
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope)
            .select()
            .where(Customer.id.in_([b.customer_id for b in bookings] or [None]))
        )
    }

    busy, calendar = await _calendar_busy(session, request, scope, begin, finish)
    taken = [*busy]
    for m in in_range:
        if m["status"] not in ("cancelled",):
            taken.append(
                (datetime.fromisoformat(m["starts_at"]), datetime.fromisoformat(m["ends_at"]))
            )
    taken += [(b.starts_at, b.ends_at) for b in bookings if b.status != "completed"]
    hours = meeting_hours(settings)

    waiting = await _waiting(session, scope, conversations, customers, tz)
    week_start = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min, tz)
    this_week = [
        m
        for m in meetings
        if week_start.astimezone(UTC).isoformat()
        <= m["starts_at"]
        < (week_start + timedelta(days=7)).astimezone(UTC).isoformat()
    ]
    today = [m for m in meetings if m["local"][:10] == f"{now:%Y-%m-%d}"]
    return {
        "timezone": zone,
        "zone_name": ZONE_NAMES.get(zone, zone),
        "now": now.astimezone(UTC).isoformat(),
        "start": first.isoformat(),
        "days": days,
        "hours": hours,
        "calendar": calendar,
        "busy": [
            {"starts_at": s.astimezone(UTC).isoformat(), "ends_at": e.astimezone(UTC).isoformat()}
            for s, e in busy
        ],
        "meetings": in_range,
        "upcoming": [m for m in meetings if m["status"] in ("scheduled", "live")][:20],
        "needs_outcome": [m for m in meetings if m["status"] == "awaiting_outcome"][:20],
        "history": [
            m for m in reversed(meetings) if m["status"] in ("done", "no_show", "cancelled")
        ][:20],
        "bookings": [
            {
                "id": b.id,
                "customer_name": booking_names.get(b.customer_id) or "Customer",
                "starts_at": b.starts_at.isoformat(),
                "ends_at": b.ends_at.isoformat(),
                "status": b.status,
                "conversation_id": b.conversation_id,
            }
            for b in bookings
        ],
        "free": free_slots(hours, tz, first, days, taken, now),
        "waiting": waiting,
        "stats": {
            "today": sum(1 for m in today if m["status"] not in ("cancelled",)),
            "this_week": sum(1 for m in this_week if m["status"] not in ("cancelled",)),
            "waiting": len(waiting),
            "change_requests": sum(1 for m in meetings if m["change_to"]),
            "needs_outcome": sum(1 for m in meetings if m["status"] == "awaiting_outcome"),
            "done": sum(1 for m in this_week if m["status"] == "done"),
            "no_show": sum(1 for m in this_week if m["status"] == "no_show"),
        },
    }


async def _waiting(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversations: list[PiConversation],
    customers: dict[Any, Customer],
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """Open meeting requests: who, what they asked, and the time they suggested."""
    from app.modules.pi.service import PiService

    visible = PiService(session, scope).conversations.select().with_only_columns(PiConversation.id)
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiStaffRequest, scope)
            .select()
            .where(
                PiStaffRequest.kind == "meeting",
                PiStaffRequest.status == "open",
                PiStaffRequest.conversation_id.in_(visible),
            )
            .order_by(PiStaffRequest.created_at)
            .limit(50)
        )
    )
    by_chat = {c.id: c for c in conversations}
    missing = [r.customer_id for r in rows if r.customer_id not in customers]
    if missing:
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope).select().where(Customer.id.in_(missing))
        ):
            customers[c.id] = c
    out = []
    for row in rows:
        chat = by_chat.get(row.conversation_id) or await session.get(
            PiConversation, row.conversation_id
        )
        meeting = ((chat.service_brief if chat else None) or {}).get("meeting") or {}
        asked = _local(str(meeting.get("change_to") or meeting.get("starts_at") or ""), tz)
        customer = customers.get(row.customer_id)
        out.append(
            {
                "request_id": row.id,
                "conversation_id": row.conversation_id,
                "customer_name": (customer.name if customer else "") or "WhatsApp customer",
                "question": (row.question or "")[:400],
                "priority": row.priority,
                "asked_local": f"{asked:%Y-%m-%dT%H:%M}" if asked else None,
                "asked_label": f"{asked:%A %d %B, %I:%M %p}" if asked else None,
                "how": str(meeting.get("change_how") or meeting.get("how") or ""),
                "created_at": row.created_at,
                "topic": _topic(chat) if chat else "",
            }
        )
    return out


# ---- actions ----------------------------------------------------------------------------


class MoveInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    starts_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")  # business time
    duration_minutes: int | None = Field(default=None, ge=10, le=480)
    notify: bool = True


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(default="", max_length=300)
    notify: bool = True


class OutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["done", "no_show"]
    note: str = Field(default="", max_length=2000)


async def _current(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> tuple[PiConversation, dict[str, Any], ZoneInfo, str]:
    from app.modules.pi.service import PiService

    conversation = await PiService(session, scope).conversations.get(conversation_id)
    meeting = dict((conversation.service_brief or {}).get("meeting") or {})
    if not meeting.get("link") and not meeting.get("place"):
        raise BusinessRuleViolation("NO_MEETING", "This chat has no arranged meeting", 404)
    settings = await WorkspaceRepository(session, PiSettings, scope).find()
    zone = settings.timezone if settings else "UTC"
    return conversation, meeting, _zone(zone), zone


def moved_message(meeting: dict[str, Any], language: str) -> str:
    """The new time, word for word, saying plainly that it changed."""
    text = meeting_message(meeting, language)
    if language == "roman_ur":
        return text.replace(
            "Aap ki meeting confirm ho gayi hai:", "Meeting ka waqt badal gaya hai:", 1
        )
    return text.replace("Your meeting is confirmed:", "Meeting time changed:", 1)


def _language(conversation: PiConversation) -> str:
    return "roman_ur" if (conversation.language or "") == "roman_ur" else "en"


async def _tell(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    body: str,
    key: str,
) -> str | None:
    """Queue a message to the customer when WhatsApp allows a free-form one (they wrote
    in the last 24 hours). None when it can't go out (the team is told on the board)."""
    from app.modules.pi_saas.deals import _queue

    last = conversation.last_inbound_at
    if last is None or last < datetime.now(UTC) - WINDOW:
        return None
    return await _queue(session, scope, conversation, body, key)


async def _calendar_change(
    session: AsyncSession,
    request: Request,
    scope: WorkspaceScope,
    event_id: str,
    *,
    move: tuple[datetime, datetime, str] | None = None,
) -> bool:
    """Move (or, with no ``move``, delete) the Google Calendar event. False on failure:
    the board still records the change and says the calendar wasn't updated."""
    connection = await connectors.current(session, scope, "google_calendar")
    if connection is None or connection.status not in connectors.USABLE:
        return False
    settings = request.app.state.settings
    outbound = OutboundClient(
        settings,
        request.app.state.http,
        resolver=getattr(request.app.state, "integration_resolver", None),
    )

    async def change(ctx: Any) -> Any:
        if move is None:
            return await PROVIDER.delete_event(ctx, event_id, notify=True)
        start, end, zone = move
        return await PROVIDER.update_event(
            ctx,
            event_id,
            {
                "start": {"dateTime": start.isoformat(), "timeZone": zone},
                "end": {"dateTime": end.isoformat(), "timeZone": zone},
            },
            notify=True,
        )

    try:
        async with session.begin_nested():
            await connectors.fresh(session, settings, outbound, connection)
            await ConnectionRuntime(session, settings, outbound).call(
                connection, change, kind="calendar_meet"
            )
    except (IntegrationError, BusinessRuleViolation):
        logger.warning("pi_meeting_calendar_change_failed", exc_info=True)
        return False
    return True


def _archive(conversation: PiConversation, meeting: dict[str, Any]) -> None:
    brief = dict(conversation.service_brief or {})
    past = [m for m in brief.get("meetings_past") or [] if isinstance(m, dict)]
    brief["meetings_past"] = [*past, meeting][-PAST_KEEP:]
    brief.pop("meeting", None)
    brief["meeting_requested"] = False
    conversation.service_brief = brief


async def _send_now(request: Request, message_id: str | None) -> None:
    if message_id:
        await request.app.state.queue.enqueue(
            "send_pi_message", message_id, job_id=f"send:{message_id}"
        )


@router.post("/{conversation_id}/move")
async def move(
    conversation_id: UUID, data: MoveInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """A new time for the arranged meeting: the calendar event moves, the customer gets
    the new time and the same link."""
    await require_pi(session, scope, "pi.inbox.reply")
    conversation, meeting, tz, zone = await _current(session, scope, conversation_id)
    start = _local(data.starts_at, tz)
    if start is None or start < datetime.now(tz) - timedelta(minutes=5):
        raise BusinessRuleViolation("MEETING_IN_PAST", "Pick a time that hasn't passed yet")
    minutes = data.duration_minutes or int(meeting.get("minutes") or 30)
    calendar_moved = None
    if meeting.get("event_id"):
        calendar_moved = await _calendar_change(
            session,
            request,
            scope,
            str(meeting["event_id"]),
            move=(start, start + timedelta(minutes=minutes), zone),
        )
    meeting.update(
        starts_at=data.starts_at,
        booked=data.starts_at,
        label=f"{start:%A %d %B, %I:%M %p}",
        minutes=minutes,
        zone=zone,
    )
    meeting.pop("change_to", None)
    meeting.pop("change_how", None)
    meeting.pop("reminded", None)
    conversation.service_brief = {**(conversation.service_brief or {}), "meeting": meeting}
    sent = None
    if data.notify:
        sent = await _tell(
            session,
            scope,
            conversation,
            moved_message(meeting, _language(conversation)),
            f"pi-meeting-move:{conversation.id}:{data.starts_at}",
        )
    await record(
        session,
        "pi.meeting_moved",
        scope=scope,
        entity_type="pi_conversation",
        entity_id=conversation.id,
        details={"starts_at": data.starts_at},
    )
    await session.commit()
    await _send_now(request, sent)
    return {"ok": True, "told_customer": sent is not None, "calendar_moved": calendar_moved}


@router.post("/{conversation_id}/accept-change")
async def accept_change(
    conversation_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """The customer asked for another time: move the meeting to it."""
    await require_pi(session, scope, "pi.inbox.reply")
    _, meeting, _, _ = await _current(session, scope, conversation_id)
    if not meeting.get("change_to"):
        raise BusinessRuleViolation("NO_CHANGE", "The customer didn't ask for another time")
    result = await move(
        conversation_id,
        MoveInput(starts_at=str(meeting["change_to"])),
        request,
        scope,
        session,
    )
    await _close_meeting_requests(session, scope, conversation_id)
    await session.commit()
    return result


async def _close_meeting_requests(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> None:
    for row in await session.scalars(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(
            PiStaffRequest.conversation_id == conversation_id,
            PiStaffRequest.kind == "meeting",
            PiStaffRequest.status == "open",
        )
    ):
        row.status, row.resolved_at = "resolved", datetime.now(UTC)


@router.post("/{conversation_id}/cancel")
async def cancel(
    conversation_id: UUID, data: CancelInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Cancel the arranged meeting: its calendar event goes, the customer is told."""
    await require_pi(session, scope, "pi.inbox.reply")
    conversation, meeting, _, _ = await _current(session, scope, conversation_id)
    calendar_removed = None
    if meeting.get("event_id"):
        calendar_removed = await _calendar_change(session, request, scope, str(meeting["event_id"]))
    label = str(meeting.get("label") or "")
    meeting.update(status="cancelled", outcome=data.reason)
    _archive(conversation, meeting)
    sent = None
    if data.notify:
        if _language(conversation) == "roman_ur":
            body = f"Aap ki meeting (*{label}*) cancel kar di gayi hai."
            body += f" {data.reason}" if data.reason else ""
            body += " Naya waqt chahiye ho to yahin bata dein."
        else:
            body = f"Your meeting (*{label}*) has been cancelled."
            body += f" {data.reason}" if data.reason else ""
            body += " Reply here if you'd like a new time."
        sent = await _tell(
            session, scope, conversation, body, f"pi-meeting-cancel:{conversation.id}:{label}"
        )
    await record(
        session,
        "pi.meeting_cancelled",
        scope=scope,
        entity_type="pi_conversation",
        entity_id=conversation.id,
    )
    await session.commit()
    await _send_now(request, sent)
    return {"ok": True, "told_customer": sent is not None, "calendar_removed": calendar_removed}


@router.post("/{conversation_id}/remind")
async def remind(
    conversation_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Send the customer the meeting time and link again, now."""
    await require_pi(session, scope, "pi.inbox.reply")
    conversation, meeting, _, _ = await _current(session, scope, conversation_id)
    prefix = "Yaad dahani: " if _language(conversation) == "roman_ur" else "Reminder: "
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
    sent = await _tell(
        session,
        scope,
        conversation,
        prefix + meeting_message(meeting, _language(conversation)),
        f"pi-meeting-remind:{conversation.id}:{stamp}",
    )
    if sent is None:
        raise BusinessRuleViolation(
            "OUTSIDE_WINDOW",
            "WhatsApp only allows a message within 24 hours of the customer's last one. "
            "Call them, or wait for their next message.",
        )
    meeting["reminded"] = datetime.now(UTC).isoformat()
    conversation.service_brief = {**(conversation.service_brief or {}), "meeting": meeting}
    await session.commit()
    await _send_now(request, sent)
    return {"ok": True, "told_customer": True}


@router.post("/{conversation_id}/outcome")
async def outcome(
    conversation_id: UUID, data: OutcomeInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """How the meeting went. The note becomes a team note pi reads, so its next reply
    continues from what was agreed in the meeting."""
    await require_pi(session, scope, "pi.inbox.reply")
    conversation, meeting, _, _ = await _current(session, scope, conversation_id)
    label = str(meeting.get("label") or "")
    meeting.update(status=data.status, outcome=data.note)
    _archive(conversation, meeting)
    said = "took place" if data.status == "done" else "did not happen (the customer didn't join)"
    body = f"Meeting on {label} {said}."
    if data.note:
        body += f" Outcome: {data.note}"
    notes = WorkspaceRepository(session, PiConversationNote, scope)
    await notes.add(
        notes.new(
            conversation_id=conversation.id,
            author_user_id=scope.user_id,
            author_label=(scope.actor_label or "Team")[:80],
            body=body[:4000],
        )
    )
    await record(
        session,
        "pi.meeting_outcome",
        scope=scope,
        entity_type="pi_conversation",
        entity_id=conversation.id,
        details={"status": data.status},
    )
    await session.commit()
    return {"ok": True}


@badge_provider("pi.meetings_today")
async def meetings_today(session: AsyncSession, scope: WorkspaceScope) -> int | None:
    """Meetings today that haven't finished yet (the "Meetings" nav count)."""
    if not scope.can("pi.read"):
        return None
    settings = await WorkspaceRepository(session, PiSettings, scope).find()
    tz = _zone(settings.timezone if settings else "UTC")
    now = datetime.now(tz)
    count = 0
    for conversation in await _conversations_with_meetings(session, scope):
        meeting = (conversation.service_brief or {}).get("meeting") or {}
        if str(meeting.get("starts_at") or "")[:10] == f"{now:%Y-%m-%d}" and _status(
            meeting, tz, now
        ) in ("scheduled", "live"):
            count += 1
    return count or None


# ---- automatic reminders ------------------------------------------------------------------

SOON = timedelta(hours=1)


async def remind_upcoming(ctx: dict[str, Any]) -> int:
    """Cron job (every 5 minutes): a meeting starting within the hour gets one reminder.
    The customer gets the time and link on WhatsApp (when the 24-hour window allows a
    message), the team a notification. Returns how many meetings were reminded."""
    from sqlalchemy import select

    from app.modules.notifications.service import notify
    from app.modules.pi.models import WhatsAppConnection
    from app.modules.pi.runtime import enqueue_sends, system_scope

    async with ctx["sessions"]() as session:
        connections = list(
            await session.scalars(
                select(WhatsAppConnection).where(WhatsAppConnection.status == "active")
            )
        )
    seen: set[tuple[Any, Any]] = set()
    reminded = 0
    for connection in connections:
        pair = (connection.tenant_id, connection.environment_id)
        if pair in seen:
            continue
        seen.add(pair)
        sends: list[str] = []
        async with ctx["sessions"]() as session:
            try:
                scope = await system_scope(session, connection)
                if scope is None:
                    continue
                settings = await WorkspaceRepository(session, PiSettings, scope).find()
                tz = _zone(settings.timezone if settings else "UTC")
                now = datetime.now(tz)
                for conversation in await _conversations_with_meetings(session, scope):
                    meeting = dict((conversation.service_brief or {}).get("meeting") or {})
                    start = _local(str(meeting.get("starts_at") or ""), tz)
                    if (
                        start is None
                        or meeting.get("auto_reminded") == meeting.get("starts_at")
                        or _status(meeting, tz, now) != "scheduled"
                        or not now < start <= now + SOON
                    ):
                        continue
                    language = _language(conversation)
                    prefix = "Yaad dahani: " if language == "roman_ur" else "Reminder: "
                    sent = await _tell(
                        session,
                        scope,
                        conversation,
                        prefix + meeting_message(meeting, language),
                        f"pi-meeting-auto-remind:{conversation.id}:{meeting.get('starts_at')}",
                    )
                    if sent:
                        sends.append(sent)
                    customer = await WorkspaceRepository(session, Customer, scope).find(
                        Customer.id == conversation.customer_id
                    )
                    name = (customer.name if customer else "") or "a customer"
                    await notify(
                        session,
                        scope,
                        "pi.meeting_soon",
                        f"Meeting with {name} at {start:%I:%M %p}",
                        f"{meeting.get('label')}. "
                        + (f"Join: {meeting['link']}" if meeting.get("link") else "")
                        + ("" if sent else " The customer wasn't reminded on WhatsApp."),
                        link="/pi/meetings",
                        permission="pi.read",
                        dedupe_key=f"pi-meeting-soon:{conversation.id}:{meeting.get('starts_at')}",
                    )
                    meeting["auto_reminded"] = meeting.get("starts_at")
                    conversation.service_brief = {
                        **(conversation.service_brief or {}),
                        "meeting": meeting,
                    }
                    reminded += 1
                await session.commit()
            except Exception:  # noqa: BLE001 - one workspace never stops the others
                logger.warning("pi_meeting_reminders_failed", exc_info=True)
                await session.rollback()
                continue
        await enqueue_sends(ctx, sends)
    return reminded


# ---- book from a customer's profile -----------------------------------------------------


class BookInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    customer_id: UUID
    starts_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")  # business time
    duration_minutes: int = Field(default=30, ge=10, le=480)
    how: Literal["google_meet", "video", "link", "in_person"] = "google_meet"
    link: str = Field(default="", max_length=500)
    place: str = Field(default="", max_length=300)
    note: str = Field(default="", max_length=1000)  # what it's about, told to the customer


@router.post("/book")
async def book(data: BookInput, request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """The team books a meeting for any customer (from their profile): pi makes the
    link (Google Meet, its own video link, theirs, or a place), the meeting goes on the
    board, and pi sends the customer the time and link on WhatsApp in their language."""
    from app.modules.pi_saas.deals import _contact, _conversation
    from app.modules.pi_saas.meetings import MeetingInput, arrange, runtime_for
    from app.modules.pi_saas.requests import enqueue_reply, raise_request

    await require_pi(session, scope, "pi.inbox.reply")
    customer = await WorkspaceRepository(session, Customer, scope).get(data.customer_id)
    conversation = await session.scalar(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .where(PiConversation.customer_id == customer.id, PiConversation.status == "open")
        .order_by(PiConversation.last_message_at.desc().nulls_last())
        .limit(1)
    )
    if conversation is None:
        contact = _contact(customer)
        conversation = await _conversation(session, scope, customer, contact) if contact else None
    if conversation is None:
        raise BusinessRuleViolation(
            "NO_WHATSAPP",
            "This customer has no WhatsApp number (or WhatsApp isn't connected), so pi "
            "can't send them the meeting. Add their number first.",
        )
    if conversation.customer_id is None:
        conversation.customer_id = customer.id
    who = scope.actor_label or "The team"
    row = await raise_request(
        session,
        scope,
        conversation_id=conversation.id,
        customer_id=customer.id,
        kind="meeting",
        question=f"{who} booked a meeting from the customer page."
        + (f" About: {data.note}" if data.note else ""),
        title="Meeting booked by the team",
    )
    await session.flush()
    row = await arrange(
        session,
        scope,
        runtime_for(request),
        row.id,
        MeetingInput(**data.model_dump(exclude={"customer_id"})),
        max_bytes=request.app.state.settings.knowledge_upload_max_bytes,
    )
    window = conversation.last_inbound_at is not None and (
        conversation.last_inbound_at > datetime.now(UTC) - WINDOW
    )
    await record(
        session,
        "pi.meeting_booked",
        scope=scope,
        entity_type="customer",
        entity_id=customer.id,
        details={"starts_at": data.starts_at, "how": data.how},
    )
    await session.commit()
    await enqueue_reply(request, row.id)  # pi sends the time and link word for word
    meeting = (conversation.service_brief or {}).get("meeting") or {}
    return {
        "ok": True,
        "conversation_id": conversation.id,
        "label": meeting.get("label"),
        "link": meeting.get("link") or "",
        "told_customer": window,
    }
