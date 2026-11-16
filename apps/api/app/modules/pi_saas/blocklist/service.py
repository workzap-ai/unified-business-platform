"""Blocking and unblocking WhatsApp numbers, and the one question the inbound path asks:
"is this sender blocked?" (``match``). A blocked sender's message is dropped before anything is
stored, read by pi or sent to a model, so a flood costs nothing but one indexed query."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, literal, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiConversation
from app.modules.pi_saas.blocklist.models import MIN_PREFIX, PiBlockedContact
from app.modules.pi_saas.nori_credits.resilience import digits, mask_number
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

MAX_BULK = 500


def clean_value(raw: object, kind: str) -> str:
    """Digits with country code: 7 to 15 for a number, 6 to 14 for a prefix."""
    value = digits(raw)
    if kind == "prefix":
        if not MIN_PREFIX <= len(value) <= 14:
            raise BusinessRuleViolation(
                "PREFIX_INVALID",
                f"A range needs at least {MIN_PREFIX} digits (country code and the start of the "
                "number), so a whole country can't be blocked by accident",
            )
        return value
    if not 7 <= len(value) <= 15:
        raise BusinessRuleViolation("PHONE_INVALID", "Enter the WhatsApp number with country code")
    return value


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


async def match(
    session: AsyncSession, scope: WorkspaceScope, sender: object
) -> PiBlockedContact | None:
    """The active rule that blocks this sender: the exact number, else a prefix it starts with."""
    value = digits(sender)
    if not value:
        return None
    repo = WorkspaceRepository(session, PiBlockedContact, scope)
    row = await session.scalar(
        repo.select()
        .where(
            PiBlockedContact.active.is_(True),
            or_(
                and_(PiBlockedContact.kind == "number", PiBlockedContact.value == value),
                and_(
                    PiBlockedContact.kind == "prefix",
                    literal(value).like(func.concat(PiBlockedContact.value, "%")),
                ),
            ),
        )
        .order_by(PiBlockedContact.kind.desc())  # "number" before "prefix"
        .limit(1)
    )
    return row


async def count_hit(session: AsyncSession, row: PiBlockedContact) -> None:
    row.hits += 1
    row.last_hit_at = datetime.now(UTC)
    await session.flush()


async def list_rows(session: AsyncSession, scope: WorkspaceScope) -> list[PiBlockedContact]:
    rows = await session.scalars(
        WorkspaceRepository(session, PiBlockedContact, scope)
        .select()
        .order_by(PiBlockedContact.active.desc(), PiBlockedContact.created_at.desc())
        .limit(2000)
    )
    return list(rows)


async def block(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    value: str,
    kind: str = "number",
    reason: str = "",
    note: str = "",
    source: str = "manual",
) -> tuple[PiBlockedContact, bool]:
    """Block a number or range. Blocking something already on the list switches it back on and
    keeps its history. Returns the row and whether it was new."""
    clean = clean_value(value, kind)
    repo = WorkspaceRepository(session, PiBlockedContact, scope)
    existing = await repo.find(PiBlockedContact.value == clean)
    if existing is not None:
        existing.active = True
        existing.kind = kind
        if reason:
            existing.reason = _text(reason, 200)
        if note:
            existing.note = _text(note, 500)
        existing.blocked_by = scope.user_id
        existing.updated_at = datetime.now(UTC)
        await session.flush()
        return existing, False
    try:
        async with session.begin_nested():
            row = await repo.add(
                repo.new(
                    value=clean,
                    kind=kind,
                    reason=_text(reason, 200),
                    note=_text(note, 500),
                    source=source,
                    blocked_by=scope.user_id,
                )
            )
    except IntegrityError:
        raise BusinessRuleViolation("ALREADY_BLOCKED", "This number is already blocked") from None
    return row, True


async def block_many(
    session: AsyncSession,
    scope: WorkspaceScope,
    values: list[str],
    *,
    reason: str,
    note: str = "",
) -> dict[str, Any]:
    if len(values) > MAX_BULK:
        raise BusinessRuleViolation("TOO_MANY", f"Block at most {MAX_BULK} numbers at a time")
    added = switched_on = 0
    skipped: list[str] = []
    for raw in dict.fromkeys(values):
        try:
            _, is_new = await block(
                session, scope, value=raw, reason=reason, note=note, source="bulk"
            )
        except BusinessRuleViolation:
            skipped.append(mask_number(raw))
            continue
        added, switched_on = added + is_new, switched_on + (not is_new)
    return {"added": added, "already_listed": switched_on, "skipped": skipped}


async def unblock(session: AsyncSession, scope: WorkspaceScope, row_id: UUID) -> PiBlockedContact:
    row = await WorkspaceRepository(session, PiBlockedContact, scope).get(row_id, for_update=True)
    row.active = False
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def change(
    session: AsyncSession, scope: WorkspaceScope, row_id: UUID, values: dict[str, Any]
) -> PiBlockedContact:
    row = await WorkspaceRepository(session, PiBlockedContact, scope).get(row_id, for_update=True)
    if "reason" in values:
        row.reason = _text(values["reason"], 200)
    if "note" in values:
        row.note = _text(values["note"], 500)
    if values.get("active") is not None:
        row.active = bool(values["active"])
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def close_chats(session: AsyncSession, scope: WorkspaceScope, row: PiBlockedContact) -> int:
    """Close the open chats of the blocked number or range, so they leave the inbox. Their
    messages stay as a record."""
    repo = WorkspaceRepository(session, PiConversation, scope)
    cond = (
        PiConversation.contact_wa_id == row.value
        if row.kind == "number"
        else PiConversation.contact_wa_id.like(f"{row.value}%")
    )
    chats = list(await session.scalars(repo.select().where(PiConversation.status == "open", cond)))
    for chat in chats:
        chat.status = "closed"
        chat.mode = "human"
        chat.unread_count = 0
    await session.flush()
    return len(chats)


def view(row: PiBlockedContact) -> dict[str, Any]:
    return {
        "id": row.id,
        "value": row.value,
        "masked": mask_number(row.value) if row.kind == "number" else f"{row.value}…",
        "kind": row.kind,
        "reason": row.reason,
        "note": row.note,
        "source": row.source,
        "active": row.active,
        "hits": row.hits,
        "last_hit_at": row.last_hit_at,
        "created_at": row.created_at,
    }
