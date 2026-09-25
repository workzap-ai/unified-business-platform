from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import func, literal_column, select

from app.ai.models import AIUsageEvent
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.business_settings.service import get_settings_row
from app.modules.orders.models import Order
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import (
    AGENT_KEYS,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    PiAgentRun,
    PiConversation,
    PiHandoff,
    PiMemory,
    PiMessage,
    PiToolCall,
    WhatsAppConnection,
)
from app.modules.pi.service import PiService
from app.modules.quotes.models import Quote
from app.shared.models import WorkspaceRow
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-reports"])


@router.get("/conversations/{conversation_id}/context")
async def context(conversation_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    service = PiService(session, scope)
    await service.require()
    conversation = await service.conversations.get(conversation_id)
    result: dict[str, Any] = {
        "conversation": (await service.view(conversation)).model_dump(mode="json"),
        "memory": [],
        "knowledge_used": [],
        "recent_orders": [],
        "open_quotes": [],
        "balance": None,
        "currency": (await get_settings_row(session, scope)).default_currency,
        "runs": [],
        "service_brief": conversation.service_brief,
        "followup_due_at": conversation.followup_due_at,
    }
    if scope.can("pi.memory.read"):
        memory_rows = await session.scalars(
            WorkspaceRepository(session, PiMemory, scope)
            .select()
            .where(PiMemory.customer_id == conversation.customer_id, PiMemory.status == "active")
            .order_by(PiMemory.created_at.desc())
            .limit(20)
        )
        result["memory"] = [
            {key: getattr(x, key) for key in ("id", "kind", "content", "created_at")}
            for x in memory_rows
        ]
    if scope.can("orders.read"):
        order_rows = await session.scalars(
            WorkspaceRepository(session, Order, scope)
            .select()
            .where(Order.customer_id == conversation.customer_id)
            .order_by(Order.created_at.desc())
            .limit(5)
        )
        result["recent_orders"] = [
            {
                **{key: getattr(x, key) for key in ("id", "number", "status", "created_at")},
                "total": str(x.total),
            }
            for x in order_rows
        ]
    if scope.can("quotes.read"):
        quote_rows = await session.scalars(
            WorkspaceRepository(session, Quote, scope)
            .select()
            .where(
                Quote.customer_id == conversation.customer_id,
                Quote.status.in_(["draft", "pending_approval", "approved", "sent"]),
            )
            .order_by(Quote.created_at.desc())
            .limit(5)
        )
        result["open_quotes"] = [
            {**{key: getattr(x, key) for key in ("id", "number", "status")}, "total": str(x.total)}
            for x in quote_rows
        ]
    if scope.can("billing.read"):
        balance = await session.scalar(
            select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)).where(
                WorkspaceRepository(session, Invoice, scope).predicate(),
                Invoice.customer_id == conversation.customer_id,
                Invoice.status.in_(["issued", "partially_paid"]),
                Invoice.currency == result["currency"],
            )
        )
        result["balance"] = str(balance)
    runs = list(
        await session.scalars(
            WorkspaceRepository(session, PiAgentRun, scope)
            .select()
            .where(PiAgentRun.conversation_id == conversation_id)
            .order_by(PiAgentRun.created_at.desc())
            .limit(20)
        )
    )
    tool_rows = (
        list(
            await session.scalars(
                WorkspaceRepository(session, PiToolCall, scope)
                .select()
                .where(PiToolCall.run_id.in_([x.id for x in runs]))
                .order_by(PiToolCall.created_at)
            )
        )
        if runs
        else []
    )
    from app.modules.pi.routes import tool_summary

    tools_by_run: dict[UUID, list[dict[str, Any]]] = {}
    knowledge: list[dict[str, str]] = []
    for call in tool_rows:
        tools_by_run.setdefault(call.run_id, []).append(
            {
                "tool": call.tool_key,
                "status": "error" if call.status == "invalid" else call.status,
                "summary": tool_summary(call),
            }
        )
        if call.tool_key == "search_knowledge_base" and call.status == "success":
            for passage in call.output.get("passages", [])[:3]:
                entry = {k: str(passage.get(k, ""))[:500] for k in ("title", "source", "snippet")}
                if entry not in knowledge:
                    knowledge.append(entry)
    result["knowledge_used"] = knowledge[:5]
    result["runs"] = [
        {
            **{
                key: getattr(x, key)
                for key in (
                    "id",
                    "message_id",
                    "status",
                    "intent",
                    "agent_path",
                    "provider",
                    "fallback_used",
                    "input_tokens",
                    "output_tokens",
                    "created_at",
                )
            },
            "confidence": float(x.confidence) if x.confidence is not None else None,
            "model_alias": None,
            "latency_ms": x.latency_ms or 0,
            "tools": tools_by_run.get(x.id, []),
        }
        for x in runs
    ]
    return result


