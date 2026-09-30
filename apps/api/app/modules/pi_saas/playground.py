"""Test Pi: a realistic preview that never touches customers.

Uses the same composer, knowledge search and reply guards as live conversations, with the
current published knowledge (optionally plus unpublished drafts, clearly labelled) and
the current behaviour settings. Nothing is persisted as a conversation, nothing is sent
and no tool with side effects runs: those are reported as "would do" actions. AI usage is
real and metered to the environment in use.
"""

from types import SimpleNamespace
from typing import Any, Literal, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import AIGatewayError
from app.ai.gateway import Gateway
from app.ai.manager import build_llm_manager
from app.core.config import Settings
from app.modules.catalog.models import CatalogProduct
from app.modules.pi import price_policy
from app.modules.pi.configuration import settings_row
from app.modules.pi.graph import route_message
from app.modules.pi.guard import ReplyRejected, validate_reply
from app.modules.pi.knowledge import KnowledgeService
from app.modules.pi.models import PiConversation
from app.modules.pi.service_conversation import (
    compose_service_turn,
    service_mode,
)
from app.modules.pi.tools.registry import ToolRegistry
from app.modules.pi_saas.models import PiKnowledgeDraft
from app.modules.tenants.models import Tenant
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

INTENT_ACTIONS = {
    "product_search": "Look up matching products in your catalog",
    "product_availability": "Check live stock for the item",
    "pricing": "Answer with approved prices only (following your price rules)",
    "order": "Prepare an order draft and ask the customer to confirm it",
    "order_status": "Look up the customer's own order status",
    "invoice": "Look up the customer's own invoices",
    "payment": "Hand payment questions to your team",
    "complaint": "Hand the conversation to your team",
    "human_request": "Hand the conversation to your team",
    "quote": "Prepare a quotation draft for your team to approve",
    "requirement": "Collect the requirements into an enquiry for your team",
}


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["customer", "pi"]
    text: str = Field(min_length=1, max_length=2000)


class PlaygroundInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)
    include_drafts: bool = False


async def preview(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    scope: WorkspaceScope,
    data: PlaygroundInput,
) -> dict[str, Any]:
    scope.require("pi.settings.manage")
    policy = await settings_row(session, scope)
    tools = await ToolRegistry(session).enabled_tools(scope, "requirement")
    service = await service_mode(session, scope, policy)
    mode = price_policy.price_mode(policy.response_rules, service)
    max_chars = int(policy.response_rules.get("max_reply_chars", 4000))
    knowledge: list[dict[str, str]] = []
    if "search_knowledge_base" in tools:
        knowledge = await KnowledgeService(session, scope).search(
            data.message[:500], int(policy.knowledge_config.get("top_k", 5))
        )
    drafts_used: list[str] = []
    if data.include_drafts:
        rows = await session.scalars(
            WorkspaceRepository(session, PiKnowledgeDraft, scope)
            .select()
            .where(PiKnowledgeDraft.status == "draft", PiKnowledgeDraft.customer_visible.is_(True))
            .limit(10)
        )
        for draft in rows:
            knowledge.append(
                {"snippet": draft.content[:3000], "title": draft.title, "source": "Draft"}
            )
            drafts_used.append(draft.title)
    base: dict[str, Any] = {
        "simulated": True,
        "service_mode": service,
        "price_rule": mode,
        "knowledge_used": [k["title"] for k in knowledge],
        "drafts_used": drafts_used,
        "simulated_actions": [],
        "blocked_reason": None,
    }
    await session.commit()  # No transaction is held across AI calls.
    if service:
        return await _service_preview(
            session, settings, http, sessions, scope, data, policy, knowledge, mode, max_chars, base
        )
    decision = await route_message(
        data.message,
        Gateway(settings, http),
        threshold=float(policy.handoff_rules.get("low_confidence_threshold", "0.75")),
    )
    if decision["provider_failed"]:
        return {**base, "status": "ai_unavailable", "reply": None}
    intent = decision["intent"]
    base["intent"] = intent
    if intent in INTENT_ACTIONS:
        base["simulated_actions"].append(INTENT_ACTIONS[intent])
    if intent in {"greeting"}:
        reply = str(policy.response_rules.get("greeting") or "Hello! How can we help?")
    elif intent in {"support", "unknown"} and knowledge:
        reply = "From our approved information:\n" + knowledge[0]["snippet"][:3000]
    elif intent in {"support", "unknown"}:
        base["simulated_actions"].append(
            "Ask you this question (Ask Owner) and tell the customer your team will reply"
        )
        return {**base, "status": "handoff", "reply": None}
    else:
        return {**base, "status": "action", "reply": None}
    try:
        if (code := price_policy.check(reply, mode)) is not None:
            raise ReplyRejected(code)
        reply = validate_reply(reply, [k["snippet"] for k in knowledge] + [reply], max_chars)
    except ReplyRejected as exc:
        return {**base, "status": "blocked", "reply": None, "blocked_reason": exc.code}
    return {**base, "status": "ok", "reply": reply}


async def _service_preview(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    scope: WorkspaceScope,
    data: PlaygroundInput,
    policy: Any,
    knowledge: list[dict[str, str]],
    mode: str,
    max_chars: int,
    base: dict[str, Any],
) -> dict[str, Any]:
    offerings = list(
        await session.scalars(
            WorkspaceRepository(session, CatalogProduct, scope)
            .select()
            .with_only_columns(CatalogProduct.name)
            .where(CatalogProduct.pi_visible.is_(True), CatalogProduct.status == "active")
            .order_by(CatalogProduct.name)
            .limit(40)
        )
    )
    tenant = await session.get(Tenant, scope.tenant_id)
    context = {
        "company": tenant.name if tenant else "",
        "offerings": offerings,
        "customer_memory": [],
        "approved_knowledge": knowledge,
        "operator_guidance": "",
        "brief": {},
        "history": [
            {"role": "customer" if t.role == "customer" else "ai", "text": t.text[:1000]}
            for t in data.history
        ],
        "latest_customer_message": data.message,
        "tone": policy.response_rules.get("tone", "friendly"),
        "followups_enabled": policy.whatsapp_config.get("reminder_enabled", False),
    }
    await session.commit()
    manager = build_llm_manager(settings, http, sessions)
    try:
        turn = await compose_service_turn(
            manager,
            scope,
            cast(PiConversation, SimpleNamespace(id=None)),
            policy,
            context,
        )
    except ReplyRejected as exc:
        base["simulated_actions"].append("Hand the conversation to your team")
        return {**base, "status": "blocked", "reply": None, "blocked_reason": exc.code}
    except (AIGatewayError, ValueError):
        return {**base, "status": "ai_unavailable", "reply": None}
    actions = base["simulated_actions"]
    requirements = turn.requirements.model_dump()
    if requirements["service"] or requirements["scope"]:
        actions.append("Save these requirements to an enquiry for your team")
    if turn.ready_for_team:
        actions.append("Tell your team the enquiry is ready to review")
    if turn.request_human:
        actions.append("Hand the conversation to your team")
    if policy.response_rules.get("execution_mode") == "human_approved":
        actions.append("Wait for your approval before sending this reply")
    return {
        **base,
        "status": "ok",
        "reply": turn.reply,
        "language": turn.language,
        "team_summary": turn.summary,
        "requirements": requirements,
        "missing": turn.missing,
    }
