"""Weekly summaries in the Pi app (/pi-app/digests) and the operator console."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.policy import zone
from app.modules.pi.service import require_pi
from app.modules.pi_saas import digests
from app.modules.pi_saas.models import PiBusinessAccount, PiDigest
from app.modules.pi_saas.operator import Operator
from app.shared.errors import ResourceNotFound
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/digests", tags=["pi-digests"])
operator_router = APIRouter(prefix="/operator/pi", tags=["pi-operator"])


async def _account(session: Any, scope: Any) -> PiBusinessAccount:
    row: PiBusinessAccount | None = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == scope.tenant_id)
    )
    if row is None:
        raise ResourceNotFound
    return row


@router.get("")
async def list_digests(scope: Scope, session: Session) -> list[dict[str, Any]]:
    """Past weekly summaries (business-wide numbers, so analytics access is needed)."""
    await require_pi(session, scope, "pi.analytics.read")
    account = await _account(session, scope)
    rows = await session.scalars(
        WorkspaceRepository(session, PiDigest, scope)
        .select()
        .order_by(PiDigest.period_start.desc())
        .limit(12)
    )
    return [
        {**digests.view(r), "text": digests.digest_text(account.name, r.period_start, r.metrics)}
        for r in rows
    ]


@router.get("/this-week")
async def this_week(scope: Scope, session: Session) -> dict[str, Any]:
    """The current week so far (Monday 00:00 local until now)."""
    await require_pi(session, scope, "pi.analytics.read")
    account = await _account(session, scope)
    local = datetime.now(UTC).astimezone(zone(account.timezone or "UTC"))
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    metrics = await digests.business_metrics(
        session, scope, monday.astimezone(UTC), datetime.now(UTC)
    )
    return {"since": monday.date(), "metrics": metrics}


class DigestSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: bool


@router.get("/settings")
async def digest_settings(scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.read")
    account = await _account(session, scope)
    return {"email": account.digest_email}


@router.put("/settings")
async def set_digest_settings(
    data: DigestSettings, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    account = await _account(session, scope)
    account.digest_email = data.email
    await record(
        session,
        "pi_saas.digest_settings_updated",
        scope=scope,
        entity_type="pi_business_account",
        entity_id=account.id,
        details={"email": data.email},
    )
    await session.commit()
    return {"email": account.digest_email}


@operator_router.get("/weekly")
async def operator_weekly(operator: Operator, session: Session) -> dict[str, Any]:
    """The operator's weekly summary: the same scoped facts as the console and Agenta."""
    operator.require("operator.accounts.read")
    return await digests.operator_week(session, operator)
