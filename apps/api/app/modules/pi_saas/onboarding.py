"""Resumable five-step onboarding, readiness and launch for a Pi business.

Steps: 1 business, 2 offer, 3 WhatsApp, 4 how Pi should help, 5 try and launch. Each
step saves immediately (drafts are never lost) and the wizard can be resumed. Going live
requires a connected number, published knowledge or offerings, chosen behaviour and an
entitled plan. Setup state is derived from facts, never set optimistically.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.business_settings.models import BusinessSettings
from app.modules.catalog.models import CatalogProduct
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import KnowledgeDocument, KnowledgeSource, PiSettings, WhatsAppConnection
from app.modules.pi.tools.catalog import TOOL_CATALOG
from app.modules.pi_saas.entitlement import entitlement
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiKnowledgeDraft,
    PiProviderConnection,
)
from app.modules.pi_saas.provisioning import BUSINESS_TYPES
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope

GOALS = (
    "answer_questions",
    "capture_leads",
    "book_appointments",
    "take_orders",
    "order_status",
    "quotes",
    "payments",
    "support",
    "follow_ups",
)
# Plain-language tool groups shown to customers -> controlled PI tools.
TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "knowledge": ("search_knowledge_base", "get_company_information"),
    "customers": ("search_customer", "get_customer", "search_customer_memory"),
    "catalog_orders": (
        "search_products",
        "get_product",
        "check_inventory",
        "create_order_draft",
        "calculate_order_total",
        "create_order",
        "get_order",
        "get_customer_orders",
        # Shopify order status; reports `connected: false` until a store is connected.
        "get_store_orders",
    ),
    "quotes": ("create_quote_draft",),
    "billing_status": ("get_customer_balance", "get_invoice"),
    "bookings": (
        "check_availability",
        "create_booking",
        "cancel_booking",
        "get_bookings",
        "reschedule_booking",
        "email_booking_confirmation",
    ),
    "tasks": ("create_task", "get_project_status"),
    "tickets": ("create_ticket",),
    "payments": ("request_payment", "get_payment_status"),
    # WhatsApp Flows the business published (lead details, booking request, feedback).
    "forms": ("send_form",),
}
ALWAYS_ON = ("create_handoff", "send_whatsapp_message", "ask_owner")
LANGUAGE = r"^(auto|roman_ur|[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?)$"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BusinessStep(Input):
    name: str = Field(min_length=1, max_length=160)
    business_category: str = Field(default="", max_length=60)
    language: str = Field(default="en", pattern=LANGUAGE)
    timezone: str = Field(default="UTC", max_length=64)
    country: str = Field(default="", pattern=r"^([A-Z]{2})?$")
    website: HttpUrl | None = None
    description: str = Field(default="", max_length=2000)
    # Currency for the business's own invoices and payment requests ("" keeps it).
    currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        from app.modules.pi.policy import zone

        try:
            zone(value)
        except Exception:
            raise ValueError("Choose a valid timezone") from None
        return value


class OfferingItem(Input):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    # Optional approved price. Only an explicitly entered price becomes a catalog price.
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class OfferStep(Input):
    offer_type: Literal["services", "products", "both"]
    offerings: list[OfferingItem] = Field(default_factory=list, max_length=20)


class WhatsAppStep(Input):
    choice: Literal["existing", "new"]


class HelpStep(Input):
    goals: list[str] = Field(default_factory=list, max_length=len(GOALS))
    automation_mode: Literal["human_approved", "mixed", "ai_led"] = "human_approved"
    price_disclosure: Literal["exact", "starting", "quote", "ask_team", "hidden"] = "quote"
    tools: list[str] = Field(default_factory=list, max_length=len(TOOL_GROUPS))

    @field_validator("goals")
    @classmethod
    def known_goals(cls, value: list[str]) -> list[str]:
        if set(value) - set(GOALS):
            raise ValueError("Unknown goal")
        return sorted(set(value))

    @field_validator("tools")
    @classmethod
    def known_tools(cls, value: list[str]) -> list[str]:
        if set(value) - set(TOOL_GROUPS):
            raise ValueError("Unknown tool")
        return sorted(set(value))


async def current_account(session: AsyncSession, tenant_id: UUID) -> PiBusinessAccount:
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is None:
        raise ResourceNotFound
    return account


def env_scope(
    account: PiBusinessAccount, scope: WorkspaceScope, environment: str = "production"
) -> WorkspaceScope:
    """The same actor and permissions, pointed at one of this business's environments."""
    environment_id = (
        account.test_environment_id if environment == "test" else account.production_environment_id
    )
    return WorkspaceScope(
        tenant_id=account.tenant_id,
        environment_id=environment_id,
        permissions=scope.permissions,
        user_id=scope.user_id,
        membership_id=scope.membership_id,
        actor_type=scope.actor_type,
        actor_label=scope.actor_label,
        request_id=scope.request_id,
    )