def memory_view(row: PiMemory) -> dict[str, Any]:
    return {key: getattr(row, key) for key in ("id", "kind", "content", "created_at")}


@router.get("/customers/{customer_id}/memory")
async def customer_memory(
    customer_id: UUID, scope: Scope, session: Session
) -> list[dict[str, Any]]:
    service = PiService(session, scope)
    await service.require("pi.memory.read")
    await service.customers.get(customer_id)
    rows = await session.scalars(
        WorkspaceRepository(session, PiMemory, scope)
        .select()
        .where(PiMemory.customer_id == customer_id, PiMemory.status == "active")
        .order_by(PiMemory.created_at.desc())
        .limit(100)
    )
    return [memory_view(x) for x in rows]


@router.delete("/memory/{memory_id}", status_code=204)
async def delete_memory(memory_id: UUID, scope: Scope, session: Session) -> None:
    """Hard delete (privacy). The audit entry records the action, never the content."""
    service = PiService(session, scope)
    await service.require("pi.memory.read")
    scope.require("pi.inbox.reply")
    repo = WorkspaceRepository(session, PiMemory, scope)
    row = await repo.get(memory_id, for_update=True)
    customer_id = row.customer_id
    await repo.delete(row)
    await record(
        session,
        "pi.memory_deleted",
        scope=scope,
        entity_type="customer",
        entity_id=customer_id,
    )
    await session.commit()


async def count(session: Session, scope: Scope, model: type[WorkspaceRow], *conditions: Any) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(model)
            .where(WorkspaceRepository(session, model, scope).predicate(), *conditions)
        )
        or 0
    )


