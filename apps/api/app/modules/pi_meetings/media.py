"""Saving a meeting's recording (audio and video parts).

Two places, chosen by what the workspace has:

* **A storage bucket is connected** (the S3-compatible connection in Settings -> Integrations,
  the same one the file attachments use, through the same runtime: circuit breaker, rate limits,
  usage records): audio and video both go there. A download is a short-lived signed link.
* **No bucket**: only audio is kept, in the platform database (`pi_meeting_media_data`), up to
  `DATABASE_AUDIO_CAP` bytes per meeting. Video needs a bucket (it is about twenty times the size of
  the audio) and is refused with a clear message. A download is the authenticated file route in
  media_routes.py.

This module keeps the rows that name the parts (`pi_meeting_media`) and is the only place that talks
to the bucket or writes the audio bytes for meetings.

Bucket keys are `t/<tenant>/e/<environment>/meetings/<meeting>/<kind>/<part>.<ext>`
(`scoped_key`), so one workspace can never address another's recording; a database-kept part
has the key `db/<meeting>/<kind>/<part>`. Retention: each part carries the date until which it
is kept (default 90 days; a workspace can set `response_rules.brain.meeting_retention_days`
between 30 and 3650). Nothing deletes a part when that date passes yet: a purge job is not
built, so the date is a promise to build one, not an enforcement.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import business
from app.integrations.errors import IntegrationError
from app.integrations.http import CallContext, OutboundClient
from app.integrations.providers.s3 import S3Provider, scoped_key
from app.integrations.runtime import ConnectionRuntime
from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia, PiMeetingMediaData
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

DEFAULT_RETENTION_DAYS = 90
MIN_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 3650
LINK_SECONDS = 3600
# about ten hours of audio at the recorder's bitrate: enough for any meeting, and a bound on what
# one meeting can add to the database
DATABASE_AUDIO_CAP = 150 * 1024 * 1024
DB_PREFIX = "db/"
EXTENSIONS = {
    "audio/webm": "webm",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "video/webm": "webm",
    "video/mp4": "mp4",
}


class StorageFailed(Exception):
    """The bucket could not be reached or refused the object; nothing was recorded for the part."""


class NeedsBucket(Exception):
    """Video was offered but no storage bucket is connected."""


class NoMediaConsent(Exception):
    """Nobody has said yes to saving this meeting's audio or video."""


class MeetingFull(Exception):
    """This meeting's audio has reached the most the database keeps for one meeting."""


def is_database_key(key: str) -> bool:
    return key.startswith(DB_PREFIX)


def retention_days(response_rules: dict[str, Any] | None) -> int:
    brain = (response_rules or {}).get("brain") or {}
    value = brain.get("meeting_retention_days")
    if isinstance(value, int) and not isinstance(value, bool):
        return max(MIN_RETENTION_DAYS, min(MAX_RETENTION_DAYS, value))
    return DEFAULT_RETENTION_DAYS


async def has_bucket(session: AsyncSession, scope: WorkspaceScope) -> bool:
    """Is a verified storage connection available? (No bucket is normal, not an error.)"""
    try:
        await business.connection_for(session, scope, ("s3",))
    except BusinessRuleViolation:
        return False
    return True


def _outbound(request: Request) -> OutboundClient:
    return OutboundClient(
        request.app.state.settings,
        request.app.state.http,
        resolver=getattr(request.app.state, "integration_resolver", None),
    )


async def _call(
    session: AsyncSession, scope: WorkspaceScope, request: Request, kind: str, op: Any
) -> Any:
    """Run one bucket operation through the workspace's S3 connection."""
    connection = await business.connection_for(session, scope, ("s3",))
    runtime = ConnectionRuntime(session, request.app.state.settings, _outbound(request))
    try:
        value, _ = await runtime.call(connection, op, kind=kind, call=CallContext(idempotent=True))
    except IntegrationError as error:
        raise StorageFailed(error.code) from error
    return value


# The three bucket operations are separate functions so a test can replace them with a dictionary.
async def _put(
    session: AsyncSession, scope: WorkspaceScope, request: Request, key: str, data: bytes, mime: str
) -> None:
    await _call(
        session,
        scope,
        request,
        "meeting_media_upload",
        lambda ctx: S3Provider().upload(ctx, key, data, mime),
    )


