"""What pi already knows about the customer a room's meeting is linked to (read-only).

The block is loaded for the agent and handed to the speech pipeline, which uses it only under the
identity rule of the link page: pi asks "Am I speaking with <first name>?" first, and memory is
used after a clear yes and never after a no or an unclear answer (`room_speech`, `voice`). A
meeting with no customer, a new customer or an erased one gives {} and pi behaves as it did before.
Reading memory never writes it.
"""

from typing import Any

from sqlalchemy import select

from app.modules.pi_meetings import meeting_memory
from app.modules.pi_meetings.models import PiMeeting
from app.modules.pi_meetings.room_agent_claim import Orders


async def load_block(session: Any, orders: Orders) -> dict[str, Any]:
    """The `what_i_know` block for the room's meeting, or {}. Never raises."""
    try:
        meeting = await session.scalar(
            select(PiMeeting).where(
                PiMeeting.id == orders.meeting_id,
                PiMeeting.tenant_id == orders.scope.tenant_id,
                PiMeeting.environment_id == orders.scope.environment_id,
            )
        )
        if meeting is None:
            return {}
        return await meeting_memory.load(session, orders.scope, meeting)
    except Exception:  # noqa: BLE001 - memory is context, never a reason for pi to fail
        return {}
