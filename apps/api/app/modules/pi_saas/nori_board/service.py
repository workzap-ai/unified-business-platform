"""Numbers and items of the Nori Platform board. No HTTP in here; the door, the routes and the
bridge hook call these functions.

An item is a team-board card (``pi_tasks`` row, key ``board:nori:<ref>``) plus a ``pi_nori_items``
row with who wrote, from which nori workspace and department. Filing is idempotent by ``ref``.
Text is stored redacted (cards, passwords, ID and account numbers, third parties' contact details).
"""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.service import notify
from app.modules.pi.safety import redact_pii
from app.modules.pi_saas.models import PiTask
from app.modules.pi_saas.nori_board.models import ITEM_KINDS, PiNoriItem, PiNoriNumber
from app.modules.pi_saas.nori_credits.resilience import digits, mask_number
from app.modules.pi_saas.team_board import PREFIX, SLA
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

KIND_LABEL = {
    "feature": "Feature",
    "problem": "Problem",
    "feedback": "Feedback",
    "module": "Module",
    "question": "Question",
    "change": "Change",
    "note": "Note",
}
PRIORITIES = ("low", "normal", "high", "urgent")
REF_RE = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
TEXT_MAX = 2000
TITLE_MAX = 200

# A light guess for a message that arrives without a kind (a number added by hand, writing to pi).
# English and Roman Urdu. Only a hint for the team, who can read the whole text on the card.
_PROBLEM = re.compile(
    r"\b(?:problem|issue|bug|error|broken|crash\w*|not working|doesn'?t work|stuck|slow|"
    r"masla|masle|nahi chal\w*|nhi chal\w*|kharab|band ho)\b",
    re.IGNORECASE,
)
_FEATURE = re.compile(
    r"\b(?:i need|we need|i want|we want|please add|can you add|could you add|feature|should have|"
    r"module|chahiye|chahie|add kar\w*|add kr\w*|bana do|banao)\b",
    re.IGNORECASE,
)
_FEEDBACK = re.compile(
    r"\b(?:feedback|suggest\w*|improve\w*|better|thanks|thank you|great|love|acha|achha"
    r"|shukriya)\b",
    re.IGNORECASE,
)


def normalise_phone(raw: object) -> str | None:
    """Digits of a WhatsApp number with country code (7 to 15), or None."""
    if not isinstance(raw, str):
        return None
    value = digits(raw)
    return value if 7 <= len(value) <= 15 else None


def classify(text: str) -> str:
    if _PROBLEM.search(text):
        return "problem"
    if _FEATURE.search(text):
        return "feature"
    if text.strip().endswith("?"):
        return "question"
    if _FEEDBACK.search(text):
        return "feedback"
    return "note"


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _first_line(text: str) -> str:
    line = _clean(text, 400)
    return line if len(line) <= TITLE_MAX else line[: TITLE_MAX - 1].rstrip() + "…"


# ---- The number registry --------------------------------------------------------------------


async def list_numbers(session: AsyncSession, scope: WorkspaceScope) -> list[PiNoriNumber]:
    rows = await session.scalars(
        WorkspaceRepository(session, PiNoriNumber, scope)
        .select()
        .order_by(PiNoriNumber.workspace, PiNoriNumber.person, PiNoriNumber.created_at)
        .limit(1000)
    )
    return list(rows)


async def find_number(
    session: AsyncSession, scope: WorkspaceScope, phone: object
) -> PiNoriNumber | None:
    value = normalise_phone(phone)
    if value is None:
        return None
    return await WorkspaceRepository(session, PiNoriNumber, scope).find(PiNoriNumber.phone == value)


