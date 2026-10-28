"""The Business Profile in the dashboard (platform spec v1.4, 16.3, "what I understood about your
business"): what pi understood about each business, where each fact came from, whether it is
confirmed, and the means to correct, confirm or delete a fact.

Reading needs `pi.memory.read` (it is what pi remembers about a customer); changing needs
`pi.settings.manage`. Everything is scoped to the workspace. A correction is the owner's own word:
it is stored with source "owner" and confirmed, and personal details are removed from it.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.pi import business_profile_store as store
from app.modules.pi.business_profile_models import PiBusinessProfile, PiPageSnapshot
from app.modules.pi.service import require_pi
from app.shared.errors import ResourceNotFound

router = APIRouter(prefix="/pi/business-profiles", tags=["pi-business-profile"])


class FactEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=300)


def fact_view(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "value": row.value,
        "source": row.source,
        "confirmed": row.confirmed,
        "confirmed_at": row.confirmed_at,
        "evidence": row.evidence_snippet,
        "url": row.source_url,
        "fetched_at": row.fetched_at,
        "updated_at": row.updated_at,
    }


async def profile_view(
    session: Any, scope: Any, profile: PiBusinessProfile, customer_name: str = ""
) -> dict[str, Any]:
    facts = await store.facts_of(session, scope, profile.id)
    snapshots = list(
        await session.scalars(
            select(PiPageSnapshot)
            .where(
                PiPageSnapshot.tenant_id == scope.tenant_id,
                PiPageSnapshot.environment_id == scope.environment_id,
                PiPageSnapshot.profile_id == profile.id,
            )
            .order_by(PiPageSnapshot.fetched_at.desc())
            .limit(3)
        )
    )
    return {
        "id": profile.id,
        "customer_id": profile.customer_id,
        "customer_name": customer_name,
        "business_id": profile.business_id,
        "display_name": profile.display_name,
        "what_they_do": profile.what_they_do,
        "city_area": profile.city_area,
        "since_year": profile.since_year,
        "size_band": profile.size_band,
        "channels": profile.channels,
        "website_url": profile.website_url,
        "social_urls": profile.social_urls,
        "digital_flags": profile.digital_flags,
        "language": profile.language,
        "updated_at": profile.updated_at,
        "facts": [fact_view(f) for f in facts],
        "snapshots": [
            {
                "url": s.url,
                "fetched_at": s.fetched_at,
                "content_hash": s.content_hash,
                "status": s.status,
            }
            for s in snapshots
        ],
    }


async def _profile(session: Any, scope: Any, profile_id: UUID) -> PiBusinessProfile:
    profile: PiBusinessProfile | None = await session.scalar(
        select(PiBusinessProfile).where(
            PiBusinessProfile.tenant_id == scope.tenant_id,
            PiBusinessProfile.environment_id == scope.environment_id,
            PiBusinessProfile.id == profile_id,
        )
    )
    if profile is None:
        raise ResourceNotFound
    return profile


@router.get("")
async def list_profiles(
    scope: Scope, session: Session, customer_id: UUID | None = None, limit: int = 50
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.memory.read")
    query = (
        select(PiBusinessProfile, Customer.name)
        .join(
            Customer,
            (Customer.tenant_id == PiBusinessProfile.tenant_id)
            & (Customer.environment_id == PiBusinessProfile.environment_id)
            & (Customer.id == PiBusinessProfile.customer_id),
        )
        .where(
            PiBusinessProfile.tenant_id == scope.tenant_id,
            PiBusinessProfile.environment_id == scope.environment_id,
        )
        .order_by(PiBusinessProfile.updated_at.desc())
        .limit(max(1, min(200, limit)))
    )
    if customer_id is not None:
        query = query.where(PiBusinessProfile.customer_id == customer_id)
    rows = (await session.execute(query)).all()
    return {"items": [await profile_view(session, scope, p, name) for p, name in rows]}


@router.get("/{profile_id}")
async def get_profile(profile_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.memory.read")
    profile = await _profile(session, scope, profile_id)
    name = await session.scalar(
        select(Customer.name).where(
            Customer.tenant_id == scope.tenant_id,
            Customer.environment_id == scope.environment_id,
            Customer.id == profile.customer_id,
        )
    )
    return await profile_view(session, scope, profile, name or "")


async def _audited(
    session: Any, scope: Any, action: str, profile_id: UUID, fact_id: UUID, key: str
) -> None:
    # the audit log names the fact's key, never its value (it may be the owner's own words)
    await record(
        session,
        action,
        scope=scope,
        entity_type="pi_profile_fact",
        entity_id=fact_id,
        details={"profile_id": str(profile_id), "key": key},
    )


@router.patch("/{profile_id}/facts/{fact_id}")
async def edit_fact(
    profile_id: UUID, fact_id: UUID, data: FactEdit, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    row = await store.edit_fact(session, scope, profile_id, fact_id, data.value)
    await _audited(session, scope, "pi.profile_fact_edited", profile_id, fact_id, row.key)
    await session.commit()
    await session.refresh(row)
    return fact_view(row)


@router.post("/{profile_id}/facts/{fact_id}/confirm")
async def confirm_fact(
    profile_id: UUID, fact_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    row = await store.confirm_fact(session, scope, profile_id, fact_id)
    await _audited(session, scope, "pi.profile_fact_confirmed", profile_id, fact_id, row.key)
    await session.commit()
    await session.refresh(row)
    return fact_view(row)


@router.delete("/{profile_id}/facts/{fact_id}")
async def delete_fact(
    profile_id: UUID, fact_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    row = await store.get_fact(session, scope, profile_id, fact_id)
    key = row.key
    await store.delete_fact(session, scope, profile_id, fact_id)
    await _audited(session, scope, "pi.profile_fact_deleted", profile_id, fact_id, key)
    await session.commit()
    return {"deleted": True}
