"""Platform spec v1.4, 17.7: when the reply path fails (outage).

| Step | Rule | Here |
| 1 | one short holding message, in the owner's language, an honest line about timing | queue_turn |
| 2 | queue the owner turn, retry with backoff | the message is parked (status skipped, code |
|   |   | OUTAGE_QUEUED) and due_replays hands the newest one to the normal turn again |
| 3 | on recovery answer the queued turn first, naming it | the earlier queued messages join the |
|   |   | turn through runtime.burst_before; the turn note asks the model to name the earliest |
| 4 | after 30 minutes one update, after 2 hours alert a person | send_updates |
| 5 | never silent after a holding message | the sweeper runs this every 30 s until answered |

Nothing new is stored: the queue is the owner's own message row (its `media["outage"]` holds the
retry state), the replay re-runs the webhook event that brought it (so the sweeper's grace of
`runtime.EVENT_GRACE_SECONDS` is respected: a replayed event is fresh), and the holding lines are
outbound rows with an idempotency key under `pi-outage:` so they never count as the answer to the
owner and never repeat. The turn that finally answers is the only one that carries a model reply,
so there is no duplicate answer.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.pi.language import TECH_DOWN_NOTICES, detect_language, notice_in
from app.modules.pi.models import (
    PiAgentRun,
    PiConversation,
    PiMessage,
    PiToolCall,
    WhatsAppConnection,
    WhatsAppWebhookEvent,
)
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

CODE = "OUTAGE_QUEUED"  # an owner message waiting for the reply path to recover
ANSWERED = "OUTAGE_ANSWERED"  # it was answered (by the turn that replayed it, or by a person)
DROPPED = "OUTAGE_DROPPED"  # given up: the chat is closed or with a person, or it is a day old
KEY_PREFIX = "pi-outage:"

UPDATE_AFTER = timedelta(minutes=30)  # spec 17.7 step 4 and decision 4
ALERT_AFTER = timedelta(hours=2)
GIVE_UP_AFTER = timedelta(hours=24)  # WhatsApp's free-reply window
BACKOFF_FIRST = 60  # seconds; doubles up to BACKOFF_MAX
BACKOFF_MAX = 900

# The holding line is the existing "your messages are saved" notice: no time is promised.
HOLDING_NOTICES = TECH_DOWN_NOTICES
# 30 minutes on: one honest update, still no promised time.
UPDATE_NOTICES = {
    "en": "pi is still having trouble. Your message is safe, "
    "and pi will reply here as soon as it is back.",
    "roman_ur": "pi mein abhi bhi masla hai. Aap ka paigham mehfooz hai, "
    "aur pi wapas aate hi yahin jawab dega.",
    "ar": "لا يزال pi يواجه مشكلة. رسالتك محفوظة وسيرد pi هنا فور عودته.",
    "fr": "pi a toujours un problème. Votre message est en sécurité, "
    "et pi répondra ici dès que possible.",
    "es": "pi sigue con problemas. Su mensaje está a salvo y pi responderá aquí en cuanto vuelva.",
}


def backoff_seconds(failures: int) -> int:
    """Wait before the next try after this many failures: 60 s, 2 min, 4 min ... at most 15 min."""
    return int(min(BACKOFF_FIRST * 2 ** max(failures - 1, 0), BACKOFF_MAX))


def notice_for(notices: dict[str, str], body: str | None, known: str | None) -> str:
    """The fixed line in the language of the owner's message (or of the chat so far)."""
    return notice_in(notices, detect_language(body) or known)


def is_outage_key(key: str | None) -> bool:
    return bool(key) and str(key).startswith(KEY_PREFIX)


def real_reply(model: Any = PiMessage) -> ColumnElement[bool]:
    """SQL condition: an outbound row that is not an outage holding line or update."""
    return or_(model.idempotency_key.is_(None), ~model.idempotency_key.like(f"{KEY_PREFIX}%"))


def state_of(message: PiMessage) -> dict[str, Any]:
    raw = (message.media or {}).get("outage")
    return dict(raw) if isinstance(raw, dict) else {}


def _save(message: PiMessage, state: dict[str, Any]) -> None:
    message.media = {**(message.media or {}), "outage": state}


