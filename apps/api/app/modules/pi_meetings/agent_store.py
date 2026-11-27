"""Looking up an agent for a prompt (no web framework: the room agent process uses this too)."""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.pi_meetings import agents
from app.modules.pi_meetings.models import PiMeetingAgent
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope


def _uuid(key: str) -> UUID | None:
    try:
        return UUID(key)
    except ValueError:
        return None


async def custom_row(
    session: Any, scope: WorkspaceScope, key: str, *, active: bool = True
) -> PiMeetingAgent | None:
    ident = _uuid(key)
    if ident is None:
        return None
    where = [
        PiMeetingAgent.tenant_id == scope.tenant_id,
        PiMeetingAgent.environment_id == scope.environment_id,
        PiMeetingAgent.id == ident,
    ]
    if active:
        where.append(PiMeetingAgent.archived_at.is_(None))
    row: PiMeetingAgent | None = await session.scalar(select(PiMeetingAgent).where(*where))
    return row


async def resolve(session: Any, scope: WorkspaceScope, key: str | None) -> tuple[str, str, str]:
    """(key, name, persona text) of an agent for a prompt. A missing, archived or unknown agent is
    pi's own personality: a chat or a meeting never breaks because an agent was archived."""
    if not key or key == agents.DEFAULT_KEY:
        return agents.DEFAULT_KEY, "pi", ""
    preset = agents.BY_KEY.get(key)
    if preset is not None:
        return preset.key, preset.name, agents.persona_block(preset.name, preset.instructions)
    row = await custom_row(session, scope, key, active=False)
    if row is None:
        return agents.DEFAULT_KEY, "pi", ""
    return str(row.id), row.name, agents.persona_block(row.name, row.instructions)


async def valid_key(session: Any, scope: WorkspaceScope, key: str) -> str:
    """The key of an agent that can be chosen now (built-in, or custom and not archived)."""
    if key in agents.BY_KEY:
        return key
    if await custom_row(session, scope, key) is not None:
        return key
    raise BusinessRuleViolation("AGENT_NOT_FOUND", "That agent does not exist", 404)
