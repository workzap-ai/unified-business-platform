"""Follow-ups after the listening stage in brain mode (pi Brain spec 3.9.1, R-FUP-01 to R-FUP-05).

`followup_policy.next_followup` says which follow-up a chat is owed and when; this module sends it.
Five kinds are covered here: a paused chat (X_PAUSED), the solution document and quote at 2 and 7
days (S7/S8), the kickoff reminders 24 hours and 1 hour before (S12) and, behind
`response_rules.brain.map_share`, the quiet-owner map follow-up (Book 5, 6.3, decision 6) and the
one-line "I saw what you changed" after a dashboard edit. The "still here" line for someone who went
quiet mid-description is `followups._silence_nudge`.

Inside WhatsApp's 24-hour window a follow-up is the policy's own plain text. Outside it only an
approved template can go: paused and document follow-ups use `whatsapp_config["followup_templates"]`
(language -> kind -> {name, language}) and need the person's reminder consent; kickoff reminders use
the business's approved meeting template. A missing template never blocks silently: staff are told
what to add. Never at night, at Jumu'ah or around iftar, never after "stop", never past the plan's
message allowance, never twice for the same step.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.service import notify
from app.modules.pi import fixed_lines, flow, followup_policy, map_builder, map_share
from app.modules.pi.box_models import PiMapVersion
from app.modules.pi.configuration import settings_row
from app.modules.pi.followups import (
    _friday_prayer,
    _waiting_until,
    iftar_pause,
    jumuah_country,
    person_zone,
    quiet_until,
)
from app.modules.pi.models import PiConversation, PiMessage, PiSettings, WhatsAppConnection
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.service import PiService
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("app.pi.followups")

S = flow.State
WATCHED = (
    S.S7_DELIVERED.value,
    S.S8_REVIEW.value,
    S.S12_KICKOFF.value,
    S.X_PAUSED.value,
)
TEMPLATE_KINDS = ("paused", "documents", "map")  # kickoff reminders use the meeting template
MAP_WATCHED = tuple(state.value for state in followup_policy.MAP_STATES)
BATCH = 200


def _parse(raw: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw) if isinstance(raw, str) and raw else None
    except ValueError:
        return None
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def map_followups(conversation: PiConversation) -> tuple[int, int]:
    """(map follow-ups since the owner last wrote, in all). The count starts again from zero when
    they write; the total never does (a small number over the life of the chat, then stop)."""
    done = (conversation.service_brief or {}).get("map_followups") or {}
    last = conversation.last_inbound_at.isoformat() if conversation.last_inbound_at else ""
    since = int(done.get("n") or 0) if done.get("inbound") == last else 0
    return since, int(done.get("total") or 0)


def chat_of(
    conversation: PiConversation, noted: int = 0, has_map: bool = False
) -> followup_policy.Chat | None:
    """The policy's view of this conversation, or None when it has no inbound message yet."""
    last = conversation.last_inbound_at
    if last is None:
        return None
    brief = conversation.service_brief or {}
    sent_at = _parse((brief.get("offer") or {}).get("sent_at"))
    if sent_at is not None:
        sent_at = max(sent_at, last)  # they wrote since: the timer starts again from there
    state = flow.parse(conversation.flow_state)
    if state is None:
        return None
    paused = conversation.flow_state_since if state == S.X_PAUSED else None
    map_sent, map_total = map_followups(conversation)
    return followup_policy.Chat(
        state=state,
        last_inbound_at=last,
        sent=dict(brief.get("followups_sent") or {}),
        paused_at=paused,
        documents_sent_at=sent_at,
        kickoff_at=_parse((brief.get("kickoff") or {}).get("at")),
        opted_out=brief.get("reminder_consent") == "declined",
        noted_problems=noted,
        has_map=has_map,
        map_sent=map_sent,
        map_total=map_total,
    )


def language_of(conversation: PiConversation) -> str:
    """The language of the follow-up text and of its template: Roman Urdu for Roman Urdu, Urdu,
    Hindi and Persian chats, Arabic for Arabic, English for the rest."""
    return fixed_lines.table_language(
        conversation.language, followup_policy.MESSAGES["silent"], persian=True
    )


def when_label(at: datetime, timezone: str) -> str:
    from app.modules.pi.policy import zone

    return at.astimezone(zone(timezone)).strftime("%a %d %b, %H:%M")


