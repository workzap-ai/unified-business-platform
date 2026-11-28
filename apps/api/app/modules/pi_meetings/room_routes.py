"""pi's own video rooms (`/api/v1/pi/meeting-intel/rooms`): staff and customers meet in the browser.

A person with the record permission opens a room and confirms that everyone will be told the call is
transcribed. Staff join from the app with a token made for their login; a customer joins from the
link staff send (the same link and the same consent as the audio link), and gets a token made for
THEIR guest id, good for this one call and for two hours. The browser never sends words to us: the
video provider hears the call, and after it ends hands back the transcript, which goes to the same
analysis and review as any other meeting. Nothing reaches the Problem Map until a person approves.

pi listens through the transcript. It speaks in a room only when the host switches it on for that
room (`/room/pi`), the workspace has `brain.meeting_room_speak`, and the separate room agent service
is running; the host can mute it at any moment and the agent reads the mute within seconds.

Off unless the workspace has `brain.meeting_intel` AND `brain.meeting_room` on AND the provider's
key and secret are configured. Guests also need `brain.meeting_guests` (the link itself).

The callback route has no login. Its only control is the provider's signature, checked before the
body is read as JSON; with no secret configured it refuses everything.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import (
    agent_store,
    agents,
    native_ingest,
    room_agent_claim,
    room_live,
    room_present,
)
from app.modules.pi_meetings import room_limits as limits
from app.modules.pi_meetings.guest_routes import (
    GuestToken,
    _guest_for,
    _limit,
    system_scope,
)
from app.modules.pi_meetings.models import PiMeeting, PiMeetingParticipant, PiMeetingRoom
from app.modules.pi_meetings.recording_routes import ISO_LANGUAGE
from app.modules.pi_meetings.room_provider import (
    CALL_TYPE,
    GZIP_MAGIC,
    RoomProvider,
    RoomProviderError,
    build_provider,
    guest_user,
    new_call_id,
    plain_body,
    staff_user,
    verify_signature,
)
from app.modules.pi_meetings.routes import _customer_ok, _gate, _meeting, _view
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])
public_router = APIRouter(prefix="/public/meeting-room", tags=["public"])
webhook_router = APIRouter(prefix="/public/stream", tags=["public"])

MAX_BODY = 1_000_000
STAFF_TTL_S = 2 * 3600
GUEST_TTL_S = 2 * 3600
LIVE = ("created", "live")


class PiInput(BaseModel):
    """What the host tells pi to do in this room. A field left out is left as it was."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["off", "speak"] | None = None
    muted: bool | None = None
    intake: bool | None = None


class RoomInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    customer_id: UUID | None = None
    language: str = Field(default="", max_length=12)
    # the person opening the room confirms everyone in it will be told it is transcribed
    consent: bool = False
    # the agent for this meeting: a built-in key or a custom agent's id (None: pi itself)
    agent_key: str | None = Field(default=None, max_length=40)


def provider_for(request: Request) -> RoomProvider | None:
    """The configured provider, or None. Tests assign `app.state.room_provider` instead."""
    override = getattr(request.app.state, "room_provider", None)
    if override is not None:
        return override  # type: ignore[no-any-return]
    return build_provider(request.app.state.settings, request.app.state.http)


def api_key(request: Request) -> str:
    return str(request.app.state.settings.stream_api_key or "")


def webhook_secret(request: Request) -> str | None:
    secret = request.app.state.settings.stream_api_secret
    return secret.get_secret_value() if secret is not None else None


async def room_enabled(session: Any, scope: WorkspaceScope) -> bool:
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    return brain.get("meeting_intel") is True and brain.get("meeting_room") is True


async def audio_enabled(session: Any, scope: WorkspaceScope) -> bool:
    """Each voice is recorded briefly, to write the transcript with our own speech-to-text."""
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    return await room_enabled(session, scope) and brain.get("meeting_room_audio") is True


async def _require_room(session: Any, scope: WorkspaceScope) -> None:
    if not await room_enabled(session, scope):
        raise BusinessRuleViolation(
            "MEETING_ROOM_OFF", "Video rooms are not switched on for this workspace", 403
        )
    await _not_paused(session, scope)


