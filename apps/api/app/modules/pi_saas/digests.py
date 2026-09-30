"""Weekly summaries: one for each business ("your week with Pi") and one for operators.

Business digests are built every Monday morning (08:00 in the business's time zone) for
the previous Monday-Sunday, from real counts only, kept for looking back, announced
in-app, and emailed to the owner only when they switched that on and the business has a
verified email connection. Operator summaries use the same scoped operator functions as
the console and Pi (Agenta), so an operator never sees more than they may open.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.notifications.service import notify
from app.modules.pi.models import PiAgentRun, PiConversation, PiHandoff, PiMessage
from app.modules.pi.policy import zone
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.models import PiBooking, PiBusinessAccount, PiDigest, PiStaffRequest
from app.modules.tenants.models import Tenant
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

SEND_HOUR = 8


def last_week(timezone: str, now: datetime | None = None) -> tuple[date, date, datetime, datetime]:
    """(Monday, next Monday) of the previous full week, as local dates and UTC bounds."""
    tz = zone(timezone)
    local = (now or datetime.now(UTC)).astimezone(tz)
    this_monday = local.date() - timedelta(days=local.weekday())
    start = this_monday - timedelta(days=7)
    start_utc = datetime.combine(start, time(), tz).astimezone(UTC)
    end_utc = datetime.combine(this_monday, time(), tz).astimezone(UTC)
    return start, this_monday, start_utc, end_utc


async def business_metrics(
    session: AsyncSession, scope: WorkspaceScope, start: datetime, end: datetime
) -> dict[str, Any]:
    def repo(model: Any) -> Any:
        return WorkspaceRepository(session, model, scope)

    async def count(model: Any, *where: Any, column: Any = None) -> int:
        target = func.count(func.distinct(column)) if column is not None else func.count()
        return int(
            await session.scalar(
                select(target).select_from(model).where(repo(model).predicate(), *where)
            )
            or 0
        )

    in_week = (PiMessage.created_at >= start, PiMessage.created_at < end)
    paid = await session.execute(
        select(PiPaymentRequest.currency, func.sum(PiPaymentRequest.amount))
        .where(
            repo(PiPaymentRequest).predicate(),
            PiPaymentRequest.status == "paid",
            PiPaymentRequest.updated_at >= start,
            PiPaymentRequest.updated_at < end,
        )
        .group_by(PiPaymentRequest.currency)
    )
    return {
        "customers_who_messaged": await count(
            PiMessage,
            PiMessage.direction == "inbound",
            *in_week,
            column=PiMessage.conversation_id,
        ),
        "messages_received": await count(PiMessage, PiMessage.direction == "inbound", *in_week),
        "pi_replies": await count(
            PiMessage,
            PiMessage.sender_type == "ai",
            PiMessage.status.in_(["sent", "delivered", "read"]),
            *in_week,
        ),
        "team_replies": await count(
            PiMessage,
            PiMessage.sender_type == "human",
            PiMessage.status.in_(["sent", "delivered", "read"]),
            *in_week,
        ),
        "new_customers": await count(
            Customer, Customer.created_at >= start, Customer.created_at < end
        ),
        "handed_to_team": await count(
            PiHandoff, PiHandoff.created_at >= start, PiHandoff.created_at < end
        ),
        "enquiries": await count(
            PiAgentRun,
            PiAgentRun.intent.in_(["requirement", "quote", "order", "pricing"]),
            PiAgentRun.created_at >= start,
            PiAgentRun.created_at < end,
            column=PiAgentRun.conversation_id,
        ),
        "bookings": await count(
            PiBooking,
            PiBooking.created_at >= start,
            PiBooking.created_at < end,
            PiBooking.status != "cancelled",
        ),
        "campaign_messages": await count(
            PiMessage,
            PiMessage.idempotency_key.like("pi-campaign:%"),
            PiMessage.status.in_(["sent", "delivered", "read"]),
            *in_week,
        ),
        "payments_received": {currency: str(total) for currency, total in paid if total},
        # What still needs someone, as of when the summary was made.
        "waiting_now": {
            "replies_to_approve": await count(PiMessage, PiMessage.status == "pending_approval"),
            "questions_for_you": await count(PiStaffRequest, PiStaffRequest.status == "open"),
            "payments_to_check": await count(
                PiPaymentRequest, PiPaymentRequest.status == "awaiting_verification"
            ),
            "open_conversations": await count(PiConversation, PiConversation.status == "open"),
        },
    }


def digest_text(name: str, start: date, metrics: dict[str, Any]) -> str:
    m = metrics
    lines = [
        f"{name}: your week with Pi ({start:%d %b} to {start + timedelta(days=6):%d %b}).",
        f"{m['customers_who_messaged']} customers messaged you; Pi sent {m['pi_replies']} "
        f"replies and your team {m['team_replies']}.",
        f"{m['new_customers']} new customers, {m['enquiries']} enquiries, "
        f"{m['bookings']} bookings, {m['handed_to_team']} handed to your team.",
    ]
    if m["payments_received"]:
        amounts = ", ".join(
            f"{currency} {Decimal(total):,.2f}"
            for currency, total in m["payments_received"].items()
        )
        lines.append(f"Payments confirmed: {amounts}.")
    waiting = m["waiting_now"]
    todo = [
        f"{waiting['replies_to_approve']} replies to approve"
        if waiting["replies_to_approve"]
        else "",
        f"{waiting['questions_for_you']} questions for you" if waiting["questions_for_you"] else "",
        f"{waiting['payments_to_check']} payments to check" if waiting["payments_to_check"] else "",
    ]
    todo = [t for t in todo if t]
    if todo:
        lines.append("Waiting for you: " + ", ".join(todo) + ".")
    return "\n".join(lines)


def view(row: PiDigest) -> dict[str, Any]:
    return {
        "id": row.id,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "metrics": row.metrics,
        "delivery": row.delivery,
        "created_at": row.created_at,
    }


def digest_scope(account: PiBusinessAccount) -> WorkspaceScope:
    """Read-only system scope for the business's live environment."""
    return WorkspaceScope.system(
        account.tenant_id,
        account.production_environment_id,
        frozenset({"pi.read", "pi.analytics.read"}),
        "PI weekly summary",
    )