def marked_map(brief: dict[str, Any], conversation: PiConversation) -> dict[str, Any]:
    """The brief with one more map follow-up counted for this quiet spell and in all."""
    since, total = map_followups(conversation)
    last = conversation.last_inbound_at.isoformat() if conversation.last_inbound_at else ""
    return {**brief, "map_followups": {"inbound": last, "n": since + 1, "total": total + 1}}


def marked_sent(brief: dict[str, Any], kind: str) -> dict[str, Any]:
    """The brief with this follow-up counted (documents count 1 then 2, the rest are once)."""
    sent = dict(brief.get("followups_sent") or {})
    sent[kind] = int(sent.get(kind, 0)) + 1
    return {**brief, "followups_sent": sent}


def blocked_by_time(
    policy: PiSettings, now: datetime, contact_wa_id: str | None = None
) -> datetime | None:
    """When the quiet hours (21:00-09:00), Jumu'ah (Friday 12:00-14:30, PK and UAE numbers only)
    or the iftar pause end, or None when sending is fine now. All by the zone of the person's
    number (+92 PK, +971 UAE, +1 Canada by area code; else the workspace zone), R-FUP-03/04."""
    config = policy.whatsapp_config
    tz = person_zone(contact_wa_id, policy.timezone)
    later = quiet_until(
        tz, int(config.get("quiet_start", 21)), int(config.get("quiet_end", 9)), now
    )
    if later is None and jumuah_country(contact_wa_id) and _friday_prayer(tz):
        later = now + timedelta(hours=1)
    if later is None:
        later = iftar_pause(tz, config, now)
    return later


async def _noted(session: AsyncSession, conversation: PiConversation) -> int:
    if conversation.customer_id is None:
        return 0
    count = await session.scalar(
        select(func.count())
        .select_from(PiProblem)
        .where(
            PiProblem.tenant_id == conversation.tenant_id,
            PiProblem.environment_id == conversation.environment_id,
            PiProblem.customer_id == conversation.customer_id,
        )
    )
    return int(count or 0)


async def _template_for(
    policy: PiSettings, conversation: PiConversation, kind: str
) -> dict[str, str] | None:
    config = policy.whatsapp_config or {}
    if kind in TEMPLATE_KINDS:
        by_language = config.get("followup_templates") or {}
        # the map follow-up is written in the owner's own language where a template exists
        own = (conversation.language or "en") if kind == "map" else language_of(conversation)
        for language in (own, language_of(conversation), "en"):
            template = (by_language.get(language) or {}).get(kind)
            if isinstance(template, dict) and template.get("name") and template.get("language"):
                return {"name": template["name"], "language": template["language"]}
        return None
    meeting = config.get("meeting_templates") or {}
    for language in (language_of(conversation), "en"):
        template = meeting.get(language)
        if (
            isinstance(template, dict)
            and template.get("name")
            and template.get("status", "APPROVED") == "APPROVED"
        ):
            return {"name": template["name"], "language": template["language"]}
    return None