async def _policies(
    session: AsyncSession, account: PiBusinessAccount, scope: WorkspaceScope
) -> list[PiSettings]:
    return [
        await settings_row(session, env_scope(account, scope, env))
        for env in ("production", "test")
    ]


async def save_step(
    session: AsyncSession,
    scope: WorkspaceScope,
    account: PiBusinessAccount,
    step: int,
    data: BaseModel,
) -> None:
    scope.require("pi.settings.manage")
    done = dict(account.onboarding_data.get("done", {}))
    if isinstance(data, BusinessStep):
        account.name = data.name
        account.business_category = data.business_category
        account.language = data.language
        account.timezone = data.timezone
        account.country = data.country
        account.website = str(data.website) if data.website else ""
        account.description = data.description
        await session.execute(
            update(Tenant).where(Tenant.id == account.tenant_id).values(name=data.name)
        )
        if data.currency:
            await session.execute(
                update(BusinessSettings)
                .where(BusinessSettings.tenant_id == account.tenant_id)
                .values(default_currency=data.currency)
            )
        for policy in await _policies(session, account, scope):
            policy.timezone = data.timezone
            summary = data.language if len(data.language) in (2, 3) else "en"
            policy.response_rules = {**policy.response_rules, "staff_summary_language": summary}
    elif isinstance(data, OfferStep):
        account.offer_type = data.offer_type
        await session.execute(
            update(BusinessSettings)
            .where(BusinessSettings.tenant_id == account.tenant_id)
            .values(business_type=BUSINESS_TYPES[data.offer_type])
        )
        await _save_offerings(session, scope, account, data)
    elif isinstance(data, WhatsAppStep):
        account.onboarding_data = {**account.onboarding_data, "whatsapp_choice": data.choice}
    elif isinstance(data, HelpStep):
        account.goals = data.goals
        account.automation_mode = data.automation_mode
        enabled = {tool for group in data.tools for tool in TOOL_GROUPS[group]} | set(ALWAYS_ON)
        for policy in await _policies(session, account, scope):
            policy.response_rules = {
                **policy.response_rules,
                "execution_mode": data.automation_mode,
                "price_disclosure": data.price_disclosure,
            }
            policy.tool_permissions = {
                name: name in enabled or name in ALWAYS_ON for name in TOOL_CATALOG
            }
            policy.whatsapp_config = {
                **policy.whatsapp_config,
                "reminder_enabled": "follow_ups" in data.goals,
            }
        account.onboarding_data = {
            **account.onboarding_data,
            "tools": data.tools,
            "price_disclosure": data.price_disclosure,
        }
    else:  # pragma: no cover - guarded by the route
        raise BusinessRuleViolation("INVALID_STEP", "Unknown onboarding step")
    done[str(step)] = True
    account.onboarding_data = {**account.onboarding_data, "done": done}
    account.onboarding_step = max(account.onboarding_step, min(step + 1, 5))
    await record(
        session,
        "pi_saas.onboarding_step_saved",
        scope=scope,
        entity_type="pi_business_account",
        entity_id=account.id,
        details={"step": step},
    )
    await refresh_state(session, scope, account)


async def _save_offerings(
    session: AsyncSession, scope: WorkspaceScope, account: PiBusinessAccount, data: OfferStep
) -> None:
    """Offerings become a knowledge draft for review; explicitly priced products also
    become catalog items (the catalog is the source of truth for prices)."""
    if not data.offerings:
        return
    production = env_scope(account, scope)
    lines = []
    for item in data.offerings:
        line = f"- {item.name}"
        if item.description:
            line += f": {item.description}"
        lines.append(line)
    draft = PiKnowledgeDraft(
        tenant_id=account.tenant_id,
        environment_id=account.production_environment_id,
        origin="owner_text",
        title="What we offer",
        content="\n".join(lines),
        source_text="\n".join(lines),
        created_by_user_id=scope.user_id,
    )
    session.add(draft)
    priced = [i for i in data.offerings if i.price is not None and data.offer_type != "services"]
    if priced and production.can("catalog.write"):
        from app.modules.catalog.schemas import ProductCreate, VariantCreate
        from app.modules.catalog.service import CatalogService

        catalog = CatalogService(session, production)
        for index, item in enumerate(priced, start=1):
            await catalog.create_product(
                ProductCreate(
                    offering_type="product",
                    name=item.name,
                    description=item.description,
                    pi_visible=True,
                    variants=[
                        VariantCreate(
                            sku=f"PI-{datetime.now(UTC):%y%m%d%H%M%S}-{index}",
                            name="Standard",
                            price=item.price or Decimal(0),
                            currency=item.currency,
                        )
                    ],
                )
            )
    await session.flush()


