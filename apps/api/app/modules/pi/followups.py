"""One consented template reminder per unanswered service enquiry turn."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.modules.notifications.service import notify
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.service import PiService

# One follow-up template per chat in this time, whichever sender (the older single
# reminder here, or pi Customer's ladder) sent the last one.
TEMPLATE_GAP = timedelta(hours=72)


async def last_follow_up_template(
    session: Any, conversation: PiConversation, since: datetime
) -> datetime | None:
    """When a follow-up template (a ladder step or the single reminder) last went, or was
    queued, to this chat after ``since``; None when none did."""
    rows = await session.scalars(
        select(PiMessage)
        .where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "outbound",
            PiMessage.created_at > since,
        )
        .order_by(PiMessage.created_at.desc())
        .limit(50)
    )
    for message in rows:
        media = message.media or {}
        if ("ladder" in media or "reminder" in media) and message.status not in (
            "failed",
            "skipped",
        ):
            created: datetime = message.created_at
            return created
    return None


def _waiting_until(brief: dict[str, Any]) -> datetime | None:
    """Until when the customer said they are waiting on someone else (pi Customer)."""
    raw = brief.get("customer_waiting_until")
    try:
        return datetime.fromisoformat(raw) if isinstance(raw, str) and raw else None
    except ValueError:
        return None


def quiet_until(
    timezone: str, start: int = 21, end: int = 9, now: datetime | None = None
) -> datetime | None:
    """During quiet hours [start, end) in the business's time zone, when they end (the
    next local ``end`` o'clock); otherwise None. start == end means no quiet hours."""
    from app.modules.pi.policy import zone

    local = (now or datetime.now(UTC)).astimezone(zone(timezone))
    hour = local.hour
    quiet = start != end and (start <= hour or hour < end if start > end else start <= hour < end)
    if not quiet:
        return None
    wake = local.replace(hour=end, minute=0, second=0, microsecond=0)
    if wake <= local:
        wake += timedelta(days=1)
    return wake.astimezone(UTC)


def reminder_language(conversation: PiConversation, config: dict[str, Any]) -> str:
    """The template language for this chat: Urdu, Hindi and Roman Urdu share the Roman Urdu
    templates; anything without its own template uses English."""
    language = conversation.language or "en"
    if language in ("roman_ur", "ur", "hi"):
        language = "roman_ur"
    return language if language in (config.get("reminder_templates") or {}) else "en"


def _friday_prayer(timezone: str) -> bool:
    from app.modules.pi.policy import zone

    local = datetime.now(UTC).astimezone(zone(timezone))
    minutes = local.hour * 60 + local.minute
    return local.weekday() == 4 and 12 * 60 + 30 <= minutes < 14 * 60 + 30


def iftar_pause(
    timezone: str, config: dict[str, Any], now: datetime | None = None
) -> datetime | None:
    """During Ramadan, no proactive message within an hour either side of Maghrib (R-FUP-04).
    Ramadan dates come from `whatsapp_config["ramadan"]` ([{"start": "2027-02-08", "end":
    "2027-03-09"}], set per year and country) and the local Maghrib time from
    `whatsapp_config["maghrib"]` ("HH:MM", default 18:45). Returns when the window ends, or None.
    """
    from app.modules.pi.policy import zone

    local = (now or datetime.now(UTC)).astimezone(zone(timezone))
    today = local.date().isoformat()
    spans = config.get("ramadan") or []
    if not any(str(s.get("start", "")) <= today <= str(s.get("end", "")) for s in spans):
        return None
    try:
        hour, minute = (int(x) for x in str(config.get("maghrib") or "18:45").split(":"))
    except ValueError:
        hour, minute = 18, 45
    maghrib = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    start, end = maghrib - timedelta(hours=1), maghrib + timedelta(hours=1)
    return end.astimezone(UTC) if start <= local < end else None


async def _silence_nudge(
    session: Any,
    scope: Any,
    conversation: PiConversation,
    policy: Any,
    outgoing: list[str],
) -> None:
    """The brain's one free-form "still here" line (spec 3.9.1). Never outside the 24-hour
    window, at night, at Jumu'ah or around iftar; never after "stop" or once the person wrote."""
    from app.modules.pi import flow, followup_policy

    now = datetime.now(UTC)
    brief = dict(conversation.service_brief or {})
    last = conversation.last_inbound_at
    sendable = (
        conversation.mode == "ai"
        and conversation.status == "open"
        and policy.auto_reply_enabled
        and last is not None
        and now - last < followup_policy.WINDOW
        and brief.get("reminder_consent") != "declined"
        and flow.parse(conversation.flow_state)
        in (flow.State.S1_LISTENING, flow.State.S2_CLARIFYING)
        and not (brief.get("followups_sent") or {}).get("silent")
    )
    if not sendable:
        conversation.followup_due_at = None
        return
    later = quiet_until(
        policy.timezone,
        int(policy.whatsapp_config.get("quiet_start", 21)),
        int(policy.whatsapp_config.get("quiet_end", 9)),
    )
    if later is None and _friday_prayer(policy.timezone):
        later = now + timedelta(hours=1)
    if later is None:
        later = iftar_pause(policy.timezone, policy.whatsapp_config)
    if later is not None:
        conversation.followup_due_at = later
        return
    from app.modules.pi_saas.entitlement import remaining as allowance_left

    left = await allowance_left(session, scope.tenant_id, scope.environment_id, "messages_out")
    if left is not None and left <= 0:
        conversation.followup_due_at = now + timedelta(hours=6)
        return
    assert last is not None
    service = PiService(session, scope)
    key = f"pi-followup-silent:{conversation.id}:{last.isoformat()}"
    if await service.messages.find(PiMessage.idempotency_key == key) is None:
        message = await service.messages.add(
            service.messages.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                body=followup_policy.text_for("silent", conversation.language),
                status="queued",
                idempotency_key=key,
                media={"followup": {"kind": "silent"}},
            )
        )
        outgoing.append(str(message.id))
    sent = dict(brief.get("followups_sent") or {})
    sent["silent"] = 1
    brief["followups_sent"] = sent
    brief.pop("followup_kind", None)
    conversation.service_brief = brief
    conversation.followup_due_at = None