def _when(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def hold_needed(session: AsyncSession, conversation_id: UUID) -> bool:
    """One holding message per outage: none yet, or a real reply went out after the last one."""
    base = (
        PiMessage.conversation_id == conversation_id,
        PiMessage.direction == "outbound",
    )
    last_hold = await session.scalar(
        select(func.max(PiMessage.created_at)).where(
            *base, PiMessage.idempotency_key.like(f"{KEY_PREFIX}{conversation_id}:hold:%")
        )
    )
    if last_hold is None:
        return True
    last_real = await session.scalar(
        select(func.max(PiMessage.created_at)).where(*base, real_reply())
    )
    return last_real is not None and last_hold < last_real


async def queue_turn(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    message: PiMessage,
    event_id: UUID,
    now: datetime | None = None,
) -> list[str]:
    """Steps 1 and 2: park this owner message for a replay, and return the ids of the outbound
    rows to send (the one holding line, or none when one already went out for this outage).
    The caller sets the message's status with `park` once its own bookkeeping is done."""
    from app.modules.pi.service import PiService

    now = now or datetime.now(UTC)
    state = state_of(message)
    failures = int(state.get("failures", 0)) + 1
    state.update(
        queued_at=state.get("queued_at") or now.isoformat(),
        event_id=str(event_id),
        failures=failures,
        next_at=(now + timedelta(seconds=backoff_seconds(failures))).isoformat(),
    )
    _save(message, state)
    if not await hold_needed(session, conversation.id):
        return []
    service = PiService(session, scope)
    text = notice_for(HOLDING_NOTICES, message.body, conversation.language)
    if not await session.scalar(
        select(PiMessage.id)
        .where(
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "outbound",
            real_reply(),
        )
        .limit(1)
    ):
        # pi has not spoken in this chat yet: the holding line is its first message and says what
        # pi is (R-DISC-01).
        from app.modules.pi.constitution import opening_line

        known = detect_language(message.body) or conversation.language
        ctx = {"reply_language": known, "latest_customer_message": message.body or ""}
        text = f"{opening_line(ctx)} {text}"
    row = await service.messages.add(
        service.messages.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="system",
            body=text,
            status="queued",
            idempotency_key=f"{KEY_PREFIX}{conversation.id}:hold:{message.id}",
        )
    )
    conversation.last_message_at = now
    conversation.last_message_preview = text[:200]
    return [str(row.id)]


def park(message: PiMessage) -> None:
    message.status, message.error_code = "skipped", CODE


async def settle(session: AsyncSession) -> int:
    """Close queued messages that were answered meanwhile: a reply of pi's or of a person went out
    after them, or a later message of the same chat was processed (it answered the whole turn)."""
    later_out = aliased(PiMessage)
    later_in = aliased(PiMessage)
    rows = list(
        await session.scalars(
            select(PiMessage)
            .where(
                PiMessage.direction == "inbound",
                PiMessage.status == "skipped",
                PiMessage.error_code == CODE,
                or_(
                    exists().where(
                        later_out.conversation_id == PiMessage.conversation_id,
                        later_out.direction == "outbound",
                        later_out.sender_type.in_(("ai", "human")),
                        later_out.status != "failed",
                        later_out.created_at > PiMessage.created_at,
                        real_reply(later_out),
                    ),
                    exists().where(
                        later_in.conversation_id == PiMessage.conversation_id,
                        later_in.direction == "inbound",
                        later_in.status == "processed",
                        later_in.created_at > PiMessage.created_at,
                    ),
                ),
            )
            .limit(200)
        )
    )
    for row in rows:
        row.error_code = ANSWERED
    return len(rows)


@dataclass
class Replay:
    event_id: UUID
    failures: int


async def due_replays(session: AsyncSession, now: datetime) -> list[Replay]:
    """Step 2, the retry: for every chat with queued owner messages whose backoff is over, the
    newest one goes through the normal turn again (the earlier queued ones join its turn). Oldest
    chats first. A chat with a message already being processed is left alone."""
    await settle(session)
    queued = list(
        await session.scalars(
            select(PiMessage)
            .where(
                PiMessage.direction == "inbound",
                PiMessage.status == "skipped",
                PiMessage.error_code == CODE,
            )
            .order_by(PiMessage.created_at)
            .limit(200)
        )
    )
    chats: dict[UUID, list[PiMessage]] = {}
    for row in queued:
        chats.setdefault(row.conversation_id, []).append(row)
    out: list[Replay] = []
    for conversation_id, rows in chats.items():
        newest = rows[-1]
        state = state_of(newest)
        started = _when(state_of(rows[0]).get("queued_at")) or rows[0].created_at
        conversation = await session.get(PiConversation, conversation_id)
        if (
            conversation is None
            or conversation.mode != "ai"
            or conversation.status != "open"
            or now - started >= GIVE_UP_AFTER
        ):
            for row in rows:
                row.error_code = DROPPED
            continue
        due = _when(state.get("next_at"))
        if due is not None and due > now:
            continue
        in_flight = await session.scalar(
            select(PiMessage.id)
            .where(
                PiMessage.conversation_id == conversation_id,
                PiMessage.direction == "inbound",
                PiMessage.status == "received",
            )
            .limit(1)
        )
        if in_flight is not None:
            continue
        event = (
            await session.get(
                WhatsAppWebhookEvent, UUID(str(state["event_id"])), with_for_update=True
            )
            if state.get("event_id")
            else None
        )
        if event is None:
            for row in rows:
                row.error_code = DROPPED
            continue
        # The event runs again from a clean slate and is fresh (updated now), so the sweeper's own
        # grace keeps it from picking it up a second time while a worker is on it.
        event.status, event.attempts, event.processed_at = "received", 0, None
        event.updated_at = now
        # The failed try left a run row for this message; the turn would treat it as "already
        # handled" and stop. It had no tool calls (the model never answered), so it makes way.
        await session.execute(
            delete(PiAgentRun).where(
                PiAgentRun.message_id == newest.id,
                ~exists().where(PiToolCall.run_id == PiAgentRun.id),
            )
        )
        newest.status, newest.error_code = "received", None
        out.append(Replay(event.id, int(state.get("failures", 0))))
    return out


