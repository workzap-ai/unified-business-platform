"""A signed, expiring link to the photo or file behind a card, for nori to open.

pi never stores a customer's media: it keeps the provider's media id and fetches the file on
demand with the workspace's own credentials (behind the app login). Nori cannot log in, so the card
sent to nori carries `https://<api>/api/pi/nori-media/<token>`. The token names one card and an
expiry and is signed with the bridge secret (domain-separated), so it cannot be guessed, reused for
another card or extended. The route behind it re-checks that the card still exists and was filed
from a registry number's inbound message, then streams the file; nothing is copied or cached.
"""

import hashlib
import hmac
import time
from typing import Any
from uuid import UUID

LINK_TTL_SECONDS = 30 * 24 * 3600
PATH = "/api/pi/nori-media/"
_TAG_LEN = 32
KINDS = {"image": "image", "audio": "audio", "video": "video", "other": "document"}


def _tag(secret: str, item_id: UUID, expires: int) -> str:
    message = f"nori-media:{item_id}:{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:_TAG_LEN]


def make_token(secret: str, item_id: UUID, *, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + LINK_TTL_SECONDS)
    return f"{item_id.hex}.{expires}.{_tag(secret, item_id, expires)}"


def read_token(secret: str, token: str, *, now: float | None = None) -> UUID | None:
    """The card id when the token is genuine and not expired, else None."""
    parts = token.split(".")
    if len(parts) != 3 or len(token) > 120:
        return None
    raw_id, raw_expires, tag = parts
    try:
        item_id = UUID(hex=raw_id)
        expires = int(raw_expires)
    except ValueError:
        return None
    if expires < (time.time() if now is None else now):
        return None
    if not hmac.compare_digest(tag, _tag(secret, item_id, expires)):
        return None
    return item_id


async def media_of(session: Any, item: Any) -> tuple[Any, dict[str, Any]] | None:
    """The inbound message and its media record behind a card, or None (no file to give)."""
    from app.modules.pi.models import PiMessage

    if item.message_id is None or item.source != "whatsapp":
        return None
    message = await session.get(PiMessage, item.message_id)
    if (
        message is None
        or message.direction != "inbound"
        or message.tenant_id != item.tenant_id
        or message.environment_id != item.environment_id
        or message.message_type not in KINDS
        or message.message_type == "text"
    ):
        return None
    media = message.media if isinstance(message.media, dict) else {}
    if not str(media.get("provider_media_id") or ""):
        return None
    return message, media


async def fetch(session: Any, state: Any, token: str) -> tuple[bytes, str, str] | None:
    """Bytes, mime type and file name for a genuine token, else None. Needs the bridge on and the
    workspace's forward flag exactly true (the same switch that lets the card leave pi)."""
    from sqlalchemy import select

    from app.integrations.whatsapp_bridge import token as connection_token
    from app.modules.pi.models import PiConversation, PiSettings, WhatsAppConnection
    from app.modules.pi.whatsapp import WhatsApp
    from app.modules.pi_saas.nori_board.models import PiNoriItem
    from app.modules.pi_saas.nori_credits.config import killed, read_env, workspace_bridge
    from app.shared.errors import BusinessRuleViolation

    settings, http = state.settings, state.http
    env = read_env(settings)
    if env is None or killed(settings):
        return None
    item_id = read_token(env.secret, token)
    if item_id is None:
        return None
    item = await session.get(PiNoriItem, item_id)
    if item is None:
        return None
    rules = await session.scalar(
        select(PiSettings.response_rules).where(
            PiSettings.tenant_id == item.tenant_id,
            PiSettings.environment_id == item.environment_id,
        )
    )
    bridge = workspace_bridge(rules)
    if bridge is None or not (bridge.forward and bridge.forward_media):
        return None
    found = await media_of(session, item)
    if found is None:
        return None
    message, media = found
    conversation = await session.get(PiConversation, message.conversation_id)
    if conversation is None or conversation.id != item.conversation_id:
        return None
    connection = await session.get(WhatsAppConnection, conversation.connection_id)
    if connection is None:
        return None
    try:
        data, mime = await WhatsApp(settings, http, connection.provider).media(
            str(media.get("provider_media_id")),
            await connection_token(session, settings, connection),
            url=str(media.get("media_url") or ""),
            mime=str(media.get("mime_type") or ""),
        )
    except BusinessRuleViolation:
        return None
    return data, mime, str(media.get("filename") or media.get("file_name") or "file")


def public_base(settings: Any) -> str | None:
    base = str(getattr(settings, "integrations_public_base_url", "") or "").strip().rstrip("/")
    return base if base.startswith("https://") else None


def url_for(settings: Any, secret: str, item_id: UUID) -> str | None:
    base = public_base(settings)
    return f"{base}{PATH}{make_token(secret, item_id)}" if base else None