async def _not_paused(session: Any, scope: WorkspaceScope) -> None:
    if await limits.killed(session, scope):
        raise BusinessRuleViolation(
            "MEETING_ROOM_PAUSED", "Video rooms are paused for this workspace", 503
        )


async def _seat(
    session: Any, scope: WorkspaceScope, meeting_id: UUID, stream_user: str
) -> PiMeetingParticipant | None:
    """The person's existing seat in this room, or None for a new person; a new person is refused
    once the room is full."""
    seat = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.stream_user_id == stream_user,
        )
    )
    if seat is None and await limits.people_in(session, scope, meeting_id) >= limits.MAX_PEOPLE:
        raise BusinessRuleViolation(
            "MEETING_ROOM_FULL", f"This room already has {limits.MAX_PEOPLE} people", 409
        )
    return seat  # type: ignore[no-any-return]


def _view_room(room: PiMeetingRoom) -> dict[str, Any]:
    return {
        "id": str(room.id),
        "meeting_id": str(room.meeting_id),
        "state": room.state,
        "live": room.state in LIVE,
        "audio": room.audio,
        "present": room_present.summary(room.present),
        "transcript_state": room.transcript_state,
        "lines": room.lines,
        "started_at": room.started_at.isoformat() if room.started_at else None,
        "ended_at": room.ended_at.isoformat() if room.ended_at else None,
        "pi": {
            "mode": room.pi_mode,
            "muted": room.pi_muted,
            "intake": room.pi_intake,
            # an agent has answered within its lease: pi is really in the room
            "here": bool(
                room.agent_id
                and room.agent_beat_at
                and datetime.now(UTC) - room.agent_beat_at
                < timedelta(seconds=room_agent_claim.LEASE_S)
            ),
        },
    }


async def room_of(session: Any, scope: WorkspaceScope, meeting_id: UUID) -> PiMeetingRoom | None:
    return await session.scalar(  # type: ignore[no-any-return]
        select(PiMeetingRoom).where(
            PiMeetingRoom.tenant_id == scope.tenant_id,
            PiMeetingRoom.environment_id == scope.environment_id,
            PiMeetingRoom.meeting_id == meeting_id,
        )
    )


def _unconfigured() -> BusinessRuleViolation:
    return BusinessRuleViolation(
        "MEETING_ROOM_UNCONFIGURED", "The video room service is not set up yet", 503
    )


def _failed(error: RoomProviderError) -> BusinessRuleViolation:
    return BusinessRuleViolation(error.code, error.message, error.status)


async def delete_calls(request: Request, call_ids: list[str]) -> None:
    """Remove calls (with their transcripts and recordings) at the provider. Raises
    BusinessRuleViolation when it cannot: an erase must not end with the words still held there."""
    if not call_ids:
        return
    provider = provider_for(request)
    if provider is None:
        raise BusinessRuleViolation(
            "ROOM_DELETE_UNAVAILABLE",
            "This meeting was held in a video room that cannot be removed from the video room "
            "service right now, so nothing was erased; set the service up again and retry",
            409,
        )
    try:
        for call_id in call_ids:
            await provider.delete_call(call_id)
    except RoomProviderError:
        raise BusinessRuleViolation(
            "ROOM_DELETE_UNAVAILABLE",
            "The video room service could not remove this meeting's call, so nothing was erased; "
            "try again in a moment",
            409,
        ) from None


@router.get("/rooms/options")
async def room_options(scope: Scope, session: Session) -> dict[str, bool]:
    """What a new room will do in this workspace, so the page can tell people before they agree."""
    await _gate(session, scope, "pi.meetings.record")
    await _require_room(session, scope)
    return {"audio": await audio_enabled(session, scope)}


