"""The ONE writer of pi's decision and rejection ledgers (`pi_decisions`, `pi_rejections`).

Callers are the existing gates, each with a one-line hook: `service_conversation.apply_decision`
(the yes gate, the offer, a decline, a revision request, the owner's approval), the brain document
approval route, and `solution_ideas.react` (an idea the owner rejected). Nothing else writes.

Rules:
* brain mode only (`response_rules.pi_mode == "brain"`); other workspaces write nothing.
* the owner's words are redacted first (card, ID, phone, e-mail; a third party's name where the
  words around it give it away), then cut. The ledger keeps roles, never names.
* idempotent: the same (customer, kind, subject, source message) is written once, a replay does
  nothing; the same statement again on a subject changes nothing.
* a newer statement on a subject supersedes the older one: the old row stays (`superseded`,
  `valid_to` set) and the new one points at it. Nothing is overwritten and nothing is deleted.
* a rejection is reversed (row kept) when the owner later accepts the same target.
* every write runs in its own savepoint and a failure (a table that does not exist yet, a race) is
  logged and swallowed: the ledger can never stop a customer's message from being answered.
Logs carry counts and ids, never the owner's words.
"""

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import problem_fields
from app.modules.pi.memory_models import PiDecision, PiRejection
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

OFFER_SUBJECT = "box:offer"
# A scope or a price agreed on a document is stored as kind "other" (the table's kind constraint
# is fixed in production) under one subject per customer; the reader shows the subject as the kind.
SCOPE_SUBJECT = "scope"
PRICE_SUBJECT = "price"
WORDS_CAP = 300
IDEA_CAP = 500


def brain_on(response_rules: dict[str, Any] | None) -> bool:
    return (response_rules or {}).get("pi_mode") == "brain"


def redacted(text: Any, cap: int = WORDS_CAP) -> str:
    """The text as it may be stored: redacted, third-party names protected, whitespace collapsed,
    cut to `cap`. Redact first, then cut, so a number cut in half is never left behind."""
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    try:
        # the same cleaning the problem notes use: card, ID, account, e-mail and phone numbers
        # (local forms too) out, a third party's name protected, then cut
        return problem_fields.clean(raw, cap)[0]
    except Exception:  # noqa: BLE001 - when redaction fails nothing is stored, never raw text
        return ""


def idea_hash(text: str) -> str:
    """A stable key for an idea's wording: lower case, letters and digits only."""
    key = re.sub(r"[^a-z0-9؀-ۿऀ-ॿ]+", " ", str(text or "").lower()).strip()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _mine(model: Any, scope: WorkspaceScope) -> tuple[Any, ...]:
    return (model.tenant_id == scope.tenant_id, model.environment_id == scope.environment_id)


async def message_words(
    session: AsyncSession, scope: WorkspaceScope, message_id: UUID | None
) -> str:
    """The redacted words of one inbound message of this workspace (the owner's own message)."""
    if message_id is None:
        return ""
    from app.modules.pi.models import PiMessage

    body = await session.scalar(
        select(PiMessage.body).where(
            *_mine(PiMessage, scope), PiMessage.id == message_id, PiMessage.direction == "inbound"
        )
    )
    return redacted(body)


