"""pi Health: pi checks its own set-up and work, fixes the safe things itself, and shows
the owner what went wrong and what was fixed.

Everything is computed live from existing tables (no table of its own):

- checks: WhatsApp, Replies, Knowledge, Deals & payments, Meetings, Follow-ups, Problem
  maps and API (AI provider calls, connected apps, outgoing webhooks);
- automatic fixes are only the safe, repeatable kind: work that got stuck is queued
  again (an outbound message, an inbound receipt, a knowledge document) and stale
  customer maps are refreshed. Each fix is written to the audit log as
  ``pi.health.fixed`` with ``{check, what, count}``, which is also where "Fixed by pi"
  and the charts read it back from;
- anything that changes a business's settings, prices, messages or customer data is
  never done automatically: it is shown with a link to the right page, or a button the
  owner presses (replaying failed inbound receipts, re-reading failed documents).

"Learning" here means learning from gaps: the questions pi couldn't answer, most asked
first, and the team's answers on the request desk that became knowledge. No model is
trained.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from sqlalchemy import Integer, and_, cast, exists, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.models import AIUsageEvent
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.integrations.models import Delivery, IntegrationConnection
from app.modules.pi.models import (
    KnowledgeDocument,
    PiAgentRun,
    PiConversation,
    PiMessage,
    PiSettings,
    WhatsAppConnection,
    WhatsAppWebhookEvent,
)
from app.modules.pi_saas import connectors
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.deal_models import PiDealSettings
from app.modules.pi_saas.models import PiKnowledgeDraft, PiStaffRequest
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.tenants.models import Tenant
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

Status = Literal["ok", "warning", "problem", "fixed"]
Fix = Literal["auto", "button", "settings"] | None
# (job name, argument, job id) -> queued?
Enqueue = Callable[[str, str, str], Awaitable[Any]]

AREAS = (
    "WhatsApp",
    "Replies",
    "Knowledge",
    "Deals & payments",
    "Meetings",
    "Follow-ups",
    "Problem maps",
    "API",
)
FIXED_ACTION = "pi.health.fixed"
STUCK = timedelta(minutes=5)
KNOWLEDGE_STUCK = timedelta(minutes=10)
# A fix within this window shows the check as "fixed" (pi just did it) instead of open.
JUST_FIXED = timedelta(minutes=15)
QUIET_DAYS = 3
MAP_REFRESH_PER_RUN = 3
SLOW_AI_MS = 20_000
PENALTY = {"problem": 20, "warning": 7, "ok": 0, "fixed": 0}

REPLY_CODES = {
    "REPLY_LANGUAGE_MISMATCH": "reply wasn't in the customer's language",
    "INVENTED_DETAIL": "reply had a detail not in your knowledge",
    "provider_failure": "AI providers were unavailable",
    "tool_failure": "a tool step failed",
    "low_confidence": "pi wasn't sure what was asked",
    "reply_rejected": "reply failed a safety check",
}
WHATSAPP_CODES = {
    "WHATSAPP_BILLING_PAUSED": "WhatsApp billing is paused, so paid (template) messages "
    "can't go out. Fix billing in your WhatsApp/Meta account.",
    "WHATSAPP_REJECTED": "WhatsApp refused the last message pi tried to send.",
    "WHATSAPP_NOT_CONNECTED": "The WhatsApp number isn't connected.",
    "CONNECTION_NOT_CONFIGURED": "The WhatsApp access token is missing or can't be read. "
    "Reconnect the number.",
}


@dataclass
class Check:
    key: str
    area: str
    status: Status
    title: str
    detail: str = ""
    count: int = 0
    fix: Fix = None
    href: str | None = None
    action: str | None = None  # button label
    last_fixed_at: datetime | None = None

    def view(self) -> dict[str, Any]:
        data = asdict(self)
        data["last_fixed_at"] = self.last_fixed_at.isoformat() if self.last_fixed_at else None
        return data


@dataclass
class Context:
    """What a heal run may use: a queue for jobs, and (optionally) AI for maps."""

    enqueue: Enqueue
    settings: Any = None
    http: httpx.AsyncClient | None = None
    sessions: async_sessionmaker[AsyncSession] | None = None
    fixes: list[dict[str, Any]] = field(default_factory=list)


# ---- Scoring -------------------------------------------------------------------------


def score(checks: list[Check] | list[dict[str, Any]]) -> int:
    """100 minus 20 per problem and 7 per warning (never below 0). Fixed and ok checks
    cost nothing: what pi already put right isn't the owner's problem."""
    total = 0
    for check in checks:
        status = check["status"] if isinstance(check, dict) else check.status
        total += PENALTY.get(status, 0)
    return max(0, 100 - total)


def verdict(value: int, problems: int) -> str:
    if problems:
        return f"pi needs you for {problems} thing{'s' if problems != 1 else ''}."
    if value >= 90:
        return "pi is healthy and working normally."
    if value >= 70:
        return "pi is working; a few things could be better."
    return "pi is working, but several things need a look."


def _share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


# ---- Checks --------------------------------------------------------------------------


def _pred(session: AsyncSession, model: Any, scope: WorkspaceScope) -> Any:
    return WorkspaceRepository(session, model, scope).predicate()


async def _last_fixes(session: AsyncSession, scope: WorkspaceScope) -> dict[str, datetime]:
    # One literal key: a bound parameter in both SELECT and GROUP BY isn't "the same".
    check = AuditEvent.details.op("->>")(literal_column("'check'"))
    rows = await session.execute(
        select(check, func.max(AuditEvent.created_at))
        .where(
            AuditEvent.tenant_id == scope.tenant_id,
            AuditEvent.environment_id == scope.environment_id,
            AuditEvent.action == FIXED_ACTION,
            AuditEvent.created_at >= datetime.now(UTC) - timedelta(days=7),
        )
        .group_by(check)
    )
    return {key: at for key, at in rows.all() if key}


def _auto(check: Check, fixed: dict[str, datetime], now: datetime) -> Check:
    """An auto-fixed check pi acted on moments ago shows as fixed while the work runs."""
    check.fix = "auto"
    check.last_fixed_at = fixed.get(check.key)
    if (
        check.status != "ok"
        and check.last_fixed_at is not None
        and now - check.last_fixed_at <= JUST_FIXED
    ):
        check.status = "fixed"
    return check


async def _whatsapp(
    session: AsyncSession, scope: WorkspaceScope, fixed: dict[str, datetime], now: datetime
) -> list[Check]:
    area, out = "WhatsApp", []
    connection = await session.scalar(
        WorkspaceRepository(session, WhatsAppConnection, scope)
        .select()
        .order_by((WhatsAppConnection.status == "active").desc(), WhatsAppConnection.created_at)
        .limit(1)
    )
    if connection is None:
        return [
            Check(
                "whatsapp_connection",
                area,
                "problem",
                "No WhatsApp number is connected",
                "pi can't talk to customers until a number is connected.",
                fix="settings",
                href="/pi/whatsapp",
            )
        ]
    if connection.status != "active":
        out.append(
            Check(
                "whatsapp_connection",
                area,
                "problem",
                f"WhatsApp number is {connection.status}",
                "Messages aren't received or sent while the number isn't active.",
                fix="settings",
                href="/pi/whatsapp",
            )
        )
    elif connection.last_error_code:
        code = connection.last_error_code
        out.append(
            Check(
                "whatsapp_connection",
                area,
                "problem",
                "WhatsApp reported an error",
                WHATSAPP_CODES.get(code, f"Last error from WhatsApp: {code}."),
                fix="settings",
                href="/pi/whatsapp",
            )
        )
    else:
        out.append(Check("whatsapp_connection", area, "ok", "WhatsApp number is connected"))
    recent_chats = await session.scalar(
        select(func.count())
        .select_from(PiConversation)
        .where(
            _pred(session, PiConversation, scope),
            PiConversation.last_message_at >= now - timedelta(days=30),
        )
    )
    quiet = connection.last_inbound_at is None or connection.last_inbound_at < now - timedelta(
        days=QUIET_DAYS
    )
    if recent_chats and quiet and connection.status == "active":
        out.append(
            Check(
                "whatsapp_quiet",
                area,
                "warning",
                f"No customer messages for {QUIET_DAYS}+ days",
                "Customers have chatted this month but nothing has arrived lately. If that "
                "isn't expected, check the number's webhook in WhatsApp settings.",
                fix="settings",
                href="/pi/whatsapp/webhook",
            )
        )
    events = (WhatsAppWebhookEvent.tenant_id == scope.tenant_id) & (
        WhatsAppWebhookEvent.environment_id == scope.environment_id
    )
    stuck = await session.scalar(
        select(func.count())
        .select_from(WhatsAppWebhookEvent)
        .where(
            events,
            WhatsAppWebhookEvent.status.in_(["received", "queued"]),
            WhatsAppWebhookEvent.attempts < 3,
            WhatsAppWebhookEvent.created_at < now - STUCK,
        )
    )
    out.append(
        _auto(
            Check(
                "whatsapp_stuck_events",
                area,
                "warning" if stuck else "ok",
                f"{_plural(stuck or 0, 'incoming message')} waiting to be read"
                if stuck
                else "Incoming messages are read on time",
                "pi queues them again by itself." if stuck else "",
                count=stuck or 0,
            ),
            fixed,
            now,
        )
    )
    failed = await session.scalar(
        select(func.count())
        .select_from(WhatsAppWebhookEvent)
        .where(
            events,
            WhatsAppWebhookEvent.kind == "message",
            or_(
                WhatsAppWebhookEvent.status == "failed",
                WhatsAppWebhookEvent.attempts >= 3,
            ),
            WhatsAppWebhookEvent.status != "processed",
            WhatsAppWebhookEvent.created_at >= now - timedelta(hours=24),
        )
    )
    if failed:
        out.append(
            Check(
                "whatsapp_failed_events",
                area,
                "problem",
                f"{_plural(failed, 'incoming message')} couldn't be processed",
                "pi tried 3 times and stopped (last 24 hours). Retrying reads them again; "
                "pi may reply late to those customers.",
                count=failed,
                fix="button",
                action="Retry them",
            )
        )
    return out


async def _messages(
    session: AsyncSession, scope: WorkspaceScope, fixed: dict[str, datetime], now: datetime
) -> list[Check]:
    area = "WhatsApp"
    pred = _pred(session, PiMessage, scope)
    stuck = await session.scalar(
        select(func.count())
        .select_from(PiMessage)
        .where(
            pred,
            PiMessage.direction == "outbound",
            PiMessage.status == "queued",
            PiMessage.created_at < now - STUCK,
        )
    )
    failed_rows = await session.execute(
        select(PiMessage.error_code, func.count())
        .where(
            pred,
            PiMessage.direction == "outbound",
            PiMessage.status == "failed",
            PiMessage.created_at >= now - timedelta(hours=24),
        )
        .group_by(PiMessage.error_code)
    )
    failed = {code or "unknown": n for code, n in failed_rows.all()}
    total_failed = sum(failed.values())
    out = [
        _auto(
            Check(
                "messages_stuck",
                area,
                "warning" if stuck else "ok",
                f"{_plural(stuck or 0, 'reply')} stuck before sending"
                if stuck
                else "Replies go out on time",
                "Queued for more than 5 minutes; pi sends them again by itself." if stuck else "",
                count=stuck or 0,
            ),
            fixed,
            now,
        )
    ]
    if total_failed:
        reasons = ", ".join(f"{code} ×{n}" for code, n in sorted(failed.items()))
        out.append(
            Check(
                "messages_failed",
                area,
                "problem" if total_failed >= 5 else "warning",
                f"{_plural(total_failed, 'message')} failed to send (24h)",
                f"{reasons}. They aren't resent automatically because WhatsApp may already "
                "have delivered them; open the chat to check.",
                count=total_failed,
                fix="settings",
                href="/pi/inbox",
            )
        )
    return out


async def _replies(
    session: AsyncSession, scope: WorkspaceScope, settings: Any, now: datetime
) -> list[Check]:
    area = "Replies"
    pred = _pred(session, PiAgentRun, scope) & (PiAgentRun.created_at >= now - timedelta(hours=24))
    total, failed, held, fallback = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(
                    or_(PiAgentRun.status == "failed", PiAgentRun.outcome == "provider_failure")
                ),
                func.count().filter(
                    PiAgentRun.error_code.is_not(None),
                    PiAgentRun.status != "failed",
                    PiAgentRun.outcome != "provider_failure",
                ),
                func.count().filter(PiAgentRun.fallback_used.is_(True)),
            ).where(pred)
        )
    ).one()
    out: list[Check] = []
    if not total:
        out.append(Check("replies_quality", area, "ok", "No replies to check in the last 24h"))
    else:
        codes = await session.execute(
            select(func.coalesce(PiAgentRun.error_code, PiAgentRun.outcome), func.count())
            .where(
                pred,
                or_(
                    PiAgentRun.error_code.is_not(None),
                    PiAgentRun.status == "failed",
                    PiAgentRun.outcome == "provider_failure",
                ),
            )
            .group_by(func.coalesce(PiAgentRun.error_code, PiAgentRun.outcome))
            .order_by(func.count().desc())
            .limit(4)
        )
        reasons = "; ".join(
            f"{REPLY_CODES.get(code or '', code or 'unknown')} ×{n}" for code, n in codes.all()
        )
        bad = failed + held
        status: Status = (
            "problem"
            if _share(failed, total) > 0.2
            else "warning"
            if _share(bad, total) > 0.1 or failed
            else "ok"
        )
        out.append(
            Check(
                "replies_quality",
                area,
                status,
                f"{bad} of {total} replies were held back or failed (24h)"
                if bad
                else f"All {total} replies passed their checks (24h)",
                f"{reasons}. Held-back replies go to your team instead of the customer."
                if bad
                else "",
                count=bad,
                fix="settings" if bad else None,
                href="/pi/analytics/agent-runs" if bad else None,
            )
        )
        if _share(fallback, total) > 0.3:
            out.append(
                Check(
                    "replies_fallback",
                    area,
                    "warning",
                    f"Backup AI used for {round(100 * _share(fallback, total))}% of replies",
                    "The main AI provider is failing or slow; replies still go out using "
                    "the backup.",
                    count=fallback,
                    fix="settings",
                    href="/pi/analytics/fallbacks",
                )
            )
    if settings is not None:
        from app.ai.manager import provider_status

        providers = [p for p in provider_status(settings)["providers"] if p["active"]]
        paused = [p["name"] for p in providers if p["circuit"] != "closed"]
        if not providers:
            out.append(
                Check(
                    "ai_providers",
                    area,
                    "problem",
                    "No AI provider is set up",
                    "pi can't write replies; every message goes to your team.",
                    fix="settings",
                    href="/pi/settings/provider-configuration",
                )
            )
        elif len(paused) == len(providers):
            out.append(
                Check(
                    "ai_providers",
                    area,
                    "problem",
                    "Every AI provider is paused",
                    f"Paused after errors: {', '.join(paused)}. They are retried by "
                    "themselves after a cool-down.",
                    count=len(paused),
                )
            )
        elif paused:
            out.append(
                Check(
                    "ai_providers",
                    area,
                    "warning",
                    f"{_plural(len(paused), 'AI provider')} paused",
                    f"{', '.join(paused)} paused after errors; the others answer meanwhile.",
                    count=len(paused),
                )
            )
        else:
            out.append(Check("ai_providers", area, "ok", "AI providers are working"))
    return out


async def _knowledge(
    session: AsyncSession, scope: WorkspaceScope, fixed: dict[str, datetime], now: datetime
) -> list[Check]:
    area, out = "Knowledge", []
    pred = _pred(session, KnowledgeDocument, scope)
    ready, stuck, failed = (
        await session.execute(
            select(
                func.count().filter(KnowledgeDocument.status == "ready"),
                func.count().filter(
                    KnowledgeDocument.status.in_(["pending", "processing"]),
                    KnowledgeDocument.updated_at < now - KNOWLEDGE_STUCK,
                ),
                func.count().filter(KnowledgeDocument.status == "failed"),
            ).where(pred)
        )
    ).one()
    if not ready:
        out.append(
            Check(
                "knowledge_empty",
                area,
                "problem",
                "pi has no knowledge about your business",
                "Without it pi can only pass questions to your team. Add your services, "
                "prices and FAQs.",
                fix="settings",
                href="/pi/knowledge",
            )
        )
    else:
        out.append(Check("knowledge_empty", area, "ok", f"{_plural(ready, 'document')} ready"))
    out.append(
        _auto(
            Check(
                "knowledge_stuck",
                area,
                "warning" if stuck else "ok",
                f"{_plural(stuck, 'document')} still being read"
                if stuck
                else "Documents are read on time",
                "Waiting more than 10 minutes; pi queues them again by itself." if stuck else "",
                count=stuck,
            ),
            fixed,
            now,
        )
    )
    if failed:
        out.append(
            Check(
                "knowledge_failed",
                area,
                "warning",
                f"{_plural(failed, 'document')} couldn't be read",
                "pi doesn't use them until they are read again.",
                count=failed,
                fix="button",
                action="Read again",
            )
        )
    out.append(await _business_name(session, scope, pred))
    return out


async def _business_name(session: AsyncSession, scope: WorkspaceScope, pred: Any) -> Check:
    """The name customers see (WhatsApp) should match the workspace and the knowledge."""
    key, area = "knowledge_business_name", "Knowledge"
    tenant = await session.get(Tenant, scope.tenant_id)
    workspace = (tenant.name if tenant else "").strip()
    display = (
        await session.scalar(
            select(WhatsAppConnection.display_name)
            .where(_pred(session, WhatsAppConnection, scope), WhatsAppConnection.status == "active")
            .limit(1)
        )
        or ""
    ).strip()

    async def mentions(name: str) -> int:
        if not name:
            return 0
        return (
            await session.scalar(
                select(func.count())
                .select_from(KnowledgeDocument)
                .where(
                    pred,
                    KnowledgeDocument.status == "ready",
                    KnowledgeDocument.body.ilike(f"%{name}%"),
                )
            )
            or 0
        )

    in_kb_workspace = await mentions(workspace)
    in_kb_display = await mentions(display) if display else 0
    differs = bool(display) and _norm(display) != _norm(workspace)
    if differs:
        where = (
            f"your knowledge mentions “{display}”"
            if in_kb_display and not in_kb_workspace
            else f"your knowledge mentions “{workspace}”"
            if in_kb_workspace and not in_kb_display
            else "your knowledge mentions both"
            if in_kb_display and in_kb_workspace
            else "your knowledge mentions neither"
        )
        return Check(
            key,
            area,
            "warning",
            "Business name doesn't match",
            f"Customers see “{display}” on WhatsApp but this workspace is called "
            f"“{workspace}”, and {where}. pi may introduce the business by the wrong name: "
            "use one name everywhere, or explain in your knowledge that both are the same "
            "business.",
            fix="settings",
            href="/pi/knowledge",
        )
    total_ready = await session.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(pred, KnowledgeDocument.status == "ready")
    )
    if total_ready and not in_kb_workspace and not in_kb_display:
        return Check(
            key,
            area,
            "warning",
            "Knowledge never says the business name",
            f"None of your documents mention “{display or workspace}”, the name customers "
            "see. Add a short “About us” so pi can introduce the business correctly.",
            fix="settings",
            href="/pi/knowledge",
        )
    return Check(key, area, "ok", "Business name matches what customers see")


async def _deals(session: AsyncSession, scope: WorkspaceScope, now: datetime) -> list[Check]:
    area, out = "Deals & payments", []
    quotes = _pred(session, Quote, scope)
    unpriced = await session.scalar(
        select(func.count())
        .select_from(Quote)
        .where(
            quotes,
            Quote.status == "draft",
            Quote.created_at < now - timedelta(hours=24),
            or_(
                Quote.total <= 0,
                exists().where(
                    QuoteLine.tenant_id == Quote.tenant_id,
                    QuoteLine.environment_id == Quote.environment_id,
                    QuoteLine.quote_id == Quote.id,
                    QuoteLine.unit_price <= 0,
                ),
            ),
        )
    )
    out.append(
        Check(
            "deals_unpriced",
            area,
            "warning" if unpriced else "ok",
            f"{_plural(unpriced or 0, 'proposal')} waiting for prices for over a day"
            if unpriced
            else "No proposals waiting for prices",
            "pi can't send a proposal without prices. Add them and pi sends it."
            if unpriced
            else "",
            count=unpriced or 0,
            fix="settings" if unpriced else None,
            href="/quotes?status=draft" if unpriced else None,
        )
    )
    invoiced = exists().where(
        Invoice.tenant_id == Quote.tenant_id,
        Invoice.environment_id == Quote.environment_id,
        Invoice.order_id == Quote.order_id,
        Invoice.status != "void",
    )
    no_invoice = await session.scalar(
        select(func.count())
        .select_from(Quote)
        .where(
            quotes,
            Quote.status == "accepted",
            Quote.updated_at < now - timedelta(hours=1),
            or_(Quote.order_id.is_(None), ~invoiced),
        )
    )
    if no_invoice:
        out.append(
            Check(
                "deals_no_invoice",
                area,
                "warning",
                f"{_plural(no_invoice, 'accepted proposal')} without an invoice",
                "The customer said yes but no invoice was made, so they can't pay yet.",
                count=no_invoice,
                fix="settings",
                href="/sales/pipeline",
            )
        )
    waiting = await session.scalar(
        select(func.count())
        .select_from(PiPaymentRequest)
        .where(
            _pred(session, PiPaymentRequest, scope),
            PiPaymentRequest.status == "awaiting_verification",
            PiPaymentRequest.updated_at < now - timedelta(hours=24),
        )
    )
    if waiting:
        out.append(
            Check(
                "payments_unverified",
                area,
                "warning",
                f"{_plural(waiting, 'payment')} waiting for you to verify",
                "Customers sent proof of a bank or cash payment more than a day ago.",
                count=waiting,
                fix="settings",
                href="/billing/payments",
            )
        )
    deal = await WorkspaceRepository(session, PiDealSettings, scope).find()
    labels = {
        "auto_proposal": "proposals",
        "auto_order": "orders",
        "auto_invoice": "invoices",
        "auto_payment_request": "payment links",
        "auto_followups": "deal reminders",
    }
    off = [label for name, label in labels.items() if deal is not None and not getattr(deal, name)]
    out.append(
        Check(
            "deals_automation",
            area,
            "warning" if off else "ok",
            "Some deal steps are manual" if off else "Deal steps run by themselves",
            f"Turned off: {', '.join(off)}. Your team does these by hand." if off else "",
            count=len(off),
            fix="settings" if off else None,
            href="/sales/pipeline" if off else None,
        )
    )
    return out


async def _meetings(session: AsyncSession, scope: WorkspaceScope, now: datetime) -> list[Check]:
    area, out = "Meetings", []
    waiting = await session.scalar(
        select(func.count())
        .select_from(PiStaffRequest)
        .where(
            _pred(session, PiStaffRequest, scope),
            PiStaffRequest.kind == "meeting",
            PiStaffRequest.status == "open",
            PiStaffRequest.created_at < now - timedelta(hours=2),
        )
    )
    out.append(
        Check(
            "meetings_waiting",
            area,
            "warning" if waiting else "ok",
            f"{_plural(waiting or 0, 'meeting request')} waiting over 2 hours"
            if waiting
            else "No meeting requests waiting",
            "Customers asked for a meeting and are waiting for a time." if waiting else "",
            count=waiting or 0,
            fix="settings" if waiting else None,
            href="/pi/requests" if waiting else None,
        )
    )
    calendar = await connectors.current(session, scope, "google_calendar")
    if calendar is not None and calendar.status not in connectors.USABLE:
        if calendar.status in ("expired", "error", "degraded", "disabled"):
            out.append(
                Check(
                    "calendar_reconnect",
                    area,
                    "problem",
                    "Google Calendar needs reconnecting",
                    "pi can't make Meet links or check free times until it is reconnected.",
                    fix="settings",
                    href="/pi/setup",
                )
            )
    return out


async def _followups(session: AsyncSession, scope: WorkspaceScope, now: datetime) -> list[Check]:
    area, out = "Follow-ups", []
    policy = await WorkspaceRepository(session, PiSettings, scope).find()
    config = (policy.whatsapp_config if policy else None) or {}
    href = "/pi/settings/whatsapp-configuration"
    if config.get("reminder_enabled", True) is False:
        out.append(
            Check(
                "followups_reminders",
                area,
                "warning",
                "Reminders are off",
                "pi won't remind customers who stop replying, even when they agreed to it.",
                fix="settings",
                href=href,
            )
        )
    else:
        out.append(Check("followups_reminders", area, "ok", "Reminders are on"))
    if config.get("check_in_enabled", True) is False:
        out.append(
            Check(
                "followups_check_ins",
                area,
                "warning",
                "Check-ins are off",
                "pi won't check in with customers who went quiet mid-conversation.",
                fix="settings",
                href=href,
            )
        )
    brief = PiConversation.service_brief
    recent = _pred(session, PiConversation, scope) & (
        PiConversation.last_message_at >= now - timedelta(days=30)
    )
    confirmed, granted = (
        await session.execute(
            select(
                func.count().filter(brief["projects"].contains([{"status": "confirmed"}])),
                func.count().filter(brief["reminder_consent"].astext == "granted"),
            ).where(recent)
        )
    ).one()
    if confirmed >= 3 and not granted:
        out.append(
            Check(
                "followups_consent",
                area,
                "warning",
                "No customer has agreed to reminders",
                f"{_plural(confirmed, 'customer')} confirmed a brief this month, but none "
                "said yes to reminders, so pi can't follow up after 24 hours.",
                count=confirmed,
            )
        )
    return out


async def _maps(
    session: AsyncSession, scope: WorkspaceScope, fixed: dict[str, datetime], now: datetime
) -> list[Check]:
    stale = len(await _stale_maps(session, scope, now, limit=200))
    return [
        _auto(
            Check(
                "maps_stale",
                "Problem maps",
                "warning" if stale > 10 else "ok",
                f"{_plural(stale, 'customer map')} out of date"
                if stale
                else "Customer maps are up to date",
                f"pi refreshes up to {MAP_REFRESH_PER_RUN} every few minutes." if stale else "",
                count=stale,
            ),
            fixed,
            now,
        )
    ]


async def _stale_maps(
    session: AsyncSession, scope: WorkspaceScope, now: datetime, *, limit: int
) -> list[PiConversation]:
    from app.modules.pi_customer.service import report_current

    rows = await session.scalars(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .where(
            PiConversation.last_message_at >= now - timedelta(days=7),
            # A settled chat: a live one changes again in a moment.
            PiConversation.last_message_at < now - timedelta(minutes=10),
        )
        .order_by(PiConversation.last_message_at.desc())
        .limit(limit)
    )
    return [c for c in rows if not report_current(c)]


async def _api(session: AsyncSession, scope: WorkspaceScope, now: datetime) -> list[Check]:
    """APIs pi depends on, from what the app records: AI provider calls
    (ai_usage_events), connected apps (integration_connections) and outgoing webhooks
    (integration_deliveries). The server's own HTTP responses are only logged, not
    stored, so they can't be counted here."""
    area, out = "API", []
    since = now - timedelta(hours=24)
    total, failed, slow = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(AIUsageEvent.status == "failed"),
                func.count().filter(AIUsageEvent.latency_ms > SLOW_AI_MS),
            ).where(_pred(session, AIUsageEvent, scope), AIUsageEvent.created_at >= since)
        )
    ).one()
    if total and (_share(failed, total) > 0.1 or slow >= 5):
        kinds = await session.execute(
            select(AIUsageEvent.error_kind, func.count())
            .where(
                _pred(session, AIUsageEvent, scope),
                AIUsageEvent.created_at >= since,
                AIUsageEvent.status == "failed",
            )
            .group_by(AIUsageEvent.error_kind)
            .order_by(func.count().desc())
            .limit(3)
        )
        why = ", ".join(f"{k or 'error'} ×{n}" for k, n in kinds.all())
        out.append(
            Check(
                "api_ai_calls",
                area,
                "problem" if _share(failed, total) > 0.5 else "warning",
                f"AI calls: {failed} of {total} failed, {slow} slow (24h)",
                (f"Errors: {why}. " if why else "")
                + f"Slow means over {SLOW_AI_MS // 1000} seconds. Failed calls are retried "
                "with the backup provider.",
                count=failed + slow,
                fix="settings",
                href="/pi/analytics/ai-usage",
            )
        )
    else:
        out.append(
            Check(
                "api_ai_calls",
                area,
                "ok",
                f"AI calls are healthy ({total} in 24h)" if total else "No AI calls in 24h",
            )
        )
    broken = list(
        await session.scalars(
            WorkspaceRepository(session, IntegrationConnection, scope)
            .select()
            .where(
                or_(
                    IntegrationConnection.status.in_(["expired", "error"]),
                    and_(
                        IntegrationConnection.status.in_(["connected", "degraded"]),
                        IntegrationConnection.health == "failing",
                    ),
                )
            )
            .limit(20)
        )
    )
    if broken:
        names = ", ".join(sorted({c.display_name for c in broken}))
        out.append(
            Check(
                "api_connected_apps",
                area,
                "problem",
                f"{_plural(len(broken), 'connected app')} failing",
                f"{names}: sign-in expired or calls are failing. Reconnect to fix.",
                count=len(broken),
                fix="settings",
                href="/settings/integrations/health",
            )
        )
    else:
        out.append(Check("api_connected_apps", area, "ok", "Connected apps are working"))
    deliveries = await session.scalar(
        select(func.count())
        .select_from(Delivery)
        .where(
            _pred(session, Delivery, scope),
            Delivery.status.in_(["failed", "dead_letter"]),
            Delivery.updated_at >= since,
        )
    )
    if deliveries:
        out.append(
            Check(
                "api_webhooks",
                area,
                "warning",
                f"{_plural(deliveries, 'outgoing webhook')} failed (24h)",
                "Another system didn't accept events sent to it.",
                count=deliveries,
                fix="settings",
                href="/settings/integrations/failures",
            )
        )
    return out


