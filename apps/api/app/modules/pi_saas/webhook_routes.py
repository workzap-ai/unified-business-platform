"""Public, signature-authenticated webhooks for the Pi SaaS.

Both endpoints verify the provider signature over the raw body, persist each event once
(provider idempotency key / event id), commit, enqueue bounded background processing and
acknowledge immediately. Invalid signatures are rejected without storing anything.
"""

import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.modules.access.dependencies import Session
from app.modules.integrations.webhook_routes import _body
from app.modules.pi_saas import billing, connections
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
