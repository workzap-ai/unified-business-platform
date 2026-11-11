"""The outbound door: nori asks pi to send one queued credits notification.

`handle(...)` is the whole decision, kept apart from FastAPI so it can be tested without a server.
Order (the first failing check answers, and every check after the signature leaves an audit row):

  kill switch / not configured  -> 503      (before anything is read)
  body size limit               -> 413
  signature (constant time)     -> 401      (the body is not parsed before this passes)
  a workspace with the flag on  -> 503
  body shape                    -> 400
  timestamp freshness (10 min)  -> 401
  replay (ts + signature, 24 h) -> 409
  per-minute rate limit         -> 429
  recipient allowlist           -> 403      (a nori member by `identify`, or has messaged pi)
  content limits                -> 422      (length, no URL but nori's own host, template shape)
  send through pi's provider adapter -> 200, or 422/502 with a short reason

The audit row holds who (masked number and a hash), when, the outcome and a reason. Never the text.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiConversation, PiSettings, WhatsAppConnection
from app.modules.pi_saas.nori_credits import signing, store
from app.modules.pi_saas.nori_credits.client import NoriClient
from app.modules.pi_saas.nori_credits.config import (
    MAX_TEXT_CHARS,
    WorkspaceBridge,
    killed,
    read_env,
    workspace_bridge,
)
from app.modules.pi_saas.nori_credits.resilience import METRICS, digits, mask_number
from app.shared.errors import BusinessRuleViolation

logger = logging.getLogger("app.pi.nori_credits")

MAX_BODY_BYTES = 8 * 1024
FRESHNESS_SECONDS = 600
MAX_TEMPLATE_PARAMS = 10

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")
_URL = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|ai|pk|me|co|app|link|xyz|ly|gl|to"
    r"|in|info|biz|dev|site|online|shop|store|cc|tk|ru|cn)\b(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
_TEMPLATE_NAME = re.compile(r"[a-z0-9_]{1,512}")
_TEMPLATE_LANG = re.compile(r"[a-z]{2,3}(?:_[A-Z]{2})?")


@dataclass
class SendResult:
    status: int
    body: dict[str, Any] = field(default_factory=dict)


def _fail(status: int, reason: str) -> SendResult:
    return SendResult(status, {"ok": False, "reason": reason})


def parse_ts(value: Any) -> float | None:
    """Epoch seconds, epoch milliseconds or an ISO date, as seconds. None when unreadable."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d+", value)):
        number = float(value)
        return number / 1000 if number > 1e11 else number
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.timestamp() if parsed.tzinfo else None
    return None


def _host_allowed(host: str, nori_host: str) -> bool:
    host = host.lower().rstrip(".")
    return bool(nori_host) and (host == nori_host or host.endswith("." + nori_host))


def foreign_urls(text: str, nori_host: str) -> list[str]:
    """Links in `text` that do not point at nori's own host (or one of its subdomains)."""
    found = []
    for match in _URL.finditer(text):
        raw = match.group(0).rstrip(".,;:!?)")
        bare = re.sub(r"^(?:https?://)", "", raw, flags=re.IGNORECASE)
        host = re.split(r"[/:?#]", bare, maxsplit=1)[0]
        host = host[4:] if host.lower().startswith("www.") else host
        if not _host_allowed(host, nori_host):
            found.append(host)
    return found


def check_content(
    text: Any, template: Any, nori_host: str
) -> tuple[str, dict[str, Any] | None, str | None]:
    """(clean text, validated template or None, reason when refused)."""
    if not isinstance(text, str):
        return "", None, "bad_text"
    clean = _CONTROL.sub("", text).strip()
    if not clean:
        return "", None, "empty_text"
    if len(clean) > MAX_TEXT_CHARS:
        return "", None, "text_too_long"
    if foreign_urls(clean, nori_host):
        return "", None, "link_not_allowed"
    if template is None:
        return clean, None, None
    if not isinstance(template, dict):
        return "", None, "bad_template"
    name, language, params = template.get("name"), template.get("language"), template.get("params")
    if not isinstance(name, str) or not _TEMPLATE_NAME.fullmatch(name):
        return "", None, "bad_template"
    if not isinstance(language, str) or not _TEMPLATE_LANG.fullmatch(language):
        return "", None, "bad_template"
    if not isinstance(params, list) or not 1 <= len(params) <= MAX_TEMPLATE_PARAMS:
        return "", None, "bad_template"
    values = []
    for item in params:
        if not isinstance(item, str):
            return "", None, "bad_template"
        value = _CONTROL.sub("", item).strip()
        if len(value) > MAX_TEXT_CHARS:
            return "", None, "text_too_long"
        if foreign_urls(value, nori_host):
            return "", None, "link_not_allowed"
        values.append(value)
    return clean, {"name": name, "language": language, "params": values}, None


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
        )
        .order_by(WhatsAppConnection.created_at)
    )
    found = []
    for connection, rules in rows.all():
        bridge = workspace_bridge(rules)
        if bridge is not None and bridge.send_enabled:
            found.append((connection, bridge))
    return found


