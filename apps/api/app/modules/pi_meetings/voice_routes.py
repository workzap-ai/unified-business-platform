"""pi talks with the person on a meeting link (`/public/meeting-join/guest/pi-turn`).

Phase 2 of "pi in the meeting". Staff choose what pi does in a meeting (`PATCH .../pi-mode`: off,
listen, speak). Only in `speak` does the link page let pi talk, and only while the workspace flag
`response_rules.brain.meeting_voice` is on (default off). Muting is instant: every turn checks the
mode again, so switching a meeting back from `speak` makes the next turn a 409.

A turn is one thing the person said (a short audio clip, or nothing for pi's opening) and one reply.
The person's words go through the same speech-to-text, redaction and storage as a recorded part.
pi's reply is written by the model and judged by the code (`voice.py`) before anything is returned
or stored. The lines of both are kept in the meeting's transcript like any others, in their own
number range so a spoken conversation reads in the order it happened.
"""

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text

from app.ai.errors import GatewayUnavailable, MediaValidationError
from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import voice
from app.modules.pi_meetings.guest_routes import (
    GUEST_MIMES,
    BoundedRoute,
    GuestToken,
    _guest_for,
    _limit,
    _start_clock,
    voice_enabled,
)
from app.modules.pi_meetings.models import PI_MODES, PiMeetingParticipant, PiMeetingSegment
from app.modules.pi_meetings.recording_routes import ISO_LANGUAGE, join_spoken_digits
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])
public_router = APIRouter(prefix="/public/meeting-join", tags=["public"], route_class=BoundedRoute)

VOICE_BASE = 100_000_000  # spoken-conversation lines are numbered from here, one after another
MAX_TURN_BYTES = 600 * 1024  # a clip of one thing said: well under the part limit
MAX_TURN_MS = 45_000
MAX_TURNS = 200  # things one meeting's conversation may hold
PI_ROLE = "staff"


class ModeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str


@router.patch("/{meeting_id}/pi-mode")
async def set_pi_mode(
    meeting_id: UUID, data: ModeInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """What pi does in this meeting. `speak` needs the workspace flag and a recorded consent."""
    await _gate(session, scope, "pi.meetings.record")
    if data.mode not in PI_MODES:
        raise BusinessRuleViolation("MEETING_PI_MODE_INVALID", "Choose off, listen or speak", 422)
    meeting = await _meeting(session, scope, meeting_id)
    if data.mode == "speak":
        brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
        if brain.get("meeting_voice") is not True:
            raise BusinessRuleViolation(
                "MEETING_VOICE_OFF", "pi talking in meetings is not switched on", 403
            )
        if meeting.consent_at is None:
            raise BusinessRuleViolation(
                "MEETING_CONSENT_REQUIRED", "The meeting needs a recorded consent first", 422
            )
    before = meeting.pi_mode
    meeting.pi_mode = data.mode
    await record(
        session,
        "pi.meeting_pi_mode",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"from": before, "to": data.mode},
    )
    await session.commit()
    return {"pi_mode": meeting.pi_mode}


async def _pi_participant(session: Any, scope: Any, meeting_id: UUID) -> UUID:
    """pi's own speaker in this meeting: made once, a team member, never a guest's name."""
    found = await session.scalar(
        select(PiMeetingParticipant.id).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.label == voice.PI_LABEL,
        )
    )
    if found is not None:
        return found  # type: ignore[no-any-return]
    made = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting_id,
        label=voice.PI_LABEL,
        role=PI_ROLE,
    )
    session.add(made)
    await session.flush()
    return made.id  # type: ignore[no-any-return]


async def _conversation(session: Any, scope: Any, meeting_id: UUID) -> list[tuple[int, bool, str]]:
    """The spoken conversation so far, oldest first: (ordinal, said by pi, words)."""
    rows = (
        await session.execute(
            select(
                PiMeetingSegment.ordinal,
                PiMeetingParticipant.label,
                PiMeetingSegment.text,
            )
            .join(
                PiMeetingParticipant,
                (PiMeetingParticipant.id == PiMeetingSegment.participant_id)
                & (PiMeetingParticipant.tenant_id == PiMeetingSegment.tenant_id)
                & (PiMeetingParticipant.environment_id == PiMeetingSegment.environment_id),
            )
            .where(
                PiMeetingSegment.tenant_id == scope.tenant_id,
                PiMeetingSegment.environment_id == scope.environment_id,
                PiMeetingSegment.meeting_id == meeting_id,
                PiMeetingSegment.ordinal >= VOICE_BASE,
            )
            .order_by(PiMeetingSegment.ordinal)
        )
    ).all()
    return [(o, label == voice.PI_LABEL, t) for o, label, t in rows]


