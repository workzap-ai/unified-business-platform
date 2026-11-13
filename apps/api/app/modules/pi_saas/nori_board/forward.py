"""Send a registry person's card back to nori's requirement inbox (default OFF).

When a number nori pushed (it has a `nori_ref`) writes to pi, the card is already on the board. With
`response_rules.nori_bridge.forward` exactly true, the sweep also posts the card to nori
(`POST /api/pi/board-card`, signed like every nori door) so the Workzap team sees it in nori's
/admin/requirements. This sends the card's text out of pi: it is the redacted board text, never the
raw message, and only for numbers that carry nori's ref (a number added by hand is never sent).

Delivery is at-least-once and idempotent: the card id is the key at nori (a repeat answers
`duplicate: true`). The sweep stops after a few tries or on a refusal nori will not change (400).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiSettings
from app.modules.pi_saas.models import PiTask
from app.modules.pi_saas.nori_board.models import PiNoriItem
from app.modules.pi_saas.nori_credits.client import NoriClient
from app.modules.pi_saas.nori_credits.config import killed, read_env, workspace_bridge
from app.modules.pi_saas.nori_credits.resilience import METRICS

logger = logging.getLogger("app.pi.nori_credits")

PATH = "/api/pi/board-card"
MAX_ATTEMPTS = 6
OWED_FOR = timedelta(hours=24)  # a card older than this is no longer sent (the board has it)
BATCH = 25
NORI_KINDS = {"feature", "problem", "question", "meeting", "change"}


def payload_for(item: PiNoriItem, task: PiTask) -> dict[str, Any]:
    """The body nori expects (the phone number is left out: nori reads it from the ref)."""
    kind = item.item_kind if item.item_kind in NORI_KINDS else "feature"
    text = (task.description or task.title or "").strip()[:5000]
    body: dict[str, Any] = {
        "ref": item.forward_ref,
        "card_id": str(task.id),
        "text": text or task.title,
        "kind": kind,
    }
    if item.person:
        body["person"] = item.person[:120]
    return body


async def forward_due(session: AsyncSession, settings: Any, http: Any) -> int:
    """Send the cards that are owed, for workspaces with the flag on. Returns how many nori took.
    The caller commits."""
    env = read_env(settings)
    if env is None or killed(settings):
        return 0
    since = datetime.now(UTC) - OWED_FOR
    owed = list(
        await session.scalars(
            select(PiNoriItem)
            .where(
                PiNoriItem.forward_ref.is_not(None),
                PiNoriItem.forwarded_at.is_(None),
                PiNoriItem.forward_attempts < MAX_ATTEMPTS,
                PiNoriItem.source == "whatsapp",
                PiNoriItem.created_at > since,
            )
            .order_by(PiNoriItem.created_at)
            .limit(BATCH)
        )
    )
    taken = 0
    bridges: dict[tuple[Any, Any], Any] = {}
    for item in owed:
        key = (item.tenant_id, item.environment_id)
        if key not in bridges:
            rules = await session.scalar(
                select(PiSettings.response_rules).where(
                    PiSettings.tenant_id == item.tenant_id,
                    PiSettings.environment_id == item.environment_id,
                )
            )
            bridge = workspace_bridge(rules)
            bridges[key] = bridge if bridge is not None and bridge.forward else None
        bridge = bridges[key]
        if bridge is None:
            continue  # flag off: the card stays owed, nothing leaves pi
        task = await session.get(PiTask, item.task_id)
        if task is None:
            item.forward_attempts = MAX_ATTEMPTS
            item.forward_note = "no_card"
            continue
        result = await NoriClient(env, http, bridge).call(PATH, payload_for(item, task))
        item.forward_attempts += 1
        if result.ok and result.data.get("ok") is True:
            item.forwarded_at = datetime.now(UTC)
            item.forward_note = "duplicate" if result.data.get("duplicate") else "sent"
            taken += 1
            METRICS.inc("forward", "sent")
        elif result.reason == "http_4xx" and result.status == 400:
            # nori will not change its mind (unknown_ref, bad_card, ...): give up, keep the reason.
            reason = str(result.data.get("reason") or "refused")
            item.forward_attempts = MAX_ATTEMPTS
            item.forward_note = reason[:40]
            METRICS.inc("forward", "refused")
            logger.warning("nori_forward_refused", extra={"reason": reason[:40]})
        else:
            item.forward_note = result.reason[:40]
            METRICS.inc("forward", "retry")
    await session.flush()
    return taken
