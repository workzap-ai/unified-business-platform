"""Staff review of pi conversations (spec 8.11.1, 10.7, 6.5; architecture vision section 9).

Read-only and staff-only: the caller needs `pi.handoffs.manage` (the capability to take a handoff),
the PI product must be enabled, and a conversation is reachable only through the inbox scope
(`PiService.conversations`), so another workspace's conversation, or one a member may not see, is
"not found". Notes are added with the existing `/pi/conversations/{id}/notes` routes; nothing here
writes.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.customers.models import Customer
from app.modules.pi import staff_review
from app.modules.pi.models import PiConversation, PiHandoff
from app.modules.pi.service import ACTIVE_HANDOFF, PiService

router = APIRouter(prefix="/pi/review", tags=["pi-staff-review"])
PERMISSION = "pi.handoffs.manage"
CANDIDATES = 200


@router.get("/attention")
async def attention(
    scope: Scope, session: Session, limit: int = Query(50, ge=1, le=100)
) -> dict[str, Any]:
    """Open conversations with a live alert, the most urgent first (red, amber, yellow, blue)."""
    service = PiService(session, scope)
    await service.require(PERMISSION)
    rows = (
        await session.execute(
            select(PiConversation, Customer.phone)
            .join(
                Customer,
                (Customer.id == PiConversation.customer_id)
                & (Customer.tenant_id == PiConversation.tenant_id),
            )
            .where(service.conversations.predicate(), PiConversation.status == "open")
            .order_by(PiConversation.last_message_at.desc())
            .limit(CANDIDATES)
        )
    ).all()
    ids = [c.id for c, _ in rows]
    open_handoffs = set(
        await session.scalars(
            service.handoffs.select()
            .with_only_columns(PiHandoff.conversation_id)
            .where(PiHandoff.conversation_id.in_(ids), PiHandoff.status.in_(ACTIVE_HANDOFF))
        )
    )
    asks = await staff_review.unanswered_counts(session, scope, ids)
    items: list[dict[str, Any]] = []
    for conversation, phone in rows:
        inbound = await staff_review.inbound_texts(
            session, scope, conversation.id, staff_review.SIGNAL_MESSAGES
        )
        open_, late = asks.get(conversation.id, (0, 0))
        alerts = staff_review.alerts_for(
            inbound,
            handoff_open=conversation.id in open_handoffs,
            asks_open=open_,
            asks_unanswered=late,
        )
        if not alerts:
            continue
        items.append(
            {
                "conversation_id": conversation.id,
                "customer_ref": str(conversation.customer_id)[:8],
                "phone": staff_review.mask_phone(phone or conversation.contact_wa_id),
                "language": conversation.language,
                "mode": conversation.mode,
                "unread_count": conversation.unread_count,
                "last_message_at": conversation.last_message_at,
                "alerts": alerts,
                "_rank": staff_review.alert_rank(alerts),
            }
        )
    items.sort(key=lambda i: (i["_rank"], -i["last_message_at"].timestamp()))
    for item in items:
        item.pop("_rank")
    return {"items": items[:limit], "total": len(items)}


@router.get("/conversations/{conversation_id}")
async def conversation_review(
    conversation_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    """Everything staff need to take over: map, dials, diagnosis, handover reason, box, alerts."""
    service = PiService(session, scope)
    await service.require(PERMISSION)
    conversation = await service.conversations.get(conversation_id)
    customer = await service.customers.get(conversation.customer_id)
    return await staff_review.review(session, scope, conversation, customer.phone)
