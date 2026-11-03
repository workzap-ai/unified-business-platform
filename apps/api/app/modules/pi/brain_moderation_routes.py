"""A person decides about a chat pi stopped answering (pi Brain spec 6.7: "X_BLOCKED by human
decision"). After repeated abuse or a threat pi hands the chat over and goes silent; spam is
answered once and then ignored. This lets staff put such a chat back to listening.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi import flow
from app.modules.pi.models import PiConversation
from app.modules.pi.service import require_pi
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

router = APIRouter(prefix="/pi/brain-moderation", tags=["pi-brain-moderation"])
STOPPED = (flow.State.X_BLOCKED.value, flow.State.X_OUT_OF_SCOPE.value)


@router.post("/{conversation_id}/unblock")
async def unblock(conversation_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Put a blocked or ignored chat back to listening and clear its strikes."""
    await require_pi(session, scope, "pi.inbox.reply")
    row = await session.get(PiConversation, conversation_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        raise ResourceNotFound
    if row.flow_state not in STOPPED:
        raise BusinessRuleViolation("NOT_BLOCKED", "This chat is not blocked or ignored", 409)
    before = row.flow_state
    row.flow_state = flow.State.S1_LISTENING.value
    row.flow_state_since = datetime.now(UTC)
    brief = dict(row.service_brief or {})
    brief.pop("abuse_strikes", None)
    brief.pop("declined_trade", None)
    row.service_brief = brief
    await record(
        session,
        "pi.brain_chat_unblocked",
        scope=scope,
        entity_type="pi_conversation",
        entity_id=row.id,
        details={"from": before},
    )
    await session.commit()
    return {"id": row.id, "flow_state": row.flow_state, "from": before}
