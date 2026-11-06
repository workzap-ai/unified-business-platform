"""Meeting recording and speech-to-text (`/api/v1/pi/meeting-intel/{id}/recording/...`).

The browser records a meeting in short, self-contained audio parts (a few minutes each) and sends
them one at a time. Each part is transcribed as it arrives, so a long meeting never meets the
provider's upload limit or a request timeout, a lost connection costs one part and not the whole
meeting, and sending a part again replaces its segments instead of duplicating them.

What is kept: the words, redacted (card, ID, phone and e-mail numbers removed) and cut into
timestamped segments. The audio itself is NOT stored: it is held in memory for the one
speech-to-text call and dropped. No bucket or retention decision exists yet (docs/pi-saas/
pi-meeting-brain.md, "Needed from the owner"), so `recording_key` stays empty and the meeting can
still be deleted. When storage is added, this is the place that will write the part.

Rules that apply: recording needs the consent recorded when the meeting was created; speech-to-text
cannot tell speakers apart, so every segment belongs to one "Speaker 1" of unknown role and nothing
is taken as the customer's own words until a person confirms the speaker; audit entries carry ids
and counts only, never a transcript.
"""

import hashlib
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import GatewayUnavailable, MediaValidationError
from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingInsight,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.modules.pi_meetings.routes import _gate, _meeting, _view
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

# One part is a few minutes of compressed audio (about 1 MB); the cap is generous but bounded,
# and well under the speech-to-text provider's own 25 MB limit.
MAX_PART_BYTES = 8 * 1024 * 1024
MAX_PARTS = 400  # about 26 hours at five minutes a part
PART_STRIDE = 1000  # segment ordinals reserved per part: re-sending a part replaces its range
MAX_PART_MS = 15 * 60 * 1000
SEGMENT_CHARS = 1500
SPEAKER = "Speaker 1"
ISO_LANGUAGE = re.compile(r"^[a-z]{2}$")
SENTENCE_END = re.compile(r"(?<=[.!?۔؟])\s+")
MAX_PART_TEXT = 60_000
# Speech-to-text writes spoken digits as "4111. 1111. 1111. 1111." or "0300. 1234567.": a full stop
# between two digit groups. The shared redactor reads spaced groups, so the stops are dropped first.
SPOKEN_GROUPS = re.compile(r"(?<=\d{2})[.,]\s+(?=\d{2})")
# states in which more audio may still be added: once the transcript is complete (analysing), or
# analysed or reviewed, it is not reopened
OPEN_STATES = frozenset({"created", "uploaded", "transcribing", "failed"})


def join_spoken_digits(text: str) -> str:
    return SPOKEN_GROUPS.sub(" ", text)


def split_sentences(text: str) -> list[str]:
    """Sentence-sized pieces (Latin and Urdu punctuation), each no longer than one segment. A long
    run without punctuation is cut at word boundaries."""
    pieces: list[str] = []
    for sentence in SENTENCE_END.split(" ".join(text.split())):
        sentence = sentence.strip()
        while len(sentence) > SEGMENT_CHARS:
            cut = sentence.rfind(" ", 0, SEGMENT_CHARS)
            cut = cut if cut > 0 else SEGMENT_CHARS
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)
    return pieces


def timed(pieces: list[str], offset_ms: int, duration_ms: int) -> list[tuple[int, int, str]]:
    """(start, end, words) per piece. The provider returns plain text, so the span of a piece is its
    share of the part's characters: good enough to jump near the right moment, and honest that it
    is an estimate (the UI shows it as a position, never as a quote time)."""
    total = sum(len(p) for p in pieces) or 1
    out: list[tuple[int, int, str]] = []
    cursor = 0
    for piece in pieces:
        start = offset_ms + duration_ms * cursor // total
        cursor += len(piece)
        end = offset_ms + duration_ms * cursor // total
        out.append((start, max(start, end), piece))
    return out


async def _speaker(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID
) -> PiMeetingParticipant:
    found = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.label == SPEAKER,
        )
    )
    if found is not None:
        return found
    created = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting_id,
        label=SPEAKER,
        role="unknown",  # speech-to-text cannot tell who spoke: never assumed to be the customer
    )
    session.add(created)
    await session.flush()
    return created


