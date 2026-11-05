"""Meeting Intelligence API (`/api/v1/pi/meeting-intel`).

Every route needs the PI product, the `pi.meetings.*` permission for what it does, and the
workspace flag `response_rules.brain.meeting_intel` (off by default). Audit entries carry ids and
counts only, never a transcript or an insight's text. A meeting or an insight of another workspace
is "not found", never "forbidden".

Nothing here fakes a stage that does not exist yet: a recording upload and speech-to-text are not
wired (no storage or provider is configured), so a meeting is filled by importing a transcript the
team already has, and the analysis stage runs on it exactly as it will on a transcribed recording.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.pi.configuration import settings_row
from app.modules.pi.memory_ledger import redacted
from app.modules.pi.service import require_pi
from app.modules.pi_meetings import analyse as analysis
from app.modules.pi_meetings import brain_bridge, erase
from app.modules.pi_meetings.insight_rules import Segment
from app.modules.pi_meetings.models import (
    MEETING_SOURCES,
    PiMeeting,
    PiMeetingInsight,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.modules.tenants.errors import ResourceNotFound
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

MAX_TRANSCRIPT_CHARS = (
    24_000  # four analysis calls: this runs inside the request until the job exists
)
MAX_LINES = 600
PAGE = 200
ROLE_LABELS = frozenset({"customer", "client", "staff", "team", "agent", "owner", "host", "guest"})
CUSTOMER_LABELS = frozenset({"customer", "client"})
SPEAKER_N = re.compile(r"^speaker \d{1,2}$")
SPEAKER_LINE = re.compile(r"^\s*([A-Za-z][\w .'-]{0,40}?)\s*[:：]\s*(.+)$")


async def _gate(session: AsyncSession, scope: WorkspaceScope, permission: str) -> None:
    await require_pi(session, scope, permission)
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    if brain.get("meeting_intel") is not True:
        raise BusinessRuleViolation(
            "MEETING_INTEL_OFF", "Meeting intelligence is not switched on for this workspace", 403
        )


def _view(m: PiMeeting) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "title": m.title,
        "customer_id": str(m.customer_id) if m.customer_id else None,
        "source": m.source,
        "status": m.status,
        "language": m.language,
        "consent_at": m.consent_at.isoformat() if m.consent_at else None,
        "has_recording": bool(m.recording_key),
        "duration_ms": m.duration_ms,
        "held_at": m.held_at.isoformat() if m.held_at else None,
        "retention_until": m.retention_until.isoformat() if m.retention_until else None,
        "failure_reason": m.failure_reason,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _insight(i: PiMeetingInsight) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "kind": i.kind,
        "basis": i.basis,
        "text": i.edited_text or i.text,
        "confidence": i.confidence,
        "segment_refs": list(i.segment_refs or []),
        "owner_label": i.owner_label,
        "due_text": i.due_text,
        "review_status": i.review_status,
        "written_to_brain": i.written_at is not None,
        "brain_ref": i.brain_ref,
    }


async def _meeting(session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID) -> PiMeeting:
    found = await WorkspaceRepository(session, PiMeeting, scope).find(PiMeeting.id == meeting_id)
    if found is None:
        raise ResourceNotFound
    return found


async def _customer_ok(session: AsyncSession, scope: WorkspaceScope, customer_id: UUID) -> None:
    if await WorkspaceRepository(session, Customer, scope).find(Customer.id == customer_id) is None:
        raise ResourceNotFound


class CreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    customer_id: UUID | None = None
    source: str = "upload"
    language: str = Field(default="", max_length=12)
    consent_given: bool = False
    consent_note: str = Field(default="", max_length=300)
    held_at: datetime | None = None


@router.post("", status_code=201)
async def create_meeting(
    data: CreateInput, scope: Scope, session: Session, request: Request
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    if data.source not in MEETING_SOURCES:
        raise BusinessRuleViolation("MEETING_SOURCE_INVALID", "Unknown meeting source", 422)
    if not data.consent_given:
        raise BusinessRuleViolation(
            "MEETING_CONSENT_REQUIRED",
            "Everyone in the meeting must agree to it being recorded and analysed first",
            422,
        )
    if data.customer_id is not None:
        await _customer_ok(session, scope, data.customer_id)
    now = datetime.now(UTC)
    meeting = PiMeeting(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=data.customer_id,
        title=redacted(data.title, 200),
        source=data.source,
        language=data.language.strip().lower(),
        consent_at=now,
        consent_by=scope.user_id,
        consent_note=redacted(data.consent_note, 300),
        held_at=data.held_at,
        created_by=scope.user_id,
    )
    session.add(meeting)
    await session.flush()
    await record(
        session,
        "pi.meeting_created",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"source": data.source, "linked": data.customer_id is not None},
    )
    await session.commit()
    return _view(meeting)


@router.get("")
async def list_meetings(
    scope: Scope,
    session: Session,
    customer_id: UUID | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    query = (
        WorkspaceRepository(session, PiMeeting, scope)
        .select()
        .order_by(PiMeeting.created_at.desc())
        .limit(100)
    )
    if customer_id is not None:
        query = query.where(PiMeeting.customer_id == customer_id)
    if status:
        query = query.where(PiMeeting.status == status)
    return {"items": [_view(m) for m in (await session.scalars(query)).all()]}


@router.get("/search")
async def search(scope: Scope, session: Session, q: str) -> dict[str, Any]:
    """Transcript search over the segments of this workspace's meetings (Postgres full text)."""
    await _gate(session, scope, "pi.meetings.read")
    words = " ".join(q.split())[:200]
    if len(words) < 2:
        return {"items": []}
    query = func.plainto_tsquery("simple", words)
    rows = await session.execute(
        select(
            PiMeetingSegment.meeting_id,
            PiMeetingSegment.ordinal,
            PiMeetingSegment.start_ms,
            PiMeetingSegment.text,
            PiMeeting.title,
        )
        .join(
            PiMeeting,
            (PiMeeting.id == PiMeetingSegment.meeting_id)
            & (PiMeeting.tenant_id == PiMeetingSegment.tenant_id)
            & (PiMeeting.environment_id == PiMeetingSegment.environment_id),
        )
        .where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.tsv.op("@@")(query),
        )
        .order_by(func.ts_rank(PiMeetingSegment.tsv, query).desc())
        .limit(30)
    )
    items = [
        {
            "meeting_id": str(mid),
            "title": title,
            "ordinal": ordinal,
            "start_ms": start,
            "text": text[:240],
        }
        for mid, ordinal, start, text, title in rows.all()
    ]
    await record(
        session,
        "pi.meeting_searched",
        scope=scope,
        details={"results": len(items), "query_chars": len(words)},
    )
    await session.commit()
    return {"items": items}