async def run_checks(
    session: AsyncSession, scope: WorkspaceScope, settings: Any = None
) -> list[Check]:
    """Every check for this business, computed now. ``settings`` adds the AI provider
    status (in-process circuit state; no provider is called)."""
    now = datetime.now(UTC)
    fixed = await _last_fixes(session, scope)
    checks: list[Check] = []
    checks += await _whatsapp(session, scope, fixed, now)
    checks += await _messages(session, scope, fixed, now)
    checks += await _replies(session, scope, settings, now)
    checks += await _knowledge(session, scope, fixed, now)
    checks += await _deals(session, scope, now)
    checks += await _meetings(session, scope, now)
    checks += await _followups(session, scope, now)
    checks += await _maps(session, scope, fixed, now)
    checks += await _api(session, scope, now)
    order = {"problem": 0, "warning": 1, "fixed": 2, "ok": 3}
    return sorted(checks, key=lambda c: (AREAS.index(c.area), order[c.status]))


# ---- Learning from gaps -------------------------------------------------------------


async def knowledge_gaps(
    session: AsyncSession, scope: WorkspaceScope, *, days: int = 30, limit: int = 10
) -> list[dict[str, Any]]:
    """Questions pi couldn't answer, across chats, most asked first."""
    rows = await session.execute(
        select(PiConversation.service_brief["knowledge_gaps"], PiConversation.last_message_at)
        .where(
            _pred(session, PiConversation, scope),
            PiConversation.last_message_at >= datetime.now(UTC) - timedelta(days=days),
            PiConversation.service_brief.has_key("knowledge_gaps"),
        )
        .limit(500)
    )
    found: dict[str, dict[str, Any]] = {}
    for gaps, at in rows.all():
        if not isinstance(gaps, list):
            continue
        for gap in {str(g).strip() for g in gaps if str(g).strip()}:
            key = _norm(gap)
            if not key:
                continue
            item = found.setdefault(key, {"question": gap[:200], "asked": 0, "last_asked_at": at})
            item["asked"] += 1
            if at and at > item["last_asked_at"]:
                item["last_asked_at"] = at
    ranked = sorted(found.values(), key=lambda i: (-i["asked"], -i["last_asked_at"].timestamp()))
    return [
        {**item, "last_asked_at": item["last_asked_at"].isoformat(), "href": "/pi/knowledge"}
        for item in ranked[:limit]
    ]


