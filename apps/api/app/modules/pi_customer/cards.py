"""Visual cards pi sends on WhatsApp: a signed, expiring link to a PNG the pi app draws
from the same data as the dashboard (map, journey, flow). The token names one
conversation and one card; it carries no customer details itself."""

import base64
import hmac
import json
import time
from typing import Any
from uuid import UUID

from app.core.config import Settings
from app.modules.pi_customer.access import _sign

CARD_SECONDS = 7 * 86400
KINDS = ("map", "journey", "flow")


def card_token(
    settings: Settings, conversation_id: UUID, kind: str, index: int = 0, language: str = ""
) -> str:
    data = json.dumps(
        {
            "c": str(conversation_id),
            "k": kind,
            "i": index,
            "l": language,  # the customer's language: the card's words match the chat
            "e": int(time.time()) + CARD_SECONDS,
        },
        separators=(",", ":"),
    ).encode()
    body = base64.urlsafe_b64encode(data).decode().rstrip("=")
    return f"{body}.{_sign(settings, data)}"


def read_card(settings: Settings, token: str) -> dict[str, Any] | None:
    """The card a token names, or None when it is forged, malformed or expired."""
    try:
        body, mac = token.split(".", 1)
        data = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if not hmac.compare_digest(mac, _sign(settings, data)):
            return None
        claims = json.loads(data)
        if int(claims["e"]) < time.time() or claims["k"] not in KINDS:
            return None
        return {
            "conversation_id": UUID(claims["c"]),
            "kind": claims["k"],
            "index": int(claims["i"]),
            "language": str(claims.get("l") or ""),
        }
    except (ValueError, KeyError, TypeError):
        return None


def card_url(settings: Settings, token: str) -> str:
    return f"{settings.pi_app_public_url.rstrip('/')}/customer/card/{token}/card.png"
