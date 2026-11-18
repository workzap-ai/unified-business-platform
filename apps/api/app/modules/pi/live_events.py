"""Live "something changed" signals for the inbox (Server-Sent Events over Redis pub/sub).

What this is, and what it is not:
- An event carries only a kind (``inbox`` or ``handoff``), never a message, a name, a number or an
  id. The screen reacts by refetching through the normal authenticated endpoints, which apply every
  visibility rule (assigned-only chats, workspace scope). Nothing here can leak a chat.
- Publishing is best effort: a short timeout, every error swallowed. A Redis outage or a slow
  subscriber can never delay or fail a message, a reply or a webhook.
- The stream holds no database session. The screen first asks for a short-lived signed ticket
  through a normal authenticated call, then opens the stream with it.
- Everything is off unless ``PI_EVENTS_ENABLED`` is set, and the screens keep polling as the
  fallback, so a dropped stream only means updates come a few seconds later.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

logger = logging.getLogger("platform")

KINDS = ("inbox", "handoff")
TICKET_SECONDS = 60
HEARTBEAT_SECONDS = 15
MAX_STREAM_SECONDS = 55  # short on purpose: proxies cut long streams, the screen reconnects
MAX_PER_USER = 4
MAX_PER_PROCESS = 300
PUBLISH_TIMEOUT = 0.5

_open_by_user: dict[str, int] = {}
_open_total = 0


def channel(tenant_id: UUID, environment_id: UUID) -> str:
    return f"pi:events:{tenant_id}:{environment_id}"


def enabled(settings: Any) -> bool:
    return bool(getattr(settings, "pi_events_enabled", False)) and (
        getattr(settings, "secrets_encryption_key", None) is not None
    )


async def publish(
    redis: Any, settings: Any, tenant_id: UUID, environment_id: UUID, kind: str = "inbox"
) -> bool:
    """Tell the open screens of this workspace that something changed. Never raises."""
    if redis is None or kind not in KINDS or not enabled(settings):
        return False
    try:
        await asyncio.wait_for(
            redis.publish(channel(tenant_id, environment_id), kind), PUBLISH_TIMEOUT
        )
        return True
    except Exception:  # noqa: BLE001 - a missed signal only means the next poll finds it
        logger.warning("pi_event_publish_failed")
        return False


# ---- the ticket: who may open a stream, for one minute ----------------------------------------


def _key(settings: Any) -> bytes:
    return hashlib.sha256(
        b"pi-events|" + settings.secrets_encryption_key.get_secret_value().encode()
    ).digest()


def make_ticket(
    settings: Any, tenant_id: UUID, environment_id: UUID, user_id: UUID, *, now: float | None = None
) -> str:
    body = {
        "t": str(tenant_id),
        "e": str(environment_id),
        "u": str(user_id),
        "x": int((now if now is not None else time.time()) + TICKET_SECONDS),
    }
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_key(settings), raw, hashlib.sha256).hexdigest()[:40]
    return f"{raw.decode()}.{signature}"


def read_ticket(
    settings: Any, ticket: str, *, now: float | None = None
) -> tuple[UUID, UUID, UUID] | None:
    """(tenant, environment, user) when the ticket is genuine and unexpired, else None."""
    try:
        raw, signature = ticket.rsplit(".", 1)
        expected = hmac.new(_key(settings), raw.encode(), hashlib.sha256).hexdigest()[:40]
        if not hmac.compare_digest(signature, expected):
            return None
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if int(body["x"]) < (now if now is not None else time.time()):
            return None
        return UUID(body["t"]), UUID(body["e"]), UUID(body["u"])
    except Exception:  # noqa: BLE001 - any malformed ticket is simply refused
        return None


# ---- the stream -------------------------------------------------------------------------------


def acquire(user_id: UUID) -> bool:
    """Reserve a stream slot for this person and this process (a cap on open connections)."""
    global _open_total
    user = str(user_id)
    if _open_total >= MAX_PER_PROCESS or _open_by_user.get(user, 0) >= MAX_PER_USER:
        return False
    _open_by_user[user] = _open_by_user.get(user, 0) + 1
    _open_total += 1
    return True


def release(user_id: UUID) -> None:
    global _open_total
    user = str(user_id)
    left = _open_by_user.get(user, 0) - 1
    if left > 0:
        _open_by_user[user] = left
    else:
        _open_by_user.pop(user, None)
    _open_total = max(0, _open_total - 1)


def frame(kind: str) -> str:
    return f"event: change\ndata: {json.dumps({'kind': kind})}\n\n"


async def stream(
    redis: Any, tenant_id: UUID, environment_id: UUID, *, max_seconds: float = MAX_STREAM_SECONDS
) -> AsyncIterator[str]:
    """SSE frames for one workspace: a ready line, heartbeats, and change events, for at most
    ``max_seconds`` (the screen reconnects). Closing the generator unsubscribes."""
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel(tenant_id, environment_id))
        yield "retry: 5000\n\nevent: ready\ndata: {}\n\n"
        started = last_beat = time.monotonic()
        while time.monotonic() - started < max_seconds:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            now = time.monotonic()
            if message and message.get("type") == "message":
                data = message.get("data")
                kind = data.decode() if isinstance(data, bytes) else str(data)
                if kind in KINDS:
                    yield frame(kind)
                    last_beat = now
            elif now - last_beat >= HEARTBEAT_SECONDS:
                yield "event: ping\ndata: {}\n\n"  # an event, not a comment: the screen sees it
                last_beat = now
    finally:
        try:
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            logger.warning("pi_event_unsubscribe_failed")