@router.post("/rooms", status_code=201)
async def open_room(
    data: RoomInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    await _require_room(session, scope)
    provider = provider_for(request)
    if provider is None:
        raise _unconfigured()
    if not data.consent:
        raise BusinessRuleViolation(
            "MEETING_CONSENT_REQUIRED",
            "Confirm that everyone in the room will be told the call is transcribed",
            422,
        )
    language = data.language.strip().lower()
    if language and not ISO_LANGUAGE.match(language):
        raise BusinessRuleViolation("MEETING_LANGUAGE_INVALID", "Use a language code like en", 422)
    if data.customer_id is not None:
        await _customer_ok(session, scope, data.customer_id)
    agent_key = None
    if data.agent_key and data.agent_key != agents.DEFAULT_KEY:
        agent_key = await agent_store.valid_key(session, scope, data.agent_key)
    allowance = await limits.month_allowance(session, scope)
    if await limits.month_minutes_used(session, scope) >= allowance:
        raise BusinessRuleViolation(
            "MEETING_ROOM_MONTH_LIMIT",
            f"This month's {allowance} minutes of video room time are used up",
            409,
        )
    audio = await audio_enabled(session, scope)
    now = datetime.now(UTC)
    meeting = PiMeeting(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=data.customer_id,
        title=redacted(data.title, 200),
        source="native",
        language=language,
        agent_key=agent_key,
        consent_at=now,
        consent_by=scope.user_id,
        consent_note=(
            "Host confirmed everyone in the room is told the call is transcribed and each voice "
            "is recorded briefly to write the transcript"
            if audio
            else "Host confirmed everyone in the room is told the call is transcribed"
        ),
        held_at=now,
        created_by=scope.user_id,
    )
    session.add(meeting)
    await session.flush()
    room = PiMeetingRoom(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting.id,
        provider=provider.name,
        call_id=new_call_id(),
        audio=audio,
        created_by=scope.user_id,
    )
    session.add(room)
    await session.flush()
    try:
        await provider.create_call(room.call_id, language=language, audio=audio)
    except RoomProviderError as error:
        room.state = "failed"
        meeting.status = "failed"
        meeting.failure_reason = error.message
        await record(
            session,
            "pi.meeting_room_failed",
            scope=scope,
            entity_type="pi_meeting",
            entity_id=meeting.id,
            details={"code": error.code},
        )
        await session.commit()
        raise _failed(error) from None
    await record(
        session,
        "pi.meeting_room_opened",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"provider": provider.name},
    )
    await session.commit()
    return {"meeting": _view(meeting), "room": _view_room(room)}


async def _pull(
    session: Any, scope: WorkspaceScope, meeting: PiMeeting, room: PiMeetingRoom, p: RoomProvider
) -> bool:
    """Fetch the finished transcript from the provider (when its callback did not come, or has not
    yet) and store it. False when it is not ready."""
    try:
        rows = await p.transcript(room.call_id)
    except RoomProviderError:
        return False
    if rows is None:
        return False
    await native_ingest.finish_transcript(session, scope, meeting, room, rows)
    return True


