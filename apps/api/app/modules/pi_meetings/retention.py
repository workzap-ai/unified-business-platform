"""Remove saved recordings whose retention date has passed (run from `sweep_pi_saas`).

Only the recording goes: bucket objects first, then the audio kept in the database, then the part
rows, and the meeting stops saying it has a recording. The transcript, insights and the map stay
(they are removed by deleting the meeting or erasing the customer). A meeting whose bucket cannot be
reached is skipped and tried again on the next sweep, so an object is never forgotten.
"""

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi_meetings import media
from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia, PiMeetingMediaData
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)
BATCH = 25  # meetings per sweep


def _worker_request(settings: Any, http: Any) -> Any:
    """What `media` reads from a request (`app.state`), for code that runs outside one."""
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=settings, http=http, integration_resolver=None)
        )
    )


async def purge_expired(session: AsyncSession, settings: Any, http: Any) -> int:
    """Delete the recordings of up to `BATCH` meetings whose every part is past its retention date.
    Returns how many meetings were cleared."""
    now = datetime.now(UTC)
    # a meeting is cleared as a whole, and only when none of its parts is still inside retention
    still_kept = select(PiMeetingMedia.meeting_id).where(
        PiMeetingMedia.retention_until.is_(None) | (PiMeetingMedia.retention_until >= now)
    )
    due = (
        await session.execute(
            select(
                PiMeetingMedia.tenant_id, PiMeetingMedia.environment_id, PiMeetingMedia.meeting_id
            )
            .where(PiMeetingMedia.meeting_id.not_in(still_kept))
            .distinct()
            .limit(BATCH)
        )
    ).all()
    cleared = 0
    request = _worker_request(settings, http)
    for tenant_id, environment_id, meeting_id in due:
        scope = WorkspaceScope(
            tenant_id=tenant_id,
            environment_id=environment_id,
            permissions=frozenset(),
            actor_type="system",
            actor_label="retention",
        )
        if await _clear(session, scope, request, meeting_id):
            cleared += 1
    return cleared


async def _clear(
    session: AsyncSession, scope: WorkspaceScope, request: Any, meeting_id: UUID
) -> bool:
    rows = await media.parts(session, scope, meeting_id)
    if not rows:
        return False
    try:
        await media.remove_objects(
            session,
            scope,
            request,
            [row.key for row in rows if not media.is_database_key(row.key)],
        )
    except media.StorageFailed:
        logger.warning("pi_meeting_retention_storage_unreachable")
        return False  # nothing was changed: the next sweep tries again
    await session.execute(
        delete(PiMeetingMediaData).where(
            PiMeetingMediaData.tenant_id == scope.tenant_id,
            PiMeetingMediaData.environment_id == scope.environment_id,
            PiMeetingMediaData.media_id.in_([row.id for row in rows]),
        )
    )
    await session.execute(
        delete(PiMeetingMedia).where(
            PiMeetingMedia.tenant_id == scope.tenant_id,
            PiMeetingMedia.environment_id == scope.environment_id,
            PiMeetingMedia.meeting_id == meeting_id,
        )
    )
    await session.execute(
        update(PiMeeting)
        .where(
            PiMeeting.tenant_id == scope.tenant_id,
            PiMeeting.environment_id == scope.environment_id,
            PiMeeting.id == meeting_id,
        )
        .values(recording_key=None, recording_bytes=0, retention_until=None)
    )
    await record(
        session,
        "pi.meeting_recording_expired",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting_id,
        details={"parts": len(rows)},
    )
    return True
