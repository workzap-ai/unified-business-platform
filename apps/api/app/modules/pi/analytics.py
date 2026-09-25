"""Workspace-scoped aggregates. Unconfigured cost estimates remain null."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, literal_column, select

from app.ai.models import AIUsageEvent
from app.modules.access.dependencies import Scope, Session
from app.modules.pi.models import (
    AGENT_KEYS,
    PiAgentRun,
    PiConversation,
    PiHandoff,
    PiMessage,
    PiToolCall,
)
from app.modules.pi.service import PiService
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-reports"])


@router.get("/analytics")
async def analytics(
    scope: Scope, session: Session, range: int = Query(7, ge=7, le=90)
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.analytics.read")
    if range not in {7, 30, 90}:
        raise HTTPException(422, "Choose 7, 30 or 90 days")
    since = datetime.now(UTC) - timedelta(days=range)

    def predicate(model: Any) -> Any:
        return WorkspaceRepository(session, model, scope).predicate() & (model.created_at >= since)

    def day(column: Any) -> Any:
        return func.to_char(column, literal_column("'YYYY-MM-DD'"))

    messages = await session.execute(
        select(
            day(PiMessage.created_at),
            func.count().filter(PiMessage.direction == "inbound"),
            func.count().filter(PiMessage.sender_type == "ai"),
            func.count().filter(PiMessage.sender_type == "human"),
        )
        .where(predicate(PiMessage))
        .group_by(day(PiMessage.created_at))
        .order_by(day(PiMessage.created_at))
    )
    message_points = [
        {"day": d, "inbound": i, "outbound_ai": a, "outbound_human": h} for d, i, a, h in messages
    ]
    conversations = await session.execute(
        select(
            day(PiConversation.created_at),
            func.count(),
            func.count().filter(PiConversation.status == "closed"),
        )
        .where(predicate(PiConversation))
        .group_by(day(PiConversation.created_at))
        .order_by(day(PiConversation.created_at))
    )
    conversation_points = [{"day": d, "started": n, "resolved": r} for d, n, r in conversations]
    handoffs = await session.execute(
        select(
            day(PiHandoff.created_at),
            func.count(),
            func.count().filter(PiHandoff.status.in_(["resolved", "closed"])),
        )
        .where(predicate(PiHandoff))
        .group_by(day(PiHandoff.created_at))
        .order_by(day(PiHandoff.created_at))
    )
    handoff_points = [{"day": d, "opened": n, "resolved": r} for d, n, r in handoffs]
    reasons = await session.execute(
        select(PiHandoff.reason, func.count())
        .where(predicate(PiHandoff))
        .group_by(PiHandoff.reason)
    )
    intents = await session.execute(
        select(PiAgentRun.intent, func.count())
        .where(predicate(PiAgentRun))
        .group_by(PiAgentRun.intent)
    )
    tool_rows = await session.execute(
        select(
            PiToolCall.tool_key,
            func.count().filter(PiToolCall.status == "success"),
            func.count().filter(PiToolCall.status.in_(["error", "invalid"])),
            func.count().filter(PiToolCall.status == "denied"),
        )
        .where(predicate(PiToolCall))
        .group_by(PiToolCall.tool_key)
    )
    tool_points = [{"tool": t, "success": s, "failed": f, "denied": d} for t, s, f, d in tool_rows]
    runs = await session.execute(
        select(
            day(PiAgentRun.created_at),
            func.percentile_cont(0.5).within_group(PiAgentRun.latency_ms),
            func.percentile_cont(0.95).within_group(PiAgentRun.latency_ms),
            func.count().filter(PiAgentRun.fallback_used),
        )
        .where(predicate(PiAgentRun))
        .group_by(day(PiAgentRun.created_at))
        .order_by(day(PiAgentRun.created_at))
    )
    run_points = list(runs)
    agent_points = []
    for agent in AGENT_KEYS:
        n, f = (
            await session.execute(
                select(func.count(), func.count().filter(PiAgentRun.status == "failed")).where(
                    predicate(PiAgentRun), PiAgentRun.agent_path.contains([agent])
                )
            )
        ).one()
        agent_points.append({"agent": agent, "runs": n, "failures": f})
    usage = await session.execute(
        select(
            day(AIUsageEvent.created_at),
            AIUsageEvent.provider,
            func.count(),
            func.coalesce(func.sum(AIUsageEvent.input_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.output_tokens), 0),
        )
        .where(predicate(AIUsageEvent))
        .group_by(day(AIUsageEvent.created_at), AIUsageEvent.provider)
        .order_by(day(AIUsageEvent.created_at))
    )
    providers: dict[str, dict[str, Any]] = {}
    tokens: dict[str, dict[str, Any]] = {}
    for d, p, n, i, o in usage:
        providers.setdefault(d, {"day": d, "openai": 0, "gemini": 0, "groq": 0})[p] = n
        point = tokens.setdefault(d, {"day": d, "input": 0, "output": 0})
        point["input"] += i
        point["output"] += o
    n, failed = (
        await session.execute(
            select(func.count(), func.count().filter(PiAgentRun.status == "failed")).where(
                predicate(PiAgentRun)
            )
        )
    ).one()
    # Consecutive attempts within the same run establish actual fallback pairs.
    prior = func.lag(AIUsageEvent.provider).over(
        partition_by=AIUsageEvent.run_id, order_by=(AIUsageEvent.created_at, AIUsageEvent.id)
    )
    transitions = (
        select(
            prior.label("previous"),
            AIUsageEvent.provider.label("provider"),
            AIUsageEvent.fallback.label("fallback"),
            AIUsageEvent.error_kind.label("reason"),
        )
        .where(predicate(AIUsageEvent), AIUsageEvent.run_id.is_not(None))
        .subquery()
    )
    pairs = await session.execute(
        select(transitions.c.previous, transitions.c.provider, func.count())
        .where(
            transitions.c.previous.is_not(None),
            transitions.c.previous != transitions.c.provider,
            transitions.c.fallback,
        )
        .group_by(transitions.c.previous, transitions.c.provider)
    )
    return {
        "range": range,
        "currency_note": (
            "Token usage comes from provider responses. Costs require a configured price table. "
            "Resolution counts describe the current state of records started on each day."
        ),
        "conversations": conversation_points,
        "messages": message_points,
        "latency": [
            {"day": d, "p50": float(p50 or 0), "p95": float(p95 or 0)}
            for d, p50, p95, f in run_points
        ],
        "runs_by_agent": agent_points,
        "intents": [{"intent": i or "unknown", "count": c} for i, c in intents],
        "tools": tool_points,
        "handoffs_by_reason": [{"reason": r, "count": c} for r, c in reasons],
        "handoffs_by_day": handoff_points,
        "fallbacks": [{"day": d, "count": f} for d, p50, p95, f in run_points],
        "fallback_pairs": [
            {"from": a, "to": b, "count": c, "top_reason": "Provider attempt unavailable"}
            for a, b, c in pairs
        ],
        "provider_usage": list(providers.values()),
        "tokens": list(tokens.values()),
        "cost_estimate": None,
        "totals": {
            "conversations": sum(x["started"] for x in conversation_points),
            "messages": sum(
                x["inbound"] + x["outbound_ai"] + x["outbound_human"] for x in message_points
            ),
            "ai_responses": sum(x["outbound_ai"] for x in message_points),
            "runs": n,
            "tool_calls": sum(x["success"] + x["failed"] + x["denied"] for x in tool_points),
            "handoffs": sum(x["opened"] for x in handoff_points),
            "fallbacks": sum(x[3] for x in run_points),
            "failure_rate": failed / n if n else 0,
            "input_tokens": sum(x["input"] for x in tokens.values()),
            "output_tokens": sum(x["output"] for x in tokens.values()),
            "cost_estimate_usd": None,
        },
    }
