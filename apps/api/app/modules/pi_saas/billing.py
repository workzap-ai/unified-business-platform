"""Pi subscription billing (the business paying for Pi).

This is separate from a business collecting payments from its own WhatsApp customers,
which uses that business's own payment integration. Checkout and the customer portal are
Stripe-hosted; the platform never handles card data. Subscription state changes only
through verified webhooks (or an audited operator action), are deduplicated by event id
and applied in event order, so a delayed or replayed event cannot roll state back.

Plans have no hard-coded prices: an operator sets the price and Stripe price id before a
plan can be bought. Trials need no payment method and run on the configured plan.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.providers.stripe import StripeProvider
from app.modules.audit.service import record
from app.modules.notifications.service import notify
from app.modules.pi_saas.json_util import as_dict, as_list
from app.modules.pi_saas.models import (
    PiBillingEvent,
    PiBusinessAccount,
    PiPlan,
    PiPlatformInvoice,
    PiSubscription,
)
from app.modules.pi_saas.payment_models import PiCheckoutAttempt, PiManualPayment
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

ZERO_DECIMAL = {
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "JPY",
    "KMF",
    "KRW",
    "MGA",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
}
STRIPE_STATUS = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "incomplete": "past_due",
    "unpaid": "suspended",
    "paused": "suspended",
    "canceled": "canceled",
    "incomplete_expired": "canceled",
}
INVOICE_STATUS = {"draft", "open", "paid", "void", "uncollectible"}


def _money(amount: Any, currency: str) -> Decimal:
    value = Decimal(int(amount or 0))
    return value if currency.upper() in ZERO_DECIMAL else (value / 100).quantize(Decimal("0.01"))


def _ts(value: Any) -> datetime | None:
    return datetime.fromtimestamp(int(value), UTC) if isinstance(value, int) and value > 0 else None


class Stripe:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings, self.http = settings, http

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        key = self.settings.pi_billing_stripe_secret_key
        if key is None:
            raise BusinessRuleViolation(
                "BILLING_NOT_CONFIGURED",
                "Online payment isn't available yet. Contact us to activate your plan.",
                503,
            )
        headers = {"Authorization": f"Bearer {key.get_secret_value()}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:255]
        return headers

    async def post(self, path: str, form: dict[str, str], idempotency_key: str) -> dict[str, Any]:
        headers = self._headers(idempotency_key)
        try:
            response = await self.http.post(
                f"{self.settings.stripe_api_base_url}{path}",
                headers=headers,
                data=form,
                timeout=20,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise BusinessRuleViolation(
                "BILLING_UNAVAILABLE", "Billing is temporarily unavailable. Try again.", 503
            ) from None
        if response.status_code >= 400:
            raise BusinessRuleViolation(
                "BILLING_REJECTED", "The billing provider could not complete this request", 502
            )
        try:
            data = response.json()
        except ValueError:
            raise BusinessRuleViolation(
                "BILLING_UNAVAILABLE", "Unexpected billing response", 502
            ) from None
        if not isinstance(data, dict):
            raise BusinessRuleViolation("BILLING_UNAVAILABLE", "Unexpected billing response", 502)
        return data

    async def get(self, path: str) -> dict[str, Any]:
        try:
            response = await self.http.get(
                f"{self.settings.stripe_api_base_url}{path}",
                headers=self._headers(),
                timeout=20,
                follow_redirects=False,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (httpx.HTTPError, ValueError):
            raise BusinessRuleViolation(
                "BILLING_UNAVAILABLE",
                "We could not confirm the previous checkout. "
                "Please retry before starting another payment",
                503,
            ) from None


async def subscription_for(session: AsyncSession, tenant_id: UUID) -> PiSubscription:
    row = await session.scalar(
        select(PiSubscription)
        .where(PiSubscription.tenant_id == tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise BusinessRuleViolation("NO_SUBSCRIPTION", "No Pi plan is set up", 404)
    return row


async def checkout(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    account: PiBusinessAccount,
    plan_key: str,
    email: str,
) -> str:
    scope.require("pi.billing.manage")
    plan = await session.scalar(
        select(PiPlan).where(PiPlan.key == plan_key, PiPlan.status == "available")
    )
    if (
        plan is None
        or plan.visibility != "public"
        or plan.monthly_price is None
        or plan.monthly_price == 0
        or not plan.stripe_price_id
    ):
        raise BusinessRuleViolation(
            "PLAN_NOT_PURCHASABLE",
            "This plan can't be bought online yet. Contact us and we'll set it up.",
            409,
        )
    subscription = await subscription_for(session, account.tenant_id)
    if not settings.pi_billing_stripe_secret_key or not settings.pi_billing_stripe_webhook_secret:
        raise BusinessRuleViolation(
            "BILLING_NOT_CONFIGURED",
            "Card billing is not configured yet. Choose another available payment method",
            409,
        )
    now = datetime.now(UTC)
    if subscription.external_subscription_id and subscription.status != "canceled":
        raise BusinessRuleViolation(
            "SUBSCRIPTION_EXISTS",
            "You already have a card subscription. Use Manage billing to change your plan",
            409,
        )
    if (
        subscription.billing_provider == "manual"
        and subscription.status == "active"
        and subscription.current_period_end
        and subscription.current_period_end > now
    ):
        raise BusinessRuleViolation(
            "PAID_PERIOD_ACTIVE",
            "Your current period is already paid. Switch to card after it ends",
            409,
        )
    if await session.scalar(
        select(PiManualPayment.id).where(
            PiManualPayment.tenant_id == account.tenant_id,
            PiManualPayment.status.in_(["awaiting_payment", "submitted"]),
        )
    ):
        raise BusinessRuleViolation(
            "PAYMENT_PENDING",
            "Resolve your bank or cash payment request before starting card checkout",
            409,
        )
    attempt = await session.scalar(
        select(PiCheckoutAttempt)
        .where(
            PiCheckoutAttempt.tenant_id == account.tenant_id,
            PiCheckoutAttempt.status.in_(
                ["creating", "open"]
                if subscription.external_subscription_id and subscription.status == "canceled"
                else ["creating", "open", "complete"]
            ),
        )
        .order_by(PiCheckoutAttempt.created_at.desc())
        .limit(1)
    )
    if attempt and attempt.expires_at <= now:
        if attempt.external_id:
            remote = await Stripe(settings, http).get(
                f"/v1/checkout/sessions/{attempt.external_id}"
            )
            if remote.get("status") != "expired":
                raise BusinessRuleViolation(
                    "CHECKOUT_CONFIRMING",
                    "Your earlier card payment is still being confirmed. "
                    "Contact billing support if it does not update",
                    409,
                )
        # An ambiguous request without a provider id is held beyond Stripe's expiry
        # window; reuse of its persisted key below is safer than issuing a new charge.
        else:
            raise BusinessRuleViolation(
                "CHECKOUT_RECONCILIATION",
                "The earlier checkout needs billing support to confirm its outcome",
                409,
            )
        attempt.status = "expired"
        attempt = None
    if attempt:
        if attempt.plan_key != plan.key:
            raise BusinessRuleViolation(
                "CHECKOUT_PENDING",
                "Finish the existing checkout or let it expire before choosing another plan",
                409,
            )
        if attempt.url:
            return attempt.url
    base = settings.pi_app_public_url.rstrip("/")
    form = {
        "mode": "subscription",
        "line_items[0][price]": plan.stripe_price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": str(account.tenant_id),
        "success_url": f"{base}/settings/billing?checkout=success",
        "cancel_url": f"{base}/settings/billing?checkout=cancelled",
        "subscription_data[metadata][tenant_id]": str(account.tenant_id),
        "subscription_data[metadata][plan_key]": plan.key,
        "metadata[tenant_id]": str(account.tenant_id),
        "metadata[plan_key]": plan.key,
    }
    if subscription.external_customer_id:
        form["customer"] = subscription.external_customer_id
    else:
        form["customer_email"] = email
    if attempt is None:
        expires = now + timedelta(hours=1)
        form["expires_at"] = str(int(expires.timestamp()))
        attempt = PiCheckoutAttempt(
            tenant_id=account.tenant_id,
            plan_key=plan.key,
            status="creating",
            expires_at=expires,
            form=form,
        )
        session.add(attempt)
        await session.flush()
        # Preserve the provider idempotency key before the external call. A timeout
        # must never turn the next retry into a second checkout.
        await session.commit()
        subscription = await subscription_for(session, account.tenant_id)
        attempt = await session.get(PiCheckoutAttempt, attempt.id, populate_existing=True)
        assert attempt is not None
        if attempt.url:
            return attempt.url
    data = await Stripe(settings, http).post(
        "/v1/checkout/sessions", dict(attempt.form), f"pi-checkout:{attempt.id}"
    )
    url = str(data.get("url") or "")
    if not url.startswith("https://"):
        raise BusinessRuleViolation("BILLING_UNAVAILABLE", "Unexpected billing response", 502)
    attempt.url, attempt.external_id, attempt.status = (
        url,
        str(data.get("id") or "")[:120] or None,
        "open",
    )
    subscription.pending_plan_key = plan.key
    await record(
        session,
        "pi_saas.checkout_started",
        scope=scope,
        entity_type="pi_subscription",
        entity_id=subscription.id,
        details={"plan": plan.key},
    )
    return url


async def portal(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    account: PiBusinessAccount,
) -> str:
    """Stripe-hosted portal for payment methods, invoices and plan changes."""
    scope.require("pi.billing.manage")
    subscription = await subscription_for(session, account.tenant_id)
    if not subscription.external_customer_id:
        raise BusinessRuleViolation(
            "NO_BILLING_ACCOUNT", "Choose a plan first to manage payment details", 409
        )
    data = await Stripe(settings, http).post(
        "/v1/billing_portal/sessions",
        {
            "customer": subscription.external_customer_id,
            "return_url": f"{settings.pi_app_public_url.rstrip('/')}/settings/billing",
        },
        f"pi-portal:{account.tenant_id}:{datetime.now(UTC):%Y%m%d%H%M}",
    )
    url = str(data.get("url") or "")
    if not url.startswith("https://"):
        raise BusinessRuleViolation("BILLING_UNAVAILABLE", "Unexpected billing response", 502)
    return url


async def cancel(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    account: PiBusinessAccount,
) -> PiSubscription:
    """Cancel at the end of the paid period (trials end now). Data is retained per the
    documented retention policy; Pi stops replying when the subscription ends."""
    scope.require("pi.billing.manage")
    subscription = await subscription_for(session, account.tenant_id)
    if subscription.status in {"canceled"}:
        return subscription
    if subscription.billing_provider == "stripe" and subscription.external_subscription_id:
        await Stripe(settings, http).post(
            f"/v1/subscriptions/{subscription.external_subscription_id}",
            {"cancel_at_period_end": "true"},
            f"pi-cancel:{subscription.external_subscription_id}",
        )
        subscription.cancel_at_period_end = True  # Confirmed later by the webhook.
    elif (
        subscription.status == "active"
        and subscription.current_period_end
        and subscription.current_period_end > datetime.now(UTC)
    ):
        subscription.cancel_at_period_end = True
        subscription.grace_ends_at = subscription.current_period_end
    else:
        subscription.status = "canceled"
        subscription.canceled_at = datetime.now(UTC)
    await record(
        session,
        "pi_saas.subscription_cancel_requested",
        scope=scope,
        entity_type="pi_subscription",
        entity_id=subscription.id,
    )
    return subscription


def verify(settings: Settings, headers: dict[str, str], body: bytes) -> bool:
    secret = settings.pi_billing_stripe_webhook_secret
    if secret is None:
        return False
    return StripeProvider().verify_webhook(
        headers,
        body,
        {"webhook_secret": secret.get_secret_value()},
        settings,
        datetime.now(UTC).timestamp(),
    )


async def store_event(session: AsyncSession, event: dict[str, Any]) -> UUID | None:
    event_id = str(event.get("id") or "")[:120]
    if not event_id:
        return None
    obj = as_dict(as_dict(event.get("data")).get("object"))
    return await session.scalar(
        insert(PiBillingEvent)
        .values(
            provider="stripe",
            event_id=event_id,
            event_type=str(event.get("type") or "")[:80],
            payload={
                "created": event.get("created"),
                "object": {
                    k: obj.get(k)
                    for k in (
                        "id",
                        "object",
                        "status",
                        "customer",
                        "subscription",
                        "client_reference_id",
                        "metadata",
                        "cancel_at_period_end",
                        "current_period_start",
                        "current_period_end",
                        "items",
                        "number",
                        "amount_due",
                        "amount_paid",
                        "currency",
                        "hosted_invoice_url",
                        "period_start",
                        "period_end",
                        "parent",
                        "lines",
                    )
                    if k in obj
                },
            },
        )
        .on_conflict_do_nothing(constraint="uq_pi_billing_events_event")
        .returning(PiBillingEvent.id)
    )


def _tenant_hint(obj: dict[str, Any]) -> str | None:
    metadata = as_dict(obj.get("metadata"))
    details = as_dict(as_dict(obj.get("parent")).get("subscription_details"))
    metadata = {**as_dict(details.get("metadata")), **metadata}
    return str(metadata.get("tenant_id") or obj.get("client_reference_id") or "") or None


async def _subscription(session: AsyncSession, obj: dict[str, Any]) -> PiSubscription | None:
    row: PiSubscription | None
    hint = _tenant_hint(obj)
    external = obj.get("id") if obj.get("object") == "subscription" else obj.get("subscription")
    if not external:
        external = as_dict(as_dict(obj.get("parent")).get("subscription_details")).get(
            "subscription"
        )
    if external:
        row = await session.scalar(
            select(PiSubscription)
            .where(PiSubscription.external_subscription_id == str(external))
            .with_for_update()
        )
        if row is not None:
            return row
    if hint:
        try:
            tenant_id = UUID(hint)
        except ValueError:
            return None
        row = await session.scalar(
            select(PiSubscription).where(PiSubscription.tenant_id == tenant_id).with_for_update()
        )
        return row
    customer = obj.get("customer")
    if customer:
        row = await session.scalar(
            select(PiSubscription)
            .where(PiSubscription.external_customer_id == str(customer))
            .with_for_update()
        )
        return row
    return None


async def apply_event(session: AsyncSession, settings: Settings, row: PiBillingEvent) -> None:
    obj = as_dict(row.payload.get("object"))
    created = _ts(row.payload.get("created")) or datetime.now(UTC)
    subscription = await _subscription(session, obj)
    if subscription is None:
        row.status = "ignored"
        return
    row.tenant_id = subscription.tenant_id
    kind = row.event_type
    previous = subscription.status
    if (
        subscription.billing_provider == "manual"
        and subscription.last_event_at
        and created <= subscription.last_event_at
    ):
        row.status = "ignored"
        return
    external = obj.get("id") if obj.get("object") == "subscription" else obj.get("subscription")
    if not external:
        external = as_dict(as_dict(obj.get("parent")).get("subscription_details")).get(
            "subscription"
        )
    # An old canceled Stripe subscription must not reclaim a manually paid account.
    if (
        subscription.billing_provider == "manual"
        and subscription.last_event_at
        and external == subscription.external_subscription_id
    ):
        row.status = "ignored"
        return
    if kind.startswith("customer.subscription."):
        if subscription.last_event_at is not None and created < subscription.last_event_at:
            row.status = "ignored"  # Out-of-order: a newer state was already applied.
            return
        subscription.last_event_at = created
        subscription.billing_provider = "stripe"
        subscription.external_subscription_id = str(obj.get("id") or "")[:120] or None
        subscription.external_customer_id = (
            str(obj.get("customer") or "")[:120] or subscription.external_customer_id
        )
        status = (
            "canceled"
            if kind.endswith(".deleted")
            else STRIPE_STATUS.get(str(obj.get("status")), subscription.status)
        )
        subscription.status = status
        subscription.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        item = as_dict((as_list(as_dict(obj.get("items")).get("data")) or [{}])[0])
        start = _ts(obj.get("current_period_start")) or _ts(
            (item or {}).get("current_period_start")
        )
        end = _ts(obj.get("current_period_end")) or _ts((item or {}).get("current_period_end"))
        subscription.current_period_start = start or subscription.current_period_start
        subscription.current_period_end = end or subscription.current_period_end
        plan_key = as_dict(obj.get("metadata")).get("plan_key")
        price_id = as_dict(item.get("price")).get("id")
        plan = None
        if price_id:
            plan = await session.scalar(
                select(PiPlan).where(PiPlan.stripe_price_id == str(price_id))
            )
            if plan is None:
                raise BusinessRuleViolation(
                    "UNKNOWN_STRIPE_PRICE",
                    "Map this Stripe price to a Pi plan before retrying",
                    409,
                )
        elif plan_key:
            plan = await session.scalar(select(PiPlan).where(PiPlan.key == str(plan_key)))
        if plan is not None:
            subscription.plan_key, subscription.pending_plan_key = plan.key, None
            subscription.currency = plan.currency
        if status == "past_due" and previous != "past_due":
            subscription.grace_ends_at = datetime.now(UTC) + timedelta(
                days=settings.pi_past_due_grace_days
            )
        elif status == "active":
            subscription.grace_ends_at = (
                end + timedelta(days=2) if end else None
            )  # Covers a delayed renewal webhook.
        if status == "canceled":
            subscription.canceled_at = subscription.canceled_at or datetime.now(UTC)
    elif kind == "checkout.session.completed":
        if subscription.last_event_at is not None and created < subscription.last_event_at:
            row.status = "ignored"
            return
        attempt = await session.scalar(
            select(PiCheckoutAttempt).where(
                PiCheckoutAttempt.external_id == str(obj.get("id") or ""),
                PiCheckoutAttempt.tenant_id == subscription.tenant_id,
            )
        )
        if attempt:
            attempt.status = "complete"
        subscription.external_customer_id = (
            str(obj.get("customer") or "")[:120] or subscription.external_customer_id
        )
        if obj.get("subscription"):
            subscription.external_subscription_id = str(obj["subscription"])[:120]
        subscription.billing_provider = "stripe"
    elif kind.startswith("invoice."):
        applied = await _invoice(session, subscription, obj, created)
        recent = applied and (
            subscription.last_event_at is None or created >= subscription.last_event_at
        )
        if (
            recent
            and kind == "invoice.payment_failed"
            and subscription.status in {"active", "trialing"}
        ):
            subscription.status = "past_due"
            subscription.grace_ends_at = datetime.now(UTC) + timedelta(
                days=settings.pi_past_due_grace_days
            )
        elif recent and kind == "invoice.paid" and subscription.status == "past_due":
            subscription.status = "active"
        if recent and kind in {"invoice.paid", "invoice.payment_failed"}:
            subscription.last_event_at = created
    else:
        row.status = "ignored"
        return
    row.status = "processed"
    if subscription.status != previous:
        await record(
            session,
            "pi_saas.subscription_status_changed",
            tenant_id=subscription.tenant_id,
            entity_type="pi_subscription",
            entity_id=subscription.id,
            details={"from": previous, "to": subscription.status, "event": kind},
            include_environment=False,
        )
        environment_id = await session.scalar(
            select(PiBusinessAccount.production_environment_id).where(
                PiBusinessAccount.tenant_id == subscription.tenant_id
            )
        )
        if environment_id is not None and subscription.status in {
            "past_due",
            "suspended",
            "canceled",
        }:
            await notify(
                session,
                WorkspaceScope.system(
                    subscription.tenant_id, environment_id, frozenset(), "Billing"
                ),
                "pi.billing_attention",
                "Your Pi plan needs attention",
                "Update your payment details to keep Pi replying to customers.",
                link="/settings/billing",
                permission="pi.billing.read",
                dedupe_key=f"pi-billing:{subscription.id}:{subscription.status}",
            )


async def _invoice(
    session: AsyncSession, subscription: PiSubscription, obj: dict[str, Any], created: datetime
) -> bool:
    currency = str(obj.get("currency") or subscription.currency).upper()[:3]
    status = str(obj.get("status") or "open")
    prior = await session.scalar(
        select(PiPlatformInvoice).where(PiPlatformInvoice.external_id == str(obj.get("id") or ""))
    )
    if prior and (
        prior.tenant_id != subscription.tenant_id
        or (prior.last_event_at and created < prior.last_event_at)
        or (prior.status == "paid" and status == "open")
    ):
        return False
    values = {
        "tenant_id": subscription.tenant_id,
        "number": str(obj.get("number") or "")[:60],
        "status": status if status in INVOICE_STATUS else "open",
        "amount_due": _money(obj.get("amount_due"), currency),
        "amount_paid": _money(obj.get("amount_paid"), currency),
        "currency": currency,
        "last_event_at": created,
        "period_start": _ts(obj.get("period_start")),
        "period_end": _ts(obj.get("period_end")),
        "external_id": str(obj.get("id") or "")[:120],
        "hosted_url": (
            str(obj["hosted_invoice_url"])[:500]
            if str(obj.get("hosted_invoice_url") or "").startswith("https://")
            else None
        ),
    }
    if not values["external_id"]:
        return False
    await session.execute(
        insert(PiPlatformInvoice)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_pi_platform_invoices_external",
            set_={k: v for k, v in values.items() if k not in {"tenant_id", "external_id"}},
        )
    )
    return True


async def sweep_lifecycle(session: AsyncSession) -> int:
    """Record lapsed grace periods as suspended so dashboards show the real state.
    Entitlement is always computed from dates too, so this is bookkeeping only."""
    now = datetime.now(UTC)
    rows = list(
        await session.scalars(
            select(PiSubscription)
            .where(
                or_(
                    and_(
                        PiSubscription.status == "past_due",
                        PiSubscription.grace_ends_at.is_not(None),
                        PiSubscription.grace_ends_at <= now,
                    ),
                    and_(
                        PiSubscription.billing_provider == "manual",
                        PiSubscription.status == "active",
                        PiSubscription.current_period_end.is_not(None),
                        PiSubscription.current_period_end <= now,
                    ),
                ),
            )
            .with_for_update(skip_locked=True)
            .limit(200)
        )
    )
    for row in rows:
        previous = row.status
        row.status = "canceled" if row.cancel_at_period_end else "suspended"
        if row.status == "canceled":
            row.canceled_at = row.canceled_at or now
        await record(
            session,
            "pi_saas.subscription_status_changed",
            tenant_id=row.tenant_id,
            entity_type="pi_subscription",
            entity_id=row.id,
            details={"from": previous, "to": row.status, "event": "paid_period_or_grace_expired"},
            include_environment=False,
        )
    return len(rows)
