"""The request desk: pi asks the team, the team answers, pi carries on.

    pi raises a request (a question it can't answer, a proposal to price or approve,
    a document to review, a meeting to arrange)  →  the team sees it in Requests
    (Owner OS and the pi app) and writes an answer for pi  →  the chat goes back to pi,
    which replies to the customer itself, in their language, using that answer.

The answer is a note *for pi* (facts to follow), never sent to the customer verbatim.
Answered requests and the team's conversation notes stay in pi's context for later
turns. Price and approve requests close by themselves once that proposal is sent.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.navigation.service import badge_provider
from app.modules.notifications.service import notify
from app.modules.pi.models import PiConversation, PiHandoff, PiMessage
from app.modules.pi_saas.meetings import MeetingInput
from app.modules.pi_saas.models import (
    ESCALATION_KINDS,
    REQUEST_KINDS,
    PiConversationNote,
    PiStaffRequest,
)
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)
DONE = ("answered", "published", "resolved")
TITLES = {
    "question": "pi needs an answer",
    "price": "Price a proposal",
    "review_document": "Review a customer's document",
    "approve": "Approve a proposal",
    "meeting": "Arrange a meeting",
    "other": "pi needs your help",
}
PRIORITY_RANK = {"normal": 0, "high": 1, "urgent": 2}
CONTEXT_MAX = 12000  # the ticket's summary, open problems and last 20 messages (spec 6.6)
# Escalation reasons (spec 6.6, 6.9): what the team is told in the alert's title.
ESCALATION_TITLES = {
    "human_requested": "A customer asked for a person",
    "emergency": "Possible emergency: check the chat now",
    "payment_detail_change": "Claimed change of Workzap bank details",
    "refund": "Refund or dispute",
    "complaint_about_pi": "Complaint about pi",
    "complaint_about_workzap": "Complaint about Workzap",
    "cant_help": "pi could not help",
    "legal_threat": "Legal threat",
    "abuse": "Abusive customer",
    "press": "Press enquiry",
    "partnership": "Partnership enquiry",
    "enterprise_lead": "Enterprise lead",
    "existing_project": "Question about an existing project",
    "technical_failure": "Technical failure reported",
    "demo_request": "nori demo request",
    "jobs": "Job application",
    "vendor": "Supplier or vendor pitch",
    "deletion_request": "Delete my data",
    "price_request": "Discount or lower price asked",
    "payment_method": "Customer asks to pay another way",
    "company_info": "Question about Workzap",
    "cancel_after_payment": "Cancellation after payment",
    "quote_expired": "Expired quote",
}


def notification_kind(kind: str) -> str:
    """The alert's kind (the column holds 32 characters, some reasons are longer)."""
    return "pi.request.escalation" if kind in ESCALATION_KINDS else f"pi.request.{kind}"


def request_title(kind: str) -> str:
    return ESCALATION_TITLES.get(kind) or TITLES.get(kind, TITLES["other"])


# ---- Raising and closing ----------------------------------------------------------------


