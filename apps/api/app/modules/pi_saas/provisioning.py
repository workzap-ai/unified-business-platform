"""Behind-the-scenes provisioning of a Pi business.

One business = one new tenant, even when the owner already has other businesses or
workspaces: businesses, customers and memories are never merged by owner or phone number.
The tenant gets a production and a test environment, PI installed and enabled in both
with automatic replies OFF until launch, and a trial subscription on the configured plan.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.access.permissions import ALL
from app.modules.audit.service import record
from app.modules.business_settings.models import BusinessSettings
from app.modules.environments.models import Environment
from app.modules.pi.configuration import settings_row
from app.modules.pi_saas.models import PiBusinessAccount, PiPlan, PiSubscription
from app.modules.products.service import ProductService, sync_products
from app.modules.tenants.onboarding import provision_tenant
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

BUSINESS_TYPES = {
    "services": "service_business",
    "products": "product_business",
    "both": "hybrid_business",
}


async def provision_business(
    session: AsyncSession,
    settings: Settings,
    owner: PlatformUser,
    name: str,
    *,
    offer_type: str = "services",
    request_id: str | None = None,
) -> PiBusinessAccount:
    """Runs inside the caller's transaction; the caller commits."""
    plan = await session.scalar(
        select(PiPlan).where(PiPlan.key == settings.pi_trial_plan, PiPlan.status == "available")
    )
    if plan is None:
        raise BusinessRuleViolation(
            "PLAN_UNAVAILABLE", "Sign-up is temporarily unavailable. Please try again later.", 503
        )
    tenant, production, membership = await provision_tenant(session, owner, name)
    test = Environment(
        tenant_id=tenant.id, key="test", name="Test", kind="staging", is_default=False
    )
    session.add(test)
    await session.flush()
    business_type = BUSINESS_TYPES.get(offer_type, "service_business")
    for environment in (production, test):
        session.add(
            BusinessSettings(
                tenant_id=tenant.id, environment_id=environment.id, business_type=business_type
            )
        )
    await sync_products(session)
    for environment in (production, test):
        scope = WorkspaceScope(
            tenant_id=tenant.id,
            environment_id=environment.id,
            permissions=ALL,
            user_id=owner.id,
            membership_id=membership.id,
            actor_label=owner.display_name[:80],
            request_id=request_id,
        )
        await ProductService(session, scope).install("pi")
        policy = await settings_row(session, scope)
        policy.auto_reply_enabled = False  # Enabled only by an explicit launch.
        # Follow-ups stay off until the business enables them (consent is still required).
        policy.whatsapp_config = {**policy.whatsapp_config, "reminder_enabled": False}
        policy.response_rules = {**policy.response_rules, "execution_mode": "human_approved"}
    account = PiBusinessAccount(
        tenant_id=tenant.id,
        name=name,
        offer_type=offer_type if offer_type in BUSINESS_TYPES else "services",
        production_environment_id=production.id,
        test_environment_id=test.id,
        created_by_user_id=owner.id,
    )
    session.add(account)
    session.add(
        PiSubscription(
            tenant_id=tenant.id,
            plan_key=plan.key,
            status="trialing",
            trial_ends_at=datetime.now(UTC) + timedelta(days=plan.trial_days),
            currency=plan.currency,
        )
    )
    await session.flush()
    await record(
        session,
        "pi_saas.business_provisioned",
        tenant_id=tenant.id,
        environment_id=production.id,
        actor_user_id=owner.id,
        entity_type="pi_business_account",
        entity_id=account.id,
        details={"plan": plan.key, "trial_days": plan.trial_days},
        request_id=request_id,
    )
    return account