async def build(
    session: AsyncSession, account: PiBusinessAccount, now: datetime | None = None
) -> tuple[PiDigest, bool]:
    """The digest for last week (created once). Returns (digest, created_now)."""
    scope = digest_scope(account)
    start, end, start_utc, end_utc = last_week(account.timezone or "UTC", now)
    repo = WorkspaceRepository(session, PiDigest, scope)
    existing = await repo.find(PiDigest.period_start == start)
    if existing is not None:
        return existing, False
    metrics = await business_metrics(session, scope, start_utc, end_utc)
    inserted = await session.scalar(
        insert(PiDigest)
        .values(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            period_start=start,
            period_end=end - timedelta(days=1),
            metrics=metrics,
        )
        .on_conflict_do_nothing(constraint="uq_pi_digest_week")
        .returning(PiDigest.id)
    )
    row = await repo.find(PiDigest.period_start == start)
    assert row is not None
    return row, inserted is not None


async def deliver(session: AsyncSession, account: PiBusinessAccount, row: PiDigest) -> list[str]:
    """In-app notification always; email only when switched on. Returns integration
    operation ids to deliver."""
    scope = digest_scope(account)
    text = digest_text(account.name, row.period_start, row.metrics)
    await notify(
        session,
        scope,
        "pi.weekly_digest",
        "Your week with Pi",
        text[:500],
        link="/home",
        permission="pi.analytics.read",
        dedupe_key=f"pi-digest:{row.period_start}",
    )
    delivery = {**row.delivery, "in_app": "sent"}
    operations: list[str] = []
    if account.digest_email:
        from app.integrations.business import connection_for, operation
        from app.integrations.email import EMAIL_KEYS
        from app.modules.users.models import PlatformUser
        from app.shared.errors import BusinessRuleViolation

        owner = (
            await session.get(PlatformUser, account.created_by_user_id)
            if account.created_by_user_id
            else None
        )
        try:
            if owner is None:
                raise BusinessRuleViolation("NO_OWNER", "No owner email")
            connection = await connection_for(session, scope, EMAIL_KEYS)
            op = await operation(
                session,
                scope,
                connection,
                "notification",
                f"pi-digest:{row.id}",
                "pi_digest",
                row.id,
                {
                    "recipient": owner.email,
                    "title": f"Your week with Pi: {row.period_start:%d %b}",
                    "message": text,
                    "template": "customer_notice",
                    "name": owner.display_name,
                    "business": account.name,
                },
            )
            operations.append(str(op.id))
            delivery["email"] = "queued"
        except BusinessRuleViolation as exc:
            delivery["email"] = exc.code.lower()  # e.g. integration_not_configured
    row.delivery = delivery
    return operations


