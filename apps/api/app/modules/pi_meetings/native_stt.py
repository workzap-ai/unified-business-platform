"""The transcript of a video room, written by our own speech-to-text (Urdu and other languages).

The video provider's captions do not understand Urdu (they answer in Devanagari, or in another
language altogether). So, for a workspace that has switched on `brain.meeting_room_audio`, each
person's voice is also recorded on its own, as a separate file per person. When the call has ended
the worker transcribes each file with Whisper (word times, so every line gets a real time), puts
each line under the room's own user id (`s_...` staff, `g_...` guest: that id is the only thing
that says who spoke), merges the lines into one transcript in the order they were said, and removes
the call, with its recordings, at the provider. The provider's captions stay as the fallback: a
person whose file could not be read keeps the provider's lines, and if no file could be read at all
the meeting uses the provider's transcript, as it did before.

Nothing here stores audio: the bytes are held in memory only while they are transcribed.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import GatewayUnavailable
from app.ai.types import Word
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import native_ingest
from app.modules.pi_meetings.bot_ingest import LINE_CHARS, MAX_LINES, VOICE_BASE
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingParticipant,
    PiMeetingRoom,
    PiMeetingSegment,
)
from app.modules.pi_meetings.recording_routes import join_spoken_digits
from app.modules.pi_meetings.room_provider import (
    MAX_AUDIO_BYTES,
    RoomProvider,
    RoomProviderError,
)
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

ALIAS = "stt_multi"
PURPOSE = "meeting_room_stt"
SENTENCE_END = re.compile(r"[.!?؟۔।]$")  # . ! ? and the Urdu and Hindi full stops
GAP_S = 1.2  # a pause this long ends a line even without a full stop
MAX_LINE_CHARS = 400
WAIT_S = 45  # the provider writes the files a little after the call ends
GIVE_UP_S = 6 * 60  # after this long without usable files the provider's transcript is used
MAX_TRIES = 12


@dataclass(frozen=True)
class Spoken:
    """One line of the transcript, before it is stored."""

    participant_id: Any
    text: str
    start_ms: int
    end_ms: int


def sentences(words: list[Word]) -> list[tuple[str, float, float]]:
    """Words become lines: a line ends at a full stop (Latin, Urdu or Hindi), at a long pause, or
    when it grows too long. Returns (text, start, end) in seconds."""
    out: list[tuple[str, float, float]] = []
    cur: list[Word] = []

    def flush() -> None:
        if cur:
            out.append((" ".join(w.text for w in cur), cur[0].start, cur[-1].end))
            cur.clear()

    for word in words:
        if cur and word.start - cur[-1].end > GAP_S:
            flush()
        cur.append(word)
        if SENTENCE_END.search(word.text) or sum(len(w.text) + 1 for w in cur) > MAX_LINE_CHARS:
            flush()
    flush()
    return out


def _span(offset_ms: int, start: float, end: float) -> tuple[int, int]:
    """A line's start and end in milliseconds. The speech service can time a word backwards (an end
    before its start), and the database refuses a line that ends before it begins, so the end is
    never earlier than the start and neither is negative."""
    first = max(0, offset_ms + int(start * 1000))
    return first, max(first + 1, offset_ms + int(end * 1000))


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _ms(later: datetime, earlier: datetime) -> int:
    return int((_aware(later) - _aware(earlier)).total_seconds() * 1000)


def start_offset_ms(
    *,
    recorded: datetime | None,
    joined: datetime | None,
    base: datetime,
    trust_recorded: bool,
    earliest: datetime | None = None,
) -> int:
    """Where one person's recording starts on the room's clock, in milliseconds. When the files
    carry different start times they keep the distance between them, and the whole group is moved
    to the room's clock (never earlier than the room began). When they all share one start (the
    provider timed the call, not the file) every person's times would start at 0, so the moment
    they entered the room is used instead."""
    if trust_recorded and recorded and earliest:
        return max(0, _ms(earliest, base)) + max(0, _ms(recorded, earliest))
    when = joined or recorded
    return 0 if when is None else max(0, _ms(when, base))


async def _joined(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: Any, users: set[str]
) -> dict[str, datetime]:
    """When each room user was made a participant of the meeting (they enter right after)."""
    rows = await session.execute(
        select(PiMeetingParticipant.stream_user_id, PiMeetingParticipant.created_at).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.stream_user_id.in_(users),
        )
    )
    return {user: made for user, made in rows if user and made}


async def _words(
    manager: Any, scope: WorkspaceScope, audio: bytes, language: str
) -> list[Word] | None:
    """The timed words of one person's recording, or None when no service could read it."""
    try:
        result = await manager.transcribe(
            scope,
            audio,
            "audio/webm",  # the provider's files are Matroska/Opus: the same container family
            alias=ALIAS,
            purpose=PURPOSE,
            language=language or None,
            timestamps=True,
            max_bytes=MAX_AUDIO_BYTES,
        )
    except GatewayUnavailable:
        return None
    return list(result.words)


