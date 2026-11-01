# ruff: noqa: E501
"""Level 3: the two small hooks `service_conversation` calls. Both return at once when
`response_rules.brain.level3_exec` is off (the default), so other workspaces see no change.

- `capped_status`: the conversation's implementation status can be raised to "implemented" only by a
  run whose tasks are all verified (acceptance evidence, intact seals and audit chain); a tampered run
  is ignored. It never lowers the existing status and never raises it from a model statement.
- `owner_reply`: an explicit yes (closed grammar, never "ok", "hmm" or "maybe") to a proposal that
  staff marked as shown approves exactly that scope, from the owner's own named chat.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.pi import execution_flow as ef
from app.modules.pi import execution_store as store
from app.shared.scope import WorkspaceScope

_ORDER = {"proposed": 0, "approved": 1, "implemented": 2}


async def capped_status(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: Any,
    rules: dict[str, Any] | None,
    current: str,
) -> str:
    if customer_id is None or not ef.availability(rules, get_settings().app_env)[0]:
        return current
    best = current
    for _row, run in await store.for_customer(session, scope, customer_id):
        s = run.outcome()["implementation_status"]
        if _ORDER.get(s, 0) > _ORDER.get(best, 0):
            best = s
    return best


async def owner_reply(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: Any,
    rules: dict[str, Any] | None,
    text: str,
    owner_name: str,
) -> str | None:
    """A confirmation line when this message approved a shown scope, else None (normal flow goes on)."""
    if conversation.customer_id is None or not ef.availability(rules, get_settings().app_env)[0]:
        return None
    if not ef.owner_reply_is_yes(text, owner_name):
        return None
    for row, run in await store.for_customer(session, scope, conversation.customer_id):
        if run.scope is None and run.pending is not None and run.pending.shown:
            step = run.approve_scope(
                approver=owner_name, approval_text=text, source="owner_chat", now=datetime.now(UTC)
            )
            await store.save(session, scope, run, row)
            if step.ok:
                return (
                    "Thank you. That exact scope is approved. Nothing starts until staff set up "
                    "and approve each task."
                )
            return None
    return None
