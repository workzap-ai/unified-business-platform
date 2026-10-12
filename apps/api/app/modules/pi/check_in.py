"""pi picks an unfinished conversation back up, inside WhatsApp's 24-hour window.

Two cases, each at most once per message:
- The customer went quiet: pi's last message waited ``check_in_after_hours`` (default 2)
  with something still open (a question, the business details pi doesn't know yet, a
  brief not yet confirmed). pi writes one short check-in that remembers where they were.
- A message was missed: the customer's last message got no answer (it came while the
  team held the chat, or a run failed) and pi has the chat again. pi answers it now.

The later steps (the ~20h nudge and the day 3/7/14 templates) stay with the follow-up
ladder in ``pi_customer.engine``; this only covers the first hours.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.pi.configuration import settings_row
from app.modules.pi.followups import _waiting_until, quiet_until
from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=23)  # Leaves time for the send before WhatsApp's window closes.
MISSED_AFTER = timedelta(minutes=10)
HUMAN_QUIET = timedelta(hours=12)
PER_DAY = 2
FOLLOW_UP_MEDIA = ("nudge", "ladder", "reminder", "check_in")
PROFILE_FIELDS = (
    ("name", "their name"),
    ("business_name", "their business name"),
    ("business_type", "what their business does"),
)


def missing_profile(profile: dict[str, str], returning: bool) -> list[str]:
    """What pi still doesn't know about who the customer is."""
    if returning and (profile.get("business_name") or profile.get("business_type")):
        return []
    missing = [label for key, label in PROFILE_FIELDS if not profile.get(key)]
    # A business name or a description is enough to know whose business it is.
    if profile.get("business_name") or profile.get("business_type"):
        missing = [m for m in missing if m == "their name"]
    return missing


def unfinished(brief: dict[str, Any], last_ai: str, missing: list[str]) -> bool:
    """Something is still open on the customer's side."""
    projects = brief.get("projects") or []
    collecting = any(p.get("status") in (None, "", "collecting") for p in projects)
    return bool(
        brief.get("awaiting_customer")
        or "?" in last_ai
        or (missing and not brief.get("ready_for_team"))
        or collecting
    )


async def _candidates(ctx: dict[str, Any], now: datetime) -> list[UUID]:
    async with ctx["sessions"]() as session:
        return list(
            await session.scalars(
                select(PiConversation.id)
                .where(
                    PiConversation.status == "open",
                    PiConversation.mode == "ai",
                    PiConversation.last_inbound_at >= now - WINDOW,
                    PiConversation.last_message_at <= now - MISSED_AFTER,
                )
                .order_by(PiConversation.last_message_at)
                .limit(200)
            )
        )


