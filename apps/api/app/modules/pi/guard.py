"""Runtime guards: spam/cost/loop rate limits and outbound response validation.

Limits are counted from durable rows (messages and runs), so they hold across workers and
restarts without extra infrastructure. Validation treats every reply as untrusted: facts
(amounts, stock figures) must come from tool results, and nothing internal may leak.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository


@dataclass(frozen=True)
class Limit:
    code: str
    count: int
    window: timedelta


# Inbound bursts on one conversation (spam / stuck client).
CONVERSATION_BURST = Limit("RATE_LIMIT_CONVERSATION", 8, timedelta(minutes=1))
# One customer across conversations (cost control).
CUSTOMER_HOURLY = Limit("RATE_LIMIT_CUSTOMER", 60, timedelta(hours=1))
# Whole workspace AI runs (cost ceiling / runaway protection).
TENANT_HOURLY = Limit("RATE_LIMIT_TENANT", 1000, timedelta(hours=1))
# AI replies on one conversation (bot-to-bot loops).
AI_REPLY_LOOP = Limit("RATE_LIMIT_LOOP", 10, timedelta(minutes=10))


async def _count(session: AsyncSession, statement: object) -> int:
    return int(await session.scalar(statement) or 0)  # type: ignore[call-overload]


async def rate_limited(
    session: AsyncSession, scope: WorkspaceScope, conversation: PiConversation
) -> str | None:
    """Return the first exceeded limit code, or None. Counts include the current message."""
    now = datetime.now(UTC)
    messages = WorkspaceRepository(session, PiMessage, scope)
    burst = await _count(
        session,
        select(func.count())
        .select_from(PiMessage)
        .where(
            messages.predicate(),
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "inbound",
            PiMessage.created_at >= now - CONVERSATION_BURST.window,
        ),
    )
    if burst > CONVERSATION_BURST.count:
        return CONVERSATION_BURST.code
    conversations = WorkspaceRepository(session, PiConversation, scope)
    customer = await _count(
        session,
        select(func.count())
        .select_from(PiMessage)
        .where(
            messages.predicate(),
            PiMessage.direction == "inbound",
            PiMessage.created_at >= now - CUSTOMER_HOURLY.window,
            PiMessage.conversation_id.in_(
                conversations.select()
                .with_only_columns(PiConversation.id)
                .where(PiConversation.customer_id == conversation.customer_id)
            ),
        ),
    )
    if customer > CUSTOMER_HOURLY.count:
        return CUSTOMER_HOURLY.code
    loop = await _count(
        session,
        select(func.count())
        .select_from(PiMessage)
        .where(
            messages.predicate(),
            PiMessage.conversation_id == conversation.id,
            PiMessage.sender_type == "ai",
            PiMessage.created_at >= now - AI_REPLY_LOOP.window,
        ),
    )
    if loop >= AI_REPLY_LOOP.count:
        return AI_REPLY_LOOP.code
    tenant = await _count(
        session,
        select(func.count())
        .select_from(PiAgentRun)
        .where(
            WorkspaceRepository(session, PiAgentRun, scope).predicate(),
            PiAgentRun.created_at >= now - TENANT_HOURLY.window,
        ),
    )
    if tenant >= TENANT_HOURLY.count:
        return TENANT_HOURLY.code
    return None


# ---------------------------------------------------------------------- response checks

LEAK_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{12,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
    re.compile(r"system prompt|developer message|operator_routing_guidance", re.IGNORECASE),
    re.compile(r"\b(tenant|environment)_id\b", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
)
AMOUNT = re.compile(r"\d[\d,]*\.\d{2}\b")
STOCK = re.compile(r"\b(\d+)\s+(?:available|in stock|units?)\b", re.IGNORECASE)


class ReplyRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_reply(text: str, facts: list[str], max_chars: int) -> str:
    """Return the reply to send, or raise ReplyRejected. ``facts`` are serialized tool
    results and approved texts; any amount or stock figure must appear in them."""
    reply = text.strip()
    if not reply:
        raise ReplyRejected("EMPTY_REPLY")
    for pattern in LEAK_PATTERNS:
        if pattern.search(reply):
            raise ReplyRejected("LEAK_BLOCKED")
    evidence = "\n".join(facts)
    for amount in AMOUNT.findall(reply):
        if amount not in evidence and amount.replace(",", "") not in evidence:
            raise ReplyRejected("UNSUPPORTED_FACT")
    for figure in STOCK.findall(reply):
        if not re.search(rf"\b{figure}\b", evidence):
            raise ReplyRejected("UNSUPPORTED_FACT")
    limit = max(100, min(max_chars, 4000))
    if len(reply) > limit:
        cut = reply[:limit]
        reply = cut[: cut.rfind("\n")] if "\n" in cut[limit // 2 :] else cut
    return reply
