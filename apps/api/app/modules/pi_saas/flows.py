"""WhatsApp Flows: short structured forms (lead details, booking request, feedback).

A business builds and publishes each Flow in its WhatsApp Manager, then registers it
here (``whatsapp_config.flows``: purpose -> flow id, button text, first screen). Pi can
then send the form inside the 24-hour customer-service window through the opt-in
``send_form`` tool, as an ordinary outbound message with the usual re-checks.

Every form carries a signed ``flow_token`` bound to the conversation and purpose. A
reply is accepted only when that token verifies and belongs to the same conversation,
so a forwarded or forged form can't write into someone else's record. Answers are kept
on the conversation's brief (and in customer memory) as the customer's own statements;
they never become business knowledge.
"""

import hashlib
import hmac
import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.pi.models import PiConversation, PiMessage
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

PURPOSES = ("lead", "booking", "feedback")
LABEL = {"lead": "Your details", "booking": "Booking request", "feedback": "Your feedback"}
MAX_FIELDS = 30
MAX_VALUE = 500
MAX_RESPONSE_BYTES = 16 * 1024


def valid_config(value: Any) -> bool:
    if not isinstance(value, dict) or len(value) > len(PURPOSES):
        return False
    for purpose, flow in value.items():
        if purpose not in PURPOSES or not isinstance(flow, dict):
            return False
        if set(flow) - {"flow_id", "cta", "screen", "body"}:
            return False
        if not re.fullmatch(r"[0-9]{5,32}", str(flow.get("flow_id", ""))):
            return False
        if not 1 <= len(str(flow.get("cta", ""))) <= 20:  # WhatsApp's button limit
            return False
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,49}", str(flow.get("screen", ""))):
            return False
        if len(str(flow.get("body", ""))) > 400:
            return False
    return True


def _key(settings: Settings) -> bytes | None:
    secret = settings.secrets_encryption_key
    if secret is None:
        return None
    return hashlib.sha256(b"pi-flow-token:" + secret.get_secret_value().encode()).digest()


def token(settings: Settings, conversation_id: UUID, purpose: str) -> str | None:
    key = _key(settings)
    if key is None:
        return None
    body = f"{purpose}.{conversation_id}"
    sig = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"pi.{body}.{sig}"


def verify(settings: Settings, value: str, conversation_id: UUID) -> str | None:
    """The purpose when the token is ours and for this conversation, else None."""
    match = re.fullmatch(r"pi\.(lead|booking|feedback)\.([0-9a-f-]{36})\.([0-9a-f]{32})", value)
    if not match or match.group(2) != str(conversation_id):
        return None
    expected = token(settings, conversation_id, match.group(1))
    return match.group(1) if expected and hmac.compare_digest(expected, value) else None


def parse_reply(raw: Any) -> dict[str, Any] | None:
    """The response JSON of a WhatsApp ``nfm_reply`` (a string), bounded and flat."""
    if not isinstance(raw, str) or len(raw.encode()) > MAX_RESPONSE_BYTES:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def clean_fields(data: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in data.items():
        if key == "flow_token" or len(fields) >= MAX_FIELDS:
            continue
        name = re.sub(r"[^A-Za-z0-9_]", "_", str(key))[:40]
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value[:10])
        if isinstance(value, (str, int, float, bool)) and name:
            fields[name] = str(value)[:MAX_VALUE]
    return fields


def interactive_reply(message: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    """Normalize an inbound interactive message: (message_type, text, form answers).

    A Flow (form) reply becomes "interactive" with its answers; tapping a reply button or
    a list option is simply text (the option's title)."""
    interactive = message.get("interactive")
    if not isinstance(interactive, dict):
        return "other", "", None
    kind = interactive.get("type")
    if kind == "nfm_reply":
        reply = interactive.get("nfm_reply") or {}
        form = parse_reply(reply.get("response_json")) if isinstance(reply, dict) else None
        if form is None:
            return "other", "", None
        return "interactive", summary(clean_fields(form)), form
    if kind in {"button_reply", "list_reply"}:
        choice = interactive.get(kind) or {}
        title = str(choice.get("title", "") if isinstance(choice, dict) else "")[:200]
        return ("text", title, None) if title else ("other", "", None)
    return "other", "", None


def summary(fields: dict[str, str]) -> str:
    parts = [f"{k.replace('_', ' ')}: {v}" for k, v in list(fields.items())[:12]]
    return ("Form reply. " + "; ".join(parts))[:4000] if parts else "Form reply."


async def note_form_reply(
    session: AsyncSession, settings: Settings, scope: WorkspaceScope, message: PiMessage
) -> bool:
    """Save a verified form reply to the conversation brief and customer memory."""
    form = (message.media or {}).get("form_response")
    if message.direction != "inbound" or not isinstance(form, dict):
        return False
    purpose = verify(settings, str(form.get("flow_token", "")), message.conversation_id)
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        message.conversation_id
    )
    if purpose is None:
        await record(
            session,
            "pi.form_reply_rejected",
            scope=scope,
            entity_type="pi_conversation",
            entity_id=conversation.id,
        )
        return False
    fields = clean_fields(form)
    brief = dict(conversation.service_brief or {})
    forms = dict(brief.get("forms") or {})
    forms[purpose] = {"fields": fields, "message_id": str(message.id)}
    brief["forms"] = forms
    conversation.service_brief = brief
    if conversation.customer_id is not None and fields:
        from app.modules.pi.knowledge import remember

        await remember(
            session,
            scope,
            conversation.customer_id,
            f"{LABEL[purpose]} (customer's own form answers): {summary(fields)[12:]}",
            message.id,
        )
    return True