async def raise_request(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    conversation_id: UUID,
    customer_id: UUID,
    kind: str,
    question: str,
    context: str = "",
    title: str = "",
    lead_id: UUID | None = None,
    quote_id: UUID | None = None,
    file_id: UUID | None = None,
    priority: str = "normal",
    link: str = "",
) -> PiStaffRequest:
    """One open request per chat, kind and linked record: asking again adds to it. A brain
    escalation has a kind of its own (its reason), so it never joins a request of another reason;
    an urgent flag always alerts the team, even when it joins an older request of the same kind."""
    if kind not in REQUEST_KINDS:
        kind = "other"
    if priority not in PRIORITY_RANK:
        priority = "normal"
    repo = WorkspaceRepository(session, PiStaffRequest, scope)
    existing = await repo.find(
        PiStaffRequest.conversation_id == conversation_id,
        PiStaffRequest.status == "open",
        PiStaffRequest.kind == kind,
        PiStaffRequest.quote_id == quote_id if quote_id else PiStaffRequest.quote_id.is_(None),
    )
    if existing is not None:
        added = question not in existing.question
        if added:
            existing.question = f"{existing.question}\n\n{question}"[-4000:]
        if context and kind in ESCALATION_KINDS:
            kept = FLAGGED if FLAGGED in (existing.context_summary or "") else ""
            existing.context_summary = context[:CONTEXT_MAX] + kept  # the latest chat replaces it
        raised = PRIORITY_RANK[priority] > PRIORITY_RANK.get(existing.priority, 0)
        if raised:
            existing.priority = priority
        if priority == "urgent":
            # Every urgent flag alerts, once per message the person sent (a retry or a second
            # path in the same turn shares that message, so it does not alert twice).
            chat = await session.get(PiConversation, conversation_id)
            turn_key = chat.last_inbound_at.isoformat() if chat and chat.last_inbound_at else ""
            await notify(
                session,
                scope,
                notification_kind(kind),
                title or request_title(kind),
                question[:200],
                link=link or f"/pi/requests?request={existing.id}",
                permission="pi.inbox.reply",
                severity="critical",
                dedupe_key=f"pi-request:{existing.id}:urgent:{turn_key}"[:160],
            )
        return existing
    row = await repo.add(
        repo.new(
            conversation_id=conversation_id,
            customer_id=customer_id,
            question=question[:4000],
            context_summary=context[:CONTEXT_MAX],
            kind=kind,
            priority=priority,
            lead_id=lead_id,
            quote_id=quote_id,
            file_id=file_id,
        )
    )
    await notify(
        session,
        scope,
        notification_kind(kind),
        title or request_title(kind),
        question[:200],
        link=link or f"/pi/requests?request={row.id}",
        permission="pi.inbox.reply",
        severity={"urgent": "critical", "high": "warning"}.get(priority, "info"),
        dedupe_key=f"pi-request:{row.id}",
    )
    return row


# ---- Brain escalations (spec 6.6) -----------------------------------------------------------

URGENT_REASONS = frozenset({"emergency", "payment_detail_change"})
# The reasons the brain's own code uses (older names kept) -> the request kind of that reason.
REASON_KIND = {
    "emergency": "emergency",
    "deletion_request": "deletion_request",
    "payment_detail_change": "payment_detail_change",
    "refund_dispute": "refund",
    "refund": "refund",
    "price_request": "price_request",
    "payment_method": "payment_method",
    "company_info": "company_info",
    "abuse": "abuse",
    "abuse_threat": "abuse",
    "legal_threat": "legal_threat",
    "human_requested": "human_requested",
    "cant_help": "cant_help",
    "cancel_after_payment": "cancel_after_payment",
    "quote_expired": "quote_expired",
    "demo_request": "demo_request",
    "enterprise_lead": "enterprise_lead",
    "jobs": "jobs",
    "vendor": "vendor",
    "partnership": "partnership",
    "press": "press",
    "existing_project": "existing_project",
    "technical_failure": "technical_failure",
}
ABOUT_PI = re.compile(r"\b(?:pi|the bot|the ai|chatbot|assistant)\b", re.IGNORECASE)


def escalation_route(reason: str, said: str = "") -> tuple[str, str]:
    """The request kind and priority for a reason: urgent for an emergency and a claimed change of
    Workzap's bank details, high for everything else the team must look at (spec 6.6). A
    complaint is about pi when the person says so, otherwise about Workzap (R-COMPL-01)."""
    if reason == "complaint":
        kind = "complaint_about_pi" if ABOUT_PI.search(said or "") else "complaint_about_workzap"
    else:
        kind = REASON_KIND.get(reason, "other")
    return kind, "urgent" if kind in URGENT_REASONS else "high"


