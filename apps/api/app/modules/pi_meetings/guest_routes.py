"""Meeting links (PMB-4): staff make a link, other people open it and add their own microphone.

Staff routes (`/api/v1/pi/meeting-intel/{id}/invite`, `.../guests`) need `pi.meetings.record`. The
public routes (`/api/v1/public/meeting-join/{token}`) have no session: the token in the link is the
only key, it is stored only as a hash, and it can do exactly two things: show what the meeting is
called, and (with the person's consent) join it. A guest receives their own token, which is later
accepted for sending audio parts of THIS meeting and nothing else; no token reads a transcript.

Everything is off unless `response_rules.brain.meeting_guests` is true (default off), and an
invite works only while its meeting is open for audio, the invite has not expired or been revoked,
and fewer than `max_guests` people have joined.
"""

import hashlib
import secrets
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Request,
    Response,
    UploadFile,
)
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import GatewayUnavailable, MediaValidationError
from app.ai.manager import build_llm_manager
from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingGuest,
    PiMeetingInsight,
    PiMeetingInvite,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.modules.pi_meetings.recording_routes import (
    GUEST_RANGE_START,
    HOST_PART_MS,
    ISO_LANGUAGE,
    MAX_PARTS,
    PART_STRIDE,
    _recordable,
    join_spoken_digits,
    split_sentences,
    timed,
)
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])
MAX_BODY_BYTES = 1_500_000  # a guest part is at most 1 MB of audio plus form overhead


class BoundedRoute(APIRoute):
    """Refuses an oversized body BEFORE it is read: multipart is parsed (and spooled to disk)
    before a handler runs, and these routes take no session, so anyone could send a huge body to
    a made-up token. (A body without a length is still capped by the read limit in the handler.)"""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_BODY_BYTES:
                raise BusinessRuleViolation(
                    "MEETING_AUDIO_TOO_LARGE", "This request is too large", 413
                )
            return await original(request)

        return handler


public_router = APIRouter(prefix="/public/meeting-join", tags=["public"], route_class=BoundedRoute)

TOKEN_PATTERN = r"^[A-Za-z0-9_-]{30,64}$"
Token = Annotated[str, Path(pattern=TOKEN_PATTERN)]
JOINABLE = frozenset({"created", "uploaded", "transcribing"})
MAX_NAME = 60
RESERVED_LABEL = "Speaker 1"  # the host's own lines: a guest can never take it
RESERVED_LABELS = frozenset({RESERVED_LABEL.lower(), "pi (ai)"})  # and pi's own speaker


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def system_scope(tenant_id: UUID, environment_id: UUID) -> WorkspaceScope:
    """The trusted context for work done for a link: scoped to the invite's own workspace."""
    return WorkspaceScope(
        tenant_id=tenant_id,
        environment_id=environment_id,
        permissions=frozenset(),
        actor_type="system",
        actor_label="meeting-guest",
    )


async def guests_enabled(session: AsyncSession, scope: WorkspaceScope) -> bool:
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    return brain.get("meeting_intel") is True and brain.get("meeting_guests") is True


async def voice_enabled(session: AsyncSession, scope: WorkspaceScope) -> bool:
    """pi may talk on links only when the workspace has switched on both links and voice."""
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    return await guests_enabled(session, scope) and brain.get("meeting_voice") is True


async def _require_enabled(session: AsyncSession, scope: WorkspaceScope) -> None:
    if not await guests_enabled(session, scope):
        raise BusinessRuleViolation(
            "MEETING_GUESTS_OFF", "Meeting links are not switched on for this workspace", 403
        )


# ---- staff: say when the recording began, make, read and revoke the link, remove a guest


class InviteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: int = Field(default=24, ge=1, le=168)
    max_guests: int = Field(default=10, ge=1, le=20)


async def _start_clock(session: AsyncSession, meeting: PiMeeting) -> None:
    """Start the meeting's clock if nobody has: one UPDATE that only succeeds while it is empty,
    so two callers at once cannot overwrite each other."""
    await session.execute(
        update(PiMeeting)
        .where(
            PiMeeting.tenant_id == meeting.tenant_id,
            PiMeeting.environment_id == meeting.environment_id,
            PiMeeting.id == meeting.id,
            PiMeeting.recording_started_at.is_(None),
        )
        .values(recording_started_at=datetime.now(UTC))
    )
    await session.refresh(meeting, ["recording_started_at"])


