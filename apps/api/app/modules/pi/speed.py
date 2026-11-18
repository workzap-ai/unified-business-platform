"""How fast pi answers, and how fast the screen hears about it, in seconds.

Two honest measurements, both aggregates only (no message text, name, number or id):

- Reply speed, from rows pi already keeps: for each AI reply that went out, the time from the
  customer's message being stored to the reply leaving, split into waiting for more messages,
  thinking, getting from the queue to the sender, and sending. Replies sent before the send timing
  was recorded count only in the totals that do not need it.
- Live-update speed, from samples the open screens report after each event: how long the signal
  waited on the server, and how long the screen took from hearing it to showing the data.

Nothing here changes what pi says or does; it only reads.
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.pi import live_events
from app.modules.pi.models import PiAgentRun, PiMessage
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("platform")

MAX_ROWS = 500
TIMING_KEEP = 300
TIMING_DAYS = 7
MAX_MS = 600_000


def percentiles(values: list[float]) -> dict[str, float] | None:
    """Median, 90th percentile, average and the slowest, or None when there is nothing."""
    if not values:
        return None
    ordered = sorted(values)

    def at(q: float) -> float:
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    return {
        "p50": round(at(0.5), 2),
        "p90": round(at(0.9), 2),
        "avg": round(sum(ordered) / len(ordered), 2),
        "max": round(ordered[-1], 2),
    }


def _seconds(delta: timedelta) -> float:
    return max(0.0, delta.total_seconds())


async def reply_stats(session: AsyncSession, scope: WorkspaceScope, hours: int) -> dict[str, Any]:
    """Reply speed over the last ``hours`` (the newest ``MAX_ROWS`` AI replies)."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    inbound, reply = aliased(PiMessage), aliased(PiMessage)
    rows = (
        await session.execute(
            select(
                inbound.created_at,
                PiAgentRun.created_at,
                PiAgentRun.completed_at,
                PiAgentRun.latency_ms,
                reply.created_at,
                reply.media,
                reply.delivered_at,
            )
            .select_from(PiAgentRun)
            .join(inbound, inbound.id == PiAgentRun.message_id)
            .join(reply, reply.id == PiAgentRun.response_message_id)
            .where(
                PiAgentRun.tenant_id == scope.tenant_id,
                PiAgentRun.environment_id == scope.environment_id,
                PiAgentRun.created_at >= since,
                PiAgentRun.status == "completed",
                reply.sender_type == "ai",
                reply.status.in_(("sent", "delivered", "read")),
            )
            .order_by(PiAgentRun.created_at.desc())
            .limit(MAX_ROWS)
        )
    ).all()
    waiting: list[float] = []
    thinking: list[float] = []
    queued: list[float] = []
    sending: list[float] = []
    totals: list[float] = []
    delivered: list[float] = []
    timed = 0
    for stored, run_start, run_end, latency_ms, queued_at, media, delivered_at in rows:
        if stored is None or run_start is None:
            continue
        waiting.append(_seconds(run_start - stored))
        if latency_ms is not None:
            thinking.append(latency_ms / 1000)
        elif run_end is not None:
            thinking.append(_seconds(run_end - run_start))
        timing = (media or {}).get("send_timing") or {}
        picked, sent = timing.get("picked_ms"), timing.get("send_ms")
        if picked is None or sent is None:
            continue
        timed += 1
        queued.append(picked / 1000)
        sending.append(sent / 1000)
        left = queued_at + timedelta(milliseconds=picked + sent)
        totals.append(_seconds(left - stored))
        if delivered_at is not None:
            delivered.append(_seconds(delivered_at - left))
    return {
        "hours": hours,
        "replies": len(rows),
        "with_send_timing": timed,
        "total_s": percentiles(totals),
        "stages_s": {
            "waiting_for_more_messages": percentiles(waiting),
            "thinking": percentiles(thinking),
            "queue_to_sender": percentiles(queued),
            "sending": percentiles(sending),
            "delivered_after_sent": percentiles(delivered),
        },
    }


# ---- live-update samples (reported by the open screens) ----------------------------------------


def _timing_key(tenant_id: UUID, environment_id: UUID) -> str:
    return f"pi:events:timing:{tenant_id}:{environment_id}"


def clamp_ms(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= MAX_MS else None


async def record_timing(
    redis: Any, tenant_id: UUID, environment_id: UUID, lag_ms: object, screen_ms: object
) -> bool:
    """Keep one sample (server lag, screen time) for this workspace. Never raises."""
    lag, screen = clamp_ms(lag_ms), clamp_ms(screen_ms)
    if redis is None or lag is None or screen is None:
        return False
    key = _timing_key(tenant_id, environment_id)
    try:
        pipe = redis.pipeline()
        pipe.lpush(key, f"{lag},{screen},{int(time.time())}")
        pipe.ltrim(key, 0, TIMING_KEEP - 1)
        pipe.expire(key, TIMING_DAYS * 86400)
        await pipe.execute()
        return True
    except Exception:  # noqa: BLE001 - a lost sample only makes the report a little thinner
        logger.warning("pi_event_timing_failed")
        return False


async def live_stats(
    redis: Any, settings: Any, tenant_id: UUID, environment_id: UUID
) -> dict[str, Any]:
    enabled = live_events.enabled(settings)
    out: dict[str, Any] = {
        "enabled": enabled,
        "publishing": False,
        "samples": 0,
        "server_lag_ms": None,
        "screen_ms": None,
        "total_ms": None,
    }
    if redis is None or not enabled:
        return out
    out["publishing"] = await live_events.publisher_alive(redis)
    try:
        raw = await redis.lrange(_timing_key(tenant_id, environment_id), 0, TIMING_KEEP - 1)
    except Exception:  # noqa: BLE001
        return out
    lags: list[float] = []
    screens: list[float] = []
    for item in raw:
        text = item.decode() if isinstance(item, bytes) else str(item)
        parts = text.split(",")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            lags.append(int(parts[0]))
            screens.append(int(parts[1]))
    out["samples"] = len(lags)
    out["server_lag_ms"] = percentiles(lags)
    out["screen_ms"] = percentiles(screens)
    out["total_ms"] = percentiles([a + b for a, b in zip(lags, screens, strict=True)])
    return out
