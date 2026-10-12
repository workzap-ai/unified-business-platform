"""Invites on WhatsApp: the invite link (set your password) goes to the new team member
on WhatsApp, for Owner OS and the pi app.

WhatsApp lets a business number write freely only to someone who messaged it in the
last 24 hours. So: when the person has an open chat with the business's pi number, pi
sends the invite from that number; otherwise the inviter gets a wa.me link that opens
their own WhatsApp with the message ready (one tap to send). Only invite and sign-in
links of this platform can be sent, never an arbitrary link.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.campaigns import production_connection
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

WINDOW = timedelta(hours=24)
router = APIRouter(prefix="/team-invites", tags=["team-invites"])


class WhatsAppInvite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    phone: str = Field(min_length=8, max_length=32)
    name: str = Field(default="", max_length=120)
    link: str = Field(min_length=10, max_length=600)


def _allowed_link(request: Request, link: str) -> bool:
    """Only this platform's invite (set your password) or sign-in links."""
    settings = request.app.state.settings
    for base in (settings.web_base, (settings.pi_app_public_url or "").rstrip("/")):
        if not base or not link.startswith(f"{base}/"):
            continue
        path = link[len(base) :]
        if path.startswith("/accept-invite?token=") or path in ("/login", "/sign-in"):
            return True
    return False


@router.post("/whatsapp")
async def send_invite_on_whatsapp(
    data: WhatsAppInvite, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("admin.members.manage")
    digits = "".join(ch for ch in data.phone if ch.isdigit())
    if not 8 <= len(digits) <= 15:
        raise BusinessRuleViolation("PHONE_INVALID", "Enter the WhatsApp number with country code")
    if not _allowed_link(request, data.link):
        raise BusinessRuleViolation("LINK_INVALID", "Only invite links can be sent", 422)
    workspace = await session.scalar(select(Tenant.name).where(Tenant.id == scope.tenant_id))
    hello = f"Hi {data.name.split()[0]}, " if data.name.strip() else "Hi, "
    text = (
        f"{hello}{scope.actor_label} invited you to join {workspace or 'the team'}. "
        f"Open this link to set your password and sign in: {data.link}"
    )
    share = f"https://wa.me/{digits}?text={url_quote(text)}"
    connection = await production_connection(session, scope)
    if connection is None:
        return {"delivery": "manual", "share": share, "message": text}
    conversation = await WorkspaceRepository(session, PiConversation, scope).find(
        PiConversation.connection_id == connection.id,
        PiConversation.contact_wa_id == digits,
        PiConversation.status == "open",
    )
    now = datetime.now(UTC)
    if (
        conversation is None
        or conversation.last_inbound_at is None
        or conversation.last_inbound_at < now - WINDOW
    ):
        # No open chat with the business number: WhatsApp needs the inviter to send it.
        return {"delivery": "manual", "share": share, "message": text}
    repo = WorkspaceRepository(session, PiMessage, scope)
    message = await repo.add(
        repo.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="system",
            body=text,
            status="queued",
            idempotency_key=f"team-invite:{digits}:{data.link[-24:]}",
        )
    )
    conversation.last_message_at = now
    conversation.last_message_preview = text[:200]
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    return {"delivery": "sent", "share": share, "message": text}
