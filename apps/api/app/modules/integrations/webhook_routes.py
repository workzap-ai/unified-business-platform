"""Public inbound webhook routes: /api/v1/webhooks/{integration_key}/{endpoint_token}.

No session, no CSRF. The Origin check is bypassed for exactly this path shape by
`PublicWebhookOriginExemption` (see app.main); everything else stays protected.
"""

import logging
import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.integrations import webhooks
from app.modules.access.dependencies import Session

logger = logging.getLogger("platform")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
Key = Annotated[str, Path(pattern=r"^[a-z0-9_]{2,60}$")]
Token = Annotated[str, Path(min_length=32, max_length=64)]
PUBLIC_WEBHOOK_PATH = re.compile(r"^/api/v1/webhooks/[a-z0-9_]{2,60}/[A-Za-z0-9_-]{32,64}/?$")


class PublicWebhookOriginExemption:
    """Strip the Origin header on public webhook paths only.

    OriginCheckMiddleware rejects unsafe requests from foreign browser origins; provider
    webhooks carry no cookies and are authenticated by signature, so an Origin header
    (some relays add one) must not block them. Must wrap OriginCheckMiddleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and PUBLIC_WEBHOOK_PATH.fullmatch(scope.get("path", "")):
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"origin"]
        await self.app(scope, receive, send)


async def _body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413)
    return bytes(body)


@router.get("/{integration_key}/{endpoint_token}", include_in_schema=False)
async def verify(
    integration_key: Key, endpoint_token: Token, request: Request, session: Session
) -> PlainTextResponse:
    try:
        challenge = await webhooks.handshake(
            session,
            request.app.state.settings,
            integration_key,
            endpoint_token,
            dict(request.query_params),
        )
    except webhooks.WebhookNotFound:
        raise HTTPException(404) from None
    if challenge is None:
        raise HTTPException(403)
    return PlainTextResponse(challenge)


@router.post("/{integration_key}/{endpoint_token}", include_in_schema=False)
async def receive(
    integration_key: Key, endpoint_token: Token, request: Request, session: Session
) -> JSONResponse:
    settings = request.app.state.settings
    body = await _body(request, settings.webhook_max_body_bytes)
    try:
        result = await webhooks.receive(
            session,
            settings,
            integration_key,
            endpoint_token,
            dict(request.headers),
            body,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
    except webhooks.WebhookNotFound:
        raise HTTPException(404) from None
    except webhooks.WebhookUnauthorized:
        raise HTTPException(401) from None
    except webhooks.WebhookInvalid:
        raise HTTPException(400) from None
    await session.commit()
    await webhooks.enqueue_events(request.app.state.queue, result.queued)
    return JSONResponse(
        {"received": True, "accepted": result.accepted, "duplicates": result.duplicates}
    )
