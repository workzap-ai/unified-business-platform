"""When a Pi business may connect WhatsApp: its business review is approved by the
operator, and it pays for a plan (Stripe, bank transfer or cash, verified) or the
operator gave it a free plan. A trial alone is not enough (the "Try Pi" chat works
without WhatsApp). Owner OS workspaces (no Pi business account) are never gated."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiBusinessVerification,
    PiPlan,
    PiSubscription,
)
from app.shared.errors import BusinessRuleViolation

PAID_STATES = ("active", "past_due")  # past_due stays connected during grace
MESSAGES = {
    "REVIEW_REQUIRED": "Send your business details for review first.",
    "AWAITING_APPROVAL": "The Pi team is reviewing your business.",
    "CHANGES_REQUESTED": "The Pi team asked for changes to your business details.",
    "REVIEW_DECLINED": "Your business wasn't approved. Contact the Pi team.",
    "PAYMENT_REQUIRED": "Choose a plan and pay to connect WhatsApp.",
    "ACCOUNT_SUSPENDED": "This business is suspended.",
}


@dataclass
class Gate:
    ok: bool
    reason: str = "OK"
    steps: list[dict[str, Any]] = field(default_factory=list)
    managed: bool = True

    @property
    def message(self) -> str:
        return MESSAGES.get(self.reason, "")

    def view(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "message": self.message,
            "steps": self.steps,
        }


def is_free(plan: PiPlan | None) -> bool:
    return plan is not None and plan.monthly_price is not None and plan.monthly_price == 0


async def whatsapp_gate(session: AsyncSession, settings: Settings, tenant_id: UUID) -> Gate:
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is None:
        return Gate(ok=True, managed=False)
    review = await session.scalar(
        select(PiBusinessVerification).where(PiBusinessVerification.tenant_id == tenant_id)
    )
    sub = await session.scalar(select(PiSubscription).where(PiSubscription.tenant_id == tenant_id))
    plan = await session.scalar(select(PiPlan).where(PiPlan.key == sub.plan_key)) if sub else None
    status = review.status if review is not None else "not_started"
    reviewed = status == "approved"
    paid = sub is not None and (
        sub.status in PAID_STATES or (is_free(plan) and sub.status == "trialing")
    )
    steps: list[dict[str, Any]] = [
        {"key": "details", "label": "Send business details", "done": status != "not_started"},
        {"key": "approval", "label": "Approved by the Pi team", "done": reviewed},
        {
            "key": "payment",
            "label": "Free plan" if is_free(plan) and paid else "Plan paid",
            "done": paid,
        },
    ]
    if not settings.pi_whatsapp_requires_approval:
        return Gate(ok=True, steps=steps)
    if account.status != "active":
        return Gate(ok=False, reason="ACCOUNT_SUSPENDED", steps=steps)
    reason = {
        "not_started": "REVIEW_REQUIRED",
        "submitted": "AWAITING_APPROVAL",
        "changes_requested": "CHANGES_REQUESTED",
        "rejected": "REVIEW_DECLINED",
    }.get(status)
    if reason:
        return Gate(ok=False, reason=reason, steps=steps)
    if not paid:
        return Gate(ok=False, reason="PAYMENT_REQUIRED", steps=steps)
    return Gate(ok=True, steps=steps)


async def require_whatsapp(session: AsyncSession, settings: Settings, tenant_id: UUID) -> None:
    gate = await whatsapp_gate(session, settings, tenant_id)
    if not gate.ok:
        raise BusinessRuleViolation(gate.reason, gate.message, 409)