@router.get("/{meeting_id}/room")
async def room_status(
    meeting_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Where the room is. Once the call has ended and the transcript has not arrived, it also asks
    the provider, so the page is right even if the provider's callback is not set up."""
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None:
        return {"room": None}
    provider = provider_for(request)
    # a room that records voices is finished by the worker, from the audio, not from here
    if (
        room.state == "ended"
        and room.transcript_state in ("none", "pending")
        and provider
        and not room.audio
    ):
        if await _pull(session, scope, meeting, room, provider):
            await session.commit()
    people = (
        await session.scalars(
            select(PiMeetingParticipant)
            .where(
                PiMeetingParticipant.tenant_id == scope.tenant_id,
                PiMeetingParticipant.environment_id == scope.environment_id,
                PiMeetingParticipant.meeting_id == meeting.id,
                PiMeetingParticipant.stream_user_id.is_not(None),
            )
            .order_by(PiMeetingParticipant.created_at)
        )
    ).all()
    return {
        "room": _view_room(room),
        "meeting_status": meeting.status,
        "people": [
            {
                "id": str(p.id),
                "label": p.label,
                "staff": p.role == "staff",
                "removed": p.removed_at is not None,
                "muted": p.muted_at is not None,
            }
            for p in people
        ],
        "limits": {"minutes": limits.MAX_CALL_MINUTES, "people": limits.MAX_PEOPLE},
    }


@router.get("/{meeting_id}/room/live")
async def room_live_view(
    meeting_id: UUID, scope: Scope, session: Session, after: int = 0
) -> dict[str, Any]:
    """What changed in the call's live view since `after`: captions with their translation and,
    for staff only, pi's tips and notes. Polled every couple of seconds while the room is open."""
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None:
        raise HTTPException(status_code=404)
    live_on, copilot_on = await room_agent_claim.live_flags(session, scope)
    out = room_live.view(room.live, max(0, after), staff=copilot_on)
    out["enabled"] = {"live": live_on, "copilot": copilot_on}
    return out


class KeepNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: int = Field(ge=1)


@router.post("/{meeting_id}/room/live/keep")
async def keep_note(
    meeting_id: UUID, body: KeepNote, scope: Scope, session: Session
) -> dict[str, Any]:
    """Staff keep one of pi's live notes: it becomes a DRAFT finding of the meeting (nothing is
    approved or sent), to be reviewed with all the others. Keeping it twice makes one finding."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None:
        raise HTTPException(status_code=404)
    note = next(
        (
            tip
            for tip in room_live.normal(room.live)["tips"]
            if tip["n"] == body.note and tip["kind"] == "note"
        ),
        None,
    )
    if note is None:
        raise HTTPException(status_code=404)
    created = await room_live.keep(session, scope, meeting.id, note)
    await record(
        session,
        "pi.meeting_room_note_kept",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"note": body.note, "created": created},
    )
    await session.commit()
    return {"kept": True, "created": created}


@router.post("/{meeting_id}/room/people/{participant_id}/remove")
async def remove_person(
    meeting_id: UUID, participant_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Take a guest out of a live call. They are blocked at the video service and cannot get a new
    token. Staff cannot be removed here; to close the call for everyone, end it."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None or room.state not in LIVE:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    person = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting.id,
            PiMeetingParticipant.id == participant_id,
            PiMeetingParticipant.stream_user_id.is_not(None),
        )
    )
    if person is None:
        raise HTTPException(status_code=404)
    if person.role == "staff":
        raise BusinessRuleViolation("MEETING_ROOM_STAFF", "Staff cannot be removed here", 409)
    provider = provider_for(request)
    if provider is None:
        raise _unconfigured()
    try:
        await provider.block_user(room.call_id, str(person.stream_user_id))
    except RoomProviderError as error:
        raise _failed(error) from None
    person.removed_at = person.removed_at or datetime.now(UTC)
    await record(
        session,
        "pi.meeting_room_person_removed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"participant_id": str(person.id)},
    )
    await session.commit()
    return {"removed": True}


class MuteBody(BaseModel):
    muted: bool


@router.post("/{meeting_id}/room/people/{participant_id}/mute")
async def mute_person(
    meeting_id: UUID,
    participant_id: UUID,
    body: MuteBody,
    request: Request,
    scope: Scope,
    session: Session,
) -> dict[str, Any]:
    """Hold one guest muted in a live call, or let them speak again. The microphone is switched
    off at the video service and the right to switch it on is taken away until the host undoes it.
    Staff cannot be muted here (the host mutes themselves), and pi has its own mute."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None or room.state not in LIVE:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    person = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting.id,
            PiMeetingParticipant.id == participant_id,
            PiMeetingParticipant.stream_user_id.is_not(None),
        )
    )
    if person is None:
        raise HTTPException(status_code=404)
    if person.role == "staff":
        raise BusinessRuleViolation("MEETING_ROOM_STAFF", "Staff cannot be muted here", 409)
    if person.removed_at is not None:
        raise BusinessRuleViolation("MEETING_ROOM_REMOVED", "That person was removed", 409)
    provider = provider_for(request)
    if provider is None:
        raise _unconfigured()
    try:
        await provider.mute_user(room.call_id, str(person.stream_user_id), body.muted)
    except RoomProviderError as error:
        raise _failed(error) from None
    person.muted_at = datetime.now(UTC) if body.muted else None
    await record(
        session,
        "pi.meeting_room_person_muted" if body.muted else "pi.meeting_room_person_unmuted",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"participant_id": str(person.id)},
    )
    await session.commit()
    return {"muted": body.muted}