async def send_updates(session: AsyncSession, now: datetime) -> list[str]:
    """Steps 4 and 5: a chat still waiting after 30 minutes gets one update; after 2 hours a person
    at Workzap is asked to reply by hand. Returns the ids of the outbound rows to send."""
    from app.modules.pi.runtime import system_scope
    from app.modules.pi.service import PiService

    queued = list(
        await session.scalars(
            select(PiMessage)
            .where(
                PiMessage.direction == "inbound",
                PiMessage.status == "skipped",
                PiMessage.error_code == CODE,
            )
            .order_by(PiMessage.created_at)
            .limit(200)
        )
    )
    oldest: dict[UUID, PiMessage] = {}
    for row in queued:
        oldest.setdefault(row.conversation_id, row)
    sends: list[str] = []
    for conversation_id, row in oldest.items():
        state = state_of(row)
        started = _when(state.get("queued_at"))
        if started is None:
            continue
        age = now - started
        if age < UPDATE_AFTER:
            continue
        conversation = await session.get(PiConversation, conversation_id)
        if conversation is None:
            continue
        connection = (
            await session.get(WhatsAppConnection, conversation.connection_id)
            if conversation.connection_id
            else None
        )
        scope = await system_scope(session, connection) if connection else None
        if scope is None:
            continue
        changed = False
        if not state.get("update_sent"):
            service = PiService(session, scope)
            text = notice_for(UPDATE_NOTICES, row.body, conversation.language)
            update = await service.messages.add(
                service.messages.new(
                    conversation_id=conversation_id,
                    direction="outbound",
                    sender_type="system",
                    body=text,
                    status="queued",
                    idempotency_key=f"{KEY_PREFIX}{conversation_id}:update:{row.id}",
                )
            )
            conversation.last_message_at = now
            conversation.last_message_preview = text[:200]
            sends.append(str(update.id))
            state["update_sent"] = now.isoformat()
            changed = True
        if age >= ALERT_AFTER and not state.get("alerted"):
            state["alerted"] = now.isoformat()
            changed = True
            try:
                async with session.begin_nested():
                    await _alert_person(session, scope, conversation, row)
            except Exception:  # an alert that fails must not stop the other chats
                logger.warning("pi_outage_alert_failed", exc_info=True)
        if changed:
            _save(row, state)
    return sends


async def _alert_person(
    session: AsyncSession, scope: WorkspaceScope, conversation: PiConversation, row: PiMessage
) -> None:
    from app.modules.pi.service import PiService
    from app.modules.pi.service_conversation import ask_team

    summary = (
        "pi has been unable to reply for over 2 hours (the AI provider is down). "
        "Please reply to this owner by hand."
    )
    if conversation.customer_id is not None:
        await ask_team(session, scope, conversation, summary, row.body or "")
    else:
        await PiService(session, scope).handoff(conversation.id, "provider_failure", summary)


async def sweep(session: AsyncSession, now: datetime) -> tuple[list[Replay], list[str]]:
    """One pass of the outageReplayer (spec 17.9): updates and alerts first, then the replays."""
    sends = await send_updates(session, now)
    replays = await due_replays(session, now)
    await session.commit()
    return replays, sends


__all__ = [
    "ANSWERED",
    "CODE",
    "DROPPED",
    "HOLDING_NOTICES",
    "UPDATE_NOTICES",
    "Replay",
    "backoff_seconds",
    "due_replays",
    "hold_needed",
    "is_outage_key",
    "park",
    "queue_turn",
    "real_reply",
    "send_updates",
    "settle",
    "sweep",
]
