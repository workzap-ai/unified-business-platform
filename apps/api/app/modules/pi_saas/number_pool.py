"""The platform's WhatsApp number pool (Kapso).

Operators fill the pool with numbers the platform owns:
- **Provisioning link:** a new pre-verified US number from Kapso, bought on Kapso credits
  (partner billing).
- **Connect:** an existing number, using a permanent Meta System User token that goes
  straight to Kapso.

Businesses (in the Pi app) and Owner OS workspaces then **choose** an available number
themselves, or accept a number an operator offered them. Kapso can't move a number
between its customers, so every pool number stays under one platform customer and the
tenant mapping lives in ``pi_pool_numbers``. Messages route by phone_number_id, so this
is all a number needs.

Safety:
- A number is locked (``FOR UPDATE``) while it's being given out, so two businesses
  can't take the same one.
- A number is never re-bound silently (``link_number`` refuses a number mapped
  elsewhere).
- Numbers with blocking problems are never offered: Meta test / display-name-only
  numbers, RED quality, sandbox numbers.
- A released number is retired, not recycled, so a new owner can never receive the
  previous business's customers' replies.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.notifications.service import notify
from app.modules.pi.models import WhatsAppConnection
from app.modules.pi_saas.connections import (
    Target,
    connection_for,
    link_number,
    register_webhook,
)
from app.modules.pi_saas.kapso import Kapso, PhoneNumber
from app.modules.pi_saas.models import (
    PiPlatformState,
    PiPoolNumber,
    PiProviderConnection,
)
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope

POOL_KEY = "kapso_pool_customer"
BLOCKING = frozenset({"meta_test_number", "quality_red", "sandbox", "inbound_processing_off"})
# An operator may set a sandbox number aside for a workspace to test with.
BLOCKING_WHEN_OFFERED = BLOCKING - {"sandbox"}


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    phone_number_id: str = Field(pattern=r"^[0-9]{5,32}$")
    business_account_id: str = Field(pattern=r"^[0-9]{5,32}$")
    access_token: str = Field(min_length=40, max_length=600)
    country: str = Field(default="", pattern=r"^([A-Z]{2})?$")
    label: str = Field(default="", max_length=120)


class PoolUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    country: str | None = Field(default=None, pattern=r"^([A-Z]{2})?$")
    price_label: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=300)
    status: str | None = Field(default=None, pattern=r"^(available|retired)$")


def view(row: PiPoolNumber, *, operator: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "display_phone_number": row.display_phone_number,
        "country": row.country,
        "price_label": row.price_label,
        "coexistence": row.is_coexistence,
        "display_name_status": row.name_status,
        "held_until": row.held_until,
    }
    if operator:
        out.update(
            phone_number_id=row.phone_number_id,
            status=row.status,
            quality_rating=row.quality_rating,
            verified_name=row.verified_name,
            warnings=row.warnings,
            webhook_status=row.webhook_status,
            notes=row.notes,
            assigned_tenant_id=row.assigned_tenant_id,
            assigned_environment_id=row.assigned_environment_id,
            assigned_at=row.assigned_at,
            offered_at=row.offered_at,
            synced_at=row.synced_at,
        )
    return out


async def pool_customer(session: AsyncSession, settings: Settings, http: httpx.AsyncClient) -> str:
    """The Kapso customer that holds pool numbers (created once)."""
    state = await session.get(PiPlatformState, POOL_KEY, with_for_update=True)
    if state is not None and state.value.get("customer_id"):
        return str(state.value["customer_id"])
    customer_id = await Kapso(settings, http).create_customer(
        settings.kapso_pool_customer_name, "pi-number-pool"
    )
    if state is None:
        session.add(PiPlatformState(key=POOL_KEY, value={"customer_id": customer_id}))
    else:
        state.value = {**state.value, "customer_id": customer_id}
    await session.flush()
    return customer_id


def _apply(row: PiPoolNumber, number: PhoneNumber) -> None:
    row.display_phone_number = number.display_phone_number or row.display_phone_number
    row.business_account_id = number.business_account_id or row.business_account_id
    row.kapso_customer_id = number.customer_id or row.kapso_customer_id
    row.quality_rating = number.quality_rating
    row.name_status = number.name_status
    row.verified_name = number.verified_name
    row.is_coexistence = number.is_coexistence
    row.warnings = number.warnings
    row.synced_at = datetime.now(UTC)
    if not row.country and number.display_phone_number.startswith("+1"):
        row.country = "US"


async def inventory(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient
) -> dict[str, Any]:
    """Every number in the Kapso project, with where it's used here, and the pool
    brought up to date with Kapso (new pool numbers become available)."""
    pool_id = await pool_customer(session, settings, http)
    numbers = await Kapso(settings, http).list_numbers()
    mapped = {
        c.phone_number_id: c
        for c in await session.scalars(
            select(WhatsAppConnection).where(
                WhatsAppConnection.provider == "kapso",
                WhatsAppConnection.phone_number_id.in_(
                    [n.phone_number_id for n in numbers] or [""]
                ),
            )
        )
    }
    pool = {
        r.phone_number_id: r
        for r in await session.scalars(
            select(PiPoolNumber).where(
                PiPoolNumber.phone_number_id.in_([n.phone_number_id for n in numbers] or [""])
            )
        )
    }
    items = []
    for number in numbers:
        row = pool.get(number.phone_number_id)
        if row is None and number.customer_id == pool_id:
            row = PiPoolNumber(phone_number_id=number.phone_number_id, status="available")
            session.add(row)
        if row is not None:
            _apply(row, number)
        connection = mapped.get(number.phone_number_id)
        items.append(
            {
                "phone_number_id": number.phone_number_id,
                "display_phone_number": number.display_phone_number,
                "kapso_customer_id": number.customer_id,
                "in_pool": row is not None,
                "pool_id": row.id if row is not None else None,
                "pool_status": row.status if row is not None else None,
                "warnings": number.warnings
                + ([] if number.customer_id else ["no_customer"])
                + (
                    ["default_customer"]
                    if number.customer_id and number.customer_id != pool_id and connection is None
                    else []
                ),
                "quality_rating": number.quality_rating,
                "coexistence": number.is_coexistence,
                "display_name_status": number.name_status,
                "used_by": (
                    {"tenant_id": connection.tenant_id, "environment_id": connection.environment_id}
                    if connection is not None
                    else None
                ),
            }
        )
    await session.flush()
    return {"pool_customer_id": pool_id, "numbers": items}


async def available(session: AsyncSession, target: Target) -> list[PiPoolNumber]:
    """Numbers this business may take: free ones without blocking problems, plus any an
    operator offered to it."""
    rows = await session.scalars(
        select(PiPoolNumber)
        .where(
            ((PiPoolNumber.status == "available") & PiPoolNumber.assigned_tenant_id.is_(None))
            | (
                (PiPoolNumber.status == "reserved")
                & (PiPoolNumber.assigned_tenant_id == target.tenant_id)
                & (PiPoolNumber.assigned_environment_id == target.environment_id)
            )
        )
        .order_by(PiPoolNumber.country, PiPoolNumber.display_phone_number)
        .limit(100)
    )
    return [r for r in rows if not _blocking(r) & set(r.warnings or [])]


def _blocking(row: PiPoolNumber) -> frozenset[str]:
    """Operator offers may include a sandbox number; everything else must be ready."""
    return BLOCKING_WHEN_OFFERED if row.status == "reserved" and row.offered_at else BLOCKING


async def choose(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope | None,
    target: Target,
    pool_id: UUID,
) -> PiProviderConnection:
    """The business takes a pool number (its choice is its consent)."""
    if scope is not None:
        scope.require("pi.whatsapp.manage")
    row = await session.get(PiPoolNumber, pool_id, with_for_update=True)
    if row is None:
        raise ResourceNotFound
    mine = row.assigned_tenant_id == target.tenant_id and (
        row.assigned_environment_id == target.environment_id
    )
    if not (row.status == "available" and row.assigned_tenant_id is None) and not (
        row.status == "reserved" and mine
    ):
        raise Conflict("Someone just took this number. Please choose another.")
    if _blocking(row) & set(row.warnings or []):
        raise BusinessRuleViolation("NUMBER_NOT_READY", "This number isn't ready to use yet")
    provider_row = await connection_for(session, target)
    if provider_row.status == "connected":
        raise Conflict("This workspace already has a connected WhatsApp number")
    number = PhoneNumber(
        phone_number_id=row.phone_number_id,
        display_phone_number=row.display_phone_number,
        business_account_id=row.business_account_id,
        status="CONNECTED",
        display_name=row.verified_name,
        quality_rating=row.quality_rating,
        customer_id=row.kapso_customer_id,
        is_coexistence=row.is_coexistence,
        name_status=row.name_status,
        verified_name=row.verified_name,
    )
    provider_row.external_customer_id = provider_row.external_customer_id or row.kapso_customer_id
    await link_number(session, target, provider_row, number)
    if provider_row.status != "connected":
        raise Conflict("This number is already used elsewhere. Please choose another.")
    provider_row.connection_type = "coexistence" if row.is_coexistence else "dedicated"
    row.webhook_status = await register_webhook(settings, http, row.phone_number_id)
    row.status, row.assigned_at, row.held_until = "assigned", datetime.now(UTC), None
    row.assigned_tenant_id, row.assigned_environment_id = target.tenant_id, target.environment_id
    await record(
        session,
        "pi_saas.pool_number_assigned",
        tenant_id=target.tenant_id,
        environment_id=target.environment_id,
        actor_user_id=scope.user_id if scope is not None else None,
        entity_type="pi_pool_number",
        entity_id=row.id,
        details={"number": row.display_phone_number, "offered": row.offered_at is not None},
    )
    if target.account is not None:
        from app.modules.pi_saas.onboarding import refresh_state

        await refresh_state(session, scope, target.account)
    return provider_row


async def pick(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    target: Target,
    pool_id: UUID,
) -> dict[str, Any]:
    """A Pi business picks a number. It connects at once when the business may connect
    (approved and paid, or a free plan); otherwise the number is held for it and
    connects automatically once allowed (lifecycle_notify.check)."""
    from app.modules.pi_saas.access_gate import whatsapp_gate

    scope.require("pi.whatsapp.manage")
    gate = await whatsapp_gate(session, settings, target.tenant_id)
    if gate.ok:
        connection = await choose(session, settings, http, scope, target, pool_id)
        return {"state": "connected", "connection": connection, "gate": gate.view()}
    row = await session.get(PiPoolNumber, pool_id, with_for_update=True)
    if row is None:
        raise ResourceNotFound
    mine = row.assigned_tenant_id == target.tenant_id
    if not (row.status == "available" and row.assigned_tenant_id is None) and not (
        row.status == "reserved" and mine
    ):
        raise Conflict("Someone just took this number. Please choose another.")
    if _blocking(row) & set(row.warnings or []):
        raise BusinessRuleViolation("NUMBER_NOT_READY", "This number is not ready to use yet")
    # One held number per business: switching releases the previous hold.
    for other in await session.scalars(
        select(PiPoolNumber)
        .where(
            PiPoolNumber.status == "reserved",
            PiPoolNumber.assigned_tenant_id == target.tenant_id,
            PiPoolNumber.held_until.is_not(None),
            PiPoolNumber.id != row.id,
        )
        .with_for_update()
    ):
        other.held_until = None
        if other.offered_at is None:
            other.status = "available"
            other.assigned_tenant_id = other.assigned_environment_id = None
    row.status = "reserved"
    row.held_until = datetime.now(UTC) + timedelta(days=settings.pi_number_hold_days)
    row.assigned_tenant_id, row.assigned_environment_id = target.tenant_id, target.environment_id
    await record(
        session,
        "pi_saas.pool_number_held",
        tenant_id=target.tenant_id,
        environment_id=target.environment_id,
        actor_user_id=scope.user_id,
        entity_type="pi_pool_number",
        entity_id=row.id,
        details={"number": row.display_phone_number, "reason": gate.reason},
    )
    if target.account is not None:
        from app.modules.pi_saas import lifecycle_notify

        await lifecycle_notify.send(
            session,
            target.account,
            "whatsapp",
            "pi.number_held",
            f"{row.display_phone_number} is held for you",
            "It connects automatically once your business is approved and your plan is "
            f"paid. The hold lasts until {row.held_until:%d %b}. {gate.message}",
            link="/setup",
            dedupe=f"pi-number-held:{row.id}:{target.tenant_id}:{row.held_until.date()}",
        )
    await session.flush()
    return {"state": "held", "number": view(row), "gate": gate.view()}


async def release_hold(session: AsyncSession, scope: WorkspaceScope, target: Target) -> None:
    scope.require("pi.whatsapp.manage")
    for row in await session.scalars(
        select(PiPoolNumber)
        .where(
            PiPoolNumber.status == "reserved",
            PiPoolNumber.assigned_tenant_id == target.tenant_id,
            PiPoolNumber.held_until.is_not(None),
        )
        .with_for_update()
    ):
        row.held_until = None
        if row.offered_at is None:
            row.status = "available"
            row.assigned_tenant_id = row.assigned_environment_id = None


async def offer(
    session: AsyncSession, operator_user_id: UUID, pool_id: UUID, target: Target
) -> PiPoolNumber:
    """An operator sets a number aside for one business; the business accepts it."""
    row = await session.get(PiPoolNumber, pool_id, with_for_update=True)
    if row is None:
        raise ResourceNotFound
    if row.status != "available" or row.assigned_tenant_id is not None:
        raise Conflict("This number isn't available")
    if BLOCKING_WHEN_OFFERED & set(row.warnings or []):
        raise BusinessRuleViolation("NUMBER_NOT_READY", "Fix this number's problems first")
    row.status, row.offered_at = "reserved", datetime.now(UTC)
    row.assigned_tenant_id, row.assigned_environment_id = target.tenant_id, target.environment_id
    scope = WorkspaceScope.system(target.tenant_id, target.environment_id, frozenset(), "Pi team")
    await notify(
        session,
        scope,
        "pi.whatsapp_number_offered",
        "A WhatsApp number is ready for you",
        f"{row.display_phone_number} was set aside for you. Open WhatsApp settings to accept it.",
        link="/settings/whatsapp" if target.account is not None else "/pi/whatsapp",
        permission="pi.whatsapp.manage",
        dedupe_key=f"pi-number-offer:{row.id}:{target.tenant_id}",
    )
    await record(
        session,
        "pi_operator.pool_number_offered",
        tenant_id=target.tenant_id,
        actor_user_id=operator_user_id,
        entity_type="pi_pool_number",
        entity_id=row.id,
        details={"number": row.display_phone_number},
        include_environment=False,
    )
    return row


async def withdraw_offer(
    session: AsyncSession, operator_user_id: UUID, pool_id: UUID
) -> PiPoolNumber:
    row = await session.get(PiPoolNumber, pool_id, with_for_update=True)
    if row is None:
        raise ResourceNotFound
    if row.status == "reserved":
        row.status, row.offered_at, row.held_until = "available", None, None
        row.assigned_tenant_id = row.assigned_environment_id = None
    return row


async def connect_existing(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, data: ConnectInput
) -> PiPoolNumber:
    """Add a number the platform already owns to the pool (token goes only to Kapso)."""
    customer_id = await pool_customer(session, settings, http)
    number = await Kapso(settings, http).connect_number(
        customer_id,
        name=data.label or data.phone_number_id,
        phone_number_id=data.phone_number_id,
        business_account_id=data.business_account_id,
        access_token=data.access_token,
    )
    row = await session.scalar(
        select(PiPoolNumber).where(PiPoolNumber.phone_number_id == number.phone_number_id)
    )
    if row is None:
        row = PiPoolNumber(phone_number_id=number.phone_number_id, status="available")
        session.add(row)
    _apply(row, number)
    row.kapso_customer_id = row.kapso_customer_id or customer_id
    row.country = data.country or row.country
    await session.flush()
    return row


async def provisioning_link(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, country: str
) -> str:
    """A Kapso setup link that provisions a new pre-verified number into the pool."""
    customer_id = await pool_customer(session, settings, http)
    base = (settings.cors_origins[0] if settings.cors_origins else "").rstrip("/")
    link = await Kapso(settings, http).create_setup_link(
        customer_id,
        success_url=f"{base}/operator/numbers?added=1",
        failure_url=f"{base}/operator/numbers?failed=1",
        connection_types=("dedicated",),
        provision_country=country,
    )
    return link.url


async def update(session: AsyncSession, pool_id: UUID, data: PoolUpdate) -> PiPoolNumber:
    row = await session.get(PiPoolNumber, pool_id, with_for_update=True)
    if row is None:
        raise ResourceNotFound
    if data.status == "available" and row.status == "retired":
        raise BusinessRuleViolation(
            "NUMBER_RETIRED",
            "A retired number isn't reused, so earlier customers' replies can't reach a new "
            "business.",
        )
    if data.status == "retired" and row.status == "assigned":
        raise Conflict("Disconnect the business from this number first")
    for field in ("country", "price_label", "notes", "status"):
        value = getattr(data, field)
        if value is not None:
            setattr(row, field, value)
    return row


async def release_for(session: AsyncSession, provider_row: PiProviderConnection) -> None:
    """A business disconnected its pool number: retire it (never recycled)."""
    if not provider_row.phone_number_id:
        return
    row = await session.scalar(
        select(PiPoolNumber)
        .where(PiPoolNumber.phone_number_id == provider_row.phone_number_id)
        .with_for_update()
    )
    if row is not None and row.status == "assigned":
        row.status = "retired"
        row.notes = (row.notes + " Released by the business.").strip()[:300]
