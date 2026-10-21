"""Duplicate customers: find the likely same person, and merge two records into one.

A WhatsApp customer ("Mukarram Hazari", phone) and one a team member typed in by hand
("Mukkaram", company "Hazari Impex") are the same person in two records. Merging moves
everything that belongs to the duplicate (chats, deals, proposals, orders, invoices,
notes, files, memories...) to the kept customer, fills the kept customer's blank fields
from the duplicate, and deletes the duplicate. All or nothing: if anything can't move,
nothing changes.
"""

import difflib
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.modules.access.dependencies import Session, require
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.customers.schemas import CustomerView
from app.modules.customers.service import log_activity
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/customers", tags=["customers"])
Read = Annotated[WorkspaceScope, Depends(require("customers.read"))]
Write = Annotated[WorkspaceScope, Depends(require("customers.write"))]

FILLABLE = ("email", "phone", "whatsapp_id", "company")
PLACEHOLDER = re.compile(r"^(whatsapp|customer|unknown)\b|^\+?\d[\d ]+$", re.I)


def _tokens(value: str | None) -> list[str]:
    return [t for t in re.split(r"[^\w]+", (value or "").casefold()) if len(t) > 1]


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[-10:]


def likeness(a: Customer, b: Customer) -> str | None:
    """Why two customers look like the same person, or None."""
    if a.phone and b.phone and _digits(a.phone) == _digits(b.phone):
        return "Same phone number"
    if a.email and b.email and a.email.strip().casefold() == b.email.strip().casefold():
        return "Same email"
    names_a, names_b = _tokens(a.name), _tokens(b.name)
    if not names_a or not names_b:
        return None
    whole = difflib.SequenceMatcher(None, " ".join(names_a), " ".join(names_b)).ratio()
    first = difflib.SequenceMatcher(None, names_a[0], names_b[0]).ratio()
    words_a = set(names_a) | set(_tokens(a.company))
    words_b = set(names_b) | set(_tokens(b.company))
    shared = (words_a & words_b) - {names_a[0], names_b[0]}
    if whole >= 0.85 or (
        first >= 0.8 and len(names_a[0]) >= 4 and (shared or min(len(names_a), len(names_b)) == 1)
    ):
        return "Similar name" + (f" ({', '.join(sorted(shared))})" if shared else "")
    return None


async def duplicates_of(
    session: AsyncSession, scope: WorkspaceScope, customer: Customer, limit: int = 5
) -> list[tuple[Customer, str]]:
    repo = WorkspaceRepository(session, Customer, scope)
    others = await session.scalars(
        repo.select()
        .where(Customer.id != customer.id)
        .order_by(Customer.created_at.desc())
        .limit(3000)
    )
    found = [(other, why) for other in others if (why := likeness(customer, other))]
    return found[:limit]


def _customer_columns() -> list[tuple[str, bool]]:
    """Every (table, has_workspace_columns) with a customer_id column, except customers."""
    tables = []
    for table in Base.metadata.sorted_tables:
        if table.name == Customer.__tablename__ or "customer_id" not in table.c:
            continue
        tables.append((table.name, "tenant_id" in table.c and "environment_id" in table.c))
    return tables


async def merge(
    session: AsyncSession, scope: WorkspaceScope, keep_id: UUID, drop_id: UUID
) -> tuple[Customer, dict[str, int]]:
    """Move everything of ``drop_id`` to ``keep_id`` and delete ``drop_id``."""
    scope.require("customers.write")
    if keep_id == drop_id:
        raise BusinessRuleViolation("SAME_CUSTOMER", "Pick two different customers")
    repo = WorkspaceRepository(session, Customer, scope)
    keep = await repo.get(keep_id, for_update=True)
    drop = await repo.get(drop_id, for_update=True)
    moved: dict[str, int] = {}
    where = "customer_id = :drop"
    params: dict[str, Any] = {"keep": keep.id, "drop": drop.id}
    params |= {"tenant": scope.tenant_id, "environment": scope.environment_id}
    try:
        async with session.begin_nested():
            for name, scoped in _customer_columns():
                condition = where + (
                    " AND tenant_id = :tenant AND environment_id = :environment" if scoped else ""
                )
                result = await session.execute(
                    text(f'UPDATE "{name}" SET customer_id = :keep WHERE {condition}'),  # noqa: S608
                    params,
                )
                if result.rowcount:  # type: ignore[attr-defined]
                    moved[name] = int(result.rowcount)  # type: ignore[attr-defined]
            # The kept record gets what only the duplicate knew (company, email...).
            taken = {
                f: getattr(drop, f) for f in FILLABLE if getattr(drop, f) and not getattr(keep, f)
            }
            if (
                PLACEHOLDER.search(keep.name or "")
                and drop.name
                and not PLACEHOLDER.search(drop.name)
            ):
                keep.name = drop.name
            keep.tags = sorted(set(keep.tags or []) | set(drop.tags or []))
            if drop.last_contacted_at and (
                not keep.last_contacted_at or drop.last_contacted_at > keep.last_contacted_at
            ):
                keep.last_contacted_at = drop.last_contacted_at
            for field in ("phone", "whatsapp_id"):
                setattr(drop, field, None)  # frees unique phone / WhatsApp id for the kept one
            await session.flush()
            for field, value in taken.items():
                setattr(keep, field, value)
            await session.delete(drop)
            await session.flush()
    except IntegrityError as error:
        raise BusinessRuleViolation(
            "MERGE_CONFLICT",
            "These two customers can't be merged automatically (both have a record that "
            "must be unique). Nothing was changed.",
            409,
        ) from error
    await log_activity(
        session,
        scope,
        keep.id,
        "merged",
        f"Merged with {drop.name}" + (f" ({drop.company})" if drop.company else ""),
        "customer",
    )
    await record(
        session,
        "customer.merged",
        scope=scope,
        entity_type="customer",
        entity_id=keep.id,
        details={"merged_id": str(drop_id), "moved": moved},
    )
    return keep, moved


class DuplicateView(BaseModel):
    customer: CustomerView
    reason: str


class MergeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duplicate_id: UUID


@router.get("/{customer_id}/duplicates", response_model=list[DuplicateView])
async def duplicates(customer_id: UUID, scope: Read, session: Session) -> list[DuplicateView]:
    customer = await WorkspaceRepository(session, Customer, scope).get(customer_id)
    return [
        DuplicateView(customer=CustomerView.model_validate(other), reason=why)
        for other, why in await duplicates_of(session, scope, customer)
    ]


@router.post("/{customer_id}/merge", response_model=CustomerView)
async def merge_customer(
    customer_id: UUID, data: MergeInput, scope: Write, session: Session
) -> CustomerView:
    """Keep this customer; move everything of ``duplicate_id`` into it and delete it."""
    keep, _ = await merge(session, scope, customer_id, data.duplicate_id)
    await session.commit()
    return CustomerView.model_validate(keep)


__all__ = ["duplicates_of", "likeness", "merge", "router"]