async def _recordable(session: AsyncSession, scope: WorkspaceScope, meeting: PiMeeting) -> None:
    """Consent is on record and the transcript can still grow. Audio is refused once the meeting
    has insights (they cite segment ordinals, which new audio would rewrite), is past
    transcribing, or already holds an imported transcript (part 0 would overwrite its lines)."""
    if meeting.consent_at is None:
        raise BusinessRuleViolation("MEETING_CONSENT_REQUIRED", "No consent is recorded", 422)
    if meeting.status not in OPEN_STATES:
        raise BusinessRuleViolation(
            "MEETING_CLOSED", "This meeting already has its transcript; start a new one", 409
        )
    mine = (
        PiMeetingInsight.tenant_id == scope.tenant_id,
        PiMeetingInsight.environment_id == scope.environment_id,
        PiMeetingInsight.meeting_id == meeting.id,
    )
    imported = (
        PiMeetingSegment.tenant_id == scope.tenant_id,
        PiMeetingSegment.environment_id == scope.environment_id,
        PiMeetingSegment.meeting_id == meeting.id,
        PiMeetingSegment.end_ms == 0,  # an imported line has no timing; a recorded one always does
    )
    if (await session.scalar(select(PiMeetingInsight.id).where(*mine).limit(1))) is not None or (
        await session.scalar(select(PiMeetingSegment.id).where(*imported).limit(1))
    ) is not None:
        raise BusinessRuleViolation(
            "MEETING_CLOSED", "This meeting already has its transcript; start a new one", 409
        )


@router.post("/{meeting_id}/recording/parts")
async def upload_part(
    meeting_id: UUID,
    scope: Scope,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File()],
    index: Annotated[int, Form(ge=0, lt=MAX_PARTS)],
    offset_ms: Annotated[int, Form(ge=0)] = 0,
    duration_ms: Annotated[int, Form(ge=0, le=MAX_PART_MS)] = 0,
) -> dict[str, Any]:
    """Transcribe one part of the recording and store its words as segments."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    await _recordable(session, scope, meeting)
    try:
        audio = await file.read(MAX_PART_BYTES + 1)
    finally:
        await file.close()
    if len(audio) > MAX_PART_BYTES:
        raise BusinessRuleViolation("MEETING_AUDIO_TOO_LARGE", "This audio part is too large", 413)
    if not audio:
        raise BusinessRuleViolation("MEETING_AUDIO_EMPTY", "This audio part is empty", 422)
    # "audio/webm;codecs=opus" from the browser is "audio/webm" to the validator
    mime = (file.content_type or "").split(";")[0].strip().lower()
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
        # nothing was stored for this part: sending it again is safe
        meeting.status = "failed"
        meeting.failure_reason = "Speech-to-text is unavailable; try again"
        await session.commit()
        raise BusinessRuleViolation(
            "MEETING_TRANSCRIBE_FAILED", "Speech-to-text is unavailable; try again", 502
        ) from None
    finally:
        del audio  # the audio is not kept

    base = index * PART_STRIDE
    await session.execute(
        delete(PiMeetingSegment).where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting.id,
            PiMeetingSegment.ordinal >= base,
            PiMeetingSegment.ordinal < base + PART_STRIDE,
        )
    )
    speaker = await _speaker(session, scope, meeting.id)
    # redact the whole part first, then cut: a card or phone number must never be split across two
    # segments where neither half looks like one (redacted fails closed: it returns "" on error)
    cleaned = redacted(join_spoken_digits(result.text), MAX_PART_TEXT)
    kept = 0
    for start, end, words in timed(
        split_sentences(cleaned), offset_ms, duration_ms or MAX_PART_MS // 3
    )[: PART_STRIDE - 1]:
        session.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=meeting.id,
                ordinal=base + kept,
                start_ms=start,
                end_ms=max(end, 1),  # recorded lines always have a timing (an import has none)
                participant_id=speaker.id,
                text=words,
                text_hash=hashlib.sha256(words.lower().encode()).hexdigest(),
            )
        )
        kept += 1
    if not meeting.language and result.language:
        meeting.language = result.language[:12].lower()
    meeting.source = "browser" if meeting.source == "upload" else meeting.source
    meeting.status = "transcribing"
    meeting.failure_reason = ""
    await record(
        session,
        "pi.meeting_part_transcribed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"part": index, "segments": kept},
    )
    await session.commit()
    return {"part": index, "segments": kept}


class CompleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_ms: int = Field(ge=0, le=MAX_PARTS * MAX_PART_MS)
    parts: int = Field(ge=0, le=MAX_PARTS)
    skipped: int = Field(default=0, ge=0, le=MAX_PARTS)


@router.post("/{meeting_id}/recording/complete")
async def complete_recording(
    meeting_id: UUID, data: CompleteInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """The recording has ended and every part has been sent: the transcript is ready to analyse."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    await _recordable(session, scope, meeting)
    count = await session.scalar(
        select(PiMeetingSegment.id)
        .where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting.id,
        )
        .limit(1)
    )
    if count is None:
        meeting.status = "failed"
        meeting.failure_reason = "No speech was found in the recording"
        await session.commit()
        raise BusinessRuleViolation("TRANSCRIPT_EMPTY", "No speech was found in the recording", 422)
    meeting.status = "analysing"
    meeting.failure_reason = ""
    meeting.duration_ms = data.duration_ms
    await record(
        session,
        "pi.meeting_recording_completed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"parts": data.parts, "skipped": data.skipped, "duration_ms": data.duration_ms},
    )
    await session.commit()
    return {**_view(meeting), "skipped": data.skipped}
