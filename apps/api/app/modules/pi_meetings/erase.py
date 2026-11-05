"""Erase a customer's meetings (called by `pi/brain_erase.erase_customer`).

Insights, transcript segments and speaker labels hold the words of the meeting, so they go with the
customer, children first. The recordings themselves live in object storage, not in the database:
the rows that name them are deleted here and the object keys are returned so the storage step can
remove the files. A key is never dropped silently.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingInsight,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.shared.scope import WorkspaceScope

MEETING_REMOVED_KEYS = (
    "meeting_insights",
    "meeting_segments",
    "meeting_participants",
    "meetings",
)


async def recording_keys(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> list[str]:
    """Object-store keys of this customer's recordings (read before the rows are deleted)."""
    rows = await session.scalars(
        select(PiMeeting.recording_key).where(
            PiMeeting.tenant_id == scope.tenant_id,
            PiMeeting.environment_id == scope.environment_id,
            PiMeeting.customer_id == customer_id,
            PiMeeting.recording_key.is_not(None),
        )
    )
    return [key for key in rows if key]


def erase_steps(scope: WorkspaceScope, customer_id: UUID) -> tuple[tuple[str, Any], ...]:
    """The delete statements, in dependency order, for `brain_erase._run_steps`."""

    def mine(model: Any) -> tuple[Any, ...]:
        return (
            model.tenant_id == scope.tenant_id,
            model.environment_id == scope.environment_id,
        )

    meeting_ids = select(PiMeeting.id).where(*mine(PiMeeting), PiMeeting.customer_id == customer_id)
    return (
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