async def _pick(
    session: AsyncSession,
    candidates: list[tuple[WhatsAppConnection, WorkspaceBridge]],
    to: str,
    preferred_number_id: str,
) -> tuple[tuple[WhatsAppConnection, WorkspaceBridge] | None, bool]:
    """(the connection to send from, whether this number has messaged pi on it)."""
    by_id = {c.id: (c, b) for c, b in candidates}
    conversation = await session.scalar(
        select(PiConversation)
        .where(
            PiConversation.connection_id.in_(list(by_id)),
            PiConversation.contact_wa_id == to,
            PiConversation.last_inbound_at.is_not(None),
        )
        .order_by(PiConversation.last_inbound_at.desc())
        .limit(1)
    )
    if conversation is not None:
        return by_id[conversation.connection_id], True
    if preferred_number_id:
        for pair in candidates:
            if pair[0].phone_number_id == preferred_number_id:
                return pair, False
    if len(candidates) == 1:
        return candidates[0], False
    return None, False


async def handle(
    session: AsyncSession,
    settings: Any,
    http: Any,
    raw: bytes,
    signature: str | None,
    *,
    declared_length: int | None = None,
    now: float | None = None,
) -> SendResult:
    """Decide and, when every check passes, send. Never raises."""
    try:
        return await _handle(session, settings, http, raw, signature, declared_length, now)
    except Exception:
        METRICS.inc("send", "error")
        logger.warning("nori_bridge_send_error", exc_info=False)
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
    number: object = "",
    target: tuple[WhatsAppConnection, WorkspaceBridge] | None = None,
    outcome: str = "rejected",
) -> SendResult:
    METRICS.inc("send", reason)
    await store.audit(
        session,
        "send",
        outcome,
        reason=reason,
        number=number,
        tenant_id=target[0].tenant_id if target else None,
        environment_id=target[0].environment_id if target else None,
    )
    await session.commit()
    return _fail(status, reason)


async def _handle(
    session: AsyncSession,
    settings: Any,
    http: Any,
    raw: bytes,
    signature: str | None,
    declared_length: int | None,
    now: float | None,
) -> SendResult:
    env = read_env(settings)
    if env is None:
        return _fail(503, "not_configured")
    if killed(settings):
        METRICS.inc("send", "killed")
        return _fail(503, "disabled")
    if len(raw) > MAX_BODY_BYTES or (declared_length or 0) > MAX_BODY_BYTES:
        METRICS.inc("send", "too_large")
        return _fail(413, "too_large")
    if not signing.verify(env.secret, raw, signature):
        METRICS.inc("send", "bad_signature")
        logger.warning("nori_bridge_send_bad_signature")
        return _fail(401, "bad_signature")

    candidates = await _candidates(session)
    if not candidates:
        METRICS.inc("send", "disabled")
        return _fail(503, "disabled")

    try:
        data = json.loads(raw)
    except ValueError:
        return await _reject(session, 400, "bad_json")
    if not isinstance(data, dict):
        return await _reject(session, 400, "bad_json")
    to = digits(data.get("to")) if isinstance(data.get("to"), str) else ""
    if not 7 <= len(to) <= 15:
        return await _reject(session, 400, "bad_recipient")

    stamp = parse_ts(data.get("ts"))
    clock = time.time() if now is None else now
    if stamp is None or abs(clock - stamp) > FRESHNESS_SECONDS:
        return await _reject(session, 401, "stale", number=to)

    fresh = await store.claim(
        session, "replay", store.key_of(str(data.get("ts")), signature or ""), outcome="seen"
    )
    if not fresh:
        return await _reject(session, 409, "replay", number=to)

    # The per-minute limit is the lowest of the enabled workspaces' settings.
    limit = min(bridge.send_per_minute for _, bridge in candidates)
    if await store.sends_in_last_minute(session) >= limit:
        return await _reject(session, 429, "rate_limited", number=to, outcome="rate_limited")

    target, history = await _pick(
        session, candidates, to, getattr(settings, "nori_bridge_phone_number_id", "") or ""
    )
    if target is None:
        return await _reject(session, 503, "no_sender", number=to)
    connection, bridge = target

    if not history:
        identity = await NoriClient(env, http, bridge).identify(to)
        if not identity.checked:
            return await _reject(session, 503, "cannot_verify", number=to, target=target)
        if not identity.known:
            return await _reject(session, 403, "recipient_not_allowed", number=to, target=target)

    text, template, refused = check_content(data.get("text"), data.get("template"), env.host)
    if refused:
        return await _reject(session, 422, refused, number=to, target=target)

    from app.integrations.whatsapp_bridge import token as connection_token
    from app.modules.pi.whatsapp import WhatsApp

    whatsapp = WhatsApp(settings, http, connection.provider)
    try:
        secret = await connection_token(session, settings, connection)
        if template is not None:
            message_id = await whatsapp.send_template_values(
                connection.phone_number_id, to, template, template["params"], secret
            )
        else:
            message_id = await whatsapp.send(connection.phone_number_id, to, text, secret)
    except BusinessRuleViolation as error:
        reason = re.sub(r"[^a-z0-9]+", "_", error.code.lower()).strip("_")[:60]
        status = 502 if error.status >= 500 else 422
        return await _reject(
            session, status, reason or "send_failed", number=to, target=target, outcome="failed"
        )
    await store.audit(
        session,
        "send",
        "sent_template" if template is not None else "sent_text",
        number=to,
        tenant_id=connection.tenant_id,
        environment_id=connection.environment_id,
    )
    await store.purge(session)
    await session.commit()
    METRICS.inc("send", "sent")
    logger.info("nori_bridge_sent", extra={"to": mask_number(to), "template": template is not None})
    return SendResult(200, {"ok": True, "sent": True, "id": message_id})