@router.post("/{meeting_id}/recording/start")
async def recording_started(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """The host's recorder says it has begun: the meeting's clock starts now (once). Everything
    said afterwards, by the host or a guest, is placed on this clock."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    if meeting.recording_started_at is None and meeting.status in JOINABLE:
        await _start_clock(session, meeting)
        await session.commit()
    started = meeting.recording_started_at
    return {"recording_started_at": started.isoformat() if started else None}


@router.post("/{meeting_id}/invite", status_code=201)
async def create_invite(
    meeting_id: UUID, data: InviteInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """Make a link for this meeting. The token is returned once and never again: only its hash is
    kept. A new link closes the previous ones."""
    await _gate(session, scope, "pi.meetings.record")
    await _require_enabled(session, scope)
    meeting = await _meeting(session, scope, meeting_id)
    if meeting.consent_at is None or meeting.status not in JOINABLE:
        raise BusinessRuleViolation(
            "MEETING_NOT_OPEN", "This meeting can no longer take more recordings", 409
        )
    await _recordable(session, scope, meeting)  # also refuses a meeting with an imported transcript
    now = datetime.now(UTC)
    for old in await _active_invites(session, scope, meeting.id, expired_too=True):
        old.revoked_at = now
    token = new_token()
    invite = PiMeetingInvite(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting.id,
        token_hash=digest(token),
        expires_at=now + timedelta(hours=data.hours),
        max_guests=data.max_guests,
        created_by=scope.user_id,
    )
    session.add(invite)
    await session.flush()
    await record(
        session,
        "pi.meeting_invite_created",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"hours": data.hours, "max_guests": data.max_guests},
    )
    await session.commit()
    return {"token": token, "expires_at": invite.expires_at.isoformat()}


async def _active_invites(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID, *, expired_too: bool = False
) -> list[PiMeetingInvite]:
    """The meeting's links that are not revoked: those still open for joining, or with
    `expired_too` also those past their expiry (whose guests keep sending until it is revoked)."""
    where = [
        PiMeetingInvite.tenant_id == scope.tenant_id,
        PiMeetingInvite.environment_id == scope.environment_id,
        PiMeetingInvite.meeting_id == meeting_id,
        PiMeetingInvite.revoked_at.is_(None),
    ]
    if not expired_too:
        where.append(PiMeetingInvite.expires_at > datetime.now(UTC))
    return list((await session.scalars(select(PiMeetingInvite).where(*where))).all())


@router.get("/{meeting_id}/invite")
async def invite_status(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Is a link open, until when, and who has joined (names as they gave them)."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    active = await _active_invites(session, scope, meeting.id)
    rows = (
        await session.execute(
            select(PiMeetingGuest, PiMeetingParticipant.label)
            .join(
                PiMeetingParticipant,
                (PiMeetingParticipant.id == PiMeetingGuest.participant_id)
                & (PiMeetingParticipant.tenant_id == PiMeetingGuest.tenant_id)
                & (PiMeetingParticipant.environment_id == PiMeetingGuest.environment_id),
            )
            .where(
                PiMeetingGuest.tenant_id == scope.tenant_id,
                PiMeetingGuest.environment_id == scope.environment_id,
                PiMeetingGuest.meeting_id == meeting.id,
            )
            .order_by(PiMeetingGuest.slot)
        )
    ).all()
    return {
        "enabled": await guests_enabled(session, scope),
        "open": bool(active),
        "expires_at": max(i.expires_at for i in active).isoformat() if active else None,
        "guests": [
            {
                "id": str(g.id),
                "slot": g.slot,
                "label": label,
                "joined_at": g.consent_at.isoformat(),
                "removed": g.removed_at is not None,
            }
            for g, label in rows
        ],
    }


@router.delete("/{meeting_id}/invite")
async def revoke_invite(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Close the link. People already in keep nothing they could read; their tokens stop working
    because a guest is accepted only while an open invite exists."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    now = datetime.now(UTC)
    closed = 0
    for invite in await _active_invites(session, scope, meeting.id, expired_too=True):
        invite.revoked_at = now
        closed += 1
    await record(
        session,
        "pi.meeting_invite_revoked",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"closed": closed},
    )
    await session.commit()
    return {"closed": closed}


@router.delete("/{meeting_id}/guests/{guest_id}")
async def remove_guest(
    meeting_id: UUID, guest_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    """Stop a guest sending more audio. What they already said stays in the transcript until the
    meeting is deleted."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    guest = await session.scalar(
        select(PiMeetingGuest).where(
            PiMeetingGuest.tenant_id == scope.tenant_id,
            PiMeetingGuest.environment_id == scope.environment_id,
            PiMeetingGuest.meeting_id == meeting.id,
            PiMeetingGuest.id == guest_id,
        )
    )
    if guest is None:
        raise HTTPException(status_code=404)
    guest.removed_at = guest.removed_at or datetime.now(UTC)
    await record(
        session,
        "pi.meeting_guest_removed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"slot": guest.slot},
    )
    await session.commit()
    return {"removed": True}