async def send_one(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    policy: PiSettings,
    due: followup_policy.Due,
    chat: followup_policy.Chat,
    now: datetime,
) -> str | None:
    """Queue this follow-up. Returns the message id, or None when it cannot go (and why is told to
    staff or recorded). Marks the step as sent only when a message was queued."""
    brief = dict(conversation.service_brief or {})
    kind = due.kind
    is_map = kind == "map"
    step = (chat.map_sent if is_map else int(chat.sent.get(kind, 0))) + 1
    language = language_of(conversation)
    when = ""
    if kind.startswith("kickoff") and chat.kickoff_at is not None:
        if now >= chat.kickoff_at:  # too late to remind: count it so it is not retried
            conversation.service_brief = marked_sent(brief, kind)
            return None
        when = when_label(chat.kickoff_at, policy.timezone)
    body = (
        map_share.followup_text(conversation.language)
        if is_map
        else followup_policy.text_for(kind, language, n=chat.noted_problems, when=when)
    )
    media: dict[str, Any] = {"followup": {"kind": kind, "step": step}}
    if now - chat.last_inbound_at >= followup_policy.WINDOW:  # outside the 24 hours: a template
        if kind in TEMPLATE_KINDS and brief.get("reminder_consent") != "granted":
            return None  # no consent for a template message: wait for them to write
        template = await _template_for(policy, conversation, kind)
        if template is None:
            await notify(
                session,
                scope,
                "pi.followup_blocked",
                "pi needs an approved WhatsApp template for a follow-up",
                f"Add a {language} '{kind}' follow-up template (or the meeting template for "
                "kickoff reminders) under pi's Auto follow-ups settings.",
                link="/pi/settings/whatsapp-configuration",
                permission="pi.settings.manage",
                dedupe_key=f"pi-followup-template:{scope.tenant_id}:{language}:{kind}",
            )
            return None
        if kind in TEMPLATE_KINDS:
            media["ladder"] = {"template": template, "step": f"{kind}{step}"}
            body = f"Follow-up template queued: {template['name']}"
        else:
            from app.modules.pi_saas.deals import _business_name

            link = (brief.get("kickoff") or {}).get("link") or "-"
            media["meeting_notice"] = {
                "template": template,
                "values": [await _business_name(session, scope), when, str(link)],
            }
    from app.modules.pi_saas.entitlement import remaining as allowance_left

    left = await allowance_left(session, scope.tenant_id, scope.environment_id, "messages_out")
    if left is not None and left <= 0:
        return None  # allowance used up: tried again on the next sweep, never over the limit
    # a map follow-up is counted per quiet spell, so its key carries the owner's last message
    spell = f":{chat.last_inbound_at.isoformat()}" if is_map else ""
    key = f"pi-followup:{kind}:{step}:{conversation.id}{spell}"
    service = PiService(session, scope)
    counted = marked_map(brief, conversation) if is_map else marked_sent(brief, kind)
    if await service.messages.find(PiMessage.idempotency_key == key) is not None:
        conversation.service_brief = counted
        return None
    message = await service.messages.add(
        service.messages.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            agent_key="requirement",
            body=body,
            status="queued",
            idempotency_key=key,
            media=media,
        )
    )
    conversation.service_brief = counted
    return str(message.id)


