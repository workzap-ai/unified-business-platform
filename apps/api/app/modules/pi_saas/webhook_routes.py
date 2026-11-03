"""Public, signature-authenticated webhooks for the Pi SaaS.

Both endpoints verify the provider signature over the raw body, persist each event once
(provider idempotency key / event id), commit, enqueue bounded background processing and
acknowledge immediately. Invalid signatures are rejected without storing anything.
"""

import hashlib
import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.modules.access.dependencies import Session
from app.modules.integrations.webhook_routes import _body
from app.modules.pi.models import WhatsAppConnection
from app.modules.pi_saas import billing, connections, nori_bridge
from app.modules.pi_saas.json_util import as_dict
from app.modules.pi_saas.kapso import split_events, verify_signature

router = APIRouter(prefix="/webhooks", tags=["pi-webhooks"])


@router.post("/kapso", include_in_schema=False)
async def kapso(request: Request, session: Session) -> dict[str, Any]:
    settings = request.app.state.settings
    body = await _body(request, settings.webhook_max_body_bytes)
    secret = settings.kapso_webhook_secret
    if secret is None or not verify_signature(
        secret.get_secret_value(), body, request.headers.get("x-webhook-signature", "")
    ):
        raise HTTPException(401)
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400) from None
    header_event = request.headers.get("x-webhook-event", "")[:80]
    header_key = request.headers.get("x-idempotency-key", "")[:128]
    events = split_events(payload, header_event)
    stored: list[str] = []
    for index, (event_type, event) in enumerate(events):
        if len(events) == 1 and header_key:
            key = header_key
        else:
            identity = str(event.get("id") or as_dict(event.get("message")).get("id") or "")
            canonical = json.dumps(event, sort_keys=True, default=str)
            key = hashlib.sha256(
                f"{event_type}:{identity or index}:{canonical}".encode()
            ).hexdigest()
        new_id = await connections.store_event(session, key, event_type, event)
        if new_id is not None:
            stored.append(str(new_id))
    await session.commit()
    for event_id in stored:
        await request.app.state.queue.enqueue(
            "process_pi_provider_event", event_id, job_id=f"pi-provider:{event_id}"
        )
    return {"received": len(events)}


@router.post("/pi-billing/stripe", include_in_schema=False)
async def stripe(request: Request, session: Session) -> dict[str, Any]:
    settings = request.app.state.settings
    body = await _body(request, settings.webhook_max_body_bytes)
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not billing.verify(settings, headers, body):
        raise HTTPException(401)
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(400) from None
    if not isinstance(event, dict) or event.get("object") != "event":
        raise HTTPException(400)
    new_id = await billing.store_event(session, event)
    await session.commit()
    if new_id is not None:
        await request.app.state.queue.enqueue(
            "process_pi_billing_event", str(new_id), job_id=f"pi-billing:{new_id}"
        )
    return {"received": True}


@router.post("/nori-send", include_in_schema=False)
async def nori_send(request: Request, session: Session) -> dict[str, Any]:
    """NORI sends a free-text WhatsApp message from the Workzap number (Workzap Connect).

    Signed like the inbound call. NORI enforces the 24-hour window from its own record of the
    member's last message; Meta refuses anything outside it and that is reported back."""
    settings = request.app.state.settings
    body = await _body(request, 64 * 1024)
    secret = settings.nori_bridge_secret
    if (
        secret is None
        or not settings.nori_bridge_phone_number_id
        or not nori_bridge.verify(
            secret.get_secret_value(), body, request.headers.get("x-workzap-signature", "")
        )
    ):
        raise HTTPException(401)
    try:
        data = json.loads(body)
    except ValueError:
        raise HTTPException(400) from None
    to = str(data.get("to") or "") if isinstance(data, dict) else ""
    text = str(data.get("text") or "").strip() if isinstance(data, dict) else ""
    if not re.fullmatch(r"[0-9]{6,15}", to) or not text:
        raise HTTPException(400)
    connection = await session.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.provider == "kapso",
            WhatsAppConnection.phone_number_id == settings.nori_bridge_phone_number_id,
            WhatsAppConnection.status == "active",
        )
    )
    if connection is None:
        raise HTTPException(503)
    from app.integrations.whatsapp_bridge import token as connection_token
    from app.modules.pi.whatsapp import WhatsApp

    sent = await WhatsApp(settings, request.app.state.http, connection.provider).send(
        connection.phone_number_id,
        to,
        text[:1000],
        await connection_token(session, settings, connection),
    )
    return {"sent": True, "id": sent}