@router.get("/{meeting_id}")
async def get_meeting(
    meeting_id: UUID, scope: Scope, session: Session, offset: int = 0
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    mine = (
        PiMeetingSegment.tenant_id == scope.tenant_id,
        PiMeetingSegment.environment_id == scope.environment_id,
        PiMeetingSegment.meeting_id == meeting.id,
    )
    segments = (
        await session.scalars(
            select(PiMeetingSegment)
            .where(*mine)
            .order_by(PiMeetingSegment.ordinal)
            .offset(max(0, offset))
            .limit(PAGE)
        )
    ).all()
    people = {
        p.id: p.label
        for p in (
            await session.scalars(
                select(PiMeetingParticipant).where(
                    PiMeetingParticipant.tenant_id == scope.tenant_id,
                    PiMeetingParticipant.environment_id == scope.environment_id,
                    PiMeetingParticipant.meeting_id == meeting.id,
                )
            )
        ).all()
    }
    insights = (
        await session.scalars(
            select(PiMeetingInsight)
            .where(
                PiMeetingInsight.tenant_id == scope.tenant_id,
                PiMeetingInsight.environment_id == scope.environment_id,
                PiMeetingInsight.meeting_id == meeting.id,
            )
            .order_by(PiMeetingInsight.created_at, PiMeetingInsight.id)
        )
    ).all()
    await record(
        session,
        "pi.meeting_viewed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"segments": len(segments), "insights": len(insights)},
    )
    await session.commit()
    return {
        **_view(meeting),
        "participants": sorted(people.values()),
        "segments": [
            {
                "ordinal": s.ordinal,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "speaker": people.get(s.participant_id, "") if s.participant_id else "",
                "text": s.text,
            }
            for s in segments
        ],
        "insights": [_insight(i) for i in insights],
    }


class LinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID


@router.patch("/{meeting_id}/customer")
async def link_customer(
    meeting_id: UUID, data: LinkInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    await _customer_ok(session, scope, data.customer_id)
    meeting.customer_id = data.customer_id
    await record(
        session,
        "pi.meeting_linked",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
    )
    await session.commit()
    return _view(meeting)


class TranscriptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_TRANSCRIPT_CHARS)


def _role_of(label: str) -> str:
    """The role the transcript itself names ("Customer:", "Staff:"); anything else is unknown, so
    nothing is taken as the customer's own words until a speaker is confirmed."""
    low = label.lower()
    if low in CUSTOMER_LABELS:
        return "customer"
    return "staff" if low in ROLE_LABELS else "unknown"


def _lines(text: str) -> list[tuple[str, str]]:
    """(speaker label, words) per line. A line without "Name: " continues the speaker before it,
    or is "Speaker 1" when it is the first."""
    out: list[tuple[str, str]] = []
    seen: dict[str, str] = {}  # label as written -> label as stored
    current = "Speaker 1"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        found = SPEAKER_LINE.match(line)
        if found:
            # roles, never names: only a role word or "Speaker N" is kept as a label; a person's
            # name becomes "Speaker N" (redaction cannot tell a name from an ordinary word)
            written = found.group(1).strip().lower()
            if written not in seen:
                if written in ROLE_LABELS or (
                    SPEAKER_N.match(written) and written.title() not in seen.values()
                ):
                    seen[written] = written.title()
                else:
                    n = len(seen) + 1
                    while f"Speaker {n}" in seen.values():
                        n += 1
                    seen[written] = f"Speaker {n}"
            current = seen[written]
            line = found.group(2).strip()
        out.append((current, line))
    return out[:MAX_LINES]


@router.post("/{meeting_id}/transcript")
async def import_transcript(
    meeting_id: UUID, data: TranscriptInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """Fill a meeting from a transcript the team already has ("Speaker: words" per line). Words are
    redacted before they are stored; importing again replaces the earlier transcript, and the
    insights are replaced when the analysis is run again."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    if meeting.consent_at is None:
        raise BusinessRuleViolation("MEETING_CONSENT_REQUIRED", "No consent is recorded", 422)
    lines = _lines(data.text)
    if not lines:
        raise BusinessRuleViolation("TRANSCRIPT_EMPTY", "The transcript has no text", 422)
    for model in (PiMeetingSegment, PiMeetingParticipant):
        await session.execute(
            delete(model).where(
                model.tenant_id == scope.tenant_id,
                model.environment_id == scope.environment_id,
                model.meeting_id == meeting.id,
            )
        )
    labels: dict[str, PiMeetingParticipant] = {}
    for label, _ in lines:
        if label not in labels:
            labels[label] = PiMeetingParticipant(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=meeting.id,
                label=label,
                role=_role_of(label),
            )
            session.add(labels[label])
    await session.flush()
    kept = 0
    for ordinal, (label, words) in enumerate(lines):
        clean = redacted(words, 1500)
        if not clean:
            continue
        session.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=meeting.id,
                ordinal=ordinal,
                start_ms=0,
                end_ms=0,
                participant_id=labels[label].id,
                text=clean,
                text_hash=hashlib.sha256(clean.lower().encode()).hexdigest(),
            )
        )
        kept += 1
    meeting.status = "analysing"
    await record(
        session,
        "pi.meeting_transcript_imported",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"lines": kept, "speakers": len(labels)},
    )
    await session.commit()
    return {**_view(meeting), "lines": kept, "speakers": len(labels)}


@router.post("/{meeting_id}/analyse")
async def run_analysis(
    meeting_id: UUID, scope: Scope, session: Session, request: Request
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    rows = (
        await session.execute(
            select(PiMeetingSegment.ordinal, PiMeetingSegment.text, PiMeetingParticipant.label)
            .join(
                PiMeetingParticipant,
                PiMeetingParticipant.id == PiMeetingSegment.participant_id,
                isouter=True,
            )
            .where(
                PiMeetingSegment.tenant_id == scope.tenant_id,
                PiMeetingSegment.environment_id == scope.environment_id,
                PiMeetingSegment.meeting_id == meeting.id,
            )
            .order_by(PiMeetingSegment.ordinal)
        )
    ).all()
    if not rows:
        raise BusinessRuleViolation("TRANSCRIPT_EMPTY", "Import a transcript first", 422)
    segments = [Segment(o, t, who or "") for o, t, who in rows]
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    meeting.attempts += 1
    try:
        kept, dropped = await analysis.analyse(
            manager,
            scope,
            segments,
            speakers=sorted({s.speaker for s in segments if s.speaker}),
            language=meeting.language,
        )
    except analysis.AnalysisFailed:
        meeting.status = "failed"
        meeting.failure_reason = "The analysis could not be completed; try again"
        await session.commit()
        raise BusinessRuleViolation(
            "MEETING_ANALYSIS_FAILED", "The analysis could not be completed; try again", 502
        ) from None
    written = await analysis.store(session, scope, meeting.id, kept)
    meeting.status = "review"
    meeting.failure_reason = ""
    await record(
        session,
        "pi.meeting_analysed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"insights": written, "dropped": len(dropped)},
    )
    await session.commit()
    return {**_view(meeting), "insights": written, "dropped": len(dropped)}


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edited_text: str = Field(default="", max_length=600)


async def _pending(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID, insight_id: UUID
) -> tuple[PiMeeting, PiMeetingInsight]:
    meeting = await _meeting(session, scope, meeting_id)
    item = await session.scalar(
        select(PiMeetingInsight).where(
            PiMeetingInsight.tenant_id == scope.tenant_id,
            PiMeetingInsight.environment_id == scope.environment_id,
            PiMeetingInsight.meeting_id == meeting.id,
            PiMeetingInsight.id == insight_id,
        )
    )
    if item is None:
        raise ResourceNotFound
    return meeting, item


@router.post("/{meeting_id}/insights/{insight_id}/approve")
async def approve_insight(
    meeting_id: UUID, insight_id: UUID, data: ReviewInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    meeting, item = await _pending(session, scope, meeting_id, insight_id)
    try:
        outcome = await brain_bridge.approve(
            session, scope, meeting, item, reviewer_id=scope.user_id, edited_text=data.edited_text
        )
    except brain_bridge.NotLinked:
        raise BusinessRuleViolation(
            "MEETING_NOT_LINKED", "Link this meeting to a customer before approving", 422
        ) from None
    except brain_bridge.NotPending:
        raise BusinessRuleViolation(
            "INSIGHT_ALREADY_REJECTED", "This insight was rejected", 409
        ) from None
    except brain_bridge.PriceInEdit:
        raise BusinessRuleViolation(
            "MEETING_PRICE_NOT_ALLOWED",
            "A price cannot be written here: pi does not price, the quote does",
            422,
        ) from None
    except brain_bridge.EditRefused:
        raise BusinessRuleViolation(
            "MEETING_EDIT_REFUSED", "That wording cannot be stored (personal data removed)", 422
        ) from None
    await record(
        session,
        "pi.meeting_insight_approved",
        scope=scope,
        entity_type="pi_meeting_insight",
        entity_id=item.id,
        details={"wrote": outcome.wrote, "kind": item.kind, "basis": item.basis},
    )
    await session.commit()
    return {**_insight(item), "wrote": outcome.wrote, "note": outcome.note}


@router.post("/{meeting_id}/insights/{insight_id}/reject")
async def reject_insight(
    meeting_id: UUID, insight_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    _, item = await _pending(session, scope, meeting_id, insight_id)
    try:
        await brain_bridge.reject(session, item, reviewer_id=scope.user_id)
    except brain_bridge.NotPending:
        raise BusinessRuleViolation(
            "INSIGHT_ALREADY_WRITTEN",
            "This insight is already in the customer's memory; correct it there",
            409,
        ) from None
    await record(
        session,
        "pi.meeting_insight_rejected",
        scope=scope,
        entity_type="pi_meeting_insight",
        entity_id=item.id,
    )
    await session.commit()
    return _insight(item)


@router.delete("/{meeting_id}")
async def delete_meeting(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Delete the meeting, its transcript and its insights. What was already written to the
    customer's memory stays there (it has its own history and is removed by erasing the customer
    or by withdrawing it). A meeting with a stored recording is refused until storage deletion
    exists."""
    await _gate(session, scope, "pi.meetings.delete")
    meeting = await _meeting(session, scope, meeting_id)
    if meeting.recording_key:
        # the file lives in object storage and nothing here can remove it yet: refuse rather than
        # lose the key and leave a recording nobody can find (erase never drops a key silently)
        raise BusinessRuleViolation(
            "RECORDING_DELETE_UNAVAILABLE",
            "This meeting has a stored recording that cannot be removed from storage yet",
            409,
        )
    await erase.erase_one(session, scope, meeting.id)
    await record(
        session,
        "pi.meeting_deleted",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting_id,
    )
    await session.commit()
    return {"deleted": True}
