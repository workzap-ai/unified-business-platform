"""After a video call, pi reads its own transcript and drafts the summary for the team.

The worker calls this once a room's transcript is written. It does what the "Analyse with pi"
button does, with the same rules: every finding is only a DRAFT (`pending`); nothing is approved, no
document is made and nothing goes to the customer until a person reviews it. The meeting moves to
"review" and the team gets one notification with a link; a call that said almost nothing is left
alone (no point paying for an empty summary), and a model that cannot be reached leaves the
meeting as it is, for the button.
"""

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.notifications.service import notify
from app.modules.pi_meetings import analyse as analysis
from app.modules.pi_meetings.analyse import Segment
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingInsight,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

MIN_LINES = 4  # a call with fewer lines than this is not worth reading
ROUNDS = 4  # one call reads what fits its time budget: a long transcript takes a few


async def analyse_finished_meeting(
    session: AsyncSession, scope: WorkspaceScope, meeting: PiMeeting, manager: Any
) -> bool:
    """Draft the findings of a finished call. True when the whole transcript was read."""
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
    if len(rows) < MIN_LINES:
        return False
    segments = [Segment(o, t, who or "") for o, t, who in rows]
    progress = None
    for _ in range(ROUNDS):
        meeting.attempts += 1
        try:
            progress = await analysis.run(
                session,
                scope,
                meeting,
                manager,
                segments,
                speakers=sorted({s.speaker for s in segments if s.speaker}),
                language=meeting.language,
            )
        except analysis.AnalysisFailed:
            logger.warning("room_auto_analysis_failed", extra={"meeting": str(meeting.id)})
            await session.commit()
            return False
        if progress.complete:
            break
    if progress is None or not progress.complete:
        await session.commit()
        return False
    drafts = int(
        await session.scalar(
            select(func.count())
            .select_from(PiMeetingInsight)
            .where(
                PiMeetingInsight.tenant_id == scope.tenant_id,
                PiMeetingInsight.environment_id == scope.environment_id,
                PiMeetingInsight.meeting_id == meeting.id,
                PiMeetingInsight.review_status == "pending",
            )
        )
        or 0
    )
    meeting.status = "review"
    meeting.failure_reason = ""
    await record(
        session,
        "pi.meeting_analysed",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"insights": drafts, "dropped": len(progress.dropped), "auto": True},
    )
    await notify(
        session,
        scope,
        "pi_meeting_ready",
        "Meeting summary is ready to review",
        f"pi read the video call and drafted {drafts} finding{'s' if drafts != 1 else ''}. "
        "Nothing is approved or sent until you review it.",
        link=f"/pi/meeting-intel?meeting={meeting.id}",
        permission="pi.meetings.approve",
        dedupe_key=f"meeting-ready:{meeting.id}",
    )
    await session.commit()
    return True