async def _sign(
    session: AsyncSession, scope: WorkspaceScope, request: Request, keys: Sequence[str]
) -> list[str]:
    async def op(ctx: Any) -> list[str]:
        provider = S3Provider()
        return [provider.signed_url(ctx, key, LINK_SECONDS, "GET") for key in keys]

    urls: list[str] = await _call(session, scope, request, "meeting_media_link", op)
    return urls


async def _remove(
    session: AsyncSession, scope: WorkspaceScope, request: Request, keys: Sequence[str]
) -> None:
    async def op(ctx: Any) -> None:
        provider = S3Provider()
        for key in keys:
            await provider.delete(ctx, key)

    await _call(session, scope, request, "meeting_media_delete", op)


def _mine(scope: WorkspaceScope, meeting_id: UUID) -> tuple[Any, ...]:
    return (
        PiMeetingMedia.tenant_id == scope.tenant_id,
        PiMeetingMedia.environment_id == scope.environment_id,
        PiMeetingMedia.meeting_id == meeting_id,
    )


async def parts(session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID) -> list[Any]:
    return list(
        (
            await session.scalars(
                select(PiMeetingMedia)
                .where(*_mine(scope, meeting_id))
                .order_by(PiMeetingMedia.kind, PiMeetingMedia.ordinal)
            )
        ).all()
    )


async def _database_bytes(session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(PiMeetingMedia.bytes), 0)).where(
            *_mine(scope, meeting_id), PiMeetingMedia.key.like(f"{DB_PREFIX}%")
        )
    )
    return int(total or 0)


async def file_bytes(session: AsyncSession, scope: WorkspaceScope, media_id: UUID) -> bytes:
    data = await session.scalar(
        select(PiMeetingMediaData.data).where(
            PiMeetingMediaData.tenant_id == scope.tenant_id,
            PiMeetingMediaData.environment_id == scope.environment_id,
            PiMeetingMediaData.media_id == media_id,
        )
    )
    return bytes(data or b"")


async def save_part(
    session: AsyncSession,
    scope: WorkspaceScope,
    request: Request,
    meeting: PiMeeting,
    *,
    kind: str,
    ordinal: int,
    data: bytes,
    mime: str,
    offset_ms: int,
    duration_ms: int,
    days: int,
) -> PiMeetingMedia:
    """Store one part and record it. Sending the same part again replaces its row and its bytes.

    Raises `NoMediaConsent` when saving was not agreed, `NeedsBucket` for video without a bucket,
    `MeetingFull` when the database would hold too much audio for one meeting, and `StorageFailed`
    when the bucket refuses the part."""
    if meeting.media_consent_at is None:
        raise NoMediaConsent
    bucket = await has_bucket(session, scope)
    if not bucket and kind == "video":
        raise NeedsBucket
    existing = await session.scalar(
        select(PiMeetingMedia).where(
            *_mine(scope, meeting.id),
            PiMeetingMedia.kind == kind,
            PiMeetingMedia.ordinal == ordinal,
        )
    )
    if bucket:
        extension = EXTENSIONS[mime]
        key = scoped_key(
            scope.tenant_id,
            scope.environment_id,
            f"meetings/{meeting.id}/{kind}/{ordinal:05d}.{extension}",
        )
        await _put(session, scope, request, key, data, mime)
    else:
        key = f"{DB_PREFIX}{meeting.id}/{kind}/{ordinal:05d}"
        # two parts of one meeting arriving together must not both pass the cap check
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:meeting))"), {"meeting": str(meeting.id)}
        )
        held = await _database_bytes(session, scope, meeting.id)
        replaced = existing.bytes if existing and is_database_key(existing.key) else 0
        if held - replaced + len(data) > DATABASE_AUDIO_CAP:
            raise MeetingFull
    until = datetime.now(UTC) + timedelta(days=days)
    if existing is None:
        existing = PiMeetingMedia(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=meeting.id,
            kind=kind,
            ordinal=ordinal,
        )
        session.add(existing)
    elif existing.key != key and not is_database_key(existing.key):
        # the part is stored under a different key now: the first object must go, and if it cannot
        # the change is abandoned (the new object is removed again), so no key is ever forgotten
        try:
            await _remove(session, scope, request, [existing.key])
        except (StorageFailed, BusinessRuleViolation):
            try:
                await _remove(session, scope, request, [key])
            except (StorageFailed, BusinessRuleViolation):
                pass
            raise StorageFailed("old_object_not_removed") from None
    existing.key, existing.mime, existing.bytes = key, mime, len(data)
    existing.offset_ms, existing.duration_ms, existing.retention_until = (
        offset_ms,
        duration_ms,
        until,
    )
    await session.flush()
    scoped = (
        PiMeetingMediaData.tenant_id == scope.tenant_id,
        PiMeetingMediaData.environment_id == scope.environment_id,
        PiMeetingMediaData.media_id == existing.id,
    )
    if is_database_key(key):
        row = await session.scalar(select(PiMeetingMediaData).where(*scoped))
        if row is None:
            session.add(
                PiMeetingMediaData(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    media_id=existing.id,
                    data=data,
                )
            )
        else:
            row.data = data
    else:  # stored in a bucket: a copy in the database is no longer needed
        await session.execute(delete(PiMeetingMediaData).where(*scoped))
    await session.flush()
    total = await session.scalar(
        select(func.coalesce(func.sum(PiMeetingMedia.bytes), 0)).where(*_mine(scope, meeting.id))
    )
    # `recording_key` marks a meeting that has a saved recording: the folder, never one file
    meeting.recording_key = f"meetings/{meeting.id}"
    meeting.recording_mime = mime
    meeting.recording_bytes = int(total or 0)
    if meeting.retention_until is None or meeting.retention_until < until:
        meeting.retention_until = until
    return existing