# ---- public: look at the link, join with consent


async def _limit(request: Request, token: str, bucket: str, per_ip: int, per_token: int) -> None:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(
        request, f"meeting-join-{bucket}", ip, per_ip, 3600
    ) or not await rate_limit.hit(request, f"meeting-join-{bucket}-token", token, per_token, 3600):
        raise BusinessRuleViolation("RATE_LIMITED", "Too many attempts. Try again later.", 429)


async def open_invite(
    session: AsyncSession, token: str
) -> tuple[PiMeetingInvite, PiMeeting, WorkspaceScope] | None:
    """The invite for a token, its meeting and a scope for its workspace, or None when anything is
    wrong (unknown, expired, revoked, feature off, meeting closed): the caller answers 404."""
    invite = await session.scalar(
        select(PiMeetingInvite).where(PiMeetingInvite.token_hash == digest(token))
    )
    now = datetime.now(UTC)
    if invite is None or invite.revoked_at is not None or invite.expires_at <= now:
        return None
    scope = system_scope(invite.tenant_id, invite.environment_id)
    if not await guests_enabled(session, scope):
        return None
    meeting = await session.scalar(
        select(PiMeeting).where(
            PiMeeting.tenant_id == invite.tenant_id,
            PiMeeting.environment_id == invite.environment_id,
            PiMeeting.id == invite.meeting_id,
        )
    )
    if meeting is None or meeting.consent_at is None or meeting.status not in JOINABLE:
        return None
    return invite, meeting, scope


@public_router.get("/{token}")
async def look(token: Token, request: Request, session: Session) -> dict[str, Any]:
    """What a person sees before joining: the meeting's name. Nothing else about it."""
    await _limit(request, token, "view", 60, 200)
    found = await open_invite(session, token)
    if found is None:
        raise HTTPException(status_code=404)
    _, meeting, scope = found
    return {
        "title": meeting.title,
        "pi_voice": meeting.pi_mode == "speak" and await voice_enabled(session, scope),
    }


class JoinInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=MAX_NAME)
    consent: bool = False


@public_router.post("/{token}", status_code=201)
async def join(token: Token, data: JoinInput, request: Request, session: Session) -> dict[str, Any]:
    """Join the meeting: the person agrees that their voice is recorded and transcribed, and gets
    their own token for sending audio. Without `consent: true` nothing is created."""
    await _limit(request, token, "join", 20, 40)
    if data.consent is not True:
        raise BusinessRuleViolation(
            "MEETING_CONSENT_REQUIRED", "You need to agree before your voice is recorded", 422
        )
    found = await open_invite(session, token)
    if found is None:
        raise HTTPException(status_code=404)
    invite, meeting, scope = found
    # two people joining at once must not both take the last place or the same slot
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:meeting))"), {"meeting": f"join:{meeting.id}"}
    )
    taken = set(
        (
            await session.scalars(
                select(PiMeetingGuest.slot).where(
                    PiMeetingGuest.tenant_id == scope.tenant_id,
                    PiMeetingGuest.environment_id == scope.environment_id,
                    PiMeetingGuest.meeting_id == meeting.id,
                )
            )
        ).all()
    )
    count = await session.scalar(
        select(func.count())
        .select_from(PiMeetingGuest)
        .where(
            PiMeetingGuest.tenant_id == scope.tenant_id,
            PiMeetingGuest.environment_id == scope.environment_id,
            PiMeetingGuest.invite_id == invite.id,
        )
    )
    slot = next((n for n in range(1, 21) if n not in taken), None)
    if slot is None or int(count or 0) >= invite.max_guests:
        raise BusinessRuleViolation("MEETING_FULL", "This meeting link is full", 409)
    name = redacted(data.name.strip(), MAX_NAME) if data.name.strip() else ""
    label = await _free_label(session, scope, meeting.id, name or f"Participant {slot}", slot)
    participant = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting.id,
        label=label,
        role="unknown",  # a guest is never assumed to be the customer
    )
    session.add(participant)
    await session.flush()
    guest_token = new_token()
    session.add(
        PiMeetingGuest(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=meeting.id,
            invite_id=invite.id,
            participant_id=participant.id,
            slot=slot,
            name=name,
            token_hash=digest(guest_token),
            consent_at=datetime.now(UTC),
        )
    )
    await record(
        session,
        "pi.meeting_guest_joined",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"slot": slot},
    )
    await session.commit()
    return {"guest_token": guest_token, "slot": slot, "label": label}


