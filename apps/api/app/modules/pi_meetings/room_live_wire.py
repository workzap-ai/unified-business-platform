"""Connects the live view (`room_live`) to the room agent: who spoke, where it is saved, what asks
the model. The agent process only calls `build_feed`; everything here is tested with a database
and a fake model, without the video provider's SDK.
"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update

from app.modules.pi_meetings import meeting_memory, room_live
from app.modules.pi_meetings.models import PiMeetingParticipant, PiMeetingRoom
from app.modules.pi_meetings.room_agent_claim import Orders

logger = logging.getLogger(__name__)


def role_of(speaker_id: str) -> str:
    """The room's own ids say who is who: `s_` is staff, `g_` is a guest (a customer)."""
    return "staff" if speaker_id.startswith("s_") else "customer"


def build_feed(
    orders: Orders,
    sessions: Any,
    manager: Any,
    block: Callable[[], dict[str, Any]],
) -> room_live.Feed | None:
    """The live feed for this room, or None when the workspace has neither captions nor the
    staff copilot on. `block` gives what pi knows about the customer (read again every minute)."""
    if not (orders.live or orders.copilot):
        return None
    people: dict[str, tuple[str, str]] = {}

    async def names(speaker_id: str) -> tuple[str, str]:
        if speaker_id in people:
            return people[speaker_id]
        role = role_of(speaker_id)
        name = "Staff" if role == "staff" else "Guest"
        try:
            async with sessions() as db:
                label = await db.scalar(
                    select(PiMeetingParticipant.label).where(
                        PiMeetingParticipant.tenant_id == orders.scope.tenant_id,
                        PiMeetingParticipant.environment_id == orders.scope.environment_id,
                        PiMeetingParticipant.meeting_id == orders.meeting_id,
                        PiMeetingParticipant.stream_user_id == speaker_id,
                    )
                )
            name = str(label or name)
        except Exception:  # noqa: BLE001 - a missing name must never stop a caption
            logger.warning("room_live_name_unknown")
        people[speaker_id] = (name, role)
        return people[speaker_id]

    async def save(live: dict[str, Any]) -> None:
        async with sessions() as db:
            await db.execute(
                update(PiMeetingRoom)
                .where(
                    PiMeetingRoom.id == orders.room_id,
                    PiMeetingRoom.tenant_id == orders.scope.tenant_id,
                    PiMeetingRoom.environment_id == orders.scope.environment_id,
                )
                .values(live=live)
            )
            await db.commit()

    async def translate_text(text: str, target: str) -> str:
        return await room_live.translate_line(manager, orders.scope, text, target)

    async def advise_staff(lines: list[dict[str, Any]]) -> room_live.Advice:
        latest = next((x["text"] for x in reversed(lines) if x["role"] == "customer"), "")
        memory = meeting_memory.speakable(block() or {}, latest)
        return await room_live.advise(manager, orders.scope, lines, memory)

    return room_live.Feed(
        orders.live_state,
        save=save,
        names=names,
        translate=translate_text if orders.live else None,
        advise_with=advise_staff if orders.copilot else None,
    )
