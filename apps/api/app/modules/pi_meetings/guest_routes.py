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
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingGuest,
    PiMeetingInvite,
    PiMeetingParticipant,
)
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])
public_router = APIRouter(prefix="/public/meeting-join", tags=["public"])

TOKEN_PATTERN = r"^[A-Za-z0-9_-]{30,64}$"
Token = Annotated[str, Path(pattern=TOKEN_PATTERN)]
JOINABLE = frozenset({"created", "uploaded", "transcribing"})
MAX_NAME = 60


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


async def _require_enabled(session: AsyncSession, scope: WorkspaceScope) -> None:
    if not await guests_enabled(session, scope):
        raise BusinessRuleViolation(
            "MEETING_GUESTS_OFF", "Meeting links are not switched on for this workspace", 403
        )


# ---- staff: make, read and revoke the link, remove a guest


class InviteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: int = Field(default=24, ge=1, le=168)
    max_guests: int = Field(default=10, ge=1, le=20)


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
    now = datetime.now(UTC)
    for old in await _active_invites(session, scope, meeting.id):
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
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID
) -> list[PiMeetingInvite]:
    return list(
        (
            await session.scalars(
                select(PiMeetingInvite).where(
                    PiMeetingInvite.tenant_id == scope.tenant_id,
                    PiMeetingInvite.environment_id == scope.environment_id,
                    PiMeetingInvite.meeting_id == meeting_id,
                    PiMeetingInvite.revoked_at.is_(None),
                    PiMeetingInvite.expires_at > datetime.now(UTC),
                )
            )
        ).all()
    )


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
    for invite in await _active_invites(session, scope, meeting.id):
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
    _, meeting, _ = found
    return {"title": meeting.title}


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
    exists = await session.scalar(
        select(PiMeetingParticipant.id).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.label == label,
        )
    )
    return label if exists is None else f"{label[: MAX_NAME - 5]} ({slot})"