async def ticket_context(
    session: AsyncSession, scope: WorkspaceScope, conversation: PiConversation
) -> str:
    """What the ticket carries (spec 6.6): a summary of the conversation, the open problems and
    the last 20 messages, personal data taken out."""
    from app.modules.pi import safety
    from app.modules.pi.problems import ProblemBook

    lines: list[str] = []
    summary = (conversation.summary or "").strip() or str(
        (conversation.service_brief or {}).get("summary") or ""
    )
    lines.append("Summary: " + (safety.redact_pii(summary).text[:800] if summary else "none yet"))
    state = conversation.flow_state or "unknown"
    lines.append(f"State: {state}")
    if conversation.customer_id is not None:
        try:
            async with session.begin_nested():
                book = ProblemBook(session, scope, conversation.customer_id, "en")
                noted = await book.active()
            lines.append(
                "Open problems: "
                + (
                    "; ".join(f"P{p.number} {safety.redact_pii(p.title).text}" for p in noted[:20])
                    or "none noted"
                )
            )
        except DBAPIError:
            logger.warning("pi_ticket_problems_unavailable", exc_info=True)
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiMessage, scope)
            .select()
            .where(PiMessage.conversation_id == conversation.id)
            .order_by(PiMessage.created_at.desc(), PiMessage.id.desc())
            .limit(20)
        )
    )
    lines.append("Last messages:")
    for m in reversed(rows):
        who = {"customer": "Customer", "ai": "pi", "human": "Team"}.get(m.sender_type, "System")
        lines.append(f"{who}: {safety.redact_pii(m.body or '').text[:300]}")
    return "\n".join(lines)[:CONTEXT_MAX]


async def raise_escalation(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    reason: str,
    question: str,
    said: str = "",
) -> PiStaffRequest | None:
    """A brain escalation: a ticket of its own kind with the reason, urgent when it must be, and
    the conversation's summary, open problems and last 20 messages (redacted) attached."""
    if conversation.customer_id is None:
        return None
    kind, priority = escalation_route(reason, said)
    try:
        async with session.begin_nested():
            return await raise_request(
                session,
                scope,
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                kind=kind,
                question=question,
                context=await ticket_context(session, scope, conversation),
                priority=priority,
            )
    except DBAPIError:
        logger.warning("pi_escalation_skipped", exc_info=True)
        return None


# pi's one honest message when nobody has picked a ticket up in time (spec 6.6).
UNCLAIMED_TEXT = {
    "en": "The Workzap team hasn't picked this up yet. I've flagged it again.",
    "roman_ur": "Workzap ki team ne abhi tak ise nahi uthaya. Maine ise dobara flag kar diya hai.",
}
FLAGGED = "\n[flagged again]"
SLA_DEFAULT_MINUTES = 60
SLA_RANGE = (5, 1440)
# No message to someone pi stopped answering (X_BLOCKED) or about an abuse ticket.
NO_UNCLAIMED_MESSAGE = frozenset({"abuse", "deletion_request"})


def sla_minutes(response_rules: dict[str, Any] | None) -> int:
    """How long a ticket may sit before it is flagged again: response_rules.brain
    ["handover_sla_minutes"], clamped to 5 minutes to a day (default one hour)."""
    raw = ((response_rules or {}).get("brain") or {}).get("handover_sla_minutes")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return SLA_DEFAULT_MINUTES
    return max(SLA_RANGE[0], min(SLA_RANGE[1], int(raw)))