async def sweep_check_ins(ctx: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    for conversation_id in await _candidates(ctx, now):
        try:
            await check_in(ctx, conversation_id, now)
        except Exception:  # noqa: BLE001 - one conversation never stops the others
            logger.warning("pi_check_in_failed", exc_info=True)


async def check_in(ctx: dict[str, Any], conversation_id: UUID, now: datetime) -> str | None:
    """Queue pi's check-in (or its answer to a missed message); the queued id or None."""
    from app.ai.manager import build_llm_manager
    from app.modules.pi.runtime import enqueue_sends, system_scope
    from app.modules.pi.service_conversation import (
        compose_service_turn,
        customer_profile,
        prepare_context,
    )
    from app.modules.pi_customer.engine import STOP

    async with ctx["sessions"]() as session:
        conversation = await session.get(PiConversation, conversation_id)
        if conversation is None or conversation.mode != "ai" or conversation.status != "open":
            return None
        connection = await session.get(WhatsAppConnection, conversation.connection_id)
        scope = await system_scope(session, connection) if connection else None
        if scope is None:
            return None
        policy = await settings_row(session, scope)
        config = policy.whatsapp_config or {}
        if not policy.auto_reply_enabled or config.get("check_in_enabled", True) is False:
            return None
        brief = conversation.service_brief or {}
        waiting = _waiting_until(brief)
        if brief.get("reminder_consent") == "declined" or (waiting and waiting > now):
            return None
        repo = WorkspaceRepository(session, PiMessage, scope)
        recent = list(
            await session.scalars(
                repo.select()
                .where(PiMessage.conversation_id == conversation.id)
                .order_by(PiMessage.created_at.desc())
                .limit(30)
            )
        )
        if not recent:
            return None
        newest_id = recent[0].id
        # A picture card pi sent after its reply doesn't change whose turn it is.
        last = next((m for m in recent if "card" not in (m.media or {})), recent[0])
        latest = next((m for m in recent if m.direction == "inbound"), None)
        if latest is None or not conversation.last_inbound_at:
            return None
        if any(m.sender_type == "human" and now - m.created_at < HUMAN_QUIET for m in recent):
            return None  # A person from the team is in this chat; pi doesn't talk over them.
        if STOP.search(latest.body or ""):
            return None
        profile, returning = await customer_profile(session, scope, conversation)
        missing = missing_profile(profile, returning)
        if last.direction == "inbound":
            if not (last.body or "").strip() or now - last.created_at < MISSED_AFTER:
                return None
            missed = True
        else:
            hours = int(config.get("check_in_after_hours", 2))
            if (
                last.sender_type != "ai"
                or any(k in (last.media or {}) for k in FOLLOW_UP_MEDIA)
                or now - last.created_at < timedelta(hours=hours)
                or not unfinished(brief, last.body or "", missing)
            ):
                return None
            missed = False
        done = brief.get("check_ins") or []
        if any(c.get("since") == str(last.id) for c in done):
            return None
        today = [c for c in done if now - datetime.fromisoformat(c["at"]) < timedelta(days=1)]
        if not missed and len(today) >= PER_DAY:
            return None
        if quiet_until(
            policy.timezone, int(config.get("quiet_start", 21)), int(config.get("quiet_end", 9))
        ):
            return None  # Never at night; the next sweep after quiet hours tries again.
        key = f"pi-check-in:{conversation.id}:{last.id}"
        if await repo.find(PiMessage.idempotency_key == key) is not None:
            return None
        context = await prepare_context(session, scope, conversation, latest, policy)
        context["check_in_now"] = {
            "missed": missed,
            "hours_quiet": round((now - last.created_at).total_seconds() / 3600, 1),
            "missing_profile": missing,
            "your_last_message": "" if missed else (last.body or "")[:1500],
            "open_projects": [
                p.get("title")
                for p in brief.get("projects") or []
                if p.get("status") in (None, "", "collecting") and p.get("title")
            ][:3],
        }
        await session.commit()  # No transaction is held across the model call.

    manager = build_llm_manager(ctx["settings"], ctx["http"], ctx["sessions"])
    try:
        turn = await compose_service_turn(manager, scope, conversation, policy, context)
    except Exception:  # noqa: BLE001 - nothing is sent rather than a generic message
        logger.warning("pi_check_in_compose_failed", exc_info=True)
        return None
    body = turn.reply.strip()
    if not body or turn.request_human:
        return None

    async with ctx["sessions"]() as session:
        conversation = await session.get(PiConversation, conversation_id)
        if conversation is None or conversation.mode != "ai":
            return None
        repo = WorkspaceRepository(session, PiMessage, scope)
        newest = await session.scalar(
            repo.select()
            .where(PiMessage.conversation_id == conversation.id)
            .order_by(PiMessage.created_at.desc())
            .limit(1)
        )
        if newest is None or newest.id != newest_id:
            return None  # The chat moved on while pi was writing.
        message = await repo.add(
            repo.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                body=body,
                status="queued",
                idempotency_key=key,
                media={"check_in": "missed" if missed else "quiet"},
            )
        )
        brief = dict(conversation.service_brief or {})
        if turn.customer_profile.model_dump(exclude_defaults=True):
            from app.modules.pi.service_conversation import merge_profile

            brief["customer_profile"] = merge_profile(
                brief.get("customer_profile"), turn.customer_profile.model_dump()
            )
        brief["check_ins"] = [
            *done,
            {"since": str(last.id), "at": now.isoformat(), "kind": "missed" if missed else "quiet"},
        ][-20:]
        conversation.service_brief = brief
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_preview = body[:200]
        await session.commit()
    await enqueue_sends(ctx, [str(message.id)])
    return str(message.id)