@router.get("/overview")
async def overview(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require()
    since = datetime.now(UTC) - timedelta(days=7)
    conversations = await count(session, scope, PiConversation, PiConversation.created_at >= since)
    active = await count(session, scope, PiConversation, PiConversation.status == "open")
    inbound = await count(
        session, scope, PiMessage, PiMessage.created_at >= since, PiMessage.direction == "inbound"
    )
    outbound = await count(
        session,
        scope,
        PiMessage,
        PiMessage.created_at >= since,
        PiMessage.direction == "outbound",
        PiMessage.status.in_(["sent", "delivered", "read"]),
    )
    ai = await count(
        session,
        scope,
        PiMessage,
        PiMessage.created_at >= since,
        PiMessage.sender_type == "ai",
        PiMessage.status.in_(["sent", "delivered", "read"]),
    )
    handoffs = await count(
        session, scope, PiHandoff, PiHandoff.status.in_(["open", "assigned", "in_progress"])
    )
    latencies = await session.execute(
        select(
            func.avg(PiAgentRun.latency_ms),
            func.percentile_cont(0.95).within_group(PiAgentRun.latency_ms),
        ).where(
            WorkspaceRepository(session, PiAgentRun, scope).predicate(),
            PiAgentRun.created_at >= since,
        )
    )
    avg, p95 = latencies.one()
    connection = await WorkspaceRepository(session, WhatsAppConnection, scope).find()
    config = await settings_row(session, scope)
    providers = []
    for i, provider in enumerate(request.app.state.settings.provider_order()):
        key = getattr(request.app.state.settings, f"{provider}_api_key")
        configured = bool(key and getattr(request.app.state.settings, f"{provider}_models"))
        usage = WorkspaceRepository(session, AIUsageEvent, scope)
        n, success, p50 = (
            await session.execute(
                select(
                    func.count(),
                    func.count().filter(AIUsageEvent.status == "success"),
                    func.percentile_cont(0.5).within_group(AIUsageEvent.latency_ms),
                ).where(
                    usage.predicate(),
                    AIUsageEvent.provider == provider,
                    AIUsageEvent.created_at >= datetime.now(UTC) - timedelta(days=1),
                )
            )
        ).one()
        providers.append(
            {
                "name": provider,
                "role": ["primary", "fallback", "secondary_fallback"][i],
                "configured": configured,
                "status": "unconfigured"
                if not configured
                else "unknown"
                if not n
                else "healthy"
                if n == success
                else "degraded"
                if success
                else "down",
                "success_rate": success / n if n else 0,
                "p50_ms": float(p50 or 0),
                "requests_24h": n,
            }
        )
    rows = await session.execute(
        select(
            func.to_char(PiMessage.created_at, literal_column("'YYYY-MM-DD'")),
            PiMessage.sender_type,
            func.count(),
        )
        .where(
            WorkspaceRepository(session, PiMessage, scope).predicate(),
            PiMessage.created_at >= since,
        )
        .group_by(
            func.to_char(PiMessage.created_at, literal_column("'YYYY-MM-DD'")),
            PiMessage.sender_type,
        )
    )
    days: dict[str, dict[str, Any]] = {}
    for day, sender, n in rows:
        point = days.setdefault(day, {"day": day, "inbound": 0, "ai": 0, "human": 0})
        if sender in {"customer", "ai", "human"}:
            point["inbound" if sender == "customer" else sender] += n
    result = {
        "period_days": 7,
        "conversations_active": active,
        "conversations_total": conversations,
        "unresolved": active,
        "open_handoffs": handoffs,
        "messages_in": inbound,
        "messages_out": outbound,
        "ai_responses": ai,
        "automation_rate": ai / inbound if inbound else 0,
        "avg_response_ms": float(avg or 0),
        "p95_response_ms": float(p95 or 0),
        "fallback_count": await count(
            session, scope, PiAgentRun, PiAgentRun.fallback_used, PiAgentRun.created_at >= since
        ),
        "tool_calls": await count(session, scope, PiToolCall, PiToolCall.created_at >= since),
        "tool_failures": await count(
            session,
            scope,
            PiToolCall,
            PiToolCall.status != "success",
            PiToolCall.created_at >= since,
        ),
        "whatsapp": {
            key: getattr(connection, key)
            for key in ("status", "display_phone_number", "last_inbound_at")
        }
        if connection
        else None,
        "knowledge": {
            "sources": await count(session, scope, KnowledgeSource),
            "documents_ready": await count(
                session, scope, KnowledgeDocument, KnowledgeDocument.status == "ready"
            ),
            "documents_failed": await count(
                session, scope, KnowledgeDocument, KnowledgeDocument.status == "failed"
            ),
            "passages": await count(session, scope, KnowledgeChunk),
        },
        "providers": providers,
        "volume": sorted(days.values(), key=lambda x: x["day"]),
        "agent_activity": [],
        "auto_reply_enabled": config.auto_reply_enabled,
    }
    await session.commit()
    result["agent_activity"] = [
        {
            "agent": key,
            "runs": await count(
                session,
                scope,
                PiAgentRun,
                PiAgentRun.agent_path.contains([key]),
                PiAgentRun.created_at >= since,
            ),
        }
        for key in AGENT_KEYS
    ]
    return result