async def flag_unclaimed(ctx: dict[str, Any], now: datetime | None = None) -> list[str]:
    """Job: a brain ticket nobody has claimed within the SLA is flagged to the team again (urgent
    alert) and pi tells the customer once, honestly, with no ETA. Inside the 24-hour window only,
    only in a chat pi still holds (a person who took over has claimed it)."""
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.flow import brain_mode
    from app.modules.pi.runtime import enqueue_sends
    from app.modules.pi.service import PiService
    from app.modules.pi_saas.deals import system_scope_for

    now = now or datetime.now(UTC)
    sent: list[str] = []
    async with ctx["sessions"]() as session:
        rows = list(
            await session.scalars(
                select(PiStaffRequest)
                .where(
                    PiStaffRequest.status == "open",
                    PiStaffRequest.kind.in_(ESCALATION_KINDS),
                    PiStaffRequest.created_at < now - timedelta(minutes=SLA_RANGE[0]),
                )
                .order_by(PiStaffRequest.created_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            try:
                async with session.begin_nested():
                    if FLAGGED in (row.context_summary or ""):
                        continue
                    scope = await system_scope_for(session, row.tenant_id, row.environment_id)
                    policy = await settings_row(session, scope)
                    if not brain_mode(policy.response_rules):
                        continue
                    if row.created_at > now - timedelta(minutes=sla_minutes(policy.response_rules)):
                        continue
                    service = PiService(session, scope)
                    key = f"pi-unclaimed:{row.id}"
                    if await service.messages.find(PiMessage.idempotency_key == key) is not None:
                        continue
                    conversation = await service.conversations.get(row.conversation_id)
                    await notify(
                        session,
                        scope,
                        "pi.request.unclaimed",
                        "Nobody has picked this up: " + request_title(row.kind),
                        row.question[:200],
                        link=f"/pi/requests?request={row.id}",
                        permission="pi.inbox.reply",
                        severity="critical",
                        dedupe_key=f"pi-request-unclaimed:{row.id}",
                    )
                    window_open = bool(
                        conversation.last_inbound_at and now - conversation.last_inbound_at < WINDOW
                    )
                    # A person who took the chat over has claimed it; a handoff still "open" has
                    # not been (pi is held silent by it, but says this one honest line).
                    claimed = await session.scalar(
                        select(PiHandoff.id).where(
                            PiHandoff.tenant_id == row.tenant_id,
                            PiHandoff.environment_id == row.environment_id,
                            PiHandoff.conversation_id == conversation.id,
                            PiHandoff.status.in_(("assigned", "in_progress")),
                        )
                    )
                    waiting_for_person = (
                        conversation.mode == "human" and row.kind == "human_requested"
                    )
                    if (
                        claimed is None
                        and (conversation.mode == "ai" or waiting_for_person)
                        and conversation.status == "open"
                        and policy.auto_reply_enabled
                        and window_open
                        and row.kind not in NO_UNCLAIMED_MESSAGE
                        and conversation.flow_state != "X_BLOCKED"
                        and (conversation.flow_state != "X_HUMAN" or waiting_for_person)
                    ):
                        language = "roman_ur" if conversation.language == "roman_ur" else "en"
                        message = await service.messages.add(
                            service.messages.new(
                                conversation_id=conversation.id,
                                direction="outbound",
                                sender_type="system",
                                body=UNCLAIMED_TEXT[language],
                                status="queued",
                                idempotency_key=key,
                            )
                        )
                        sent.append(str(message.id))
                    row.context_summary = (row.context_summary or "") + FLAGGED  # once only
            except Exception:  # noqa: BLE001 - one bad ticket must not stop the others
                logger.warning("pi_unclaimed_flag_failed", exc_info=True)
        await session.commit()
    await enqueue_sends(ctx, sent)
    return sent


async def resolve_for_quote(
    session: AsyncSession, scope: WorkspaceScope, quote_id: UUID, note: str
) -> None:
    """The proposal went out: its price/approve requests are done."""
    rows = await session.scalars(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(
            PiStaffRequest.quote_id == quote_id,
            PiStaffRequest.status == "open",
            PiStaffRequest.kind.in_(["price", "approve"]),
        )
    )
    for row in rows:
        row.status, row.answer = "resolved", row.answer or note
        row.resolved_at = datetime.now(UTC)


# ---- Answering --------------------------------------------------------------------------


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=4000)
    save_as_knowledge: bool = False


async def answer(
    session: AsyncSession,
    scope: WorkspaceScope,
    request_id: UUID,
    text: str,
    *,
    save_as_knowledge: bool,
    max_bytes: int,
) -> PiStaffRequest:
    """The team's answer for pi. The chat goes back to pi; the caller queues pi's reply."""
    from app.modules.pi.service import PiService
    from app.modules.pi_saas.teach import DraftInput, _first_line, create_draft, publish_draft

    scope.require("pi.inbox.reply")
    repo = WorkspaceRepository(session, PiStaffRequest, scope)
    row = await repo.get(request_id, for_update=True)
    if row.status != "open":
        raise BusinessRuleViolation("REQUEST_CLOSED", "This request was already answered")
    service = PiService(session, scope)
    conversation = await service.conversations.get(row.conversation_id, for_update=True)
    if conversation.mode == "human":
        await service.mode(conversation.id, "return-to-ai")
    row.answer, row.answered_by_user_id = text, scope.user_id
    row.status, row.resolved_at = "answered", datetime.now(UTC)
    if save_as_knowledge:
        draft = await create_draft(
            session,
            scope,
            DraftInput(title=_first_line(row.question), content=f"Q: {row.question}\n\nA: {text}"),
            origin="ask_owner",
            staff_request_id=row.id,
        )
        if scope.can("pi.knowledge.publish"):
            published = await publish_draft(session, scope, draft.id, max_bytes)
            row.knowledge_document_id = published.published_document_id
            row.status = "published"
    await record(
        session,
        "pi_saas.staff_request_answered",
        scope=scope,
        entity_type="pi_staff_request",
        entity_id=row.id,
        details={"kind": row.kind, "knowledge": save_as_knowledge},
    )
    return row


async def team_notes(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> list[dict[str, str]]:
    """What the team told pi about this chat: answered requests and internal notes."""
    notes: list[dict[str, str]] = []
    try:
        async with session.begin_nested():
            answered = await session.scalars(
                WorkspaceRepository(session, PiStaffRequest, scope)
                .select()
                .where(
                    PiStaffRequest.conversation_id == conversation_id,
                    PiStaffRequest.status.in_(DONE),
                    PiStaffRequest.answer.is_not(None),
                )
                .order_by(PiStaffRequest.created_at.desc())
                .limit(5)
            )
            notes += [
                {"kind": f"answer to: {r.question[:300]}", "note": str(r.answer)[:1500]}
                for r in answered
            ]
            internal = await session.scalars(
                WorkspaceRepository(session, PiConversationNote, scope)
                .select()
                .where(PiConversationNote.conversation_id == conversation_id)
                .order_by(PiConversationNote.created_at.desc())
                .limit(5)
            )
            notes += [{"kind": "team note", "note": n.body[:1500]} for n in internal]
    except DBAPIError:
        logger.warning("pi_team_notes_unavailable", exc_info=True)
    return notes


# ---- pi replies with the team's answer --------------------------------------------------


async def reply_with_answer(ctx: dict[str, Any], request_id: str) -> None:
    """Job: pi writes the customer a reply that uses the team's answer. Inside the
    24-hour window only; otherwise the answer waits in pi's context for their next
    message. Never runs while the team holds the chat."""
    from app.ai.manager import build_llm_manager
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.guard import ReplyRejected
    from app.modules.pi.runtime import enqueue_sends
    from app.modules.pi.service_conversation import compose_service_turn, prepare_context
    from app.modules.pi_saas.deals import system_scope_for

    async with ctx["sessions"]() as session:
        row = await session.get(PiStaffRequest, UUID(request_id))
        if row is None or row.status not in DONE or not row.answer:
            return
        scope = await system_scope_for(session, row.tenant_id, row.environment_id)
        conversation = await WorkspaceRepository(session, PiConversation, scope).get(
            row.conversation_id
        )
        now = datetime.now(UTC)
        if conversation.mode == "human" or not conversation.last_inbound_at:
            return
        if conversation.last_inbound_at < now - WINDOW:
            return
        key = f"pi-team-answer:{row.id}"
        repo = WorkspaceRepository(session, PiMessage, scope)
        if await repo.find(PiMessage.idempotency_key == key) is not None:
            return
        latest = await session.scalar(
            repo.select()
            .where(
                PiMessage.conversation_id == conversation.id,
                PiMessage.direction == "inbound",
            )
            .order_by(PiMessage.created_at.desc())
            .limit(1)
        )
        if latest is None:
            return
        policy = await settings_row(session, scope)
        meeting = (conversation.service_brief or {}).get("meeting") or {}
        if str(row.answer).startswith("Meeting confirmed by the team") and meeting.get("label"):
            # The time and link go out word for word: the model's reply could lose them
            # (the price guard removes sentences with digits).
            from app.modules.pi_saas.meetings import meeting_message

            language = "roman_ur" if (conversation.language or "") == "roman_ur" else "en"
            await _send(session, repo, conversation, row, key, meeting_message(meeting, language))
            await session.commit()
            await enqueue_sends(ctx, [str(row.reply_message_id)])
            return
        context = await prepare_context(session, scope, conversation, latest, policy)
        context["team_answer_now"] = {"question": row.question[:1500], "answer": row.answer}
        await session.commit()  # No transaction is held across the model call.
        manager = build_llm_manager(ctx["settings"], ctx["http"], ctx["sessions"])
        body: str | None
        try:
            body = (await compose_service_turn(manager, scope, conversation, policy, context)).reply
        except (ReplyRejected, Exception):  # noqa: BLE001 - see the fallback below
            logger.warning("pi_team_answer_reply_failed", exc_info=True)
            # A customer's question still gets its answer: as the team wrote it. Other
            # kinds (internal notes on prices, approvals) are never sent verbatim.
            body = row.answer if row.kind == "question" else None
        if not body:
            return
        message = await repo.add(
            repo.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                body=body,
                status="queued",
                idempotency_key=key,
            )
        )
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_preview = body[:200]
        row.reply_message_id = message.id
        await session.commit()
        await enqueue_sends(ctx, [str(message.id)])


async def _send(
    session: AsyncSession,
    repo: WorkspaceRepository[PiMessage],
    conversation: PiConversation,
    row: PiStaffRequest,
    key: str,
    body: str,
) -> None:
    message = await repo.add(
        repo.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            agent_key="requirement",
            body=body,
            status="queued",
            idempotency_key=key,
        )
    )
    conversation.last_message_at = datetime.now(UTC)
    conversation.last_message_preview = body[:200]
    row.reply_message_id = message.id


async def enqueue_reply(request: Request, request_id: UUID) -> None:
    await request.app.state.queue.enqueue(
        "pi_reply_with_team_answer", str(request_id), job_id=f"pi-team-answer:{request_id}"
    )


# ---- API --------------------------------------------------------------------------------

router = APIRouter(prefix="/pi/requests", tags=["pi-requests"])


async def view(
    session: AsyncSession, scope: WorkspaceScope, rows: list[PiStaffRequest]
) -> list[dict[str, Any]]:
    names = {
        c.id: c.name
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope)
            .select()
            .where(Customer.id.in_([r.customer_id for r in rows] or [None]))
        )
    }
    return [
        {
            "id": r.id,
            "kind": r.kind if r.kind not in ESCALATION_KINDS else "other",
            # The apps know normal and high; "urgent" shows as high there, with its own flag.
            "priority": "high" if r.priority == "urgent" else r.priority,
            "urgent": r.priority == "urgent",
            "reason": r.kind if r.kind in ESCALATION_KINDS else None,
            "reason_label": ESCALATION_TITLES.get(r.kind),
            "status": r.status,
            "question": r.question,
            "context": r.context_summary,
            "answer": r.answer,
            "conversation_id": r.conversation_id,
            "customer_id": r.customer_id,
            "customer_name": names.get(r.customer_id),
            "lead_id": r.lead_id,
            "quote_id": r.quote_id,
            "file_id": r.file_id,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        }
        for r in rows
    ]


