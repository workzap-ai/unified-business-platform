"""The inbound pre-hook: ask nori before pi's brain, for enabled workspaces only.

Order of work for one inbound text message:
  1. gates: server variables, kill switch, workspace flag. Any closed gate returns at once.
  2. `identify` with the sender's number ONLY. An unknown number (or a failed call) ends here and
     pi carries on exactly as before; no text has left pi.
  3. for a nori member: claim the WhatsApp message id (a retry never replies twice), then POST the
     message to nori's inbound door. `handled: true` stops the brain and nori's reply is sent;
     anything else, and every error, carries on as if the hook did not exist (fail open).
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.modules.pi_saas.nori_credits import store
from app.modules.pi_saas.nori_credits.client import NoriClient
from app.modules.pi_saas.nori_credits.config import (
    MAX_TEXT_CHARS,
    killed,
    read_env,
    workspace_bridge,
)
from app.modules.pi_saas.nori_credits.resilience import METRICS, digits, mask_number
from app.modules.pi_saas.nori_credits.send_door import foreign_urls

logger = logging.getLogger("app.pi.nori_credits")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")


@dataclass(frozen=True)
class HookOutcome:
    handled: bool = False
    reply: str | None = None
    reason: str = "off"
    board_ref: str | None = None  # a registry number wrote: the card's ref; the chat goes on


PASS = HookOutcome()
LINK_FALLBACK = "Done. Please open nori to see the details."


def clean_reply(value: Any) -> str | None:
    """nori's reply as plain text to send: control and direction characters removed, capped."""
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub("", value).strip()
    return text[:MAX_TEXT_CHARS] or None


async def pre_hook(
    ctx: dict[str, Any], session: Any, scope: Any, connection: Any, event: Any
) -> HookOutcome:
    """Never raises. handled=True: send `reply` (if any) and stop, pi's brain must not run."""
    payload = getattr(event, "payload", None)
    if not isinstance(payload, dict) or payload.get("kind") != "message":
        return PASS
    if payload.get("message_type") not in ("text", *MEDIA_TYPES) or payload.get("signal"):
        return PASS
    settings = ctx.get("settings")
    env = read_env(settings)
    if env is None:
        return PASS  # inert: no variable, no work
    if killed(settings):
        METRICS.inc("inbound", "killed")
        return PASS
    try:
        return await _run(ctx, session, scope, connection, payload, settings, env)
    except Exception:
        METRICS.inc("inbound", "error")
        logger.warning("nori_bridge_hook_error", exc_info=False)
        return PASS


# A photo, voice note, video or file from a registry number is filed as a card too (a placeholder
# line plus any caption) and the chat is kept, so pi's brain never answers such a person. For any
# other sender non-text messages are untouched.
MEDIA_TYPES = ("audio", "image", "video", "other")
MEDIA_LABEL = {"audio": "voice note", "image": "photo", "video": "video", "other": "file"}

BOARD_ACK = "I'm pi, an AI assistant. I've passed this to the Workzap team."
BOARD_RETRY = "I'm pi, an AI assistant. I could not save that just now. Please send it again."


async def _board_path(
    session: Any,
    scope: Any,
    connection: Any,
    payload: dict[str, Any],
    sender: str,
    message_id: str,
    text: str,
) -> HookOutcome | None:
    """A number on the Nori Platform board's registry (added by hand on the board): its message is
    filed as a board card and answered here, so pi's sales brain never runs for it. None when the
    sender is not on the registry (or is switched off there): the hook carries on as before.

    Idempotent by WhatsApp message id: the claim and the card are saved together, so a failure
    leaves neither behind and the person is asked to send again."""
    from app.modules.pi_saas.nori_board import service

    entry = await service.find_number(session, scope, sender)
    if entry is None or not entry.active:
        return None
    from app.modules.pi import safety

    if safety.emergency(text) is not None or safety.opt_out_asked(text):
        # An emergency or a "stop" belongs to pi's own pre-model gates (emergency numbers, opt-out):
        # nothing is filed here and no board reply is sent.
        METRICS.inc("inbound", "board_safety_pass")
        return PASS
    key = store.key_of("board", str(getattr(connection, "phone_number_id", "")), message_id)
    try:
        async with session.begin_nested():
            fresh = await store.claim(
                session,
                "inbound",
                key,
                tenant_id=getattr(scope, "tenant_id", None),
                environment_id=getattr(scope, "environment_id", None),
            )
            if fresh:
                await service.file_item(
                    session,
                    scope,
                    ref="wa:" + key[:40],
                    kind=service.classify(text),
                    text=text,
                    workspace=entry.workspace,
                    person=entry.person,
                    department=entry.department,
                    phone=sender,
                    source="whatsapp",
                    created_by_label="pi",
                )
    except Exception:
        METRICS.inc("inbound", "board_error")
        logger.warning("nori_bridge_board_error", exc_info=False)
        return HookOutcome(handled=True, reply=BOARD_RETRY, reason="board_error")
    ref = "wa:" + key[:40]
    if not fresh:
        METRICS.inc("inbound", "board_duplicate")
        return HookOutcome(reason="board_duplicate", board_ref=ref)
    await store.set_outcome(session, "inbound", key, "handled", "board")
    METRICS.inc("inbound", "board_filed")
    # Not handled: pi's runtime stores the message in the inbox, puts the chat in human mode (the
    # brain stays silent), links the card to the chat and sends BOARD_ACK once.
    return HookOutcome(reason="board", board_ref=ref)