async def learned(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """The request desk: team answers that became knowledge, and questions still open."""
    pred = _pred(session, PiStaffRequest, scope)
    since = datetime.now(UTC) - timedelta(days=30)
    taught, open_questions = (
        await session.execute(
            select(
                func.count().filter(
                    PiStaffRequest.knowledge_document_id.is_not(None),
                    PiStaffRequest.updated_at >= since,
                ),
                func.count().filter(
                    PiStaffRequest.status == "open", PiStaffRequest.kind == "question"
                ),
            ).where(pred)
        )
    ).one()
    drafts = await session.scalar(
        select(func.count())
        .select_from(PiKnowledgeDraft)
        .where(_pred(session, PiKnowledgeDraft, scope), PiKnowledgeDraft.status == "draft")
    )
    return {
        "answers_learned_30d": taught,
        "open_questions": open_questions,
        "drafts_waiting": drafts or 0,
    }


# ---- History -------------------------------------------------------------------------


def _day(column: Any) -> Any:
    return func.to_char(column, literal_column("'YYYY-MM-DD'"))


async def fixed_recently(session: AsyncSession, scope: WorkspaceScope) -> dict[str, Any]:
    rows = list(
        await session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == scope.tenant_id,
                AuditEvent.environment_id == scope.environment_id,
                AuditEvent.action == FIXED_ACTION,
                AuditEvent.created_at >= datetime.now(UTC) - timedelta(days=7),
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(200)
        )
    )
    total = sum(int((r.details or {}).get("count") or 1) for r in rows)
    return {
        "total": total,
        "items": [
            {
                "check": (r.details or {}).get("check"),
                "what": (r.details or {}).get("what"),
                "count": int((r.details or {}).get("count") or 1),
                "at": r.created_at.isoformat(),
            }
            for r in rows[:20]
        ],
    }


