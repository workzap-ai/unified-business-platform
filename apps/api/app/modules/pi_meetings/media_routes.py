"""Saved recordings of a meeting (`/api/v1/pi/meeting-intel/{id}/recording/...`).

The browser sends the recording as short parts: the audio goes with each transcribed part
(`keep` on the part upload, see recording_routes.py) and the video as its own parts here. A part is
stored in the workspace's own S3-compatible bucket when one is connected (video needs it), otherwise
audio only is kept in the platform database (media.py). Playback is a short-lived signed link, or
the authenticated file route for database audio. Saving needs consent (recorded when the meeting was
created, and checked again here); the transcript works either way.
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Path, Request, Response, UploadFile

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi_meetings import media
from app.modules.pi_meetings.recording_routes import MAX_PARTS, _recordable
from app.modules.pi_meetings.routes import _gate, _meeting
from app.modules.tenants.errors import ResourceNotFound
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 40 * 1024 * 1024
MAX_PART_MS = 15 * 60 * 1000
ALLOWED = {
    "audio": frozenset({"audio/webm", "audio/mp4", "audio/ogg", "audio/mpeg", "audio/wav"}),
    "video": frozenset({"video/webm", "video/mp4"}),
}


def looks_like(mime: str, data: bytes) -> bool:
    """The bytes start like the type they claim (a webm/matroska header, an mp4 'ftyp' box, Ogg,
    MP3 or WAV): a renamed file of another kind is not stored."""
    if mime.endswith("/webm"):
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if mime.endswith("/mp4"):
        return data[4:8] == b"ftyp"
    if mime == "audio/ogg":
        return data.startswith(b"OggS")
    if mime == "audio/mpeg":
        return data.startswith(b"ID3") or data[:1] == b"\xff"
    if mime == "audio/wav":
        return data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    return False


def clean_mime(raw: str | None) -> str:
    return (raw or "").split(";")[0].strip().lower()


@router.post("/{meeting_id}/recording/media/{kind}/{index}")
async def save_media(
    meeting_id: UUID,
    kind: Annotated[str, Path(pattern="^(audio|video)$")],
    index: Annotated[int, Path(ge=0, lt=MAX_PARTS)],
    scope: Scope,
    session: Session,
    request: Request,
    file: Annotated[UploadFile, File()],
    offset_ms: Annotated[int, Form(ge=0)] = 0,
    duration_ms: Annotated[int, Form(ge=0, le=MAX_PART_MS)] = 0,
) -> dict[str, Any]:
    """Save one part of the recording (audio or video) in the workspace's storage."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    await _recordable(session, scope, meeting)
    limit = MAX_VIDEO_BYTES if kind == "video" else MAX_AUDIO_BYTES
    try:
        data = await file.read(limit + 1)
    finally:
        await file.close()
    if len(data) > limit:
        raise BusinessRuleViolation("MEETING_MEDIA_TOO_LARGE", "This part is too large", 413)
    mime = clean_mime(file.content_type)
    if mime not in ALLOWED[kind] or not data or not looks_like(mime, data):
        raise BusinessRuleViolation(
            "MEETING_MEDIA_INVALID", "This file is not a recording that can be saved", 422
        )
    days = media.retention_days((await settings_row(session, scope)).response_rules)
    try:
        row = await media.save_part(
            session,
            scope,
            request,
            meeting,
            kind=kind,
            ordinal=index,
            data=data,
            mime=mime,
            offset_ms=offset_ms,
            duration_ms=duration_ms,
            days=days,
        )
    except media.NoMediaConsent:
        raise BusinessRuleViolation(
            "MEETING_MEDIA_CONSENT_REQUIRED",
            "Saving the recording needs a yes first (save-consent) for this meeting",
            422,
        ) from None
    except media.NeedsBucket:
        raise BusinessRuleViolation(
            "MEETING_VIDEO_NEEDS_STORAGE",
            "Saving video needs a storage bucket: connect one in Settings -> Integrations "
            "(the audio can still be saved without it)",
            409,
        ) from None
    except media.MeetingFull:
        raise BusinessRuleViolation(
            "MEETING_AUDIO_STORE_FULL",
            "This meeting's saved audio has reached the most that can be kept without a bucket",
            413,
        ) from None
    except media.StorageFailed:
        raise BusinessRuleViolation(
            "MEETING_MEDIA_STORE_FAILED", "The recording could not be saved to storage", 502
        ) from None
    await record(
        session,
        "pi.meeting_media_saved",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"kind": kind, "part": index, "bytes": len(data)},
    )
    await session.commit()
    return {
        "kind": kind,
        "part": index,
        "bytes": len(data),
        "retention_until": row.retention_until.isoformat() if row.retention_until else None,
    }


