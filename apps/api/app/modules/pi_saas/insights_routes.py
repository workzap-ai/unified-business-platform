"""Home insights for the Pi app: a 7-day activity chart, how much Pi handled on its own,
how fast it replied and what customers asked about. Counted only over conversations
the member may see, in the business's own timezone. No sample or estimated numbers."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.modules.access.dependencies import Scope, Session
from app.modules.pi.models import PiAgentRun, PiConversation, PiHandoff, PiMessage
from app.modules.pi.service import PiService
from app.modules.pi_saas import onboarding
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/home", tags=["pi-app"])
DAYS = 7
SENT = ("sent", "delivered", "read")


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@router.get("/insights")
async def insights(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    account = await onboarding.current_account(session, scope.tenant_id)
    zone = _zone(account.timezone)
    today = datetime.now(zone).date()
    first = today - timedelta(days=DAYS - 1)
    since = datetime.combine(first, datetime.min.time(), zone).astimezone(UTC)
    service = PiService(session, scope)
    visible = service.conversations.select().with_only_columns(PiConversation.id)

    # Messages per local day: customer messages, Pi's replies, the team's replies.
    local_day = func.date(func.timezone(zone.key, PiMessage.created_at))
    rows = await session.execute(
        select(
            local_day,
            func.count().filter(PiMessage.direction == "inbound"),
            func.count().filter(
                PiMessage.direction == "outbound",
                PiMessage.sender_type == "ai",
                PiMessage.status.in_(SENT),
            ),
            func.count().filter(
                PiMessage.direction == "outbound",
                PiMessage.sender_type == "human",
                PiMessage.status.in_(SENT),
            ),
        )
        .where(
            service.messages.predicate(),
            PiMessage.conversation_id.in_(visible),
            PiMessage.created_at >= since,
        )
        .group_by(local_day)
    )
    by_day: dict[date, tuple[int, int, int]] = {
        day: (int(a), int(b), int(c)) for day, a, b, c in rows.all()
    }
    daily = [
        {
            "day": (first + timedelta(days=i)).isoformat(),
            "customers": by_day.get(first + timedelta(days=i), (0, 0, 0))[0],
            "pi": by_day.get(first + timedelta(days=i), (0, 0, 0))[1],
            "team": by_day.get(first + timedelta(days=i), (0, 0, 0))[2],
        }
        for i in range(DAYS)
    ]

    # Conversations active this week, and how many Pi handled without a person.
    active = (
        select(PiConversation.id)
        .where(service.conversations.predicate(), PiConversation.last_message_at >= since)
        .subquery()
    )
    total = int(await session.scalar(select(func.count()).select_from(active)) or 0)
    handed = int(
        await session.scalar(
            select(func.count(func.distinct(PiHandoff.conversation_id))).where(
                service.handoffs.predicate(),
                PiHandoff.conversation_id.in_(select(active.c.id)),
                PiHandoff.created_at >= since,
            )
        )
        or 0
    )

    # Reply speed: from the customer's message to Pi's reply (median over the week).
    asked = aliased(PiMessage)
    asked_at = (
        select(func.max(asked.created_at))
        .where(
            asked.tenant_id == PiMessage.tenant_id,
            asked.conversation_id == PiMessage.conversation_id,
            asked.direction == "inbound",
            asked.created_at <= PiMessage.created_at,
        )
        .scalar_subquery()
    )
    delay = func.extract("epoch", PiMessage.created_at - asked_at)
    speed = (
        await session.execute(
            select(func.percentile_cont(0.5).within_group(delay), func.count(delay)).where(
                service.messages.predicate(),
                PiMessage.conversation_id.in_(visible),
                PiMessage.direction == "outbound",
                PiMessage.sender_type == "ai",
                PiMessage.status.in_(SENT),
                PiMessage.created_at >= since,
            )
        )
    ).one()
    runs = WorkspaceRepository(session, PiAgentRun, scope)
    topics = await session.execute(
        select(PiAgentRun.intent, func.count(func.distinct(PiAgentRun.conversation_id)))
        .where(
            runs.predicate(),
            PiAgentRun.conversation_id.in_(visible),
            PiAgentRun.created_at >= since,
            PiAgentRun.intent.is_not(None),
        )
        .group_by(PiAgentRun.intent)
        .order_by(func.count(func.distinct(PiAgentRun.conversation_id)).desc())
        .limit(5)
    )
    language = func.coalesce(PiConversation.language, "unknown").label("language")
    languages = await session.execute(
        select(language, func.count())
        .where(service.conversations.predicate(), PiConversation.last_message_at >= since)
        .group_by(language)
        .order_by(func.count().desc())
        .limit(4)
    )
    median_seconds, measured = speed
    return {
        "timezone": zone.key,
        "daily": daily,
        "conversations": total,
        "handled_by_pi": max(total - handed, 0),
        "automation_rate": round((total - handed) / total, 3) if total else None,
        "median_reply_seconds": round(float(median_seconds), 1) if measured else None,
        "topics": [{"intent": i, "conversations": int(n)} for i, n in topics.all()],
        "languages": [{"language": lang, "conversations": int(n)} for lang, n in languages.all()],
    }