async def trends(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    """Per day, last 7 days: replies sent, replies held back/failed, failed sends, fixes."""
    today = datetime.now(UTC).date()
    start = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=UTC)
    days = {
        (today - timedelta(days=n)).isoformat(): {
            "day": (today - timedelta(days=n)).isoformat(),
            "replies": 0,
            "held": 0,
            "failed_sends": 0,
            "fixes": 0,
        }
        for n in range(6, -1, -1)
    }
    messages = await session.execute(
        select(
            _day(PiMessage.created_at),
            func.count().filter(
                PiMessage.sender_type == "ai",
                PiMessage.status.in_(["sent", "delivered", "read"]),
            ),
            func.count().filter(PiMessage.status == "failed"),
        )
        .where(
            _pred(session, PiMessage, scope),
            PiMessage.direction == "outbound",
            PiMessage.created_at >= start,
        )
        .group_by(_day(PiMessage.created_at))
    )
    for day, replies, failed in messages.all():
        if day in days:
            days[day]["replies"], days[day]["failed_sends"] = replies, failed
    runs = await session.execute(
        select(
            _day(PiAgentRun.created_at),
            func.count().filter(
                or_(
                    PiAgentRun.error_code.is_not(None),
                    PiAgentRun.status == "failed",
                    PiAgentRun.outcome == "provider_failure",
                )
            ),
        )
        .where(_pred(session, PiAgentRun, scope), PiAgentRun.created_at >= start)
        .group_by(_day(PiAgentRun.created_at))
    )
    for day, held in runs.all():
        if day in days:
            days[day]["held"] = held
    fixes = await session.execute(
        select(
            _day(AuditEvent.created_at),
            func.coalesce(
                func.sum(cast(func.coalesce(AuditEvent.details["count"].astext, "1"), Integer)),
                0,
            ),
        )
        .where(
            AuditEvent.tenant_id == scope.tenant_id,
            AuditEvent.environment_id == scope.environment_id,
            AuditEvent.action == FIXED_ACTION,
            AuditEvent.created_at >= start,
        )
        .group_by(_day(AuditEvent.created_at))
    )
    for day, count in fixes.all():
        if day in days:
            days[day]["fixes"] = int(count or 0)
    return list(days.values())