async def links(
    session: AsyncSession,
    scope: WorkspaceScope,
    request: Request,
    rows: Sequence[PiMeetingMedia],
    file_url: Any,
) -> list[str]:
    """Where to play each part, in the same order as `rows`: a short-lived signed link for a part in
    the bucket, `file_url(row)` (an authenticated route) for one kept in the database."""
    if not rows:
        return []
    bucket_rows = [row for row in rows if not is_database_key(row.key)]
    signed: dict[Any, str] = {}
    if bucket_rows:
        urls = await _sign(session, scope, request, [row.key for row in bucket_rows])
        signed = dict(zip([row.id for row in bucket_rows], urls, strict=True))
    return [file_url(row) if is_database_key(row.key) else signed[row.id] for row in rows]


async def remove_objects(
    session: AsyncSession, scope: WorkspaceScope, request: Request, keys: Sequence[str]
) -> None:
    """Remove bucket objects by key. Raises `StorageFailed` when there is no usable bucket or it
    cannot be reached, so a caller can stop before it forgets a key."""
    if not keys:
        return
    try:
        await _remove(session, scope, request, list(keys))
    except BusinessRuleViolation:  # no storage connection
        raise StorageFailed("no_storage") from None


async def delete_all(
    session: AsyncSession, scope: WorkspaceScope, request: Request, meeting: PiMeeting
) -> int:
    """Remove every stored part of the meeting: objects from the bucket first, then the audio kept
    in the database, then the rows. Nothing is changed when the bucket cannot be reached
    (`StorageFailed`), so a key is never forgotten. A meeting that names an object but has no part
    rows (`recording_key` that is not the folder marker) has that object removed too. Returns how
    many parts went."""
    rows = await parts(session, scope, meeting.id)
    bucket_keys = [row.key for row in rows if not is_database_key(row.key)]
    legacy = meeting.recording_key
    if not rows and legacy and not legacy.startswith("meetings/"):
        bucket_keys.append(legacy)
    await remove_objects(session, scope, request, bucket_keys)
    if not rows:
        return 0
    meeting_id = meeting.id
    await session.execute(
        delete(PiMeetingMediaData).where(
            PiMeetingMediaData.tenant_id == scope.tenant_id,
            PiMeetingMediaData.environment_id == scope.environment_id,
            PiMeetingMediaData.media_id.in_([row.id for row in rows]),
        )
    )
    await session.execute(delete(PiMeetingMedia).where(*_mine(scope, meeting_id)))
    return len(rows)
