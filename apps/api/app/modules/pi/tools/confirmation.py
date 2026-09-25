"""Single-use, expiring confirmation tokens bound to one draft and one conversation.

token = sha256(nonce : conversation_id : draft fingerprint). The nonce is stored on the
pending action; the token is recomputed from the *current* draft at confirmation time, so
any change to the draft (lines, prices, totals, status, customer) or a different
conversation yields a different token. Model output never sees or produces the token: the
runtime derives it only after the customer explicitly replies ``CONFIRM <reference>``.
"""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiConversation, PiPendingAction
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

CONFIRMATION_TTL = timedelta(minutes=30)


def fingerprint(order: dict[str, Any]) -> str:
    """Hash of the draft as PI presented it (the OrderOut tool shape)."""
    values = {
        key: order[key]
        for key in ("id", "number", "status", "currency", "subtotal", "tax_total", "total")
        + ("notes", "lines")
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def token_for(nonce: str, conversation_id: UUID, draft_fingerprint: str) -> str:
    return hashlib.sha256(f"{nonce}:{conversation_id}:{draft_fingerprint}".encode()).hexdigest()


def tokens_match(expected: str, supplied: str) -> bool:
    return hmac.compare_digest(expected.encode(), supplied.encode())


def order_summary(order: dict[str, Any]) -> str:
    summary = f"Order {order['number']}: " + "; ".join(
        f"{line['description']} × {line['quantity']} @ {line['unit_price']}"
        for line in order["lines"]
    )
    return summary + f". Total {order['total']} {order['currency']}."


async def issue(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    order: dict[str, Any],
) -> tuple[PiPendingAction, str]:
    """Create the pending confirmation for a draft; any earlier pending one is cancelled."""
    repo = WorkspaceRepository(session, PiPendingAction, scope)
    previous = await session.scalar(
        repo.select()
        .where(
            PiPendingAction.conversation_id == conversation.id,
            PiPendingAction.status == "pending",
        )
        .with_for_update()
    )
    if previous is not None:
        previous.status, previous.resolved_at = "cancelled", datetime.now(UTC)
        await session.flush()
    nonce = secrets.token_hex(16)
    draft_fingerprint = fingerprint(order)
    pending = await repo.add(
        repo.new(
            conversation_id=conversation.id,
            kind="confirm_order",
            payload={
                "order_id": str(order["id"]),
                "reference": order["number"],
                "total": str(order["total"]),
                "currency": order["currency"],
                "fingerprint": draft_fingerprint,
                "nonce": nonce,
            },
            summary=order_summary(order),
            expires_at=datetime.now(UTC) + CONFIRMATION_TTL,
        )
    )
    return pending, token_for(nonce, conversation.id, draft_fingerprint)


def token_of(pending: PiPendingAction) -> str:
    """Runtime-only: the token for a pending action as issued (before any draft change)."""
    return token_for(
        str(pending.payload.get("nonce", "")),
        pending.conversation_id,
        str(pending.payload.get("fingerprint", "")),
    )
