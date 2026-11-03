"""Workzap Connect: the bridge between pi's Workzap number and NORI (Commerce Center).

NORI workspace members link their WhatsApp number by sending a one-time code
(``NORI-123456``) to the Workzap number. pi receives every message on that number, so for the
one configured number it first asks NORI whether the message is its own (a link code, or a
number that is already linked). NORI answers ``{"handled": bool, "reply": str | None}``.

- handled: pi stores nothing, runs no brain, and sends ``reply`` as free text (the person just
  wrote, so the 24-hour window is open).
- not handled, or NORI unreachable: pi carries on as usual (fail open). The one exception is a
  message that looks like a link code: it is never given to the brain, the person is told to
  try again.

Both directions are signed: ``X-Workzap-Signature: sha256=<HMAC-SHA256 of the raw body>``
with ``NORI_BRIDGE_SECRET``. NORI sends through pi with ``POST /api/v1/webhooks/nori-send``
(see webhook_routes.py), so the Workzap token never leaves pi.
"""

import hashlib
import hmac
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger("app.pi.nori_bridge")

CODE = re.compile(r"\bNORI[-\s]?\d{6}\b", re.IGNORECASE)
RETRY_TEXT = "I could not connect your WhatsApp just now. Please send the code again in a minute."
TIMEOUT_SECONDS = 8


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, header: str) -> bool:
    return bool(header) and hmac.compare_digest(sign(secret, body), header.strip().lower())


def configured_for(settings: Settings, phone_number_id: str | None) -> bool:
    return bool(
        settings.nori_bridge_url
        and settings.nori_bridge_secret is not None
        and settings.nori_bridge_phone_number_id
        and phone_number_id == settings.nori_bridge_phone_number_id
    )


def looks_like_code(text: str) -> bool:
    return bool(CODE.search(text or ""))


async def ask_nori(
    settings: Settings, http: httpx.AsyncClient, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """NORI's answer, or None when it could not be reached or answered badly."""
    secret = settings.nori_bridge_secret
    if secret is None or not settings.nori_bridge_url:
        return None
    body = json.dumps(payload, separators=(",", ":")).encode()
    try:
        response = await http.post(
            settings.nori_bridge_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Workzap-Signature": sign(secret.get_secret_value(), body),
            },
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("pi_nori_bridge_unreachable")
        return None
    if response.status_code != 200 or not isinstance(data, dict):
        logger.warning("pi_nori_bridge_rejected", extra={"status": response.status_code})
        return None
    return data


async def try_handle(
    ctx: dict[str, Any], connection: Any, payload: dict[str, Any]
) -> tuple[bool, str | None]:
    """(handled, reply) for one inbound message event payload of pi's webhook event."""
    settings: Settings = ctx["settings"]
    if payload.get("kind") != "message" or payload.get("message_type") != "text":
        return False, None
    if not configured_for(settings, getattr(connection, "phone_number_id", None)):
        return False, None
    text = str(payload.get("body") or "")
    answer = await ask_nori(
        settings,
        ctx["http"],
        {
            "from": str(payload.get("sender") or ""),
            "message_id": str(payload.get("message_id") or ""),
            "text": text[:4000],
            "name": payload.get("profile") or None,
            "timestamp": None,
        },
    )
    if answer is None:
        return (True, RETRY_TEXT) if looks_like_code(text) else (False, None)
    if not answer.get("handled"):
        return False, None
    reply = answer.get("reply")
    return True, reply.strip()[:1000] if isinstance(reply, str) and reply.strip() else None