async def add_number(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    phone: str,
    workspace: str,
    person: str = "",
    department: str = "",
    source: str = "manual",
) -> PiNoriNumber:
    value = normalise_phone(phone)
    if value is None:
        raise BusinessRuleViolation("PHONE_INVALID", "Enter the WhatsApp number with country code")
    name = _clean(workspace, 120)
    if not name:
        raise BusinessRuleViolation("WORKSPACE_REQUIRED", "Say which nori workspace this is")
    if await find_number(session, scope, value) is not None:
        raise BusinessRuleViolation("NUMBER_EXISTS", "This number is already on the board")
    repo = WorkspaceRepository(session, PiNoriNumber, scope)
    try:
        async with session.begin_nested():
            return await repo.add(
                repo.new(
                    phone=value,
                    workspace=name,
                    person=_clean(person, 120),
                    department=_clean(department, 80),
                    source=source,
                )
            )
    except IntegrityError:
        raise BusinessRuleViolation(
            "NUMBER_EXISTS", "This number is already on the board"
        ) from None


async def upsert_pushed_number(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    phone: str,
    workspace: str,
    person: str,
    department: str,
    active: bool,
    ref: str | None = None,
) -> tuple[PiNoriNumber, bool]:
    """nori tells pi about a team member. A new number is added with source "nori". A number the
    team added by hand keeps its source, and nori can switch it off but never back on (the team's
    own on/off switch wins). Returns the row and whether it was new."""
    row = await find_number(session, scope, phone)
    if row is None:
        repo = WorkspaceRepository(session, PiNoriNumber, scope)
        async with session.begin_nested():
            row = await repo.add(
                repo.new(
                    phone=phone,
                    workspace=_clean(workspace, 120),
                    person=_clean(person, 120),
                    department=_clean(department, 80),
                    active=active,
                    source="nori",
                    nori_ref=ref,
                )
            )
        return row, True
    row.workspace = _clean(workspace, 120)
    row.person = _clean(person, 120)
    row.department = _clean(department, 80)
    if row.source == "nori":
        row.nori_ref = ref
    if row.source == "nori" or not active:
        row.active = active
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row, False


async def update_number(
    session: AsyncSession, scope: WorkspaceScope, number_id: UUID, values: dict[str, Any]
) -> PiNoriNumber:
    row = await WorkspaceRepository(session, PiNoriNumber, scope).get(number_id, for_update=True)
    if "workspace" in values:
        name = _clean(values["workspace"], 120)
        if not name:
            raise BusinessRuleViolation("WORKSPACE_REQUIRED", "Say which nori workspace this is")
        row.workspace = name
    if "person" in values:
        row.person = _clean(values["person"], 120)
    if "department" in values:
        row.department = _clean(values["department"], 80)
    if values.get("active") is not None:
        row.active = bool(values["active"])
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def delete_number(session: AsyncSession, scope: WorkspaceScope, number_id: UUID) -> None:
    repo = WorkspaceRepository(session, PiNoriNumber, scope)
    await repo.delete(await repo.get(number_id, for_update=True))


# ---- Items ----------------------------------------------------------------------------------


async def item_for_ref(session: AsyncSession, scope: WorkspaceScope, ref: str) -> PiNoriItem | None:
    return await WorkspaceRepository(session, PiNoriItem, scope).find(PiNoriItem.ref == ref)


