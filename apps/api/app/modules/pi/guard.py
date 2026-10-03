"""Runtime guards: spam/cost/loop rate limits and outbound response validation.

Limits are counted from durable rows (messages and runs), so they hold across workers and
restarts without extra infrastructure. Validation treats every reply as untrusted: facts
(amounts, stock figures) must come from tool results, and nothing internal may leak.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

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
# Whole or decimal numbers written next to a currency marker ("Rs 500", "500 AED").
_CUR = r"(?:rs\.?|pkr|usd|aed|sar|qar|eur|gbp|inr|dollars?|rupees?|dirhams?|riyals?|[$€£₹﷼])"
CURRENCY_AMOUNT = re.compile(
    rf"{_CUR}\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?{_CUR}(?![a-z])", re.IGNORECASE
)
STOCK = re.compile(r"\b(\d+)\s+(?:available|in stock|units?)\b", re.IGNORECASE)
# A standalone number in evidence (not part of an ID, a word or a longer figure).
EVIDENCE_NUMBER = re.compile(r"(?<![\w.,])\d[\d,]*(?:\.\d+)?(?!\w)")


# Accepted digit grouping: 1,500,000 (Western) or 15,00,000 (South Asian). Anything else,
# such as "1,50", is ambiguous (it may mean 1.50) and is never treated as evidence.
GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}")


def _decimal(figure: str) -> Decimal | None:
    figure = figure.strip(",.")
    whole = figure.split(".")[0]
    if "," in whole and not GROUPED.fullmatch(whole):
        return None
    try:
        return Decimal(figure.replace(",", ""))
    except InvalidOperation:
        return None


def evidence_amounts(evidence: str) -> set[Decimal]:
    """Canonical values of every number in the evidence, so "1,500" equals "1500.00"
    and "50" never matches inside "150.00"."""
    values = {_decimal(m.group()) for m in EVIDENCE_NUMBER.finditer(evidence)}
    return {v for v in values if v is not None}


class ReplyRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _bold(match: re.Match[str]) -> str:
    return f"*{match.group(1) or match.group(2)}*"


def whatsapp_text(text: str) -> str:
    """Markdown a model may still write, in WhatsApp's own formatting: **bold** and
    headings become *bold*, "-"/"*" list items become "•" lines, blank runs collapse."""
    lines = []
    for line in text.strip().splitlines():
        line = line.rstrip()
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*$", line)
        if heading:
            line = f"*{heading.group(1).strip('*_ ')}*"
        line = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", line)
        line = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", _bold, line)
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def validate_reply(text: str, facts: list[str], max_chars: int) -> str:
    """Return the reply to send, or raise ReplyRejected. ``facts`` are serialized tool
    results and approved texts; any amount or stock figure must appear in them."""
    reply = whatsapp_text(text)
    if not reply:
        raise ReplyRejected("EMPTY_REPLY")
    for pattern in LEAK_PATTERNS:
        if pattern.search(reply):
            raise ReplyRejected("LEAK_BLOCKED")
    evidence = "\n".join(facts)
    known = evidence_amounts(evidence)
    figures = AMOUNT.findall(reply) + [a or b for a, b in CURRENCY_AMOUNT.findall(reply)]
    for figure in figures:
        # Compare canonical values, never substrings of serialized evidence.
        if _decimal(figure) not in known:
            raise ReplyRejected("UNSUPPORTED_FACT")
    for figure in STOCK.findall(reply):
        if not re.search(rf"\b{figure}\b", evidence):
            raise ReplyRejected("UNSUPPORTED_FACT")
    limit = max(100, min(max_chars, 4000))
    if len(reply) > limit:
        cut = reply[:limit]
        reply = cut[: cut.rfind("\n")] if "\n" in cut[limit // 2 :] else cut
    return reply
