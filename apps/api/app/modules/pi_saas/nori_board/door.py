"""The board door: nori pushes one requirement, problem or feedback item onto pi's Nori Platform
board. `handle(...)` is the whole decision, apart from FastAPI so it can be tested without a server.

Order (the first failing check answers; every check after the signature leaves an audit row):

  not configured / kill switch  -> 503      (before anything is read)
  body size limit (8 KB)        -> 413
  signature (constant time)     -> 401      (the body is not parsed before this passes)
  a workspace with board on     -> 503
  body shape and values         -> 400
  timestamp freshness (10 min)  -> 401
  replay (ts + signature, 24 h) -> 409
  per-minute limit              -> 429
  file the card (idempotent by ref) -> 200 {"ok": true, "id": ..., "created": true|false}

The audit row holds the outcome and a masked number, never the text. Same signature as the send
door: ``X-Workzap-Signature: sha256=<HMAC-SHA256 of the raw body>`` with WORKZAP_BRIDGE_SECRET.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiSettings, WhatsAppConnection
from app.modules.pi_saas.nori_board import service
from app.modules.pi_saas.nori_board.models import ITEM_KINDS
from app.modules.pi_saas.nori_credits import signing, store
from app.modules.pi_saas.nori_credits.config import (
    WorkspaceBridge,
    killed,
    read_env,
    workspace_bridge,
)
from app.modules.pi_saas.nori_credits.models import PiNoriBridgeLog
from app.modules.pi_saas.nori_credits.resilience import METRICS
from app.modules.pi_saas.nori_credits.send_door import (
    FRESHNESS_SECONDS,
    _host_allowed,
    parse_ts,
)
from app.shared.errors import BusinessRuleViolation

logger = logging.getLogger("app.pi.nori_credits")

MAX_BODY_BYTES = 8 * 1024
KIND = "board"  # the audit kind in pi_nori_bridge_log
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")


@dataclass
class DoorResult:
    status: int
    body: dict[str, Any] = field(default_factory=dict)


def _fail(status: int, reason: str) -> DoorResult:
    return DoorResult(status, {"ok": False, "reason": reason})


async def _candidates(session: AsyncSession) -> list[tuple[WhatsAppConnection, WorkspaceBridge]]:
    rows = await session.execute(
        select(WhatsAppConnection, PiSettings.response_rules)
        .join(
            PiSettings,
            (PiSettings.tenant_id == WhatsAppConnection.tenant_id)
            & (PiSettings.environment_id == WhatsAppConnection.environment_id),
        )
        .where(
            WhatsAppConnection.status == "active",
            PiSettings.response_rules["nori_bridge"]["enabled"].as_boolean().is_(True),
            PiSettings.response_rules["nori_bridge"]["board"].as_boolean().is_(True),
        )
        .order_by(WhatsAppConnection.created_at)
    )
    found = []
    for connection, rules in rows.all():
        bridge = workspace_bridge(rules)
        if bridge is not None and bridge.board:
            found.append((connection, bridge))
    return found


def _text(value: Any, limit: int, *, required: bool = False) -> str | None:
    """Clean text, "" when absent, None when it is the wrong type or too long (or missing and
    required)."""
    if value is None:
        return None if required else ""
    if not isinstance(value, str):
        return None
    clean = _CONTROL.sub("", value).strip()
    if len(clean) > limit:
        return None
    if required and not clean:
        return None
    return clean


def parse_item(data: dict[str, Any], nori_host: str) -> dict[str, Any] | str:
    """The checked item, or the reason it was refused."""
    ref = data.get("ref")
    if not isinstance(ref, str) or not service.REF_RE.fullmatch(ref):
        return "bad_ref"
    kind = data.get("kind", "note")
    if kind not in ITEM_KINDS:
        return "bad_kind"
    title = _text(data.get("title"), service.TITLE_MAX)
    body = _text(data.get("text"), service.TEXT_MAX)
    if title is None or body is None or not (title or body):
        return "bad_text"
    workspace = _text(data.get("workspace"), 120, required=True)
    person = _text(data.get("person"), 120)
    department = _text(data.get("department"), 80)
    if workspace is None or person is None or department is None:
        return "bad_item"
    priority = data.get("priority", "normal")
    if priority not in service.PRIORITIES:
        return "bad_priority"
    phone = data.get("phone")
    if phone not in (None, ""):
        phone = service.normalise_phone(phone)
        if phone is None:
            return "bad_phone"
    url = data.get("url")
    if url not in (None, ""):
        if not isinstance(url, str) or len(url) > 300:
            return "bad_url"
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return "bad_url"
        if not _host_allowed(parsed.hostname, nori_host):
            return "bad_url"
    else:
        url = None
    return {
        "ref": ref,
        "kind": kind,
        "title": title,
        "text": body,
        "workspace": workspace,
        "person": person,
        "department": department,
        "phone": phone or "",
        "priority": priority,
        "url": url,
    }


async def handle(
    session: AsyncSession,
    settings: Any,
    raw: bytes,
    signature: str | None,
    *,
    declared_length: int | None = None,
    now: float | None = None,
) -> DoorResult:
    """Decide and, when every check passes, file the card. Never raises."""
    try:
        return await _handle(session, settings, raw, signature, declared_length, now)
    except Exception:
        METRICS.inc(KIND, "error")
        logger.warning("nori_board_door_error", exc_info=False)
        try:
            await session.rollback()
        except Exception:
            pass
        return _fail(500, "internal_error")


async def _reject(
    session: AsyncSession,
    status: int,
    reason: str,
    *,
    target: WhatsAppConnection | None = None,
    outcome: str = "rejected",
) -> DoorResult:
    METRICS.inc(KIND, reason)
    await store.audit(
        session,
        KIND,
        outcome,
        reason=reason,
        tenant_id=target.tenant_id if target else None,
        environment_id=target.environment_id if target else None,
    )
    await session.commit()
    return _fail(status, reason)


async def _filed_in_last_minute(session: AsyncSession, connection: WhatsAppConnection) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PiNoriBridgeLog)
        .where(
            PiNoriBridgeLog.kind == KIND,
            PiNoriBridgeLog.tenant_id == connection.tenant_id,
            PiNoriBridgeLog.environment_id == connection.environment_id,
            PiNoriBridgeLog.dedupe_key.is_(None),
            PiNoriBridgeLog.outcome.in_(("filed", "duplicate")),
            PiNoriBridgeLog.created_at > func.now() - text("interval '1 minute'"),
        )
    )
    return int(count or 0)


async def _handle(
    session: AsyncSession,
    settings: Any,
    raw: bytes,
    signature: str | None,
    declared_length: int | None,
    now: float | None,
) -> DoorResult:
    env = read_env(settings)
    if env is None:
        return _fail(503, "not_configured")
    if killed(settings):
        METRICS.inc(KIND, "killed")
        return _fail(503, "disabled")
    if len(raw) > MAX_BODY_BYTES or (declared_length or 0) > MAX_BODY_BYTES:
        METRICS.inc(KIND, "too_large")
        return _fail(413, "too_large")
    if not signing.verify(env.secret, raw, signature):
        METRICS.inc(KIND, "bad_signature")
        logger.warning("nori_board_bad_signature")
        return _fail(401, "bad_signature")

    candidates = await _candidates(session)
    if not candidates:
        METRICS.inc(KIND, "disabled")
        return _fail(503, "disabled")
    preferred = getattr(settings, "nori_bridge_phone_number_id", "") or ""
    matched = [pair for pair in candidates if preferred and pair[0].phone_number_id == preferred]
    if not matched and len(candidates) > 1:
        # Several workspaces have the board on and nothing says which one nori means: refuse
        # rather than put one workspace's items on another's board.
        METRICS.inc(KIND, "ambiguous")
        return _fail(503, "ambiguous")
    connection, bridge = (matched or candidates)[0]

    try:
        data = json.loads(raw)
    except ValueError:
        return await _reject(session, 400, "bad_json", target=connection)
    if not isinstance(data, dict):
        return await _reject(session, 400, "bad_json", target=connection)

    stamp = parse_ts(data.get("ts"))
    clock = time.time() if now is None else now
    if stamp is None or abs(clock - stamp) > FRESHNESS_SECONDS:
        return await _reject(session, 401, "stale", target=connection)

    item = parse_item(data, env.host)
    if isinstance(item, str):
        return await _reject(session, 400, item, target=connection)

    if await _filed_in_last_minute(session, connection) >= bridge.send_per_minute:
        return await _reject(
            session, 429, "rate_limited", target=connection, outcome="rate_limited"
        )

    from app.modules.pi.runtime import system_scope

    scope = await system_scope(session, connection)
    if scope is None:
        return await _reject(session, 503, "no_workspace", target=connection)

    fresh = await store.claim(
        session,
        "replay",
        store.key_of("board", str(data.get("ts")), signature or ""),
        outcome="seen",
    )
    if not fresh:
        return await _reject(session, 409, "replay", target=connection)

    try:
        task, created = await service.file_item(
            session,
            scope,
            ref=item["ref"],
            kind=item["kind"],
            title=item["title"],
            text=item["text"],
            workspace=item["workspace"],
            person=item["person"],
            department=item["department"],
            phone=item["phone"],
            source="nori",
            priority=item["priority"],
            url=item["url"],
            created_by_label="nori",
        )
    except BusinessRuleViolation:
        return await _reject(session, 400, "bad_item", target=connection)
    await store.audit(
        session,
        KIND,
        "filed" if created else "duplicate",
        number=item["phone"],
        tenant_id=connection.tenant_id,
        environment_id=connection.environment_id,
    )
    await store.purge(session)
    await session.commit()
    METRICS.inc(KIND, "filed" if created else "duplicate")
    return DoorResult(200, {"ok": True, "id": str(task.id), "created": created})
