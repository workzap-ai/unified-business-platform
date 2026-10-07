"""One consented template reminder per unanswered service enquiry turn."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.modules.notifications.service import notify
from app.modules.pi.configuration import settings_row
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.modules.pi.service import PiService


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
            language = conversation.language or "en"
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
        and config.get("reminder_templates", {}).get(conversation.language or "en")
        == reminder.get("template")
    )