async def sweep(ctx: dict[str, Any], now: datetime | None = None) -> list[str]:
    """Send every brain-mode follow-up that is due. Returns the queued message ids."""
    from app.modules.pi.runtime import enqueue_sends

    now = now or datetime.now(UTC)
    outgoing: list[str] = []
    async with ctx["sessions"]() as session:
        rows = list(
            await session.scalars(
                select(PiConversation)
                .where(
                    PiConversation.flow_state.in_(WATCHED),
                    PiConversation.status == "open",
                    PiConversation.mode == "ai",
                )
                .order_by(PiConversation.last_inbound_at)
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
        )
        for conversation in rows:
            try:
                async with session.begin_nested():
                    queued = await _one(session, conversation, now)
                if queued is not None:
                    outgoing.append(queued)
            except Exception:  # noqa: BLE001 - one bad chat must not stop the others
                logger.warning("pi_brain_followup_failed", exc_info=True)
        outgoing += await _map_sweep(session, now)
        await session.commit()
    await enqueue_sends(ctx, outgoing)
    return outgoing


async def _map_sweep(session: AsyncSession, now: datetime) -> list[str]:
    """The two map messages (workspaces with response_rules.brain.map_share only): the quiet-owner
    follow-up and the line that tells what the owner changed on the dashboard."""
    quiet_before = now - timedelta(days=min(map_share.FOLLOWUP_DAYS))
    quiet = await session.scalars(
        select(PiConversation)
        .where(
            PiConversation.flow_state.in_(MAP_WATCHED),
            PiConversation.status == "open",
            PiConversation.mode == "ai",
            PiConversation.last_inbound_at <= quiet_before,
        )
        .order_by(PiConversation.last_inbound_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    )
    changed = await session.scalars(
        select(PiConversation)
        .where(
            PiConversation.service_brief.has_key("map_changes"),
            PiConversation.status == "open",
            PiConversation.mode == "ai",
        )
        .order_by(PiConversation.last_inbound_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    )
    steps = [(c, _one_map) for c in quiet] + [(c, tell_changes) for c in changed]
    out: list[str] = []
    for conversation, step in steps:
        try:
            async with session.begin_nested():
                queued = await step(session, conversation, now)
            if queued is not None:
                out.append(queued)
        except Exception:  # noqa: BLE001 - one bad chat must not stop the others
            logger.warning("pi_brain_map_followup_failed", exc_info=True)
    return out


async def _map_setup(
    session: AsyncSession, conversation: PiConversation
) -> tuple[WorkspaceScope, PiSettings] | None:
    """The workspace and its settings, only when pi is in brain mode with the map shared and may
    reply on its own."""
    from app.modules.pi.runtime import system_scope

    connection = await session.get(WhatsAppConnection, conversation.connection_id)
    scope = await system_scope(session, connection) if connection else None
    if scope is None:
        return None
    policy = await settings_row(session, scope)
    if not map_builder.share_enabled(policy.response_rules) or not policy.auto_reply_enabled:
        return None
    return scope, policy


async def _one_map(
    session: AsyncSession, conversation: PiConversation, now: datetime
) -> str | None:
    """The quiet-owner map follow-up (decision 6), if one is owed now."""
    setup = await _map_setup(session, conversation)
    if setup is None:
        return None
    scope, policy = setup
    waiting = _waiting_until(conversation.service_brief or {})
    if waiting is not None and waiting > now:  # "remind me later" / waiting on someone else
        return None
    has_map = bool(
        await session.scalar(
            select(func.count())
            .select_from(PiMapVersion)
            .where(
                PiMapVersion.tenant_id == conversation.tenant_id,
                PiMapVersion.environment_id == conversation.environment_id,
                PiMapVersion.customer_id == conversation.customer_id,
            )
        )
    )
    chat = chat_of(conversation, has_map=has_map)
    if chat is None:
        return None
    due = followup_policy.next_map_followup(chat, now)
    if due is None or blocked_by_time(policy, now, conversation.contact_wa_id) is not None:
        return None
    return await send_one(session, scope, conversation, policy, due, chat, now)


async def tell_changes(
    session: AsyncSession, conversation: PiConversation, now: datetime
) -> str | None:
    """One short line after the owner edited their map on the dashboard: what pi saw, no question.
    Edits made in a burst become one line (two minutes after the last one), at most one line an
    hour, never at night, at Jumu'ah or around iftar, and only inside WhatsApp's 24-hour window: a
    paid template is not spent on this, so outside the window the change is simply dropped (the
    owner made it themselves and sees it on the page)."""
    brief = dict(conversation.service_brief or {})
    pending = brief.get("map_changes") or {}
    at = _parse(pending.get("at"))
    setup = await _map_setup(session, conversation)
    if setup is None or at is None:
        return None
    scope, policy = setup
    if now - at < map_share.CHANGE_DEBOUNCE:
        return None  # more edits may follow
    inside = (
        conversation.last_inbound_at is not None
        and now - conversation.last_inbound_at < followup_policy.WINDOW
    )
    if not inside or brief.get("reminder_consent") == "declined":
        brief.pop("map_changes", None)  # nothing free to say it with: let it go
        conversation.service_brief = brief
        return None
    told = _parse(brief.get("map_changes_told_at"))
    if told is not None and now - told < map_share.CHANGE_GAP:
        return None  # kept for later; still inside the window it will go
    if blocked_by_time(policy, now, conversation.contact_wa_id) is not None:
        return None
    from app.modules.pi_saas.entitlement import remaining as allowance_left

    left = await allowance_left(session, scope.tenant_id, scope.environment_id, "messages_out")
    if left is not None and left <= 0:
        return None
    service = PiService(session, scope)
    key = f"pi-map-change:{conversation.id}:{at.isoformat()}"
    brief.pop("map_changes", None)
    brief["map_changes_told_at"] = now.isoformat()
    conversation.service_brief = brief
    if await service.messages.find(PiMessage.idempotency_key == key) is not None:
        return None
    message = await service.messages.add(
        service.messages.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            agent_key="requirement",
            body=map_share.changed_line(conversation.language, list(pending.get("labels") or [])),
            status="queued",
            idempotency_key=key,
            media={"map_change": True},
        )
    )
    return str(message.id)


async def _one(session: AsyncSession, conversation: PiConversation, now: datetime) -> str | None:
    from app.modules.pi.runtime import system_scope

    connection = await session.get(WhatsAppConnection, conversation.connection_id)
    scope = await system_scope(session, connection) if connection else None
    if scope is None:
        return None
    policy = await settings_row(session, scope)
    if not flow.brain_mode(policy.response_rules) or not policy.auto_reply_enabled:
        return None
    if flow.kickoff_done(conversation, now):  # S12 to S13: the kickoff call has happened
        return None
    chat = chat_of(conversation, await _noted(session, conversation))
    if chat is None:
        return None
    due = followup_policy.next_followup(chat, policy.response_rules, now)
    if due is None or blocked_by_time(policy, now, conversation.contact_wa_id) is not None:
        return None
    return await send_one(session, scope, conversation, policy, due, chat, now)
