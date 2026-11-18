"""Live inbox signals over Server-Sent Events (see live_events.py for the design).

POST /pi/events/ticket  a normal authenticated call: asks for a 60-second signed ticket. Answers
                        ``{"enabled": false}`` while PI_EVENTS_ENABLED is off.
GET  /pi/events/stream  opens the stream with that ticket. It holds no database session and no
                        cookie check: the ticket is the credential for one minute, bound to one
                        workspace and one person. Mounted for Owner OS and the pi app.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from app.core.rate_limit import hit
from app.modules.access.dependencies import Scope, Session
from app.modules.pi import live_events, speed
from app.modules.pi.service import require_pi
from app.shared.errors import BusinessRuleViolation

logger = logging.getLogger("platform")

router = APIRouter(prefix="/pi/events", tags=["pi-events"])


def events_client(request: Request) -> Redis:
    """A Redis client of its own for the streams (each holds one connection for up to a minute),
    so open screens can never use up the connections the rest of the API shares."""
    app = request.app
    client: Redis | None = getattr(app.state, "events_redis", None)
    if client is None:
        settings = app.state.settings
        client = Redis.from_url(
            settings.redis_url.get_secret_value(),
            socket_connect_timeout=settings.dependency_timeout_seconds,
            max_connections=live_events.MAX_PER_PROCESS + 20,
        )
        app.state.events_redis = client
    return client


@router.post("/ticket")
async def ticket(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.read")
    settings = request.app.state.settings
    if not live_events.enabled(settings):
        return {"enabled": False}
    assert scope.user_id is not None
    if not await hit(request, "pi-events-ticket", str(scope.user_id), 30, 60):
        raise BusinessRuleViolation("RATE_LIMITED", "Too many requests. Try again shortly.", 429)
    return {
        "enabled": True,
        "ticket": live_events.make_ticket(
            settings, scope.tenant_id, scope.environment_id, scope.user_id
        ),
        "expires_in": live_events.TICKET_SECONDS,
    }


@router.get("/stream")
async def stream(request: Request, ticket: str = Query(max_length=400)) -> Response:
    settings = request.app.state.settings
    if not live_events.enabled(settings):
        return Response(status_code=204)  # the browser stops reconnecting on a 204
    ident = live_events.read_ticket(settings, ticket)
    if ident is None:
        return Response(status_code=401)
    tenant_id, environment_id, user_id = ident
    redis = events_client(request)

    async def body() -> Any:
        # The slot is taken and freed inside the generator, so every exit path (the person left,
        # the minute ended, an error) frees it; a stream that never starts never takes one.
        if not live_events.acquire(user_id):
            yield "event: busy\ndata: {}\n\n"
            return
        try:
            async for frame in live_events.stream(redis, tenant_id, environment_id):
                yield frame
        except Exception:  # noqa: BLE001 - the screen falls back to polling
            logger.warning("pi_event_stream_failed")
        finally:
            live_events.release(user_id)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class Timing(BaseModel):
    """One sample from an open screen: how long the server held the signal and how long the screen
    took from hearing it to showing the data. Numbers only."""

    model_config = ConfigDict(extra="forbid")
    lag_ms: int = Field(ge=0, le=speed.MAX_MS)
    screen_ms: int = Field(ge=0, le=speed.MAX_MS)


@router.post("/timing", status_code=204)
async def timing(data: Timing, request: Request, scope: Scope, session: Session) -> Response:
    await require_pi(session, scope, "pi.read")
    if live_events.enabled(request.app.state.settings) and await hit(
        request, "pi-events-timing", str(scope.user_id), 12, 60
    ):
        await speed.record_timing(
            request.app.state.redis,
            scope.tenant_id,
            scope.environment_id,
            data.lag_ms,
            data.screen_ms,
        )
    return Response(status_code=204)


@router.get("/speed")
async def speed_report(
    request: Request,
    scope: Scope,
    session: Session,
    hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    """How fast pi answers (from stored rows) and how fast open screens hear about it (from their
    samples), in aggregates only."""
    await require_pi(session, scope, "pi.read")
    replies = await speed.reply_stats(session, scope, hours)
    live = await speed.live_stats(
        request.app.state.redis, request.app.state.settings, scope.tenant_id, scope.environment_id
    )
    return {"replies": replies, "live": live}