@router.post("/{meeting_id}/recording/save-consent")
async def save_consent(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Say yes to SAVING this meeting's audio and video (a separate choice from recording it).
    Nothing is stored before this; the server records who agreed and when. Saying it again keeps the
    first answer."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    await _recordable(session, scope, meeting)
    if meeting.media_consent_at is None:
        meeting.media_consent_at = datetime.now(UTC)
        meeting.media_consent_by = scope.user_id
        await record(
            session,
            "pi.meeting_media_consent",
            scope=scope,
            entity_type="pi_meeting",
            entity_id=meeting.id,
        )
        await session.commit()
    return {"media_consent_at": meeting.media_consent_at.isoformat()}


def _file_url(meeting_id: UUID) -> Any:
    """The authenticated route that serves a part kept in the database (same origin, so the
    browser's session cookie is sent when it plays)."""

    def url(row: Any) -> str:
        return (
            f"/api/v1/pi/meeting-intel/{meeting_id}/recording/media/{row.kind}/{row.ordinal}/file"
        )

    return url


UNSATISFIABLE = (-1, -1)


def _range(header: str | None, size: int) -> tuple[int, int] | None:
    """One `bytes=a-b` range, clipped to the file; None when absent or not understood (the whole
    file is sent), UNSATISFIABLE when it starts past the end (416)."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    start_text, _, end_text = header[6:].partition("-")
    try:
        if start_text == "":  # the last N bytes
            length = int(end_text)
            return (max(0, size - length), size - 1) if length > 0 else None
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    except ValueError:
        return None
    if start >= size:
        return UNSATISFIABLE
    if end < start:
        return None
    return start, min(end, size - 1)


@router.get("/{meeting_id}/recording/media/{kind}/{index}/file")
async def play_part(
    meeting_id: UUID,
    kind: Annotated[str, Path(pattern="^(audio|video)$")],
    index: Annotated[int, Path(ge=0, lt=MAX_PARTS)],
    scope: Scope,
    session: Session,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> Response:
    """Play a part that is kept in the database (audio without a storage bucket). Supports one byte
    range, so a player can jump around. Parts in a bucket are played from their signed link."""
    await _gate(session, scope, "pi.meetings.recording")
    meeting = await _meeting(session, scope, meeting_id)
    rows = [r for r in await media.parts(session, scope, meeting.id) if r.kind == kind]
    row = next((r for r in rows if r.ordinal == index and media.is_database_key(r.key)), None)
    if row is None:
        raise ResourceNotFound
    data = await media.file_bytes(session, scope, row.id)
    if not data:
        raise ResourceNotFound
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    if not (range_header or "").startswith("bytes=") or (range_header or "").startswith("bytes=0-"):
        # a listening session is one record (ids only, never the audio); later ranges are not
        await record(
            session,
            "pi.meeting_recording_played",
            scope=scope,
            entity_type="pi_meeting",
            entity_id=meeting.id,
            details={"kind": kind, "part": index},
        )
        await session.commit()
    wanted = _range(range_header, len(data))
    if wanted == UNSATISFIABLE:
        return Response(
            status_code=416, headers={**headers, "Content-Range": f"bytes */{len(data)}"}
        )
    if wanted is None:
        return Response(data, media_type=row.mime, headers=headers)
    start, end = wanted
    headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
    return Response(data[start : end + 1], status_code=206, media_type=row.mime, headers=headers)


@router.get("/{meeting_id}/recording")
async def recording(
    meeting_id: UUID, scope: Scope, session: Session, request: Request
) -> dict[str, Any]:
    """The saved parts of the recording with short-lived links to play them. The links expire after
    an hour; ask again to get new ones."""
    await _gate(session, scope, "pi.meetings.recording")
    meeting = await _meeting(session, scope, meeting_id)
    rows = await media.parts(session, scope, meeting.id)
    if not rows:
        return {"parts": [], "retention_until": None}
    try:
        urls = await media.links(session, scope, request, rows, _file_url(meeting.id))
    except media.StorageFailed:
        raise BusinessRuleViolation(
            "MEETING_MEDIA_UNAVAILABLE", "The recording storage could not be reached", 502
        ) from None
    await record(
        session,
        "pi.meeting_recording_opened",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"parts": len(rows)},
    )
    await session.commit()
    return {
        "retention_until": meeting.retention_until.isoformat() if meeting.retention_until else None,
        "parts": [
            {
                "kind": row.kind,
                "index": row.ordinal,
                "offset_ms": row.offset_ms,
                "duration_ms": row.duration_ms,
                "bytes": row.bytes,
                "mime": row.mime,
                "url": url,
            }
            for row, url in zip(rows, urls, strict=True)
        ],
    }
