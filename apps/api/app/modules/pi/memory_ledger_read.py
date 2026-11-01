"""Reads of the memory ledgers for `context_memory.build_context` (the single reader of pi's
memory): decisions, rejections, the references of stored document text, and the delivered and
verified markers. Read only; explicit column selects (never an ORM object, so a deferred column is
never lazy-loaded); every query is scoped by tenant AND environment AND customer. Each function is
called inside the bundle's own savepoint guard, so a missing table or column is reported as
"unavailable" and the rest of the bundle still returns. Texts were redacted when stored.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.context_memory_types import DecisionItem, RejectionItem
from app.modules.pi.memory_models import PiDecision, PiDocumentText, PiRejection
from app.shared.scope import WorkspaceScope


def _mine(model: Any, scope: WorkspaceScope) -> tuple[Any, ...]:
    return (model.tenant_id == scope.tenant_id, model.environment_id == scope.environment_id)


def _iso(value: Any) -> str:
    try:
        return value.isoformat() if value is not None else ""
    except Exception:  # noqa: BLE001
        return ""


async def read_decisions(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> list[DecisionItem]:
    rows = (
        await session.execute(
            select(
                PiDecision.id,
                PiDecision.kind,
                PiDecision.subject_ref,
                PiDecision.actor,
                PiDecision.owner_words,
                PiDecision.source_message_id,
                PiDecision.status,
                PiDecision.valid_from,
                PiDecision.valid_to,
            )
            .where(*_mine(PiDecision, scope), PiDecision.customer_id == customer_id)
            .order_by(PiDecision.valid_from.desc(), PiDecision.id.desc())
            .limit(size)
        )
    ).all()
    return [
        DecisionItem(
            kind=str(r.kind),
            ref=str(r.subject_ref),
            status=str(r.status),
            text=str(r.owner_words or ""),
            at=_iso(r.valid_from),
            source=f"msg:{r.source_message_id}" if r.source_message_id else f"staff:{r.actor}",
            actor=str(r.actor),
            valid_to=_iso(r.valid_to),
        )
        for r in rows
    ]


async def read_rejections(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> list[RejectionItem]:
    rows = (
        await session.execute(
            select(
                PiRejection.id,
                PiRejection.target_kind,
                PiRejection.target_key,
                PiRejection.idea_text,
                PiRejection.owner_words,
                PiRejection.reason,
                PiRejection.source_message_id,
                PiRejection.status,
                PiRejection.valid_from,
            )
            .where(*_mine(PiRejection, scope), PiRejection.customer_id == customer_id)
            .order_by(PiRejection.valid_from.desc(), PiRejection.id.desc())
            .limit(size)
        )
    ).all()
    out: list[RejectionItem] = []
    for r in rows:
        text = str(r.idea_text or r.owner_words or r.target_key or "")
        if not text:
            continue
        out.append(
            RejectionItem(
                text=text[:200],
                ref=f"rej:{str(r.id)[:8]}",
                derived=False,
                at=_iso(r.valid_from),
                status=str(r.status),
                source=f"msg:{r.source_message_id}" if r.source_message_id else "",
                reason=str(r.reason or ""),
            )
        )
    return out


async def read_text_refs(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> dict[UUID, tuple[str, ...]]:
    """file id -> the references of its stored text, in page order (no text is returned here)."""
    rows = (
        await session.execute(
            select(PiDocumentText.customer_file_id, PiDocumentText.ref)
            .where(*_mine(PiDocumentText, scope), PiDocumentText.customer_id == customer_id)
            .order_by(PiDocumentText.customer_file_id, PiDocumentText.ordinal)
            .limit(2000)
        )
    ).all()
    out: dict[UUID, list[str]] = {}
    for r in rows:
        out.setdefault(r.customer_file_id, []).append(str(r.ref))
    return {k: tuple(v) for k, v in out.items()}


async def export_document_texts(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, limit: int = 2000
) -> list[dict[str, Any]]:
    """The stored (redacted) text of the customer's documents with its references, for the
    customer export."""
    rows = (
        await session.execute(
            select(
                PiDocumentText.customer_file_id,
                PiDocumentText.ref,
                PiDocumentText.text,
                PiDocumentText.created_at,
            )
            .where(*_mine(PiDocumentText, scope), PiDocumentText.customer_id == customer_id)
            .order_by(PiDocumentText.customer_file_id, PiDocumentText.ordinal)
            .limit(limit)
        )
    ).all()
    return [
        {"file_id": str(r.customer_file_id), "ref": r.ref, "text": r.text, "at": _iso(r.created_at)}
        for r in rows
    ]


async def read_markers(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> dict[tuple[str, int, int], tuple[str, str]]:
    """(kind, number, version) of a brain document -> (delivered_at, verified_at) as ISO text, only
    for documents staff marked."""
    rows = (
        await session.execute(
            select(
                PiBrainDocument.kind,
                PiBrainDocument.number,
                PiBrainDocument.version,
                PiBrainDocument.delivered_at,
                PiBrainDocument.verified_at,
            ).where(
                *_mine(PiBrainDocument, scope),
                PiBrainDocument.customer_id == customer_id,
                PiBrainDocument.delivered_at.is_not(None),
            )
        )
    ).all()
    return {
        (str(r.kind), int(r.number), int(r.version or 1)): (
            _iso(r.delivered_at),
            _iso(r.verified_at),
        )
        for r in rows
    }