async def file_item(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    ref: str,
    kind: str = "note",
    title: str = "",
    text: str = "",
    workspace: str = "",
    person: str = "",
    department: str = "",
    phone: object = "",
    source: str = "manual",
    priority: str = "normal",
    url: str | None = None,
    created_by_label: str = "nori",
    created_by_user_id: UUID | None = None,
    forward_ref: str | None = None,
) -> tuple[PiTask, bool]:
    """The board card for this item and whether it was made now (False: the ref was filed before,
    nothing changes). The caller commits."""
    if not REF_RE.fullmatch(ref or ""):
        raise BusinessRuleViolation("ITEM_REF_INVALID", "The item reference is not valid")
    workspace = redact_pii(_clean(workspace, 120)).text
    person = redact_pii(_clean(person, 120)).text
    department = redact_pii(_clean(department, 80)).text
    kind = kind if kind in ITEM_KINDS else "note"
    priority = priority if priority in PRIORITIES else "normal"
    body = redact_pii(_clean_text(text)).text[:TEXT_MAX]
    headline = redact_pii(_clean(title, 400)).text or _first_line(body) or "Nori item"
    headline = headline if len(headline) <= TITLE_MAX else headline[: TITLE_MAX - 1] + "…"

    existing = await item_for_ref(session, scope, ref)
    if existing is not None:
        task = await WorkspaceRepository(session, PiTask, scope).get(existing.task_id)
        return task, False

    tasks = WorkspaceRepository(session, PiTask, scope)
    try:
        async with session.begin_nested():
            task = await tasks.add(
                tasks.new(
                    title=headline,
                    description=body,
                    status="open",
                    priority=priority,
                    due_at=datetime.now(UTC) + SLA[priority],
                    created_by_user_id=created_by_user_id,
                    created_by_label=created_by_label[:80],
                    idempotency_key=f"{PREFIX}nori:{ref}"[:200],
                )
            )
            items = WorkspaceRepository(session, PiNoriItem, scope)
            await items.add(
                items.new(
                    task_id=task.id,
                    ref=ref,
                    item_kind=kind,
                    nori_workspace=_clean(workspace, 120),
                    person=_clean(person, 120),
                    department=_clean(department, 80),
                    phone_mask=mask_number(phone) if phone else "",
                    source=source,
                    url=(url or None),
                    forward_ref=forward_ref,
                )
            )
    except IntegrityError:
        # Two pushes of the same ref at once: the first one won, this one is the repeat.
        existing = await item_for_ref(session, scope, ref)
        if existing is None:
            raise
        task = await WorkspaceRepository(session, PiTask, scope).get(existing.task_id)
        return task, False

    who = " · ".join(x for x in (_clean(workspace, 120), _clean(person, 120)) if x)
    await notify(
        session,
        scope,
        "pi.nori.item",
        f"nori {KIND_LABEL[kind].lower()}: {headline}"[:160],
        who,
        link="/pi/team",
        permission="pi.work.read",
        dedupe_key=f"pi-nori-item:{ref}"[:200],
    )
    return task, True


def _clean_text(value: object) -> str:
    return "\n".join(" ".join(line.split()) for line in str(value or "").splitlines()).strip()


# ---- The card's nori facts for the board view --------------------------------------------------


async def meta_for(
    session: AsyncSession, scope: WorkspaceScope, task_ids: list[UUID]
) -> dict[UUID, dict[str, Any]]:
    """{task id: the facts the board shows on a nori card}."""
    if not task_ids:
        return {}
    rows = await session.scalars(
        WorkspaceRepository(session, PiNoriItem, scope)
        .select()
        .where(PiNoriItem.task_id.in_(task_ids))
    )
    return {
        row.task_id: {
            "item_kind": row.item_kind,
            "workspace": row.nori_workspace,
            "person": row.person,
            "department": row.department,
            "phone_mask": row.phone_mask,
            "source": row.source,
            "url": row.url,
            "conversation_id": row.conversation_id,
        }
        for row in rows
    }


def number_view(row: PiNoriNumber, *, full: bool) -> dict[str, Any]:
    return {
        "id": row.id,
        "phone": row.phone if full else mask_number(row.phone),
        "workspace": row.workspace,
        "person": row.person,
        "department": row.department,
        "active": row.active,
        "source": row.source,
        "created_at": row.created_at,
    }


async def link_conversation(
    session: AsyncSession, scope: WorkspaceScope, ref: str, conversation_id: UUID
) -> None:
    item = await item_for_ref(session, scope, ref)
    if item is not None and item.conversation_id is None:
        item.conversation_id = conversation_id
        await session.flush()


async def known_workspaces(session: AsyncSession, scope: WorkspaceScope) -> list[str]:
    """Nori workspace names already on the board (numbers and items), for the form's suggestions."""
    names = set(
        await session.scalars(
            WorkspaceRepository(session, PiNoriNumber, scope)
            .select()
            .with_only_columns(PiNoriNumber.workspace)
            .distinct()
        )
    )
    names.update(
        await session.scalars(
            select(PiNoriItem.nori_workspace)
            .where(
                PiNoriItem.tenant_id == scope.tenant_id,
                PiNoriItem.environment_id == scope.environment_id,
                PiNoriItem.nori_workspace != "",
            )
            .distinct()
        )
    )
    return sorted(n for n in names if n)[:200]
