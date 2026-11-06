"""Erase a customer's meetings (called by `pi/brain_erase.erase_customer`).

Insights, transcript segments and speaker labels hold the words of the meeting, so they go with the
customer, children first. The recordings themselves live in object storage, not in the database:
the rows that name them are deleted here, and the caller (`brain_erase_routes`) removes the objects
BEFORE the erase runs, from `recording_keys`, and stops if the bucket cannot be reached. A key is
never dropped silently.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingGuest,
    PiMeetingInsight,
    PiMeetingInvite,
    PiMeetingMedia,
    PiMeetingMediaData,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.shared.scope import WorkspaceScope

MEETING_REMOVED_KEYS = (
    "meeting_media_data",
    "meeting_media",
    "meeting_guests",
    "meeting_invites",
    "meeting_insights",
    "meeting_segments",
    "meeting_participants",
    "meetings",
)


async def recording_keys(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> list[str]:
    """Object-store keys of this customer's recordings (read before the rows are deleted): every
    part
    saved in a bucket, and the key of a meeting that names a recording but has no part rows. Audio
    kept in the database has no object and is not listed: it goes with its rows."""
    mine_media = (
        PiMeetingMedia.tenant_id == scope.tenant_id,
        PiMeetingMedia.environment_id == scope.environment_id,
    )
    in_bucket = await session.scalars(
        select(PiMeetingMedia.key)
        .join(
            PiMeeting,
            (PiMeeting.id == PiMeetingMedia.meeting_id)
            & (PiMeeting.tenant_id == PiMeetingMedia.tenant_id)
            & (PiMeeting.environment_id == PiMeetingMedia.environment_id),
        )
        .where(*mine_media, PiMeeting.customer_id == customer_id)
        .where(~PiMeetingMedia.key.like("db/%"))
    )
    with_parts = select(PiMeetingMedia.meeting_id).where(*mine_media)
    legacy = await session.scalars(
        select(PiMeeting.recording_key).where(
            PiMeeting.tenant_id == scope.tenant_id,
            PiMeeting.environment_id == scope.environment_id,
            PiMeeting.customer_id == customer_id,
            PiMeeting.recording_key.is_not(None),
            PiMeeting.id.not_in(with_parts),
        )
    )
    return [key for key in [*in_bucket, *legacy] if key]


def erase_steps(scope: WorkspaceScope, customer_id: UUID) -> tuple[tuple[str, Any], ...]:
    """The delete statements, in dependency order, for `brain_erase._run_steps`."""

    def mine(model: Any) -> tuple[Any, ...]:
        return (
            model.tenant_id == scope.tenant_id,
            model.environment_id == scope.environment_id,
        )

    meeting_ids = select(PiMeeting.id).where(*mine(PiMeeting), PiMeeting.customer_id == customer_id)
    media_ids = select(PiMeetingMedia.id).where(
        *mine(PiMeetingMedia), PiMeetingMedia.meeting_id.in_(meeting_ids)
    )
    return (
        (
            "meeting_guests",
            delete(PiMeetingGuest).where(
                *mine(PiMeetingGuest), PiMeetingGuest.meeting_id.in_(meeting_ids)
            ),
        ),
        (
            "meeting_invites",
            delete(PiMeetingInvite).where(
                *mine(PiMeetingInvite), PiMeetingInvite.meeting_id.in_(meeting_ids)
            ),
        ),
        (
            "meeting_media_data",
            delete(PiMeetingMediaData).where(
                *mine(PiMeetingMediaData), PiMeetingMediaData.media_id.in_(media_ids)
            ),
        ),
        (
            "meeting_media",
            delete(PiMeetingMedia).where(
                *mine(PiMeetingMedia), PiMeetingMedia.meeting_id.in_(meeting_ids)
            ),
        ),
        (
            "meeting_insights",
            delete(PiMeetingInsight).where(
                *mine(PiMeetingInsight), PiMeetingInsight.meeting_id.in_(meeting_ids)
            ),
        ),
        (
            "meeting_segments",
            delete(PiMeetingSegment).where(
                *mine(PiMeetingSegment), PiMeetingSegment.meeting_id.in_(meeting_ids)
            ),
        ),
        (
            "meeting_participants",
            delete(PiMeetingParticipant).where(
                *mine(PiMeetingParticipant), PiMeetingParticipant.meeting_id.in_(meeting_ids)
            ),
        ),
        (
            "meetings",
            delete(PiMeeting).where(*mine(PiMeeting), PiMeeting.customer_id == customer_id),
        ),
    )


def unmap_steps(scope: WorkspaceScope, customer_id: UUID) -> tuple[tuple[str, Any], ...]:
    """A speaker mapped to this customer in someone else's meeting loses the link."""
    return (
        (
            "meeting_participants_unmapped",
            update(PiMeetingParticipant)
            .where(
                PiMeetingParticipant.tenant_id == scope.tenant_id,
                PiMeetingParticipant.environment_id == scope.environment_id,
                PiMeetingParticipant.mapped_customer_id == customer_id,
            )
            .values(mapped_customer_id=None),
        ),
    )


async def erase_one(session: AsyncSession, scope: WorkspaceScope, meeting_id: UUID) -> str | None:
    """Delete one meeting and its rows (children first). Returns the recording's object key, which
    the caller must hand to the storage step, or None when the meeting had no recording."""
    where = (
        PiMeeting.tenant_id == scope.tenant_id,
        PiMeeting.environment_id == scope.environment_id,
    )
    key = await session.scalar(
        select(PiMeeting.recording_key).where(*where, PiMeeting.id == meeting_id)
    )
    media_ids = select(PiMeetingMedia.id).where(
        PiMeetingMedia.tenant_id == scope.tenant_id,
        PiMeetingMedia.environment_id == scope.environment_id,
        PiMeetingMedia.meeting_id == meeting_id,
    )
    await session.execute(
        delete(PiMeetingMediaData).where(
            PiMeetingMediaData.tenant_id == scope.tenant_id,
            PiMeetingMediaData.environment_id == scope.environment_id,
            PiMeetingMediaData.media_id.in_(media_ids),
        )
    )
    for model in (
        PiMeetingGuest,
        PiMeetingInvite,
        PiMeetingMedia,
        PiMeetingInsight,
        PiMeetingSegment,
        PiMeetingParticipant,
    ):
        await session.execute(
            delete(model).where(
                model.tenant_id == scope.tenant_id,
                model.environment_id == scope.environment_id,
                model.meeting_id == meeting_id,
            )
        )
    await session.execute(delete(PiMeeting).where(*where, PiMeeting.id == meeting_id))
    return key or None