@router.get("")
async def list_requests(
    scope: Scope,
    session: Session,
    status: Literal["open", "done", "all"] = Query("open"),
) -> dict[str, Any]:
    from app.modules.pi.service import PiService

    scope.require("pi.read")
    service = PiService(session, scope)
    visible = service.conversations.select().with_only_columns(PiConversation.id)
    query = (
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(PiStaffRequest.conversation_id.in_(visible))
    )
    if status == "open":
        query = query.where(PiStaffRequest.status == "open")
    elif status == "done":
        query = query.where(PiStaffRequest.status != "open")
    rows = list(await session.scalars(query.order_by(PiStaffRequest.created_at.desc()).limit(200)))
    open_count = sum(1 for r in rows if r.status == "open") if status != "done" else 0
    from app.modules.pi_saas import connectors

    calendar = await connectors.current(session, scope, "google_calendar")
    return {
        "items": await view(session, scope, rows),
        "open": open_count,
        # Meeting requests can get a Google Meet link when a calendar is connected.
        "google_meet": calendar is not None and calendar.status in connectors.USABLE,
    }


@router.post("/{request_id}/answer")
async def answer_request(
    request_id: UUID, data: AnswerInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    from app.modules.pi.service import PiService
    from app.modules.pi_saas.meetings import auto_arrange, runtime_for

    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id)
    await PiService(session, scope).conversations.get(row.conversation_id)  # visibility
    max_bytes = request.app.state.settings.knowledge_upload_max_bytes
    try:
        arranged = (
            await auto_arrange(
                session, scope, runtime_for(request), row, data.answer, max_bytes=max_bytes
            )
            if row.status == "open"
            else None
        )
    except BusinessRuleViolation as error:
        if error.code == "CALENDAR_RECONNECT":
            from app.modules.pi_saas.meetings import mark_reconnect

            await mark_reconnect(session, scope)
        raise
    row = arranged or await answer(
        session,
        scope,
        request_id,
        data.answer,
        save_as_knowledge=data.save_as_knowledge,
        max_bytes=max_bytes,
    )
    await session.commit()
    await enqueue_reply(request, row.id)
    return (await view(session, scope, [row]))[0]


