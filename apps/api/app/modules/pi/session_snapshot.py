"""The session snapshot: "here's where we got to".

When a chat goes quiet for about 30 minutes after real progress (at least three changes
on the customer's picture: requests noted, connections found, stages moved), pi sends
one short summary of what changed in that session, the next step and the link to their
dashboard. It is free-form, so only inside WhatsApp's 24-hour window. It shares the
two-hour gap with pi's picture cards, never goes out at night or over a person, and
never twice for the same changes.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.pi.models import PiConversation, PiMessage, WhatsAppConnection
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

QUIET_FOR = timedelta(minutes=30)
SESSION = timedelta(hours=12)
CARD_GAP = timedelta(hours=2)
MIN_CHANGES = 3
WINDOW = timedelta(hours=23)


def session_changes(brief: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """The changes on the customer's picture since the last snapshot (this session)."""
    since_raw = brief.get("snapshot_at")
    since = datetime.fromisoformat(since_raw) if since_raw else now - SESSION
    since = max(since, now - SESSION)
    out = []
    for event in brief.get("customer_events") or []:
        try:
            at = datetime.fromisoformat(str(event.get("at")))
        except ValueError:
            continue
        if at > since and event.get("kind") in ("problem.noted", "link.found", "stage.changed"):
            out.append(event)
    return out


def compose(
    brief: dict[str, Any], events: list[dict[str, Any]], words: dict[str, Any], dashboard: str
) -> str:
    noted = list(dict.fromkeys(str(e.get("title")) for e in events if e["kind"] == "problem.noted"))
    linked = [e for e in events if e["kind"] == "link.found"]
    lines = [str(words["snapshot"])]
    if noted:
        lines.append("• " + str(words["snapshot_noted"]) + ", ".join(noted[:4]))
    for link in linked[:2]:
        detail = f" ({link['detail']})" if link.get("detail") else ""
        lines.append("• " + str(words["snapshot_linked"]) + str(link.get("title")) + detail)
    report = brief.get("customer_issues") or {}
    open_items = [i for i in report.get("issues") or [] if i.get("stage") not in ("live", "closed")]
    waiting = next(
        (i for i in open_items if i.get("ball_with") == "client" and i.get("open_question")), None
    )
    step = (
        str(waiting["open_question"])
        if waiting
        else next((str(i.get("next_step")) for i in open_items if i.get("next_step")), "")
    )
    if step:
        lines.append("• " + str(words["next"]) + step)
    if dashboard:
        lines.append(dashboard)
    return "\n".join(lines)[:1000]


async def sweep_session_snapshots(ctx: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    async with ctx["sessions"]() as session:
        ids = list(
            await session.scalars(
                select(PiConversation.id).where(
                    PiConversation.status == "open",
                    PiConversation.mode == "ai",
                    PiConversation.last_message_at <= now - QUIET_FOR,
                    PiConversation.last_message_at >= now - timedelta(hours=3),
                    PiConversation.last_inbound_at >= now - WINDOW,
                )
            )
        )
    queued = []
    for conversation_id in ids:
        try:
            message_id = await snapshot(ctx, conversation_id, now)
        except Exception:  # noqa: BLE001 - one chat never stops the others
            logger.warning("pi_session_snapshot_failed", exc_info=True)
            continue
        if message_id:
            queued.append(message_id)
    if queued:
        from app.modules.pi.runtime import enqueue_sends

        await enqueue_sends(ctx, queued)


async def snapshot(ctx: dict[str, Any], conversation_id: UUID, now: datetime) -> str | None:
    """Queue one session snapshot for this chat when it's due; the message id or None."""
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.runtime import system_scope
    from app.modules.pi_customer import service as portal
    from app.modules.pi_customer.engine import TEXT, prayer_or_quiet, wa_language

    async with ctx["sessions"]() as session:
        conversation = await session.get(PiConversation, conversation_id)
        if conversation is None or conversation.mode != "ai":
            return None
        connection = await session.get(WhatsAppConnection, conversation.connection_id)
        scope = await system_scope(session, connection) if connection else None
        if scope is None:
            return None
        policy = await settings_row(session, scope)
        config = policy.whatsapp_config or {}
        brief = dict(conversation.service_brief or {})
        if (
            config.get("session_snapshot", True) is False
            or not portal.portal_on(config)
            or brief.get("reminder_consent") == "declined"
            or prayer_or_quiet(policy, now)
        ):
            return None
        last_card = brief.get("cards_last_at")
        if last_card and now - datetime.fromisoformat(last_card) < CARD_GAP:
            return None
        events = session_changes(brief, now)
        if len(events) < MIN_CHANGES:
            return None
        repo = WorkspaceRepository(session, PiMessage, scope)
        recent = list(
            await session.scalars(
                repo.select()
                .where(PiMessage.conversation_id == conversation.id)
                .order_by(PiMessage.created_at.desc())
                .limit(20)
            )
        )
        if any(
            m.sender_type == "human" and now - m.created_at < timedelta(hours=12) for m in recent
        ):
            return None  # a person from the team is in this chat
        latest = next((m.body or "" for m in recent if m.direction == "inbound"), "")
        lang = wa_language(latest, conversation)
        settings = ctx["settings"]
        base = str(getattr(settings, "pi_app_public_url", "") or "")
        dashboard = f"{base.rstrip('/')}/customer" if base.startswith("http") else ""
        body = compose(brief, events, TEXT[lang], dashboard)
        stamp = max(str(e.get("at")) for e in events)
        key = f"pi-snapshot:{conversation.id}:{stamp}"
        if await repo.find(PiMessage.idempotency_key == key) is not None:
            return None
        message = await repo.add(
            repo.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                body=body,
                status="queued",
                idempotency_key=key,
                media={"snapshot": True},
            )
        )
        brief["snapshot_at"] = now.isoformat()
        brief["cards_last_at"] = now.isoformat()  # shares the gap with picture cards
        conversation.service_brief = brief
        await session.commit()
        return str(message.id)