@router.post("/{meeting_id}/room/token")
async def staff_token(
    meeting_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """A token for the logged-in person to join this room's call. It carries their staff id, so the
    transcript says who spoke."""
    await _gate(session, scope, "pi.meetings.record")
    await _require_room(session, scope)
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    provider = provider_for(request)
    if provider is None:
        raise _unconfigured()
    if room is None or room.state not in LIVE or scope.user_id is None:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    stream_user = staff_user(scope.user_id)
    await _seat(session, scope, meeting.id, stream_user)
    person = await native_ingest.participant_for(
        session, scope, meeting.id, stream_user, label="Staff", role="staff"
    )
    person.mapped_user_id = person.mapped_user_id or scope.user_id
    await session.commit()
    return {
        "api_key": api_key(request),
        "call_type": CALL_TYPE,
        "call_id": room.call_id,
        "user_id": stream_user,
        "name": person.label,
        "token": provider.user_token(stream_user, room.call_id, ttl_s=STAFF_TTL_S),
        "expires_in": STAFF_TTL_S,
    }


@router.post("/{meeting_id}/room/pi")
async def set_pi(meeting_id: UUID, body: PiInput, scope: Scope, session: Session) -> dict[str, Any]:
    """The host decides whether pi speaks in this room, mutes it, or lets it lead with a lone
    customer. Muting is always allowed; switching speech on needs the workspace's speech flag."""
    await _gate(session, scope, "pi.meetings.record")
    await _require_room(session, scope)
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None or room.state not in LIVE:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    if body.mode == "speak" and not await room_agent_claim.workspace_allows(session, scope):
        raise BusinessRuleViolation(
            "MEETING_ROOM_SPEAK_OFF", "pi speaking is not switched on for this workspace", 403
        )
    if body.mode is not None:
        room.pi_mode = body.mode
    if body.muted is not None:
        room.pi_muted = body.muted
    if body.intake is not None:
        room.pi_intake = body.intake
    await record(
        session,
        "pi.meeting_room_pi_set",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"mode": room.pi_mode, "muted": room.pi_muted, "intake": room.pi_intake},
    )
    await session.commit()
    return {"room": _view_room(room)}