async def latest_owner_message(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> tuple[UUID | None, str]:
    """(id, redacted words) of the owner's latest inbound message in this conversation."""
    from app.modules.pi.models import PiMessage

    row = (
        await session.execute(
            select(PiMessage.id, PiMessage.body)
            .where(
                *_mine(PiMessage, scope),
                PiMessage.conversation_id == conversation_id,
                PiMessage.direction == "inbound",
            )
            .order_by(PiMessage.created_at.desc(), PiMessage.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, ""
    return row.id, redacted(row.body)


# --------------------------------------------------------------------------- decisions


async def record_decision(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    kind: str,
    subject_ref: str,
    actor: str = "owner",
    owner_words: str = "",
    source_message_id: UUID | None = None,
    problem_id: UUID | None = None,
    now: datetime | None = None,
    verbatim: bool = False,
) -> PiDecision | None:
    """Write one decision, or return the one that already says the same. Never raises.
    `verbatim` is for words the code itself built from staff-entered figures (a price): they are
    stored as they are, not redacted (redaction would mangle a large amount), and cut to the cap."""
    stamp = now or datetime.now(UTC)
    words = (
        " ".join(str(owner_words or "").split())[: WORDS_CAP * 2]
        if verbatim
        else redacted(owner_words)
    )
    try:
        async with session.begin_nested():
            return await _write_decision(
                session,
                scope,
                customer_id=customer_id,
                kind=kind,
                subject_ref=subject_ref[:60],
                actor=actor,
                words=words,
                source_message_id=source_message_id,
                problem_id=problem_id,
                stamp=stamp,
            )
    except IntegrityError:
        # a concurrent writer won the race: what it wrote is the decision
        return await _existing(
            session, scope, customer_id, kind, subject_ref[:60], source_message_id
        )
    except Exception:  # noqa: BLE001 - the ledger never stops a reply (table missing, bad id)
        logger.warning("pi_decision_not_recorded", extra={"kind": kind}, exc_info=True)
        return None


async def _existing(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    kind: str,
    subject_ref: str,
    source_message_id: UUID | None,
) -> PiDecision | None:
    if source_message_id is None:
        return None
    try:
        async with session.begin_nested():
            found: PiDecision | None = await session.scalar(
                select(PiDecision).where(
                    *_mine(PiDecision, scope),
                    PiDecision.customer_id == customer_id,
                    PiDecision.kind == kind,
                    PiDecision.subject_ref == subject_ref,
                    PiDecision.source_message_id == source_message_id,
                )
            )
            return found
    except Exception:  # noqa: BLE001
        return None


async def _write_decision(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    kind: str,
    subject_ref: str,
    actor: str,
    words: str,
    source_message_id: UUID | None,
    problem_id: UUID | None,
    stamp: datetime,
) -> PiDecision:
    if source_message_id is not None:
        replay = await session.scalar(
            select(PiDecision).where(
                *_mine(PiDecision, scope),
                PiDecision.customer_id == customer_id,
                PiDecision.kind == kind,
                PiDecision.subject_ref == subject_ref,
                PiDecision.source_message_id == source_message_id,
            )
        )
        if replay is not None:
            return replay
    live: PiDecision | None = await session.scalar(
        select(PiDecision)
        .where(
            *_mine(PiDecision, scope),
            PiDecision.customer_id == customer_id,
            PiDecision.subject_ref == subject_ref,
            PiDecision.status == "active",
        )
        .with_for_update()
    )
    if (
        live is not None
        and live.kind == kind
        and live.actor == actor
        and live.owner_words == words
        and live.source_message_id is None
        and source_message_id is None
    ):
        return live  # the same statement again: nothing changes
    row = PiDecision(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        problem_id=problem_id,
        kind=kind,
        subject_ref=subject_ref,
        actor=actor,
        owner_words=words,
        source_message_id=source_message_id,
        status="active",
        valid_from=stamp,
    )
    if live is not None:
        live.status = "superseded"
        live.valid_to = stamp
        await session.flush()  # the old row leaves "active" before the new one arrives
        row.supersedes_id = live.id
    session.add(row)
    await session.flush()
    return row


async def withdraw_decision(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    subject_ref: str,
    now: datetime | None = None,
) -> bool:
    """The owner said a decision no longer applies: its row stays, status `withdrawn`."""
    try:
        async with session.begin_nested():
            live: PiDecision | None = await session.scalar(
                select(PiDecision).where(
                    *_mine(PiDecision, scope),
                    PiDecision.customer_id == customer_id,
                    PiDecision.subject_ref == subject_ref[:60],
                    PiDecision.status == "active",
                )
            )
            if live is None:
                return False
            live.status = "withdrawn"
            live.valid_to = now or datetime.now(UTC)
            await session.flush()
            return True
    except Exception:  # noqa: BLE001
        logger.warning("pi_decision_not_withdrawn", exc_info=True)
        return False


# --------------------------------------------------------------------------- rejections


async def record_rejection(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    target_kind: str,
    target_key: str,
    idea_text: str = "",
    owner_words: str = "",
    reason: str = "",
    source_message_id: UUID | None = None,
    problem_id: UUID | None = None,
    now: datetime | None = None,
) -> PiRejection | None:
    """Write what the owner said no to, once per (target, message). An active rejection of the
    same target is not written twice. Never raises."""
    stamp = now or datetime.now(UTC)
    try:
        async with session.begin_nested():
            same = select(PiRejection).where(
                *_mine(PiRejection, scope),
                PiRejection.customer_id == customer_id,
                PiRejection.target_kind == target_kind,
                PiRejection.target_key == target_key[:140],
            )
            if source_message_id is not None:
                replay = await session.scalar(
                    same.where(PiRejection.source_message_id == source_message_id)
                )
                if replay is not None:
                    return replay
            live: PiRejection | None = await session.scalar(
                same.where(PiRejection.status == "active").limit(1)
            )
            if live is not None:
                return live
            text = redacted(idea_text, IDEA_CAP)
            row = PiRejection(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                customer_id=customer_id,
                problem_id=problem_id,
                target_kind=target_kind,
                target_key=target_key[:140],
                idea_hash=idea_hash(text) if text else "",
                idea_text=text,
                owner_words=redacted(owner_words),
                reason=redacted(reason, 300),
                source_message_id=source_message_id,
                status="active",
                valid_from=stamp,
            )
            session.add(row)
            await session.flush()
            return row
    except IntegrityError:
        return None
    except Exception:  # noqa: BLE001
        logger.warning("pi_rejection_not_recorded", extra={"kind": target_kind}, exc_info=True)
        return None


async def reverse_rejections(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    target_kind: str,
    target_key: str,
    now: datetime | None = None,
) -> int:
    """The owner later accepted the same target: active rejections become `reversed` (rows kept)."""
    try:
        async with session.begin_nested():
            rows = list(
                await session.scalars(
                    select(PiRejection).where(
                        *_mine(PiRejection, scope),
                        PiRejection.customer_id == customer_id,
                        PiRejection.target_kind == target_kind,
                        PiRejection.target_key == target_key[:140],
                        PiRejection.status == "active",
                    )
                )
            )
            stamp = now or datetime.now(UTC)
            for row in rows:
                row.status = "reversed"
                row.valid_to = stamp
            await session.flush()
            return len(rows)
    except Exception:  # noqa: BLE001
        logger.warning("pi_rejection_not_reversed", exc_info=True)
        return 0


async def rejected_ideas(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, limit: int = 40
) -> list[str]:
    """The wording of the ideas this owner rejected and has not taken back (for the idea filter).
    Empty when the table is missing or holds nothing."""
    try:
        async with session.begin_nested():
            rows = await session.scalars(
                select(PiRejection.idea_text)
                .where(
                    *_mine(PiRejection, scope),
                    PiRejection.customer_id == customer_id,
                    PiRejection.target_kind == "idea",
                    PiRejection.status == "active",
                    PiRejection.idea_text != "",
                )
                .order_by(PiRejection.valid_from.desc(), PiRejection.id.desc())
                .limit(limit)
            )
            return [str(t) for t in rows]
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------- the gate hooks


async def on_decision(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: Any,
    decision: Any,
    response_rules: dict[str, Any] | None,
) -> None:
    """Called by `apply_decision` after the gates decided. Mirrors the decision into the ledger;
    it never decides anything and never raises. A no-op outside brain mode."""
    if not brain_on(response_rules) or conversation.customer_id is None:
        return
    change = getattr(decision, "brief", None) or {}
    effects = list(getattr(decision, "effects", None) or [])
    kind: str | None = None
    actor = "owner"
    if change.get("offer_declined"):
        kind = "decline"
    elif "request_solution" in effects:
        kind = "yes"
    elif "request_revision" in effects:
        kind = "revision_request"
    elif "record_approval" in effects:
        kind = "approval"
    elif change.get("offer_asked"):
        kind, actor = "offer", "pi"
    if kind is None:
        return
    try:
        message_id, words = (
            (None, "")
            if actor == "pi"
            else await latest_owner_message(session, scope, conversation.id)
        )
        await record_decision(
            session,
            scope,
            customer_id=conversation.customer_id,
            kind=kind,
            subject_ref=OFFER_SUBJECT,
            actor=actor,
            owner_words=words,
            source_message_id=message_id,
        )
        if kind == "decline":
            await record_rejection(
                session,
                scope,
                customer_id=conversation.customer_id,
                target_kind="offer",
                target_key=OFFER_SUBJECT,
                owner_words=words,
                source_message_id=message_id,
            )
        elif kind in ("yes", "approval"):
            await reverse_rejections(
                session,
                scope,
                customer_id=conversation.customer_id,
                target_kind="offer",
                target_key=OFFER_SUBJECT,
            )
    except Exception:  # noqa: BLE001
        logger.warning("pi_ledger_hook_failed", exc_info=True)


async def on_document_approved(
    session: AsyncSession,
    scope: WorkspaceScope,
    doc: Any,
    response_rules: dict[str, Any] | None,
) -> None:
    """A reviewer approved a solution document or quote: a staff decision on that document. The
    approver is the staff member; the words are empty (no owner words are involved)."""
    if not brain_on(response_rules) or getattr(doc, "customer_id", None) is None:
        return
    try:
        await record_decision(
            session,
            scope,
            customer_id=doc.customer_id,
            kind="document_approval",
            subject_ref=f"doc:{doc.ref}",
            actor="staff",
            owner_words="",
        )
        await _record_scope_and_price(session, scope, doc)
    except Exception:  # noqa: BLE001
        logger.warning("pi_ledger_doc_hook_failed", exc_info=True)


def scope_words(doc: Any) -> str:
    """What the approved document includes: a quote's `included` list, a solution document's
    component texts. Empty when the document says nothing."""
    content = getattr(doc, "content", None) or {}
    items = content.get("included")
    if not items:
        items = [c.get("text", "") for c in content.get("components") or [] if isinstance(c, dict)]
    return "; ".join(str(i).strip() for i in items or [] if str(i).strip())


def price_words(doc: Any) -> str:
    """The figure exactly as staff set it, with the document, its version and the approver."""
    total = getattr(doc, "total", None)
    if total is None or total <= 0:
        return ""
    figure = f"{format(total, 'f')} {getattr(doc, 'currency', '') or ''}".strip()
    approver = getattr(doc, "approved_by", None)
    return (
        f"{figure} ({doc.ref}, version {getattr(doc, 'version', 1)}, "
        f"approved by {approver if approver else 'staff'})"
    )


async def _record_scope_and_price(session: AsyncSession, scope: WorkspaceScope, doc: Any) -> None:
    """Staff approved a document: its scope and its price are now decisions, each superseding the
    last one for this customer. Only figures staff entered are recorded; pi never prices."""
    ref = str(doc.ref)
    words = scope_words(doc)
    if words:
        await record_decision(
            session,
            scope,
            customer_id=doc.customer_id,
            kind="other",
            subject_ref=SCOPE_SUBJECT,
            actor="staff",
            owner_words=f"{ref} v{getattr(doc, 'version', 1)}: {words}",
        )
    figure = price_words(doc)
    if figure:
        await record_decision(
            session,
            scope,
            customer_id=doc.customer_id,
            kind="other",
            subject_ref=PRICE_SUBJECT,
            actor="staff",
            owner_words=figure,
            verbatim=True,
        )


async def on_idea_reaction(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    arm: Any,
    memory_reaction: str,
    message_id: UUID | None,
) -> None:
    """`solution_ideas.react` applied a reaction to one idea. A rejection goes to the ledger with
    the owner's words; trying the idea (or saying they will) takes an earlier rejection back. The
    workspace's own setting decides (brain mode only); never raises."""
    if memory_reaction not in ("rejected", "tried", "engaged"):
        return
    try:
        from app.modules.pi.configuration import settings_row

        if not brain_on((await settings_row(session, scope)).response_rules):
            return
        key = str(getattr(arm, "arm_key", "") or getattr(arm, "id", ""))
        if memory_reaction == "rejected":
            await record_rejection(
                session,
                scope,
                customer_id=customer_id,
                target_kind="idea",
                target_key=key,
                idea_text=str(getattr(arm, "text", "") or ""),
                owner_words=await message_words(session, scope, message_id),
                source_message_id=message_id,
            )
        elif memory_reaction == "tried":
            await reverse_rejections(
                session, scope, customer_id=customer_id, target_kind="idea", target_key=key
            )
    except Exception:  # noqa: BLE001
        logger.warning("pi_ledger_idea_hook_failed", exc_info=True)