@router.post("/{request_id}/meeting")
async def arrange_meeting(
    request_id: UUID, data: MeetingInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Book the meeting (Google Meet, a link or a place); pi tells the customer."""
    from app.modules.pi.service import PiService
    from app.modules.pi_saas.meetings import arrange, mark_reconnect, runtime_for

    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id)
    await PiService(session, scope).conversations.get(row.conversation_id)  # visibility
    try:
        row = await arrange(
            session,
            scope,
            runtime_for(request),
            request_id,
            data,
            max_bytes=request.app.state.settings.knowledge_upload_max_bytes,
        )
    except BusinessRuleViolation as error:
        if error.code == "CALENDAR_RECONNECT":
            await mark_reconnect(session, scope)
        raise
    await session.commit()
    await enqueue_reply(request, row.id)
    return (await view(session, scope, [row]))[0]


@router.post("/{request_id}/dismiss")
async def dismiss_request(request_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.inbox.reply")
    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id, for_update=True)
    if row.status == "open":
        row.status, row.resolved_at = "dismissed", datetime.now(UTC)
    await session.commit()
    return (await view(session, scope, [row]))[0]


@badge_provider("pi.open_requests")
async def open_requests(session: AsyncSession, scope: WorkspaceScope) -> int | None:
    """What pi is waiting on the team for (the "Requests" nav count)."""
    if not scope.can("pi.inbox.reply"):
        return None
    count = await session.scalar(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .with_only_columns(func.count())
        .where(PiStaffRequest.status == "open")
    )
    return int(count or 0) or None


@badge_provider("pi.open_handoffs")
async def open_handoffs(session: AsyncSession, scope: WorkspaceScope) -> int | None:
    """Chats waiting for a person (the "Handoffs" nav count)."""
    if not (scope.can("pi.handoffs.manage") or scope.can("pi.inbox.reply")):
        return None
    count = await session.scalar(
        WorkspaceRepository(session, PiHandoff, scope)
        .select()
        .with_only_columns(func.count())
        .where(PiHandoff.status.in_(["open", "assigned", "in_progress"]))
    )
    return int(count or 0) or None