async def _run(
    ctx: dict[str, Any],
    session: Any,
    scope: Any,
    connection: Any,
    payload: dict[str, Any],
    settings: Any,
    env: Any,
) -> HookOutcome:
    sender = digits(payload.get("sender"))
    message_id = str(payload.get("message_id") or "")
    text = str(payload.get("body") or "")
    media = payload.get("message_type") != "text"
    if media:
        label = (
            "[" + MEDIA_LABEL.get(str(payload.get("message_type")), "file") + " sent on WhatsApp]"
        )
        text = f"{label} {text}".strip()
    if not 7 <= len(sender) <= 15 or not message_id or not text.strip():
        return PASS
    # Workzap Connect (pi_saas/nori_bridge.py) already posts every message of its number to the
    # same nori door. Asking twice would double the calls and could double the reply.
    from app.modules.pi_saas import nori_bridge

    if nori_bridge.configured_for(settings, getattr(connection, "phone_number_id", None)):
        METRICS.inc("inbound", "skipped_connect_number")
        return PASS
    from app.modules.pi.configuration import settings_row

    policy = await settings_row(session, scope)
    bridge = workspace_bridge(policy.response_rules)
    if bridge is None:
        return PASS
    if bridge.board:
        filed = await _board_path(session, scope, connection, payload, sender, message_id, text)
        if filed is not None:
            return filed
    if media:
        return PASS  # not on the registry: nori's identify only ever saw text
    client = NoriClient(env, ctx["http"], bridge)

    identity = await client.identify(sender)
    if not identity.checked:
        METRICS.inc("inbound", "failopen_identify")
        return HookOutcome(reason="failopen_identify")
    if not identity.known:
        METRICS.inc("inbound", "not_member")
        return HookOutcome(reason="not_member")

    key = store.key_of(str(getattr(connection, "phone_number_id", "")), message_id)
    async with session.begin_nested():
        fresh = await store.claim(
            session,
            "inbound",
            key,
            tenant_id=getattr(scope, "tenant_id", None),
            environment_id=getattr(scope, "environment_id", None),
        )
        existing = None if fresh else await store.outcome_of(session, "inbound", key)
    if not fresh:
        METRICS.inc("inbound", "duplicate")
        if existing in {"handled", "claimed"}:
            return HookOutcome(handled=True, reply=None, reason="duplicate")
        return HookOutcome(reason="duplicate_passed")

    result = await client.inbound(
        sender=sender,
        message_id=message_id,
        text=text,
        name=str(payload.get("profile") or "")[:120] or None,
    )
    if not result.ok:
        await store.set_outcome(session, "inbound", key, "failopen", result.reason)
        METRICS.inc("inbound", "failopen_" + result.reason)
        logger.warning(
            "nori_bridge_failopen",
            extra={"reason": result.reason, "status": result.status, "to": mask_number(sender)},
        )
        return HookOutcome(reason="failopen_" + result.reason)
    if result.data.get("handled") is not True:
        await store.set_outcome(session, "inbound", key, "passed")
        METRICS.inc("inbound", "passed")
        return HookOutcome(reason="not_handled")
    await store.set_outcome(session, "inbound", key, "handled")
    METRICS.inc("inbound", "handled")
    await store.purge(session)
    reply = clean_reply(result.data.get("reply"))
    if reply and foreign_urls(reply, env.host):
        # nori's own links are fine; any other link in a system reply is replaced, never sent.
        METRICS.inc("inbound", "reply_link_blocked")
        reply = LINK_FALLBACK
    return HookOutcome(handled=True, reply=reply, reason="handled")