async def state(session: AsyncSession, scope: WorkspaceScope, settings: Any = None) -> dict:
    from app.modules.pi_saas.health_selftest import latest

    checks = await run_checks(session, scope, settings)
    value = score(checks)
    problems = sum(1 for c in checks if c.status == "problem")
    return {
        "score": value,
        "verdict": verdict(value, problems),
        "counts": {
            s: sum(1 for c in checks if c.status == s)
            for s in ("problem", "warning", "fixed", "ok")
        },
        "checks": [c.view() for c in checks],
        "areas": list(AREAS),
        "fixed_recently": await fixed_recently(session, scope),
        "trends": await trends(session, scope),
        "gaps": await knowledge_gaps(session, scope),
        "learning": await learned(session, scope),
        "self_tests": await latest(session, scope),
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ---- Healing -------------------------------------------------------------------------


async def _fixed(
    session: AsyncSession, scope: WorkspaceScope, ctx: Context, check: str, what: str, n: int
) -> None:
    if n <= 0:
        return
    await record(
        session,
        FIXED_ACTION,
        scope=scope,
        entity_type="pi_health",
        details={"check": check, "what": what, "count": n},
    )
    ctx.fixes.append({"check": check, "what": what, "count": n})


async def _requeue_messages(session: AsyncSession, scope: WorkspaceScope, ctx: Context) -> None:
    cutoff = datetime.now(UTC) - STUCK
    ids = list(
        await session.scalars(
            select(PiMessage.id)
            .where(
                _pred(session, PiMessage, scope),
                PiMessage.direction == "outbound",
                PiMessage.status == "queued",
                PiMessage.created_at < cutoff,
                PiMessage.updated_at < cutoff,
            )
            .order_by(PiMessage.created_at)
            .limit(50)
        )
    )
    bucket = int(datetime.now(UTC).timestamp() // 300)
    done = 0
    for message_id in ids:
        if await ctx.enqueue(
            "send_pi_message", str(message_id), f"health:send:{message_id}:{bucket}"
        ):
            done += 1
    await _fixed(
        session, scope, ctx, "messages_stuck", f"Queued {_plural(done, 'stuck reply')} again", done
    )


async def _requeue_events(session: AsyncSession, scope: WorkspaceScope, ctx: Context) -> None:
    ids = list(
        await session.scalars(
            select(WhatsAppWebhookEvent.id)
            .where(
                WhatsAppWebhookEvent.tenant_id == scope.tenant_id,
                WhatsAppWebhookEvent.environment_id == scope.environment_id,
                WhatsAppWebhookEvent.status.in_(["received", "queued"]),
                WhatsAppWebhookEvent.attempts < 3,
                WhatsAppWebhookEvent.created_at < datetime.now(UTC) - STUCK,
            )
            .order_by(WhatsAppWebhookEvent.created_at)
            .limit(50)
        )
    )
    bucket = int(datetime.now(UTC).timestamp() // 300)
    done = 0
    for event_id in ids:
        if await ctx.enqueue(
            "process_pi_event", str(event_id), f"health:event:{event_id}:{bucket}"
        ):
            done += 1
    await _fixed(
        session,
        scope,
        ctx,
        "whatsapp_stuck_events",
        f"Queued {_plural(done, 'incoming message')} again",
        done,
    )


async def _requeue_documents(session: AsyncSession, scope: WorkspaceScope, ctx: Context) -> None:
    ids = list(
        await session.scalars(
            select(KnowledgeDocument.id)
            .where(
                _pred(session, KnowledgeDocument, scope),
                KnowledgeDocument.status.in_(["pending", "processing"]),
                KnowledgeDocument.updated_at < datetime.now(UTC) - KNOWLEDGE_STUCK,
            )
            .limit(20)
        )
    )
    bucket = int(datetime.now(UTC).timestamp() // 300)
    done = 0
    for document_id in ids:
        if await ctx.enqueue(
            "index_document", str(document_id), f"health:index:{document_id}:{bucket}"
        ):
            done += 1
    await _fixed(
        session,
        scope,
        ctx,
        "knowledge_stuck",
        f"Started reading {_plural(done, 'document')} again",
        done,
    )


async def _draft_answers(session: AsyncSession, scope: WorkspaceScope, ctx: Context) -> None:
    """Learning from the team: a question the team answered (without saving it as
    knowledge) becomes a knowledge DRAFT for the owner to approve. Never published here."""
    has_draft = (
        select(PiKnowledgeDraft.id)
        .where(
            PiKnowledgeDraft.tenant_id == PiStaffRequest.tenant_id,
            PiKnowledgeDraft.environment_id == PiStaffRequest.environment_id,
            PiKnowledgeDraft.staff_request_id == PiStaffRequest.id,
        )
        .exists()
    )
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiStaffRequest, scope)
            .select()
            .where(
                PiStaffRequest.kind == "question",
                PiStaffRequest.status == "answered",
                PiStaffRequest.answer.is_not(None),
                PiStaffRequest.knowledge_document_id.is_(None),
                ~has_draft,
            )
            .order_by(PiStaffRequest.resolved_at.desc().nulls_last())
            .limit(10)
        )
    )
    drafts = WorkspaceRepository(session, PiKnowledgeDraft, scope)
    for row in rows:
        question = " ".join(row.question.split())
        await drafts.add(
            drafts.new(
                origin="ask_owner",
                title=(question[:117] + "...") if len(question) > 120 else question,
                content=f"Q: {row.question}\n\nA: {row.answer}",
                staff_request_id=row.id,
                status="draft",
            )
        )
    await _fixed(
        session,
        scope,
        ctx,
        "learning_drafts",
        f"Drafted {_plural(len(rows), 'team answer')} as knowledge for you to approve",
        len(rows),
    )


async def _refresh_maps(session: AsyncSession, scope: WorkspaceScope, ctx: Context) -> None:
    """Best effort, at most a few per run. ``analyse`` commits on its own, so this runs
    last, outside any savepoint."""
    if ctx.settings is None or ctx.http is None:
        return
    from app.modules.pi_customer.service import analyse, report_current

    tenant = await session.get(Tenant, scope.tenant_id)
    done = 0
    for conversation in await _stale_maps(session, scope, datetime.now(UTC), limit=20):
        if done >= MAP_REFRESH_PER_RUN:
            break
        connection = await session.get(WhatsAppConnection, conversation.connection_id)
        if connection is None:
            continue
        try:
            await analyse(
                session,
                ctx.settings,
                ctx.http,
                ctx.sessions,
                conversation,
                connection,
                tenant.name if tenant else "us",
            )
        except Exception:  # noqa: BLE001 - the saved map stays; tried again next run
            logger.warning("pi_health_map_refresh_failed", exc_info=True)
            await session.rollback()
            break
        await session.refresh(conversation)
        if not report_current(conversation):
            break  # AI unavailable right now: stop, don't spend the run on retries.
        done += 1
    if done:
        await _fixed(
            session, scope, ctx, "maps_stale", f"Refreshed {_plural(done, 'customer map')}", done
        )
        await session.commit()


async def heal_scope(session: AsyncSession, scope: WorkspaceScope, ctx: Context) -> list[dict]:
    """The safe automatic fixes for one business. Each runs in its own savepoint, so one
    failure never stops the rest."""
    for fix in (_requeue_messages, _requeue_events, _requeue_documents, _draft_answers):
        try:
            async with session.begin_nested():
                await fix(session, scope, ctx)
        except Exception:  # noqa: BLE001 - the next fix and the next run still go ahead
            logger.warning("pi_health_fix_failed", extra={"fix": fix.__name__}, exc_info=True)
    await session.commit()
    try:
        await _refresh_maps(session, scope, ctx)
    except Exception:  # noqa: BLE001
        logger.warning("pi_health_maps_failed", exc_info=True)
        await session.rollback()
    return ctx.fixes


async def heal(ctx: dict[str, Any]) -> int:
    """Cron job: run the safe fixes for every business with an active WhatsApp number."""
    from app.modules.pi.runtime import system_scope

    async def enqueue(name: str, arg: str, job_id: str) -> bool:
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job(name, arg, _job_id=job_id)
            return True
        if ctx.get("queue"):
            return bool(await ctx["queue"].enqueue(name, arg, job_id=job_id))
        return False

    async with ctx["sessions"]() as session:
        connections = list(
            await session.scalars(
                select(WhatsAppConnection)
                .where(WhatsAppConnection.status == "active")
                .order_by(WhatsAppConnection.tenant_id, WhatsAppConnection.environment_id)
            )
        )
    seen: set[tuple[Any, Any]] = set()
    total = 0
    for connection in connections:
        key = (connection.tenant_id, connection.environment_id)
        if key in seen:
            continue
        seen.add(key)
        async with ctx["sessions"]() as session:
            try:
                scope = await system_scope(session, connection)
                if scope is None:
                    continue
                run = Context(
                    enqueue=enqueue,
                    settings=ctx.get("settings"),
                    http=ctx.get("http"),
                    sessions=ctx.get("sessions"),
                )
                total += sum(f["count"] for f in await heal_scope(session, scope, run))
            except Exception:  # noqa: BLE001 - one business never stops the others
                logger.warning("pi_health_heal_failed", exc_info=True)
    return total
