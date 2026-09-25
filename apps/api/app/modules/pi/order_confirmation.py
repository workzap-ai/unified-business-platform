"""Explicit customer confirmation of a summarized draft.

Only an exact ``CONFIRM <reference>`` reply to a delivered summary leads to create_order,
which re-verifies the single-use token against the current draft and conversation.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.pi.models import PiPendingAction
from app.modules.pi.tools.confirmation import token_of
from app.shared.workspace_repository import WorkspaceRepository

if TYPE_CHECKING:
    from app.modules.pi.agents import AgentContext

AFFIRMATIONS = {"yes", "confirm", "ok", "okay", "haan", "ji", "done", "theek hai"}
FAILURE_REPLIES = {
    "SUMMARY_NOT_DELIVERED": (
        "The order summary has not been delivered yet. Please wait for it before confirming."
    ),
    "DRAFT_CHANGED": "The order changed after it was summarized. Please ask for a new summary.",
    "CONFIRMATION_EXPIRED": "This order confirmation expired. Please ask for a new order summary.",
    "CONFIRMATION_USED": "This order was already confirmed.",
    "HUMAN_TAKEOVER": "",
}


async def handle_confirmation(ctx: "AgentContext") -> tuple[str | None, str | None]:
    """Return (reply, handoff_reason). (None, None) means: not a confirmation turn."""
    repo = WorkspaceRepository(ctx.session, PiPendingAction, ctx.scope)
    pending = await ctx.session.scalar(
        repo.select()
        .where(
            PiPendingAction.conversation_id == ctx.conversation.id,
            PiPendingAction.status == "pending",
        )
        .with_for_update()
    )
    if pending is None:
        return None, None
    value = " ".join(ctx.message.body.strip().casefold().split())
    reference = str(pending.payload["reference"])
    about_order = value in AFFIRMATIONS or value == "cancel" or value.startswith("confirm")
    if pending.expires_at <= datetime.now(UTC):
        pending.status, pending.resolved_at = "expired", datetime.now(UTC)
        return (FAILURE_REPLIES["CONFIRMATION_EXPIRED"], None) if about_order else (None, None)
    if value == "cancel":
        pending.status, pending.resolved_at = "cancelled", datetime.now(UTC)
        pending.resolved_by_message_id = ctx.message.id
        return "The confirmation request was cancelled. No order was placed.", None
    if value != f"confirm {reference}".casefold():
        if about_order:
            return f"Please review the summary, then reply exactly CONFIRM {reference}.", None
        return None, None
    result = await ctx.tool(
        "sales_order", "create_order", {"order_id": pending.payload["order_id"]}, token_of(pending)
    )
    if result.ok and result.data is not None:
        return (
            f"Order {result.data['number']} is confirmed. Total {result.data['total']} "
            f"{result.data['currency']}. The team will follow up on delivery.",
            None,
        )
    code = result.error_code or ""
    if code in FAILURE_REPLIES:
        if code in {"DRAFT_CHANGED", "CONFIRMATION_EXPIRED"}:
            pending.status, pending.resolved_at = "expired", datetime.now(UTC)
        return FAILURE_REPLIES[code] or None, None
    # Price/stock changes or other business refusals: never retry silently; a person decides.
    pending.status, pending.resolved_at = "failed", datetime.now(UTC)
    return "The order could not be confirmed. A team member will review it.", "tool_failure"