async def sweep_followups(ctx: dict[str, Any]) -> None:
    from app.modules.pi.runtime import enqueue_sends, system_scope

    outgoing: list[str] = []
    async with ctx["sessions"]() as session:
        conversations = list(
            await session.scalars(
                select(PiConversation)
                .where(PiConversation.followup_due_at <= datetime.now(UTC))
                .order_by(PiConversation.followup_due_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for conversation in conversations:
            connection = await session.get(WhatsAppConnection, conversation.connection_id)
            scope = await system_scope(session, connection) if connection else None
            if scope is None:
                conversation.followup_due_at = None
                continue
            policy = await settings_row(session, scope)
            brief = conversation.service_brief or {}
            source = brief.get("source_message_id")
            waiting = _waiting_until(brief)
            if waiting is not None and waiting > datetime.now(UTC):
                # The customer is waiting on someone else (a boss, a partner): don't
                # nudge them until the pause they chose is over.
                conversation.followup_due_at = waiting
                continue
            if brief.get("followup_kind") == "silent":
                await _silence_nudge(session, scope, conversation, policy, outgoing)
                continue
            if (
                conversation.mode != "ai"
                or conversation.status != "open"
                or not policy.auto_reply_enabled
                or not policy.whatsapp_config.get("reminder_enabled", True)
                or brief.get("reminder_consent") != "granted"
                or not brief.get("awaiting_customer")
                or not source
                or brief.get("reminded_source_id") == source
            ):
                conversation.followup_due_at = None
                continue
            language = reminder_language(conversation, policy.whatsapp_config)
            template = policy.whatsapp_config.get("reminder_templates", {}).get(language)
            if not template or not connection or not connection.business_account_id:
                await notify(
                    session,
                    scope,
                    "pi.followup_blocked",
                    "PI reminder needs a WhatsApp template",
                    f"Configure an approved {language} reminder template and business account ID.",
                    link="/pi/settings/whatsapp-configuration",
                    permission="pi.settings.manage",
                    dedupe_key=f"pi-reminder-config:{conversation.id}:{source}",
                )
                # Revisit configuration without starving other tenants' due reminders.
                conversation.followup_due_at = datetime.now(UTC) + timedelta(hours=1)
                continue
            later = quiet_until(
                policy.timezone,
                int(policy.whatsapp_config.get("quiet_start", 21)),
                int(policy.whatsapp_config.get("quiet_end", 9)),
            )
            if later is not None:
                conversation.followup_due_at = later  # Never at night; sent next morning.
                continue
            if _friday_prayer(policy.timezone):
                conversation.followup_due_at = datetime.now(UTC) + timedelta(hours=1)
                continue
            if (iftar := iftar_pause(policy.timezone, policy.whatsapp_config)) is not None:
                conversation.followup_due_at = iftar  # R-FUP-04: not around iftar
                continue
            last_template = await last_follow_up_template(
                session, conversation, datetime.now(UTC) - TEMPLATE_GAP
            )
            if last_template is not None:
                # The ladder wrote to this chat in the last 72 hours: not twice.
                conversation.followup_due_at = last_template + TEMPLATE_GAP
                continue
            from app.modules.pi_saas.entitlement import remaining as allowance_left

            left = await allowance_left(
                session, scope.tenant_id, scope.environment_id, "messages_out"
            )
            if left is not None and left <= 0:
                conversation.followup_due_at = datetime.now(UTC) + timedelta(hours=6)
                continue  # Monthly allowance used up: try later, never over the limit.
            service = PiService(session, scope)
            key = f"pi-followup:{conversation.id}:{source}"
            existing = await service.messages.find(PiMessage.idempotency_key == key)
            if existing is None:
                message = await service.messages.add(
                    service.messages.new(
                        conversation_id=conversation.id,
                        direction="outbound",
                        sender_type="ai",
                        agent_key="requirement",
                        body=f"Follow-up template queued: {template['name']}",
                        status="queued",
                        idempotency_key=key,
                        media={
                            "reminder": {
                                "source_message_id": source,
                                "template": template,
                                "last_inbound_at": conversation.last_inbound_at.isoformat()
                                if conversation.last_inbound_at
                                else None,
                            }
                        },
                    )
                )
                outgoing.append(str(message.id))
            conversation.followup_due_at = None
        await session.commit()
    await enqueue_sends(ctx, outgoing)


def reminder_allowed(
    conversation: PiConversation, message: PiMessage, config: dict[str, Any]
) -> bool:
    reminder = message.media.get("reminder", {})
    brief = conversation.service_brief or {}
    return bool(
        config.get("reminder_enabled", True)
        and brief.get("reminder_consent") == "granted"
        and brief.get("awaiting_customer")
        and brief.get("source_message_id") == reminder.get("source_message_id")
        and brief.get("reminded_source_id") != reminder.get("source_message_id")
        and conversation.last_inbound_at
        and conversation.last_inbound_at.isoformat() == reminder.get("last_inbound_at")
        and config.get("reminder_templates", {}).get(reminder_language(conversation, config))
        == reminder.get("template")
    )
