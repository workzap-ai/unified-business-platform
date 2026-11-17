"""Send a registry person's whole chat to nori's conversation door (default OFF).

With `response_rules.nori_bridge.forward_messages` exactly true, the sweep offers every message of a
chat whose number is on the Nori numbers registry AND carries nori's own ref (a number added by hand
is never sent) to `POST /api/pi/board-message`, signed like every nori door:

  {ref, message_id, direction in|out, from person|team|pi, text, at, person?, card_id?, files?}

`text` is redacted the way board cards are. `message_id` is pi's message id. `card_id` links a
message that also became a board card. `at` is pi's save time in epoch milliseconds. Files use the
same signed link as board cards (needs `forward_media`). A greeting kept in the chat without a
card is sent here too, so the conversation is complete.

Delivery is at-least-once and idempotent by message id (a repeat answers `duplicate: true`). Only
the last 24 hours are owed, so turning the flag on does not back-fill old chats. The ledger
(`pi_nori_thread`) holds one row per message: sent once, retried a few times, then given up on.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiConversation, PiMessage, PiSettings
from app.modules.pi.safety import redact_pii
from app.modules.pi_saas.nori_board.models import PiNoriItem, PiNoriNumber, PiNoriThread
from app.modules.pi_saas.nori_credits.client import NoriClient
from app.modules.pi_saas.nori_credits.config import killed, read_env, workspace_bridge
from app.modules.pi_saas.nori_credits.resilience import METRICS

logger = logging.getLogger("app.pi.nori_credits")

PATH = "/api/pi/board-message"
MAX_ATTEMPTS = 6
OWED_FOR = timedelta(hours=24)
BATCH = 40
TEXT_MAX = 5000
# An outbound message that never reached the person is not part of the conversation.
OUT_STATES = ("queued", "sent", "delivered", "read")


def sender_of(message: PiMessage) -> tuple[str, str]:
    """(direction, from) in nori's words."""
    if message.direction == "inbound":
        return "in", "person"
    return "out", "team" if message.sender_type == "human" else "pi"


def payload_for(
    message: PiMessage,
    ref: str,
    *,
    person: str,
    card_id: str | None,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    direction, source = sender_of(message)
    body: dict[str, Any] = {
        "ref": ref,
        "message_id": str(message.id),
        "direction": direction,
        "from": source,
        "text": redact_pii(str(message.body or "").strip()).text[:TEXT_MAX],
        "at": int(message.created_at.timestamp() * 1000),
    }
    if person:
        body["person"] = person[:120]
    if card_id:
        body["card_id"] = card_id
    if files:
        body["files"] = files
    return body


async def _owed(session: AsyncSession) -> list[tuple[PiMessage, PiConversation, PiNoriNumber]]:
    since = datetime.now(UTC) - OWED_FOR
    rows = await session.execute(
        select(PiMessage, PiConversation, PiNoriNumber)
        .join(PiConversation, PiConversation.id == PiMessage.conversation_id)
        .join(
            PiNoriNumber,
            (PiNoriNumber.tenant_id == PiConversation.tenant_id)
            & (PiNoriNumber.environment_id == PiConversation.environment_id)
            & (PiNoriNumber.phone == PiConversation.contact_wa_id),
        )
        .outerjoin(
            PiNoriThread,
            (PiNoriThread.tenant_id == PiMessage.tenant_id)
            & (PiNoriThread.environment_id == PiMessage.environment_id)
            & (PiNoriThread.message_id == PiMessage.id),
        )
        .where(
            PiNoriNumber.nori_ref.is_not(None),
            PiMessage.created_at > since,
            (PiMessage.direction == "inbound") | PiMessage.status.in_(OUT_STATES),
            PiNoriThread.id.is_(None)
            | (PiNoriThread.sent_at.is_(None) & (PiNoriThread.attempts < MAX_ATTEMPTS)),
        )
        .order_by(PiMessage.created_at, PiMessage.direction)  # a tie: the person first
        .limit(BATCH)
    )
    return [(m, c, n) for m, c, n in rows.all()]


async def thread_due(session: AsyncSession, settings: Any, http: Any) -> int:
    """Send the chat messages that are owed, for workspaces with the flag on. Returns how many nori
    took. The caller commits."""
    env = read_env(settings)
    if env is None or killed(settings):
        return 0
    taken = 0
    bridges: dict[tuple[Any, Any], Any] = {}
    for message, _conversation, number in await _owed(session):
        key = (message.tenant_id, message.environment_id)
        if key not in bridges:
            rules = await session.scalar(
                select(PiSettings.response_rules).where(
                    PiSettings.tenant_id == message.tenant_id,
                    PiSettings.environment_id == message.environment_id,
                )
            )
            bridge = workspace_bridge(rules)
            bridges[key] = bridge if bridge is not None and bridge.forward_messages else None
        bridge = bridges[key]
        if bridge is None:
            continue  # flag off: the message stays owed, nothing leaves pi
        ledger = await session.scalar(
            select(PiNoriThread).where(
                PiNoriThread.tenant_id == message.tenant_id,
                PiNoriThread.environment_id == message.environment_id,
                PiNoriThread.message_id == message.id,
            )
        )
        if ledger is None:
            ledger = PiNoriThread(
                tenant_id=message.tenant_id,
                environment_id=message.environment_id,
                message_id=message.id,
            )
            session.add(ledger)
        card = await session.scalar(
            select(PiNoriItem).where(
                PiNoriItem.tenant_id == message.tenant_id,
                PiNoriItem.environment_id == message.environment_id,
                PiNoriItem.message_id == message.id,
            )
        )
        files: list[dict[str, Any]] = []
        if card is not None and bridge.forward_media:
            from app.modules.pi_saas.nori_board.forward import files_for

            files = await files_for(session, settings, env.secret, card, bridge)
        body = payload_for(
            message,
            number.nori_ref or "",
            person=number.person,
            card_id=str(card.task_id) if card is not None else None,
            files=files,
        )
        if not body["text"] and not files:
            ledger.sent_at, ledger.note = datetime.now(UTC), "empty"  # nothing nori could show
            continue
        result = await NoriClient(env, http, bridge).call(PATH, body)
        ledger.attempts += 1
        if result.ok and result.data.get("ok") is True:
            ledger.sent_at = datetime.now(UTC)
            ledger.note = "duplicate" if result.data.get("duplicate") else "sent"
            taken += 1
            METRICS.inc("thread", "sent")
        elif result.reason == "http_4xx" and result.status in {400, 413}:
            reason = str(result.data.get("reason") or "refused")
            ledger.attempts = MAX_ATTEMPTS
            ledger.note = reason[:40]
            METRICS.inc("thread", "refused")
            logger.warning("nori_thread_refused", extra={"reason": reason[:40]})
        else:
            ledger.note = result.reason[:40]
            METRICS.inc("thread", "retry")
    await session.flush()
    return taken