async def _free_label(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID, wanted: str, slot: int
) -> str:
    """A speaker label no one else in the meeting has (labels are unique per meeting)."""
    label = wanted[:MAX_NAME]
    for n in range(0, 25):
        candidate = label if n == 0 else f"{label[: MAX_NAME - 6]} ({slot + n - 1})"
        exists = await session.scalar(
            select(PiMeetingParticipant.id).where(
                PiMeetingParticipant.tenant_id == scope.tenant_id,
                PiMeetingParticipant.environment_id == scope.environment_id,
                PiMeetingParticipant.meeting_id == meeting_id,
                func.lower(PiMeetingParticipant.label) == candidate.lower(),
            )
        )
        if exists is None and candidate.lower() not in RESERVED_LABELS:
            return candidate
    return f"Participant {slot}"


# ---- public: a guest sends their own audio

GUEST_PART_MS = 60_000  # the page cuts a guest's recording into one-minute parts
GUEST_PART_SLACK_MS = 30_000
GUEST_MAX_BYTES = 1024 * 1024  # a minute at the page's bitrate is under 300 KB
GUEST_MAX_TEXT = 12_000
GUEST_SEGMENTS = 6  # lines a one-minute part can become: its slice of the ordinal range
GUEST_MIMES = frozenset({"audio/webm", "audio/mp4", "audio/ogg"})
GUEST_MAX_SEQ = 600  # ten hours of one-minute parts
GUEST_MIN_GAP_S = 20  # a new part this soon after the last is not a person talking: it is refused
GUEST_SEQ_SLACK = 5  # parts a guest may be ahead of the minutes they have actually been in
GUEST_TTL = timedelta(hours=12)  # a guest token is good for a long meeting, not for days
WINDOW_MS = HOST_PART_MS  # the host's part length: guest lines sort into the same window
MINUTES = max(
    1, WINDOW_MS // GUEST_PART_MS
)  # guest-minute slots in a window (1 while both are a minute)