async def _rebuild(
    session: AsyncSession,
    scope: WorkspaceScope,
    meeting: PiMeeting,
    spoken: dict[str, list[Spoken]],
) -> int:
    """Replace the lines of the people we transcribed; keep the provider's lines for the others;
    number everything again in the order it was said. Returns the longest end in milliseconds."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"room-ingest:{meeting.id}"}
    )
    mine = (
        PiMeetingSegment.tenant_id == scope.tenant_id,
        PiMeetingSegment.environment_id == scope.environment_id,
        PiMeetingSegment.meeting_id == meeting.id,
        PiMeetingSegment.ordinal < VOICE_BASE,
    )
    old = (
        await session.execute(
            select(PiMeetingSegment, PiMeetingParticipant.stream_user_id)
            .join(PiMeetingParticipant, PiMeetingParticipant.id == PiMeetingSegment.participant_id)
            .where(*mine)
        )
    ).all()
    merged = [
        Spoken(seg.participant_id, seg.text, seg.start_ms, seg.end_ms)
        for seg, user in old
        if user not in spoken
    ]
    for user, lines in spoken.items():
        who = await native_ingest.participant_for(
            session, scope, meeting.id, user[:80], label="Participant"
        )
        merged.extend(Spoken(who.id, ln.text, ln.start_ms, ln.end_ms) for ln in lines)
    merged.sort(key=lambda x: (x.start_ms, x.end_ms))
    await session.execute(delete(PiMeetingSegment).where(*mine))
    for ordinal, line in enumerate(merged[:MAX_LINES]):
        session.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=meeting.id,
                ordinal=ordinal,
                start_ms=line.start_ms,
                end_ms=line.end_ms,
                participant_id=line.participant_id,
                text=line.text,
                text_hash=hashlib.sha256(line.text.lower().encode()).hexdigest(),
            )
        )
    await session.flush()
    return max((x.end_ms for x in merged), default=0)


async def _use_provider_transcript(
    session: AsyncSession,
    scope: WorkspaceScope,
    meeting: PiMeeting,
    room: PiMeetingRoom,
    provider: RoomProvider,
) -> None:
    """No usable recording: the meeting uses the provider's own transcript, as it did before."""
    try:
        rows = await provider.transcript(room.call_id)
    except RoomProviderError:
        rows = None
    await native_ingest.finish_transcript(session, scope, meeting, room, rows or [])
    await _forget_call(provider, room)


async def _forget_call(provider: RoomProvider, room: PiMeetingRoom) -> None:
    """The transcript lives with us from here: the call, its captions and any recording are removed
    at the provider (best effort; an erase of the meeting removes it later if this fails)."""
    try:
        await provider.delete_call(room.call_id)
    except RoomProviderError:
        logger.warning("room_delete_after_transcript_failed")


async def finalize(
    session: AsyncSession,
    scope: WorkspaceScope,
    meeting: PiMeeting,
    room: PiMeetingRoom,
    provider: RoomProvider,
    manager: Any,
    *,
    now: datetime | None = None,
) -> str:
    """One attempt at the room's final transcript. Returns 'waiting' (try again later), 'done' (our
    transcript) or 'fallback' (the provider's transcript was used)."""
    now = now or datetime.now(UTC)
    room.stt_tries += 1
    age = (now - (room.ended_at or now)).total_seconds()
    try:
        files = await provider.recordings(room.call_id)
    except RoomProviderError:
        files = []
    spoken: dict[str, list[Spoken]] = {}
    if files:
        # one clock for everyone: the room's start, the same one pi's own lines are timed from
        base = room.started_at or room.created_at or now
        starts = {f.start for f in files if f.start}
        trust = len(starts) > 1  # one shared start means the provider timed the call, not each file
        joined = await _joined(session, scope, meeting.id, {f.user_id for f in files})
        for item in files:
            audio = await provider.download(item.url)
            words = await _words(manager, scope, audio, meeting.language) if audio else None
            if not words:
                continue  # unreadable, or no one spoke: the provider's lines (if any) stay
            offset = start_offset_ms(
                recorded=item.start,
                joined=joined.get(item.user_id),
                base=base,
                trust_recorded=trust,
                earliest=min(starts) if starts else None,
            )
            spoken[item.user_id] = [
                Spoken(None, text, *_span(offset, start, end))
                for line, start, end in sentences(words)
                if (text := redacted(join_spoken_digits(line), LINE_CHARS))
            ]
    if spoken:
        longest = await _rebuild(session, scope, meeting, spoken)
        await native_ingest.complete(session, scope, meeting, room, longest_ms=longest, now=now)
        await _forget_call(provider, room)
        return "done"
    if age < GIVE_UP_S and room.stt_tries < MAX_TRIES:
        return "waiting"
    await _use_provider_transcript(session, scope, meeting, room, provider)
    return "fallback"


async def pending_rooms(session: AsyncSession, limit: int = 20) -> list[Any]:
    """Rooms whose call has ended and whose transcript is still being written from the audio."""
    return list(
        (
            await session.scalars(
                select(PiMeetingRoom.id)
                .where(
                    PiMeetingRoom.audio.is_(True),
                    PiMeetingRoom.state == "ended",
                    PiMeetingRoom.transcript_state == "pending",
                    PiMeetingRoom.ended_at < func.now() - text(f"interval '{WAIT_S} seconds'"),
                )
                .order_by(PiMeetingRoom.ended_at)
                .limit(limit)
            )
        ).all()
    )
