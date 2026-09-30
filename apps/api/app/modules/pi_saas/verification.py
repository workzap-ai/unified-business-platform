"""Business review: the business sends its business details, the platform operator
approves it, asks for changes or declines. WhatsApp connects only after approval and
payment (see access_gate)."""

import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi_saas.models import PiBusinessAccount, PiBusinessVerification
from app.shared.errors import BusinessRuleViolation, InvalidTransition, ResourceNotFound
from app.shared.scope import WorkspaceScope

EDITABLE = ("not_started", "changes_requested")


class Details(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    legal_name: str = Field(default="", max_length=160)
    address: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=80)
    category: str = Field(default="", max_length=60)
    website: str = Field(default="", max_length=300)  # website or social page
    contact_phone: str = Field(default="", max_length=24)
    about: str = Field(default="", max_length=600)  # what the business sells, to whom

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        if value and not re.fullmatch(r"\+?[0-9 \-]{7,24}", value):
            raise ValueError("Enter a phone number with country code, e.g. +92 300 1234567")
        return value

    @field_validator("website")
    @classmethod
    def _website(cls, value: str) -> str:
        if value and not re.match(r"^(https?://)?[\w.-]+\.[a-z]{2,}", value, re.I):
            raise ValueError("Enter a website or page address")
        return value


REQUIRED_FIELDS = {
    "legal_name": "Business name",
    "address": "Business address",
    "city": "City",
    "contact_phone": "Contact phone",
    "about": "What you sell",
}


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "request_changes", "reject"]
    note: str = Field(default="", max_length=500)


async def for_tenant(
    session: AsyncSession, tenant_id: UUID, *, lock: bool = False
) -> PiBusinessVerification:
    query = select(PiBusinessVerification).where(PiBusinessVerification.tenant_id == tenant_id)
    row = await session.scalar(query.with_for_update() if lock else query)
    if row is None:
        row = PiBusinessVerification(tenant_id=tenant_id, status="not_started", details={})
        session.add(row)
        await session.flush()
    return row


def missing(row: PiBusinessVerification) -> list[str]:
    return [label for key, label in REQUIRED_FIELDS.items() if not row.details.get(key)]


def view(row: PiBusinessVerification) -> dict[str, Any]:
    return {
        "status": row.status,
        "details": {**Details().model_dump(), **(row.details or {})},
        "missing": missing(row),
        "editable": row.status in EDITABLE,
        "submitted_at": row.submitted_at,
        "decided_at": row.decided_at,
        "note": row.decision_note,
    }


async def save_details(
    session: AsyncSession, scope: WorkspaceScope, account: PiBusinessAccount, data: Details
) -> PiBusinessVerification:
    scope.require("pi.settings.manage")
    row = await for_tenant(session, account.tenant_id, lock=True)
    if row.status not in EDITABLE:
        raise BusinessRuleViolation(
            "REVIEW_LOCKED",
            "Your details are with the Pi team. You can edit them if they ask for changes.",
        )
    row.details = data.model_dump()
    return row


async def submit(
    session: AsyncSession, scope: WorkspaceScope, account: PiBusinessAccount
) -> PiBusinessVerification:
    scope.require("pi.settings.manage")
    row = await for_tenant(session, account.tenant_id, lock=True)
    if row.status not in EDITABLE:
        raise InvalidTransition("business review", row.status, "submitted")
    gaps = missing(row)
    if gaps:
        raise BusinessRuleViolation("DETAILS_MISSING", "Please add: " + ", ".join(gaps))
    row.status, row.submitted_at = "submitted", datetime.now(UTC)
    row.decision_note = ""
    await record(
        session,
        "pi_saas.review_submitted",
        tenant_id=account.tenant_id,
        actor_user_id=scope.user_id,
        entity_type="pi_business_verification",
        entity_id=row.id,
        include_environment=False,
    )
    from app.modules.pi_saas import lifecycle_notify

    await lifecycle_notify.review_changed(session, account, row)
    return row


TRANSITIONS = {
    "approve": ("approved", ("submitted", "changes_requested", "rejected")),
    "request_changes": ("changes_requested", ("submitted", "approved", "rejected")),
    "reject": ("rejected", ("submitted", "changes_requested")),
}


async def decide(
    session: AsyncSession, operator_user_id: UUID, tenant_id: UUID, data: Decision
) -> PiBusinessVerification:
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is None:
        raise ResourceNotFound
    row = await for_tenant(session, tenant_id, lock=True)
    target, allowed = TRANSITIONS[data.action]
    if row.status not in allowed:
        raise InvalidTransition("business review", row.status, target)
    if data.action != "approve" and len(data.note) < 5:
        raise BusinessRuleViolation("NOTE_REQUIRED", "Tell the business what to change or why")
    row.status, row.decision_note = target, data.note
    row.decided_at, row.decided_by_user_id = datetime.now(UTC), operator_user_id
    await record(
        session,
        f"pi_operator.review_{target}",
        tenant_id=tenant_id,
        actor_user_id=operator_user_id,
        entity_type="pi_business_verification",
        entity_id=row.id,
        details={"note": data.note[:200]},
        include_environment=False,
    )
    from app.modules.pi_saas import lifecycle_notify

    await lifecycle_notify.review_changed(session, account, row)
    return row


async def queue(
    session: AsyncSession, status: str | None, page: int, page_size: int, assigned: Any = None
) -> dict[str, Any]:
    query = select(PiBusinessVerification, PiBusinessAccount).join(
        PiBusinessAccount, PiBusinessAccount.tenant_id == PiBusinessVerification.tenant_id
    )
    if assigned is not None:
        query = query.where(PiBusinessVerification.tenant_id.in_(assigned))
    if status:
        query = query.where(PiBusinessVerification.status == status)
    else:
        query = query.where(PiBusinessVerification.status != "not_started")
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = await session.execute(
        query.order_by(
            (PiBusinessVerification.status != "submitted"),
            PiBusinessVerification.submitted_at.asc().nulls_last(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_query = select(PiBusinessVerification.status, func.count()).group_by(
        PiBusinessVerification.status
    )
    if assigned is not None:
        count_query = count_query.where(PiBusinessVerification.tenant_id.in_(assigned))
    counts = {str(k): int(v) for k, v in await session.execute(count_query)}
    return {
        "items": [
            {
                "tenant_id": account.tenant_id,
                "business": account.name,
                "country": account.country,
                **view(row),
            }
            for row, account in rows
        ],
        "total": total,
        "counts": counts,
        "page": page,
    }