def guest_base(offset_ms: int, slot: int) -> int | None:
    """The first segment number for this guest's part. Lines are numbered inside the stretch of the
    host's part (window) in which they were spoken, minute first and guest second, so within
    the guests' half of a window the order is the order they spoke, and a guest part replaces only
    itself (the number carries the guest's own slot). None when the time is outside what a meeting
    can hold."""
    window, within = divmod(offset_ms, WINDOW_MS)
    if window >= MAX_PARTS or not 1 <= slot <= 20:
        return None
    minute = min(within // GUEST_PART_MS, MINUTES - 1)
    own = minute * 20 + (slot - 1)
    return window * PART_STRIDE + GUEST_RANGE_START + own * GUEST_SEGMENTS


def pack(sentences: list[str], into: int) -> list[str]:
    """At most `into` lines, sentences kept whole and in order."""
    if len(sentences) <= into:
        return sentences
    size = -(-len(sentences) // into)
    return [" ".join(sentences[i : i + size]) for i in range(0, len(sentences), size)]


async def _guest_for(
    session: AsyncSession, token: str
) -> tuple[PiMeetingGuest, PiMeeting, WorkspaceScope] | None:
    """The guest a token belongs to, with their meeting, while everything still allows it: not
    removed, not older than `GUEST_TTL`, the link not revoked (an expired link only stops new people
    joining), the meeting open, the workspace flag on. None otherwise (the caller answers 404)."""
    guest = await session.scalar(
        select(PiMeetingGuest).where(PiMeetingGuest.token_hash == digest(token))
    )
    if guest is None or guest.removed_at is not None:
        return None
    if datetime.now(UTC) - guest.consent_at > GUEST_TTL:
        return None
    scope = system_scope(guest.tenant_id, guest.environment_id)
    invite = await session.scalar(
        select(PiMeetingInvite).where(
            PiMeetingInvite.tenant_id == guest.tenant_id,
            PiMeetingInvite.environment_id == guest.environment_id,
            PiMeetingInvite.id == guest.invite_id,
        )
    )
    if invite is None or invite.revoked_at is not None or not await guests_enabled(session, scope):
        return None
    meeting = await session.scalar(
        select(PiMeeting).where(
            PiMeeting.tenant_id == guest.tenant_id,
            PiMeeting.environment_id == guest.environment_id,
            PiMeeting.id == guest.meeting_id,
        )
    )
    if meeting is None or meeting.consent_at is None or meeting.status not in JOINABLE:
        return None
    return guest, meeting, scope


GuestToken = Annotated[str, Header(alias="X-Guest-Token", pattern=TOKEN_PATTERN)]


@public_router.post("/guest/leave")
async def guest_leave(token: GuestToken, request: Request, session: Session) -> dict[str, Any]:
    """The guest stops: their token no longer sends anything. What they already said stays in the
    transcript (only the host's team can delete it, by deleting the meeting)."""
    await _limit(request, token, "leave", 60, 20)
    guest = await session.scalar(
        select(PiMeetingGuest).where(PiMeetingGuest.token_hash == digest(token))
    )
    if guest is None:
        raise HTTPException(status_code=404)
    if guest.removed_at is None:
        guest.removed_at = datetime.now(UTC)
        await session.commit()
    return {"left": True}


@public_router.post("/guest/parts")
async def guest_part(
    token: GuestToken,
    request: Request,
    session: Session,
    file: Annotated[UploadFile, File()],
    seq: Annotated[int, Form(ge=0, lt=GUEST_MAX_SEQ)],
    duration_ms: Annotated[int, Form(ge=1, le=GUEST_PART_MS + GUEST_PART_SLACK_MS)] = GUEST_PART_MS,
) -> dict[str, Any]:
    """Transcribe one minute of a guest's own microphone and store the words as that guest's lines.

    The token travels in a header (never in the URL, which ends up in access logs). The audio is
    read for the speech-to-text call and never stored. `seq` numbers the guest's parts from 0: part
    n sits n minutes after the guest's first part on the meeting's clock, so sending a part again
    (a retry) replaces the same lines, two parts never share a place, and the guest cannot choose
    the time. A guest sends nothing else and reads nothing.

    What keeps the cost bounded without Redis: one part at a time per guest (a database lock), at
    least `GUEST_MIN_GAP_S` between parts, no part further ahead than the minutes the guest has been
    in, and at most `GUEST_MAX_BYTES` of audio per part."""
    await _limit(request, token, "part", 1200, 200)
    found = await _guest_for(session, token)
    if found is None:
        raise HTTPException(status_code=404)
    guest, meeting, scope = found
    busy = not await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": f"guest-part:{guest.id}"}
    )
    if busy:
        raise BusinessRuleViolation("MEETING_PART_BUSY", "The last part is still being read", 429)
    now = datetime.now(UTC)
    if guest.last_seq == seq and guest.last_part_at is not None:
        return {"segments": 0, "again": True}  # a retry of a part that already went through
    if (
        guest.last_part_at is not None
        and (now - guest.last_part_at).total_seconds() < GUEST_MIN_GAP_S
    ):
        raise BusinessRuleViolation(
            "MEETING_PART_TOO_SOON", "Parts are sent about a minute apart", 429
        )
    if seq > int((now - guest.consent_at).total_seconds() // 60) + GUEST_SEQ_SLACK:
        raise BusinessRuleViolation(
            "MEETING_PART_INVALID", "This part is ahead of the meeting", 422
        )
    try:
        audio = await file.read(GUEST_MAX_BYTES + 1)
    finally:
        await file.close()
    if len(audio) > GUEST_MAX_BYTES:
        raise BusinessRuleViolation("MEETING_AUDIO_TOO_LARGE", "This audio part is too large", 413)
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if not audio or mime not in GUEST_MIMES:
        raise BusinessRuleViolation("MEETING_AUDIO_INVALID", "This is not a recording", 422)
    # where this guest's parts sit on the meeting's clock (it starts with the host's recorder; with
    # no host recording the first guest part starts it)
    if meeting.recording_started_at is None:
        await _start_clock(session, meeting)
    first_offset = guest.first_offset_ms
    if first_offset is None:
        elapsed = int((now - meeting.recording_started_at).total_seconds() * 1000)  # type: ignore[operator]
        first_offset = max(0, elapsed - duration_ms)
    offset_ms = first_offset + seq * GUEST_PART_MS
    base = guest_base(offset_ms, guest.slot)
    if base is None:
        raise BusinessRuleViolation("MEETING_PART_INVALID", "This part is outside the meeting", 422)
    guest.first_offset_ms = (
        first_offset  # only a part that fits the meeting fixes the guest's place
    )
    # lines the findings already cite are never rewritten (the host's route has the same rule)
    mine = (
        PiMeetingSegment.tenant_id == scope.tenant_id,
        PiMeetingSegment.environment_id == scope.environment_id,
        PiMeetingSegment.meeting_id == meeting.id,
    )
    has_insights = await session.scalar(
        select(PiMeetingInsight.id)
        .where(
            PiMeetingInsight.tenant_id == scope.tenant_id,
            PiMeetingInsight.environment_id == scope.environment_id,
            PiMeetingInsight.meeting_id == meeting.id,
        )
        .limit(1)
    )
    if has_insights is not None and await session.scalar(
        select(PiMeetingSegment.id)
        .where(
            *mine,
            PiMeetingSegment.ordinal >= base,
            PiMeetingSegment.ordinal < base + GUEST_SEGMENTS,
        )
        .limit(1)
    ):
        raise BusinessRuleViolation(
            "MEETING_PART_ANALYSED", "This part was already heard and analysed", 409
        )
    language = meeting.language if ISO_LANGUAGE.match(meeting.language) else None
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    meeting.attempts += 1
    try:
        result = await manager.transcribe(scope, audio, mime, alias="stt", language=language)
    except MediaValidationError:
        raise BusinessRuleViolation(
            "MEETING_AUDIO_INVALID", "This audio could not be read as a recording", 422
        ) from None
    except GatewayUnavailable:
        raise BusinessRuleViolation(
            "MEETING_TRANSCRIBE_FAILED", "Speech-to-text is unavailable; try again", 502
        ) from None
    audio = b""  # held only for the call above
    await session.execute(
        delete(PiMeetingSegment).where(
            *mine,
            PiMeetingSegment.ordinal >= base,
            PiMeetingSegment.ordinal < base + GUEST_SEGMENTS,
        )
    )
    # redact the whole part first, then cut: a card or phone number is never split across lines
    cleaned = redacted(join_spoken_digits(result.text), GUEST_MAX_TEXT)
    sentences = pack(split_sentences(cleaned), GUEST_SEGMENTS)
    lines = timed(sentences, offset_ms, duration_ms or GUEST_PART_MS)[:GUEST_SEGMENTS]
    for kept, (start, end, words) in enumerate(lines):
        session.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=meeting.id,
                ordinal=base + kept,
                start_ms=start,
                end_ms=max(end, 1),
                participant_id=guest.participant_id,
                text=words,
                text_hash=hashlib.sha256(words.lower().encode()).hexdigest(),
            )
        )
    # the meeting's language is the host's to set: a guest's detection never steers the host's parts
    meeting.status = "transcribing"
    meeting.failure_reason = ""
    guest.last_seq = seq
    guest.last_part_at = now
    await record(
        session,
        "pi.meeting_guest_part",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"slot": guest.slot, "segments": len(lines)},
    )
    await session.commit()
    return {"segments": len(lines)}
