"""A Pi business's journey, told to the business at every step: welcome, business
review (received, approved, changes, declined), payment received, trial ending, number
held / connected / hold expired.

- In-app notifications always; email too unless the owner turned that category off
  (``PiBusinessAccount.notification_prefs``). Email goes through the workspace's email
  integration or the platform SMTP, as an integration operation the sweep delivers.
- ``check`` compares the current facts with the last ones notified
  (``lifecycle_state``), so it reacts to real changes whichever code path made them
  (Stripe webhook, bank/cash verification, operator override). The sweep runs it for
  changed accounts; routes call it right after their own changes.
- When WhatsApp becomes allowed, a number the business held is connected automatically.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.notifications.service import notify
from app.modules.pi_saas.access_gate import whatsapp_gate
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiBusinessVerification,
    PiPlan,
    PiPoolNumber,
    PiSubscription,
)
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("platform")
CATEGORIES = {
    "review": "Business review",
    "billing": "Plan and payments",
    "whatsapp": "WhatsApp number",
    "trial": "Trial reminders",
}
EMAIL_DEFAULTS = {key: True for key in CATEGORIES}


def _scope(account: PiBusinessAccount) -> WorkspaceScope:
    return WorkspaceScope.system(
        account.tenant_id, account.production_environment_id, frozenset(), "Pi team"
    )


def email_on(account: PiBusinessAccount, category: str) -> bool:
    return bool((account.notification_prefs or {}).get(category, EMAIL_DEFAULTS.get(category)))


async def send(
    session: AsyncSession,
    account: PiBusinessAccount,
    category: str,
    kind: str,
    title: str,
    body: str,
    *,
    link: str,
    dedupe: str,
    permission: str = "pi.read",
    severity: str = "info",
) -> None:
    scope = _scope(account)
    await notify(
        session,
        scope,
        kind,
        title,
        body,
        link=link,
        permission=permission,
        severity=severity,
        dedupe_key=dedupe,
    )
    if email_on(account, category):
        await _email(session, account, scope, title, body, link, dedupe)


async def _email(
    session: AsyncSession,
    account: PiBusinessAccount,
    scope: WorkspaceScope,
    title: str,
    body: str,
    link: str,
    dedupe: str,
) -> None:
    from app.integrations.business import connection_for, operation
    from app.integrations.email import EMAIL_KEYS
    from app.modules.users.models import PlatformUser

    owner = (
        await session.get(PlatformUser, account.created_by_user_id)
        if account.created_by_user_id
        else None
    )
    if owner is None:
        return
    try:
        async with session.begin_nested():
            connection = await connection_for(session, scope, EMAIL_KEYS)
            await operation(
                session,
                scope,
                connection,
                "notification",
                f"pi-notice:{dedupe}"[:120],
                "pi_business_account",
                account.id,
                {
                    "recipient": owner.email,
                    "title": title,
                    "message": f"{body}\n\nOpen Pi: {link}",
                    "template": "customer_notice",
                    "name": owner.display_name,
                    "business": account.name,
                },
            )
    except BusinessRuleViolation:
        pass  # no email configured yet: in-app still works
    except Exception:  # noqa: BLE001 - email must never block the business step
        logger.warning("pi_notice_email_failed")


# ------------------------------------------------------------------ review


async def review_changed(
    session: AsyncSession, account: PiBusinessAccount, row: PiBusinessVerification
) -> None:
    stamp = f"{row.status}:{(row.decided_at or row.submitted_at or datetime.now(UTC)).isoformat()}"
    note = f"\n\nNote from the Pi team: {row.decision_note}" if row.decision_note else ""
    messages = {
        "submitted": (
            "We received your business details",
            "The Pi team will review them, usually within one working day.",
            "info",
        ),
        "approved": (
            "Your business is approved",
            "Next: choose a plan and a WhatsApp number. Pi connects the number as soon as "
            "the plan is paid (or right away on a free plan)." + note,
            "info",
        ),
        "changes_requested": (
            "Please update your business details",
            "The Pi team needs a few changes before approving your business." + note,
            "warning",
        ),
        "rejected": (
            "Your business wasn't approved",
            "The Pi team couldn't approve this business." + note,
            "warning",
        ),
    }
    if row.status not in messages:
        return
    title, body, severity = messages[row.status]
    await send(
        session,
        account,
        "review",
        f"pi.review_{row.status}",
        title,
        body,
        link="/settings/business-review",
        dedupe=f"pi-review:{account.tenant_id}:{stamp}",
        severity=severity,
    )


# ------------------------------------------------------------------ journey check


async def _held(session: AsyncSession, account: PiBusinessAccount) -> list[PiPoolNumber]:
    return list(
        await session.scalars(
            select(PiPoolNumber)
            .where(
                PiPoolNumber.status == "reserved",
                PiPoolNumber.assigned_tenant_id == account.tenant_id,
                PiPoolNumber.held_until.is_not(None),
            )
            .with_for_update()
        )
    )


async def activate_held(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, account: PiBusinessAccount
) -> list[str]:
    """Connect numbers the business held, now that it may. Returns connected numbers."""
    from app.modules.pi_saas import connections, number_pool

    connected = []
    for row in await _held(session, account):
        environment: Literal["production", "test"] = (
            "test" if row.assigned_environment_id == account.test_environment_id else "production"
        )
        try:
            async with session.begin_nested():
                await number_pool.choose(
                    session,
                    settings,
                    http,
                    None,
                    connections.pi_target(account, environment),
                    row.id,
                )
            connected.append(row.display_phone_number)
        except Exception as exc:  # noqa: BLE001 - retried by the next sweep
            logger.warning(
                "pi_hold_activation_failed", extra={"code": getattr(exc, "code", "error")}
            )
    return connected


async def check(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, account: PiBusinessAccount
) -> None:
    state = dict(account.lifecycle_state or {})
    sub = await session.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == account.tenant_id)
    )
    plan = await session.scalar(select(PiPlan).where(PiPlan.key == sub.plan_key)) if sub else None
    gate = await whatsapp_gate(session, settings, account.tenant_id)
    now = datetime.now(UTC)
    if not state:
        await send(
            session,
            account,
            "review",
            "pi.welcome",
            f"Welcome to Pi, {account.name}",
            "Three steps to go live on WhatsApp: send your business details for review, "
            "choose a plan, and pick your number. You can try Pi's replies right away.",
            link="/setup",
            dedupe=f"pi-welcome:{account.tenant_id}",
        )
    if sub is not None and plan is not None:
        was_paid = state.get("sub") in ("active", "past_due")
        if sub.status == "active" and (not was_paid or state.get("plan") != plan.key):
            free = plan.monthly_price is not None and plan.monthly_price == 0
            await send(
                session,
                account,
                "billing",
                "pi.plan_active",
                f"{plan.name} is active" if free else f"Payment received: {plan.name} is active",
                (
                    "You're on a free plan from the Pi team."
                    if free
                    else "Thank you. Your plan is active"
                    + (
                        f" until {sub.current_period_end:%d %b %Y}."
                        if sub.current_period_end
                        else "."
                    )
                ),
                link="/settings/billing",
                dedupe=f"pi-plan-active:{account.tenant_id}:{plan.key}:{sub.current_period_end}",
            )
        state["sub"], state["plan"] = sub.status, plan.key
    previous = state.get("gate")
    if gate.ok:
        numbers = await activate_held(session, settings, http, account)
        for number in numbers:
            await send(
                session,
                account,
                "whatsapp",
                "pi.whatsapp_connected",
                "Your WhatsApp number is connected",
                f"{number} is now connected to Pi. Customers who message it get answers.",
                link="/settings/whatsapp",
                dedupe=f"pi-connected:{account.tenant_id}:{number}",
            )
        if not numbers and previous not in (None, "OK") and gate.managed:
            await send(
                session,
                account,
                "whatsapp",
                "pi.whatsapp_ready",
                "You can connect WhatsApp now",
                "Your business is approved and your plan is ready. Choose a number to go live.",
                link="/settings/whatsapp",
                dedupe=f"pi-whatsapp-ready:{account.tenant_id}",
            )
    state["gate"] = gate.reason
    account.lifecycle_state = state
    account.lifecycle_checked_at = now


# ------------------------------------------------------------------ sweep


async def _expire_holds(session: AsyncSession, now: datetime) -> None:
    rows = list(
        await session.scalars(
            select(PiPoolNumber)
            .where(
                PiPoolNumber.status == "reserved",
                PiPoolNumber.held_until.is_not(None),
                PiPoolNumber.held_until < now + timedelta(days=1),
            )
            .with_for_update(skip_locked=True)
            .limit(200)
        )
    )
    for row in rows:
        account = await session.scalar(
            select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == row.assigned_tenant_id)
        )
        assert row.held_until is not None
        if row.held_until < now:
            if account is not None:
                await send(
                    session,
                    account,
                    "whatsapp",
                    "pi.hold_expired",
                    "Your held WhatsApp number was released",
                    f"{row.display_phone_number} went back to the pool because setup wasn't "
                    "finished in time. You can choose a number again.",
                    link="/settings/whatsapp",
                    dedupe=f"pi-hold-expired:{row.id}:{row.held_until.date()}",
                    severity="warning",
                )
            row.status, row.held_until = "available", None
            row.assigned_tenant_id = row.assigned_environment_id = None
        elif account is not None:
            await send(
                session,
                account,
                "whatsapp",
                "pi.hold_expiring",
                "Your held number is released tomorrow",
                f"Finish approval and payment to keep {row.display_phone_number}.",
                link="/setup",
                dedupe=f"pi-hold-expiring:{row.id}:{row.held_until.date()}",
                severity="warning",
            )


async def _trial_reminders(session: AsyncSession, now: datetime) -> None:
    rows = await session.execute(
        select(PiSubscription, PiBusinessAccount)
        .join(PiBusinessAccount, PiBusinessAccount.tenant_id == PiSubscription.tenant_id)
        .where(
            PiSubscription.status == "trialing",
            PiSubscription.trial_ends_at.is_not(None),
            PiSubscription.trial_ends_at > now,
            PiSubscription.trial_ends_at < now + timedelta(days=3),
            PiBusinessAccount.status == "active",
        )
        .limit(500)
    )
    for sub, account in rows:
        assert sub.trial_ends_at is not None
        days = 1 if sub.trial_ends_at < now + timedelta(days=1) else 3
        await send(
            session,
            account,
            "trial",
            "pi.trial_ending",
            "Your Pi trial ends tomorrow" if days == 1 else "Your Pi trial ends in 3 days",
            "Choose a plan to keep Pi answering your customers on WhatsApp.",
            link="/settings/billing",
            dedupe=f"pi-trial:{account.tenant_id}:{sub.trial_ends_at.date()}:{days}",
            permission="pi.billing.read",
        )


async def sweep(session: AsyncSession, settings: Settings, http: httpx.AsyncClient) -> int:
    now = datetime.now(UTC)
    await _expire_holds(session, now)
    await _trial_reminders(session, now)
    checked = func.coalesce(
        PiBusinessAccount.lifecycle_checked_at, datetime(2000, 1, 1, tzinfo=UTC)
    )
    accounts = list(
        await session.scalars(
            select(PiBusinessAccount)
            .outerjoin(PiSubscription, PiSubscription.tenant_id == PiBusinessAccount.tenant_id)
            .outerjoin(
                PiBusinessVerification,
                PiBusinessVerification.tenant_id == PiBusinessAccount.tenant_id,
            )
            .where(
                or_(
                    PiBusinessAccount.lifecycle_checked_at.is_(None),
                    PiSubscription.updated_at > checked,
                    PiBusinessVerification.updated_at > checked,
                    PiBusinessAccount.tenant_id.in_(
                        select(PiPoolNumber.assigned_tenant_id).where(
                            PiPoolNumber.status == "reserved", PiPoolNumber.held_until.is_not(None)
                        )
                    ),
                )
            )
            .limit(200)
        )
    )
    for account in accounts:
        try:
            async with session.begin_nested():
                await check(session, settings, http, account)
        except Exception:  # noqa: BLE001 - one business never blocks the others
            logger.warning("pi_lifecycle_check_failed")
    return len(accounts)


def preferences(account: PiBusinessAccount) -> list[dict[str, Any]]:
    return [
        {"key": key, "label": label, "email": email_on(account, key), "in_app": True}
        for key, label in CATEGORIES.items()
    ]