async def sweep_digests(ctx: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    operations: list[str] = []
    async with ctx["sessions"]() as session:
        accounts = list(
            await session.scalars(
                select(PiBusinessAccount)
                .join(Tenant, Tenant.id == PiBusinessAccount.tenant_id)
                .where(
                    PiBusinessAccount.status == "active",
                    PiBusinessAccount.launched_at.is_not(None),
                    Tenant.status == "active",
                )
                .limit(500)
            )
        )
        for account in accounts:
            local = now.astimezone(zone(account.timezone or "UTC"))
            if local.weekday() != 0 or local.hour < SEND_HOUR:
                continue
            row, created = await build(session, account, now)
            if created:
                operations += await deliver(session, account, row)
        await session.commit()
    for op_id in operations:
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job(
                "deliver_integration_operation", op_id, _job_id=f"operation:{op_id}"
            )
        elif ctx.get("queue"):
            await ctx["queue"].enqueue(
                "deliver_integration_operation", op_id, job_id=f"operation:{op_id}"
            )


# ------------------------------------------------------------------------ operators


async def operator_week(session: AsyncSession, operator: Any) -> dict[str, Any]:
    """Last 7 days across the businesses this operator may see (no customer content)."""
    from app.modules.pi_saas.agenta import gather
    from app.modules.pi_saas.operator import visible_tenants

    since = datetime.now(UTC) - timedelta(days=7)
    facts = await gather(session, operator, "attention")
    assigned = visible_tenants(operator)

    def scoped(column: Any, statement: Any) -> Any:
        return statement if assigned is None else statement.where(column.in_(assigned))

    week: dict[str, int] = {}
    if operator.can("operator.accounts.read"):
        week["new_businesses"] = int(
            await session.scalar(
                scoped(
                    PiBusinessAccount.tenant_id,
                    select(func.count())
                    .select_from(PiBusinessAccount)
                    .where(PiBusinessAccount.created_at >= since),
                )
            )
            or 0
        )
        week["went_live"] = int(
            await session.scalar(
                scoped(
                    PiBusinessAccount.tenant_id,
                    select(func.count())
                    .select_from(PiBusinessAccount)
                    .where(PiBusinessAccount.launched_at >= since),
                )
            )
            or 0
        )
    if operator.can("operator.analytics.read"):
        week["messages_received"] = int(
            await session.scalar(
                scoped(
                    PiMessage.tenant_id,
                    select(func.count())
                    .select_from(PiMessage)
                    .where(PiMessage.direction == "inbound", PiMessage.created_at >= since),
                )
            )
            or 0
        )
        week["pi_replies"] = int(
            await session.scalar(
                scoped(
                    PiMessage.tenant_id,
                    select(func.count())
                    .select_from(PiMessage)
                    .where(
                        PiMessage.sender_type == "ai",
                        PiMessage.status.in_(["sent", "delivered", "read"]),
                        PiMessage.created_at >= since,
                    ),
                )
            )
            or 0
        )
    return {"since": since, "week": week, "attention": facts}