def _add_line(
    session: Any,
    scope: Any,
    meeting_id: UUID,
    participant_id: UUID,
    ordinal: int,
    words: str,
    start_ms: int,
    end_ms: int,
) -> None:
    session.add(
        PiMeetingSegment(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=meeting_id,
            ordinal=ordinal,
            start_ms=start_ms,
            end_ms=max(end_ms, start_ms + 1),
            participant_id=participant_id,
            text=words,
            text_hash=hashlib.sha256(words.lower().encode()).hexdigest(),
        )
    )


@public_router.post("/guest/pi-turn")
async def pi_turn(
    token: GuestToken,
    request: Request,
    session: Session,
    file: Annotated[UploadFile | None, File()] = None,
    duration_ms: Annotated[int, Form(ge=0, le=MAX_TURN_MS)] = 0,
) -> dict[str, Any]:
    """One turn of the spoken conversation. With no file it is pi's opening (its AI disclosure and
    first question); with a clip it is the person's answer and pi's reply. Without `speak` mode on
    the meeting, or with the flag off, it is a 409 and pi says nothing."""
    await _limit(request, token, "pi-turn", 900, 300)
    found = await _guest_for(session, token)
    if found is None:
        raise HTTPException(status_code=404)
    guest, meeting, scope = found
    if meeting.pi_mode != "speak" or not await voice_enabled(session, scope):
        raise BusinessRuleViolation("PI_NOT_SPEAKING", "pi is not talking in this meeting", 409)
    busy = not await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": f"pi-turn:{meeting.id}"}
    )
    if busy:
        raise BusinessRuleViolation("MEETING_PART_BUSY", "pi is still answering", 429)
    talk = await _conversation(session, scope, meeting.id)
    if len(talk) >= MAX_TURNS * 2:
        raise BusinessRuleViolation("MEETING_TURNS_LIMIT", "This conversation is long enough", 429)
    if meeting.recording_started_at is None:
        await _start_clock(session, meeting)
    now = datetime.now(UTC)
    elapsed = int((now - meeting.recording_started_at).total_seconds() * 1000)  # type: ignore[operator]
    pi_id = await _pi_participant(session, scope, meeting.id)
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    history = [voice.Said(by_pi, words) for _, by_pi, words in talk]
    nxt = (talk[-1][0] + 1) if talk else VOICE_BASE

    if file is None:
        if talk:  # a reload: say again what was last said, do not start over
            last = next((h for h in reversed(history) if h.pi), None)
            return {"heard": False, "reply": last.text if last else "", "again": True}
        words = voice.opening()
        _add_line(session, scope, meeting.id, pi_id, nxt, words, elapsed, elapsed + 2000)
        meeting.status = "transcribing"
        await _audit(session, scope, meeting.id, heard=False, fallback=False)
        await session.commit()
        return {"heard": False, "reply": words, "done": False}

    try:
        audio = await file.read(MAX_TURN_BYTES + 1)
    finally:
        await file.close()
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if len(audio) > MAX_TURN_BYTES:
        raise BusinessRuleViolation("MEETING_AUDIO_TOO_LARGE", "This clip is too large", 413)
    if not audio or mime not in GUEST_MIMES:
        raise BusinessRuleViolation("MEETING_AUDIO_INVALID", "This is not a recording", 422)
    language = meeting.language if ISO_LANGUAGE.match(meeting.language) else None
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
    heard = redacted(join_spoken_digits(result.text), voice.HEARD_CHARS)
    if not heard:  # silence or noise: nothing to answer, nothing stored
        return {"heard": False, "reply": ""}
    start = max(0, elapsed - (duration_ms or 0))
    _add_line(session, scope, meeting.id, guest.participant_id, nxt, heard, start, elapsed)
    spoken = await voice.reply_to(manager, scope, history, heard, language=meeting.language)
    _add_line(session, scope, meeting.id, pi_id, nxt + 1, spoken.text, elapsed, elapsed + 2000)
    meeting.status = "transcribing"
    meeting.failure_reason = ""
    await _audit(session, scope, meeting.id, heard=True, fallback=spoken.fallback)
    await session.commit()
    return {"heard": True, "reply": spoken.text, "done": spoken.done, "fallback": spoken.fallback}


async def _audit(
    session: Any, scope: Any, meeting_id: UUID, *, heard: bool, fallback: bool
) -> None:
    await record(
        session,
        "pi.meeting_pi_turn",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting_id,
        details={"heard": heard, "fallback": fallback},
    )
