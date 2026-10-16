"""Team alerts on WhatsApp: when a card on the team board is given to someone, or one
of their cards is due within the hour, pi tells that person on WhatsApp from the
business's own number.

The setting lives in ``pi_settings.whatsapp_config["team_alerts"]`` (no table):
``{"enabled": bool, "numbers": {user_id: digits}, "template_name", "template_language"}``.
Only numbers saved there are ever messaged, and only for active members.

WhatsApp's rules, applied at send time:
- the person's number messaged the business number in the last 24 hours (a chat with
  that number has ``last_inbound_at`` within 24h) → a short free-text message;
- otherwise, if the business set an approved template (body variables {{1}} name,
  {{2}} task, {{3}} due) → that template;
- otherwise no WhatsApp: the in-app notification is all they get.

This is its own path, not a customer conversation: nothing is queued as a ``PiMessage``
and pi's customer replies never see it. Each alert is sent at most once: the key
``team-alert:<reason>:<task>:<user>`` (plus the due time for reminders) is claimed in
the audit log under an advisory lock and committed before the send, so a retry or a
second worker never sends it twice.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.memberships.models import Membership
from app.modules.notifications.service import notify
from app.modules.pi.models import PiConversation, PiSettings, WhatsAppConnection
from app.modules.pi_saas.models import PiBusinessAccount, PiTask
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

CONFIG_KEY = "team_alerts"
WINDOW = timedelta(hours=24)
DUE_SOON = timedelta(hours=1)
LIVE = ("open", "in_progress", "blocked")
ACTION = "pi.team_alert"
NAME = re.compile(r"[a-z0-9_]{1,512}")
LANGUAGE = re.compile(r"[a-z]{2,3}(?:_[A-Z]{2})?")


# ---- The setting ----------------------------------------------------------------------


def digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def valid_number(value: str) -> bool:
    return 8 <= len(value) <= 15 and not value.startswith("0")


def read_config(whatsapp_config: dict[str, Any] | None) -> dict[str, Any]:
    """The saved setting, cleaned: anything malformed is ignored, never sent to."""
    raw = (whatsapp_config or {}).get(CONFIG_KEY)
    raw = raw if isinstance(raw, dict) else {}
    numbers = raw.get("numbers")
    numbers = numbers if isinstance(numbers, dict) else {}
    clean: dict[str, str] = {}
    for user_id, number in numbers.items():
        try:
            UUID(str(user_id))
        except ValueError:
            continue
        found = digits(number)
        if valid_number(found):
            clean[str(user_id)] = found
    name = str(raw.get("template_name") or "")
    language = str(raw.get("template_language") or "")
    template = NAME.fullmatch(name) and LANGUAGE.fullmatch(language)
    return {
        # On by default: nobody is messaged until a number is saved for them.
        "enabled": raw.get("enabled", True) is not False,
        "numbers": clean,
        "template_name": name if template else "",
        "template_language": language if template else "",
    }


async def _policy(session: AsyncSession, scope: WorkspaceScope) -> PiSettings:
    from app.modules.pi.configuration import settings_row

    return await settings_row(session, scope)


async def active_members(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(PlatformUser.id, PlatformUser.display_name, PlatformUser.email)
        .join(Membership, Membership.user_id == PlatformUser.id)
        .where(
            Membership.tenant_id == scope.tenant_id,
            Membership.status == "active",
            PlatformUser.status == "active",
        )
        .order_by(PlatformUser.display_name)
        .limit(200)
    )
    return [
        {"id": user_id, "name": name or (email or "").split("@")[0]}
        for user_id, name, email in rows
    ]


async def connection_for(session: AsyncSession, scope: WorkspaceScope) -> WhatsAppConnection | None:
    from app.modules.pi_saas.campaigns import production_connection

    return await production_connection(session, scope)


async def window_open(
    session: AsyncSession, scope: WorkspaceScope, connection: WhatsAppConnection, number: str
) -> bool:
    """That number messaged the business number in the last 24 hours."""
    last = await session.scalar(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .with_only_columns(func.max(PiConversation.last_inbound_at))
        .where(
            PiConversation.connection_id == connection.id,
            PiConversation.contact_wa_id == number,
        )
    )
    return last is not None and last >= datetime.now(UTC) - WINDOW


async def team_view(
    session: AsyncSession, scope: WorkspaceScope, *, show_numbers: bool
) -> dict[str, Any]:
    policy = await _policy(session, scope)
    config = read_config(policy.whatsapp_config)
    connection = await connection_for(session, scope)
    members = []
    for member in await active_members(session, scope):
        number = config["numbers"].get(str(member["id"]), "")
        visible = show_numbers or member["id"] == scope.user_id
        members.append(
            {
                **member,
                "whatsapp": number if visible else ("saved" if number else ""),
                "window_open": bool(
                    number
                    and connection is not None
                    and await window_open(session, scope, connection, number)
                ),
            }
        )
    return {
        "enabled": config["enabled"],
        "template_name": config["template_name"],
        "template_language": config["template_language"],
        "business_number": connection.display_phone_number if connection else None,
        "members": members,
    }


async def save_config(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    enabled: bool | None = None,
    numbers: dict[str, str] | None = None,
    template_name: str | None = None,
    template_language: str | None = None,
) -> None:
    """Merge a change into the setting. Numbers: digits with country code (8-15), one
    per active member, never two members on one number; an empty value removes it."""
    policy = await _policy(session, scope)
    config = read_config(policy.whatsapp_config)
    if enabled is not None:
        config["enabled"] = enabled
    if numbers is not None:
        team = {str(m["id"]) for m in await active_members(session, scope)}
        connection = await connection_for(session, scope)
        own = digits(connection.display_phone_number) if connection else ""
        for user_id, value in numbers.items():
            try:
                user_id = str(UUID(str(user_id)))
            except ValueError:
                raise BusinessRuleViolation("MEMBER_UNKNOWN", "Pick someone on your team") from None
            if user_id not in team:
                raise BusinessRuleViolation("MEMBER_UNKNOWN", "Pick someone on your team")
            number = digits(value)
            if not number:
                config["numbers"].pop(user_id, None)
                continue
            if not valid_number(number):
                raise BusinessRuleViolation(
                    "PHONE_INVALID", "Enter the WhatsApp number with country code (8-15 digits)"
                )
            if own and number == own:
                raise BusinessRuleViolation(
                    "PHONE_IS_BUSINESS", "That's the business's own WhatsApp number"
                )
            config["numbers"][user_id] = number
        taken: dict[str, str] = {}
        for user_id, number in config["numbers"].items():
            if number in taken:
                raise BusinessRuleViolation(
                    "PHONE_DUPLICATE", "Two team members can't share one WhatsApp number"
                )
            taken[number] = user_id
    if template_name is not None or template_language is not None:
        name = (template_name if template_name is not None else config["template_name"]).strip()
        language = (
            template_language if template_language is not None else config["template_language"]
        ).strip()
        if name or language:
            if not NAME.fullmatch(name) or not LANGUAGE.fullmatch(language):
                raise BusinessRuleViolation(
                    "TEMPLATE_INVALID",
                    "Enter the template's name (lowercase, like task_assigned) and its "
                    "language code (like en or en_US)",
                )
        config["template_name"], config["template_language"] = name, language
    policy.whatsapp_config = {**(policy.whatsapp_config or {}), CONFIG_KEY: config}
    await session.flush()
    await record(
        session,
        "pi.team_alerts_updated",
        scope=scope,
        entity_type="pi_settings",
        entity_id=policy.id,
        details={
            "enabled": config["enabled"],
            "members_with_number": len(config["numbers"]),
            "template": bool(config["template_name"]),
        },
    )


# ---- The message ----------------------------------------------------------------------


def when_text(when: datetime, timezone: str) -> str:
    """ "Tue 14 Oct, 5:00 PM" in the business's time zone."""
    try:
        zone = ZoneInfo(timezone or "UTC")
    except (ValueError, ZoneInfoNotFoundError):
        zone = ZoneInfo("UTC")
    local = (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(zone)
    return f"{local:%a} {local.day} {local:%b}, {local.hour % 12 or 12}:{local:%M} {local:%p}"


async def board_link(session: AsyncSession, scope: WorkspaceScope, settings: Any) -> str:
    """The team board in the app this business uses: pi app for pi businesses."""
    pi_business = await session.scalar(
        select(PiBusinessAccount.id).where(PiBusinessAccount.tenant_id == scope.tenant_id)
    )
    pi_base = (getattr(settings, "pi_app_public_url", "") or "").rstrip("/")
    if pi_business is not None and pi_base:
        return f"{pi_base}/team"
    return f"{settings.web_base}/pi/team"


async def _about(session: AsyncSession, scope: WorkspaceScope, task: PiTask) -> str:
    """ "Ayesha Khan · Branding for Crescent Bakers": who and which project."""
    from app.modules.pi_saas import team_board

    parts = []
    if task.customer_id:
        customer = await WorkspaceRepository(session, Customer, scope).find(
            Customer.id == task.customer_id
        )
        if customer is not None and customer.name:
            parts.append(customer.name)
    try:
        project = (await team_board._context(session, scope, [task])).get(str(task.id), {})
    except Exception:  # noqa: BLE001 - the message goes without the project name
        project = {}
    if project.get("project"):
        parts.append(str(project["project"]))
    return " · ".join(parts)


def _short(value: str, limit: int) -> str:
    one = " ".join((value or "").split())
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


# ---- Sending --------------------------------------------------------------------------


async def _claimed(session: AsyncSession, scope: WorkspaceScope, key: str) -> bool:
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
    found = await session.scalar(
        select(AuditEvent.id)
        .where(
            AuditEvent.tenant_id == scope.tenant_id,
            AuditEvent.action == ACTION,
            AuditEvent.details["alert"].astext == key,
        )
        .limit(1)
    )
    return found is not None


async def _note(
    session: AsyncSession,
    scope: WorkspaceScope,
    key: str,
    result: str,
    task_id: UUID | None,
    user_id: UUID,
    outcome: str = "success",
) -> None:
    await record(
        session,
        ACTION,
        scope=scope,
        entity_type="pi_task" if task_id else "membership",
        entity_id=task_id or user_id,
        outcome=outcome,
        details={"alert": key, "result": result, "user_id": str(user_id)},
    )


async def deliver(
    ctx: dict[str, Any],
    tenant_id: str,
    environment_id: str,
    reason: str,
    task_id: str,
    user_id: str,
    assigner: str = "",
) -> str:
    """Send one team alert (``reason``: "assigned", "due" or "test"). Returns what
    happened: "sent", "template", "no_window", "no_number", "off", "duplicate", ..."""
    from app.modules.pi.runtime import system_scope

    async with ctx["sessions"]() as session:
        connection = await session.scalar(
            select(WhatsAppConnection).where(
                WhatsAppConnection.tenant_id == UUID(tenant_id),
                WhatsAppConnection.environment_id == UUID(environment_id),
                WhatsAppConnection.status == "active",
            )
        )
        scope = await system_scope(session, connection) if connection else None
        if scope is None or connection is None:
            return "no_whatsapp"
        policy = await _policy(session, scope)
        config = read_config(policy.whatsapp_config)
        if not config["enabled"]:
            return "off"
        member = UUID(user_id)
        number = config["numbers"].get(str(member))
        if not number:
            return "no_number"
        if member not in {m["id"] for m in await active_members(session, scope)}:
            return "not_member"
        task: PiTask | None = None
        if reason != "test":
            task = await WorkspaceRepository(session, PiTask, scope).find(
                PiTask.id == UUID(task_id)
            )
            if task is None or task.assignee_user_id != member or task.status not in LIVE:
                return "stale"
        key = f"team-alert:{reason}:{task.id if task else 'test'}:{member}"
        if reason == "due" and task is not None and task.due_at is not None:
            key += f":{task.due_at:%Y%m%d%H%M}"
        elif reason == "test":
            key += f":{datetime.now(UTC):%Y%m%d%H%M}"
        if await _claimed(session, scope, key):
            return "duplicate"
        task_ref = task.id if task else None
        from app.modules.pi_saas.entitlement import entitlement, meter

        allowed = await entitlement(session, scope.tenant_id, scope.environment_id)
        if not allowed.sending:
            await _note(session, scope, key, "plan_inactive", task_ref, member, "denied")
            await session.commit()
            return "plan_inactive"

        names = {m["id"]: m["name"] for m in await active_members(session, scope)}
        name = (names.get(member) or "there").split()[0]
        link = await board_link(session, scope, ctx["settings"])
        due = when_text(task.due_at, policy.timezone) if task and task.due_at else ""
        if task is None:
            title, about = "Test message", ""
            body = (
                f"pi: Hi {name}, this is a test from your team board. You'll get your "
                f"tasks here. Open: {link}"
            )
        else:
            title, about = _short(task.title, 120), await _about(session, scope, task)
            what = " · ".join(part for part in (title, about) if part)
            if reason == "due":
                body = f"pi: Reminder, due {due}: {what}. Open: {link}"
            else:
                by = assigner or "Your team"
                body = f"pi: {by} gave you a task: {what}" + (f" · due {due}" if due else "")
                body += f". Open: {link}"

        if await window_open(session, scope, connection, number):
            mode = "sent"
        elif config["template_name"]:
            mode = "template"
        else:
            await _note(session, scope, key, "no_window", task_ref, member)
            await session.commit()
            return "no_window"
        # Claimed and committed before the send: a crash after this never sends twice.
        await _note(session, scope, key, f"sending:{mode}", task_ref, member)
        await session.commit()

        from app.integrations.whatsapp_bridge import token as connection_token
        from app.modules.pi.whatsapp import WhatsApp

        result = mode
        try:
            whatsapp = WhatsApp(ctx["settings"], ctx["http"], connection.provider)
            token = await connection_token(session, ctx["settings"], connection)
            if mode == "sent":
                await whatsapp.send(connection.phone_number_id, number, body, token)
            else:
                values = [name, " · ".join(p for p in (title, about) if p), due or "no due date"]
                await whatsapp.send_template_values(
                    connection.phone_number_id,
                    number,
                    {"name": config["template_name"], "language": config["template_language"]},
                    values,
                    token,
                )
            await meter(session, scope.tenant_id, scope.environment_id, "messages_out")
            if mode == "template":
                await meter(session, scope.tenant_id, scope.environment_id, "template_messages")
            connection.last_outbound_at = datetime.now(UTC)
        except BusinessRuleViolation as exc:
            result = f"failed:{exc.code}"[:60]
            logger.warning("pi_team_alert_failed", extra={"code": exc.code})
        await _note(
            session,
            scope,
            key,
            result,
            task_ref,
            member,
            "failure" if result.startswith("failed") else "success",
        )
        await session.commit()
        return result


async def send_team_alert(
    ctx: dict[str, Any],
    tenant_id: str,
    environment_id: str,
    reason: str,
    task_id: str,
    user_id: str,
    assigner: str = "",
) -> str:
    """Worker job: one alert. Never raises after its claim, so arq never retries a send."""
    try:
        return await deliver(ctx, tenant_id, environment_id, reason, task_id, user_id, assigner)
    except Exception:  # noqa: BLE001 - an alert is best effort; the in-app note stays
        logger.warning("pi_team_alert_error", exc_info=True)
        return "error"


async def enqueue(
    queue: Any, scope: WorkspaceScope, reason: str, task_id: UUID | None, user_id: UUID
) -> None:
    """After the caller committed: send the alert from the worker."""
    job = f"team-alert:{reason}:{task_id or 'test'}:{user_id}:{datetime.now(UTC):%Y%m%d%H%M%S}"
    try:
        await queue.enqueue(
            "send_team_alert",
            str(scope.tenant_id),
            str(scope.environment_id),
            reason,
            str(task_id or ""),
            str(user_id),
            scope.actor_label[:80],
            job_id=job,
        )
    except Exception:  # noqa: BLE001 - the in-app notification already went out
        logger.warning("pi_team_alert_enqueue_failed", exc_info=True)


# ---- Due-soon reminders -----------------------------------------------------------------


async def remind_due(ctx: dict[str, Any]) -> int:
    """Cron job (every 15 minutes): a card that's still open and due within the hour
    gets one reminder for its assignee, in the app and on WhatsApp."""
    from app.modules.pi.runtime import system_scope

    async with ctx["sessions"]() as session:
        connections = list(
            await session.scalars(
                select(WhatsAppConnection)
                .where(WhatsAppConnection.status == "active")
                .order_by(WhatsAppConnection.tenant_id, WhatsAppConnection.environment_id)
            )
        )
    seen: set[tuple[Any, Any]] = set()
    sent = 0
    for connection in connections:
        pair = (connection.tenant_id, connection.environment_id)
        if pair in seen:
            continue
        seen.add(pair)
        due: list[tuple[UUID, UUID]] = []
        async with ctx["sessions"]() as session:
            try:
                scope = await system_scope(session, connection)
                if scope is None:
                    continue
                now = datetime.now(UTC)
                tasks = list(
                    await session.scalars(
                        WorkspaceRepository(session, PiTask, scope)
                        .select()
                        .where(
                            PiTask.status.in_(LIVE),
                            PiTask.assignee_user_id.is_not(None),
                            PiTask.due_at > now,
                            PiTask.due_at <= now + DUE_SOON,
                        )
                        .limit(500)
                    )
                )
                for task in tasks:
                    if task.assignee_user_id is None or task.due_at is None:
                        continue
                    await notify(
                        session,
                        scope,
                        "pi.task.due",
                        f"Due soon: {task.title}"[:160],
                        "This card on the team board is due within the hour.",
                        link="/pi/team",
                        recipient_user_id=task.assignee_user_id,
                        permission="pi.work.read",
                        dedupe_key=(
                            f"pi-task-due:{task.id}:{task.assignee_user_id}:{task.due_at:%Y%m%d%H%M}"
                        ),
                    )
                    due.append((task.id, task.assignee_user_id))
                await session.commit()
            except Exception:  # noqa: BLE001 - one business never stops the others
                logger.warning("pi_team_due_sweep_failed", exc_info=True)
                continue
        for task_id, user_id in due:
            result = await send_team_alert(
                ctx,
                str(pair[0]),
                str(pair[1]),
                "due",
                str(task_id),
                str(user_id),
            )
            sent += result in {"sent", "template"}
    return sent