@router.post("/{meeting_id}/room/end")
async def end_room(
    meeting_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """End the call for everyone. Only through here: no one in the room can end it."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    provider = provider_for(request)
    if room is None or room.state not in LIVE:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    if provider is None:
        raise _unconfigured()
    try:
        await provider.end_call(room.call_id)
    except RoomProviderError as error:
        raise _failed(error) from None
    room.state = "ended"
    room.ended_at = room.ended_at or datetime.now(UTC)
    room.transcript_state = "pending"
    room.present = room_present.stop(room.present)  # the slides are not kept after the call
    await record(
        session,
        "pi.meeting_room_ended",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"provider": room.provider},
    )
    await session.commit()
    return {"room": _view_room(room)}


@public_router.get("/live")
async def guest_live(
    token: GuestToken, request: Request, session: Session, after: int = 0
) -> dict[str, Any]:
    """The live captions for a guest, with the translation. A guest never gets pi's tips or notes
    for staff. The guest token is the only credential; polling has its own, wider, limits."""
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "meeting-room-live", ip, 6000, 3600) or not (
        await rate_limit.hit(request, "meeting-room-live-token", token, 2400, 3600)
    ):
        raise BusinessRuleViolation("RATE_LIMITED", "Too many requests. Try again shortly.", 429)
    found = await _guest_for(session, token)
    if found is None:
        raise HTTPException(status_code=404)
    guest, meeting, scope = found
    room = await room_of(session, scope, meeting.id)
    if room is None or not await room_enabled(session, scope):
        raise HTTPException(status_code=404)
    live_on, _ = await room_agent_claim.live_flags(session, scope)
    out = room_live.view(room.live, max(0, after), staff=False)
    out["enabled"] = {"live": live_on, "copilot": False}
    return out


@public_router.post("/token")
async def guest_token(token: GuestToken, request: Request, session: Session) -> dict[str, Any]:
    """A guest who joined by link (and agreed to be recorded) asks to enter the room. The token is
    made for their own guest id and for this one call."""
    await _limit(request, token, "room", 60, 30)
    found = await _guest_for(session, token)
    if found is None:
        raise HTTPException(status_code=404)
    guest, meeting, scope = found
    provider = provider_for(request)
    room = await room_of(session, scope, meeting.id)
    if provider is None or room is None or not await room_enabled(session, scope):
        raise HTTPException(status_code=404)
    await _not_paused(session, scope)
    if room.state not in LIVE:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    stream_user = guest_user(guest.participant_id)
    person = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.id == guest.participant_id,
        )
    )
    if person is None:
        raise HTTPException(status_code=404)
    if person.removed_at is not None:
        raise BusinessRuleViolation(
            "MEETING_ROOM_REMOVED", "You were removed from this room by the host", 403
        )
    await _seat(session, scope, meeting.id, stream_user)
    person.stream_user_id = stream_user  # the person made when they joined is the room's speaker
    await session.commit()
    return {
        "api_key": api_key(request),
        "call_type": CALL_TYPE,
        "call_id": room.call_id,
        "user_id": stream_user,
        "name": person.label,
        "token": provider.user_token(stream_user, room.call_id, ttl_s=GUEST_TTL_S),
        "expires_in": GUEST_TTL_S,
    }


@webhook_router.post("/webhook")
async def webhook(request: Request, session: Session) -> dict[str, bool]:
    """The provider's callbacks. Checked by signature before anything is read from the body."""
    secret = webhook_secret(request)
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY:
        raise BusinessRuleViolation("STREAM_BODY_TOO_LARGE", "Too large", 413)
    body = await request.body()
    if secret is None or len(body) > MAX_BODY:
        raise BusinessRuleViolation("STREAM_NOT_CONFIGURED", "Not available", 503)
    plain = plain_body(body, MAX_BODY)  # the provider may gzip it and signs the unzipped bytes
    if plain is None or not verify_signature(secret, request.headers.get("x-signature", ""), plain):
        logger.warning(
            "stream_signature_invalid",
            extra={
                "gzip": body[:2] == GZIP_MAGIC,
                "encoding": request.headers.get("content-encoding", "")[:20],
                "has_signature": bool(request.headers.get("x-signature")),
                "length": len(body),
            },
        )
        raise BusinessRuleViolation("STREAM_SIGNATURE_INVALID", "Invalid signature", 401)
    try:
        payload = json.loads(plain)
    except ValueError:
        return {"ok": True}  # signed but not ours to understand: do not make the provider retry
    kind = payload.get("type") if isinstance(payload, dict) else None
    cid = payload.get("call_cid") if isinstance(payload, dict) else None
    if not isinstance(kind, str) or not isinstance(cid, str) or ":" not in cid:
        return {"ok": True}
    call_type, _, call_id = cid.partition(":")
    if call_type != CALL_TYPE:
        return {"ok": True}
    room = await session.scalar(
        select(PiMeetingRoom).where(
            PiMeetingRoom.provider == "stream", PiMeetingRoom.call_id == call_id
        )
    )
    if room is None:
        return {"ok": True}  # not a room of ours (another environment, or already erased)
    scope = system_scope(room.tenant_id, room.environment_id)
    if not await room_enabled(session, scope):
        return {"ok": True}
    meeting = await session.scalar(
        select(PiMeeting).where(
            PiMeeting.tenant_id == room.tenant_id,
            PiMeeting.environment_id == room.environment_id,
            PiMeeting.id == room.meeting_id,
        )
    )
    if meeting is None:
        return {"ok": True}
    now = datetime.now(UTC)
    if kind == "call.session_started" and room.state in LIVE:
        room.state = "live"
        room.started_at = room.started_at or now
        if meeting.recording_started_at is None:
            meeting.recording_started_at = now
    elif kind == "call.session_ended":
        if room.state != "ended":
            room.state = "ended"
            room.ended_at = room.ended_at or now
        if room.transcript_state == "none":
            room.transcript_state = "pending"
    elif kind == "call.transcription_ready" and room.transcript_state != "done":
        provider = provider_for(request)
        item = payload.get("call_transcription")
        url = str(item.get("url") or "") if isinstance(item, dict) else ""
        if provider is not None:
            try:
                rows = await provider.transcript(room.call_id, url)
            except RoomProviderError:
                rows = None
            if rows is not None and room.audio:
                # the provider's captions are only a fallback for a room that records voices:
                # kept as lines, and the worker writes the real transcript from the audio
                await native_ingest.add_lines(session, scope, meeting, rows)
            elif rows is not None:
                await native_ingest.finish_transcript(session, scope, meeting, room, rows)
    await session.commit()
    return {"ok": True}