async def readiness(session: AsyncSession, account: PiBusinessAccount) -> list[dict[str, Any]]:
    """Go-live checklist, computed from stored facts for the production environment."""
    done = account.onboarding_data.get("done", {})
    env = account.production_environment_id
    documents = await session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .join(
            KnowledgeSource,
            (KnowledgeSource.id == KnowledgeDocument.source_id)
            & (KnowledgeSource.tenant_id == KnowledgeDocument.tenant_id),
        )
        .where(
            KnowledgeDocument.tenant_id == account.tenant_id,
            KnowledgeDocument.environment_id == env,
            KnowledgeDocument.status == "ready",
            KnowledgeSource.status == "active",
        )
    )
    offerings = await session.scalar(
        select(func.count())
        .select_from(CatalogProduct)
        .where(
            CatalogProduct.tenant_id == account.tenant_id,
            CatalogProduct.environment_id == env,
            CatalogProduct.pi_visible.is_(True),
            CatalogProduct.status == "active",
        )
    )
    connection = await production_connection(session, account)
    plan = await entitlement(session, account.tenant_id, env)
    return [
        {"key": "business", "label": "Business details", "done": bool(done.get("1"))},
        {
            "key": "knowledge",
            "label": "Published business information",
            "done": bool(documents or offerings),
        },
        {
            "key": "whatsapp",
            "label": "WhatsApp number connected",
            "done": connection is not None and connection.status == "connected",
        },
        {"key": "behaviour", "label": "How pi should help", "done": bool(done.get("4"))},
        {"key": "plan", "label": "Active plan", "done": plan.sending, "reason": plan.reason},
    ]


async def production_connection(
    session: AsyncSession, account: PiBusinessAccount
) -> PiProviderConnection | None:
    row: PiProviderConnection | None = await session.scalar(
        select(PiProviderConnection)
        .where(
            PiProviderConnection.tenant_id == account.tenant_id,
            PiProviderConnection.environment_id == account.production_environment_id,
        )
        .order_by(PiProviderConnection.created_at.desc())
        .limit(1)
    )
    return row


async def refresh_state(
    session: AsyncSession, scope: WorkspaceScope | None, account: PiBusinessAccount
) -> str:
    items = {i["key"]: i for i in await readiness(session, account)}
    connection = await production_connection(session, account)
    previous = account.setup_state
    if previous in {"active", "paused", "action_required"} and account.launched_at is not None:
        healthy = items["whatsapp"]["done"] and items["plan"]["done"]
        if not healthy:
            state = "action_required"
        elif previous == "action_required":
            state = "paused"  # Resolved problems never silently restart automation.
        else:
            state = previous
    elif not items["business"]["done"] or not items["behaviour"]["done"]:
        state = "draft"
    elif not items["whatsapp"]["done"]:
        state = (
            "pending_approval"
            if connection is not None and connection.status == "setup_pending"
            else "awaiting_connection"
        )
    elif all(i["done"] for i in items.values()):
        state = "ready"
    else:
        # Not launched yet: missing knowledge or plan is part of setup, not a problem.
        state = "draft"
    if state != previous:
        account.setup_state = state
        if state in {"action_required", "paused"}:
            await _set_auto_reply(session, account, False)
        await record(
            session,
            "pi_saas.setup_state_changed",
            scope=scope,
            tenant_id=account.tenant_id if scope is None else None,
            entity_type="pi_business_account",
            entity_id=account.id,
            details={"from": previous, "to": state},
        )
    return state


async def _set_auto_reply(session: AsyncSession, account: PiBusinessAccount, enabled: bool) -> None:
    await session.execute(
        update(PiSettings)
        .where(
            PiSettings.tenant_id == account.tenant_id,
            PiSettings.environment_id == account.production_environment_id,
        )
        .values(auto_reply_enabled=enabled)
    )


async def launch(session: AsyncSession, scope: WorkspaceScope, account: PiBusinessAccount) -> None:
    """Explicit go-live (and resume). Every readiness item must hold right now."""
    scope.require("pi.settings.manage")
    items = await readiness(session, account)
    missing = [i["label"] for i in items if not i["done"]]
    if missing:
        raise BusinessRuleViolation("NOT_READY", "Finish these first: " + ", ".join(missing), 409)
    active = await session.scalar(
        select(WhatsAppConnection.id).where(
            WhatsAppConnection.tenant_id == account.tenant_id,
            WhatsAppConnection.environment_id == account.production_environment_id,
            WhatsAppConnection.status == "active",
        )
    )
    if active is None:
        raise BusinessRuleViolation(
            "NOT_READY", "Finish these first: WhatsApp number connected", 409
        )
    await _set_auto_reply(session, account, True)
    account.setup_state = "active"
    account.launched_at = account.launched_at or datetime.now(UTC)
    account.paused_reason = None
    await record(
        session,
        "pi_saas.launched",
        scope=scope,
        entity_type="pi_business_account",
        entity_id=account.id,
    )


async def pause(
    session: AsyncSession, scope: WorkspaceScope, account: PiBusinessAccount, reason: str
) -> None:
    scope.require("pi.settings.manage")
    await _set_auto_reply(session, account, False)
    if account.launched_at is not None:
        account.setup_state = "paused"
    account.paused_reason = reason[:200] or None
    await record(
        session,
        "pi_saas.paused",
        scope=scope,
        entity_type="pi_business_account",
        entity_id=account.id,
        details={"reason": reason[:200]},
    )
