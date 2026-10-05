"""Platform operator (Owner OS) management of Pi businesses.

Operators are Owner OS users with a ``pi_operator_members`` row. Their capabilities come
from a role preset (optionally adjusted) and cover *operations*: onboarding progress,
connections, plans, usage, health and failed work. Customer conversations are never
part of a role: reading them requires a support grant the business approved, which is
time-limited, revocable and audited on every use. Pi Agenta summaries use these same
functions, so they can never see more than the operator asking.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.auth.dependencies import Auth
from app.modules.pi.models import PiMessage, WhatsAppWebhookEvent
from app.modules.pi_saas.models import (
    PiBillingEvent,
    PiBusinessAccount,
    PiOperatorAssignment,
    PiOperatorMember,
    PiProviderConnection,
    PiProviderEvent,
    PiSubscription,
    PiSupportGrant,
)
from app.shared.errors import PermissionDenied, ResourceNotFound

CAPABILITIES = (
    "operator.accounts.read",
    "operator.accounts.all",  # see every business, not only assigned ones
    "operator.accounts.manage",  # pause/resume, prepare configuration under a grant
    "operator.onboarding.assist",
    "operator.support.request",
    "operator.numbers.manage",
    "operator.billing.read",
    "operator.billing.manage",
    "operator.plans.manage",
    "operator.health.read",
    "operator.jobs.replay",
    "operator.analytics.read",
    "operator.team.manage",
    "operator.workspaces.read",  # every Owner OS workspace, not only Pi businesses
    "operator.workspaces.manage",  # suspend / reactivate a workspace
    "operator.users.read",  # every platform user (no passwords, no content)
    "operator.users.manage",  # disable / re-enable accounts, sign them out
    "operator.audit.read",  # the audit log across all workspaces
    "operator.system.read",  # platform status and counts
    "operator.settings.manage",  # platform API keys, AI models, sign-up settings
)
ROLE_PRESETS: dict[str, tuple[str, str, frozenset[str]]] = {
    # The stored keys stay as they are (database check constraint); the names are what
    # people see: Super admin > Admin > the operator roles.
    "owner": (
        "Super admin",
        "Everything: workspaces, users, Pi businesses, operator team, plans and platform keys",
        frozenset(CAPABILITIES),
    ),
    "operations_admin": (
        "Admin",
        "Manages every workspace, user and Pi business; no operator team, plans or keys",
        frozenset(CAPABILITIES)
        - {"operator.team.manage", "operator.plans.manage", "operator.settings.manage"},
    ),
    "onboarding_specialist": (
        "Onboarding specialist",
        "Helps assigned businesses get set up",
        frozenset(
            {
                "operator.accounts.read",
                "operator.onboarding.assist",
                "operator.support.request",
                "operator.numbers.manage",
            }
        ),
    ),
    "support": (
        "Support",
        "Helps assigned businesses with problems",
        frozenset(
            {
                "operator.accounts.read",
                "operator.support.request",
                "operator.health.read",
                "operator.jobs.replay",
            }
        ),
    ),
    "billing": (
        "Billing",
        "Plans, invoices and payment issues",
        frozenset(
            {
                "operator.accounts.read",
                "operator.accounts.all",
                "operator.billing.read",
                "operator.billing.manage",
            }
        ),
    ),
    "analyst": (
        "Analyst",
        "Aggregate usage and outcomes, no customer content",
        frozenset(
            {
                "operator.accounts.read",
                "operator.accounts.all",
                "operator.analytics.read",
                "operator.workspaces.read",
                "operator.system.read",
            }
        ),
    ),
}

# Super admin > Admin > Operator: shown in the console and used to group the roles.
TIERS: dict[str, str] = {
    "owner": "super_admin",
    "operations_admin": "admin",
    "onboarding_specialist": "operator",
    "support": "operator",
    "billing": "operator",
    "analyst": "operator",
}
TIER_NAMES = {"super_admin": "Super admin", "admin": "Admin", "operator": "Operator"}


@dataclass(frozen=True)
class OperatorContext:
    user_id: UUID
    member_id: UUID
    role: str
    capabilities: frozenset[str]
    label: str

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def require(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise PermissionDenied


def capabilities_for(member: PiOperatorMember) -> frozenset[str]:
    caps = set(ROLE_PRESETS.get(member.role, ("", "", frozenset()))[2])
    for item in member.overrides:
        if item.startswith("-"):
            caps.discard(item[1:])
        elif item in CAPABILITIES:
            caps.add(item)
    return frozenset(caps)


async def operator_context(
    auth: Auth, session: Annotated[AsyncSession, Depends(get_session)]
) -> OperatorContext:
    """Owner OS session + active operator membership, re-checked on every request."""
    member = await session.scalar(
        select(PiOperatorMember).where(
            PiOperatorMember.user_id == auth.user.id, PiOperatorMember.status == "active"
        )
    )
    if member is None:
        raise PermissionDenied
    return OperatorContext(
        auth.user.id, member.id, member.role, capabilities_for(member), auth.user.display_name[:80]
    )


Operator = Annotated[OperatorContext, Depends(operator_context)]


def visible_tenants(operator: OperatorContext) -> Any:
    """SQL predicate source: every business, or only assigned ones."""
    if operator.can("operator.accounts.all"):
        return None
    return select(PiOperatorAssignment.tenant_id).where(
        PiOperatorAssignment.operator_id == operator.member_id
    )


async def account_for(
    session: AsyncSession, operator: OperatorContext, tenant_id: UUID
) -> PiBusinessAccount:
    operator.require("operator.accounts.read")
    query = select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    assigned = visible_tenants(operator)
    if assigned is not None:
        query = query.where(PiBusinessAccount.tenant_id.in_(assigned))
    account = await session.scalar(query)
    if account is None:
        raise ResourceNotFound  # Same answer for "missing" and "not yours".
    return account


async def active_grant(
    session: AsyncSession, operator: OperatorContext, tenant_id: UUID, scopes: set[str]
) -> PiSupportGrant | None:
    now = datetime.now(UTC)
    grant: PiSupportGrant | None = await session.scalar(
        select(PiSupportGrant)
        .where(
            PiSupportGrant.tenant_id == tenant_id,
            PiSupportGrant.status == "active",
            PiSupportGrant.scope.in_(scopes),
            (PiSupportGrant.operator_user_id == operator.user_id)
            | PiSupportGrant.operator_user_id.is_(None),
            (PiSupportGrant.expires_at.is_(None)) | (PiSupportGrant.expires_at > now),
        )
        .order_by(PiSupportGrant.created_at.desc())
        .limit(1)
    )
    return grant


async def expire_grants(session: AsyncSession) -> int:
    rows = list(
        await session.scalars(
            select(PiSupportGrant)
            .where(
                PiSupportGrant.status.in_(["active", "requested"]),
                PiSupportGrant.expires_at.is_not(None),
                PiSupportGrant.expires_at <= datetime.now(UTC),
            )
            .limit(500)
        )
    )
    for row in rows:
        row.status = "expired"
    return len(rows)


async def list_accounts(
    session: AsyncSession,
    operator: OperatorContext,
    *,
    search: str | None,
    state: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    operator.require("operator.accounts.read")
    query = select(PiBusinessAccount, PiSubscription).outerjoin(
        PiSubscription, PiSubscription.tenant_id == PiBusinessAccount.tenant_id
    )
    assigned = visible_tenants(operator)
    if assigned is not None:
        query = query.where(PiBusinessAccount.tenant_id.in_(assigned))
    if search:
        from app.shared.workspace_repository import like_pattern

        query = query.where(PiBusinessAccount.name.ilike(like_pattern(search)))
    if state:
        query = query.where(PiBusinessAccount.setup_state == state)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = await session.execute(
        query.order_by(PiBusinessAccount.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for account, subscription in rows:
        connection = await session.scalar(
            select(PiProviderConnection.status).where(
                PiProviderConnection.tenant_id == account.tenant_id,
                PiProviderConnection.environment_id == account.production_environment_id,
            )
        )
        items.append(
            {
                "tenant_id": account.tenant_id,
                "name": account.name,
                "setup_state": account.setup_state,
                "status": account.status,
                "onboarding_step": account.onboarding_step,
                "help_requested": account.help_requested_at is not None,
                "plan": subscription.plan_key if subscription else None,
                "subscription_status": subscription.status if subscription else None,
                "connection_status": connection or "draft",
                "created_at": account.created_at,
            }
        )
    return items, total


async def health(session: AsyncSession, operator: OperatorContext) -> dict[str, Any]:
    """Operational signals, aggregated over the businesses this operator may see."""
    operator.require("operator.health.read")
    since = datetime.now(UTC) - timedelta(hours=24)
    assigned = visible_tenants(operator)

    def scoped(column: Any, statement: Any) -> Any:
        return statement if assigned is None else statement.where(column.in_(assigned))

    failed_messages = await session.scalar(
        scoped(
            PiMessage.tenant_id,
            select(func.count())
            .select_from(PiMessage)
            .where(PiMessage.status == "failed", PiMessage.created_at >= since),
        )
    )
    failed_events = await session.scalar(
        scoped(
            WhatsAppWebhookEvent.tenant_id,
            select(func.count())
            .select_from(WhatsAppWebhookEvent)
            .where(WhatsAppWebhookEvent.status == "failed"),
        )
    )
    provider_failures = await session.scalar(
        scoped(
            PiProviderEvent.tenant_id,
            select(func.count())
            .select_from(PiProviderEvent)
            .where(PiProviderEvent.status == "failed"),
        )
    )
    billing_failures = await session.scalar(
        scoped(
            PiBillingEvent.tenant_id,
            select(func.count())
            .select_from(PiBillingEvent)
            .where(PiBillingEvent.status == "failed"),
        )
    )
    attention = await session.scalar(
        scoped(
            PiBusinessAccount.tenant_id,
            select(func.count())
            .select_from(PiBusinessAccount)
            .where(PiBusinessAccount.setup_state == "action_required"),
        )
    )
    past_due = await session.scalar(
        scoped(
            PiSubscription.tenant_id,
            select(func.count())
            .select_from(PiSubscription)
            .where(PiSubscription.status.in_(["past_due", "suspended"])),
        )
    )
    help_requests = await session.scalar(
        scoped(
            PiBusinessAccount.tenant_id,
            select(func.count())
            .select_from(PiBusinessAccount)
            .where(
                PiBusinessAccount.help_requested_at.is_not(None),
                PiBusinessAccount.setup_state.in_(["draft", "awaiting_connection"]),
            ),
        )
    )
    number_requests = await session.scalar(
        scoped(
            PiProviderConnection.tenant_id,
            select(func.count())
            .select_from(PiProviderConnection)
            .where(
                PiProviderConnection.number_request["status"].astext.in_(["requested", "confirmed"])
            ),
        )
    )
    return {
        "failed_messages_24h": int(failed_messages or 0),
        "failed_webhook_events": int(failed_events or 0),
        "failed_provider_events": int(provider_failures or 0),
        "failed_billing_events": int(billing_failures or 0),
        "accounts_action_required": int(attention or 0),
        "subscriptions_past_due": int(past_due or 0),
        "help_requests": int(help_requests or 0),
        "number_requests": int(number_requests or 0),
    }
