"""Queuing the visuals of spec 8.11.2 next to pi's text replies.

The problem board (a picture) and the tap-to-correct list go out with the sorted summary; the
progress card goes out with the approved documents. The summary text is always sent as well: it is
the body of the list message, or a plain message when it is too long for a list. Nothing is queued
for a language the picture font cannot draw, or when nothing is noted.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.pi import brain_visuals, dials, map_builder, map_render, problems
from app.modules.pi.brain_docs import queue_message
from app.modules.pi.models import PiConversation, PiMessage
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

LIST_BODY_LIMIT = 1024  # what WhatsApp allows in the body of a list message


async def _queue_reply(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    body: str,
    key: str,
    media: dict[str, Any],
) -> str:
    """A queued message from pi itself (so every send-time guard that applies to its replies
    applies to this one)."""
    repo = WorkspaceRepository(session, PiMessage, scope)
    existing = await repo.find(PiMessage.idempotency_key == key)
    if existing is not None:
        return str(existing.id)
    message = await repo.add(
        repo.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="ai",
            body=body,
            media=media,
            status="queued",
            idempotency_key=key,
        )
    )
    return str(message.id)


async def attach_board(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    conversation: PiConversation,
    outbound: list[str],
    language: str,
) -> list[str]:
    """After a sorted summary: the board picture first, and the summary text turned into a list
    the person can tap to correct a problem. Returns the message ids in the order to send."""
    if not brain_visuals.supported(language) or conversation.customer_id is None:
        return outbound
    summary = None
    for message_id in outbound:
        row = await session.scalar(select(PiMessage).where(PiMessage.id == message_id))
        if row is not None and row.sender_type == "ai" and row.status == "queued":
            summary = row
            break
    if summary is None or (summary.media or {}).get("list") or (summary.media or {}).get("image"):
        return outbound
    book = problems.ProblemBook(session, scope, conversation.customer_id, language)
    rows = await book.active()
    if not rows:
        return outbound
    words = brain_visuals.TEXT[language]
    link = brain_visuals.url(
        settings, brain_visuals.token(settings, conversation.id, "board", language), "board"
    )
    # Sent as pi's own reply, with the summary's inbound marker: it is held back exactly when the
    # summary is (auto-reply off, a person took over, the customer wrote again meanwhile).
    inbound = (summary.media or {}).get("service_inbound_at")
    image = await _queue_reply(
        session,
        scope,
        conversation,
        words["caption"],
        f"pi-board:{conversation.id}:{summary.id}",
        {"image": link, "visual": "board", **({"service_inbound_at": inbound} if inbound else {})},
    )
    options = brain_visuals.list_rows(rows)
    keeps_buttons = bool((summary.media or {}).get("buttons"))  # a list would replace them
    if options and not keeps_buttons and len(summary.body or "") <= LIST_BODY_LIMIT:
        media: dict[str, Any] = dict(summary.media or {})
        media["list"] = {"button": words["list_button"], "rows": options}
        summary.media = media
    return [image, *outbound]


async def progress_message(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    conversation: PiConversation,
    step: int,
    key: str,
) -> str | None:
    """The progress card for this step, or None for a language the font cannot draw."""
    language = conversation.language or "en"
    if not brain_visuals.supported(language):
        return None
    link = brain_visuals.url(
        settings,
        brain_visuals.token(settings, conversation.id, "progress", language, step),
        "progress",
    )
    return await queue_message(
        session,
        scope,
        conversation,
        brain_visuals.TEXT[language]["progress_caption"],
        key,
        {"image": link, "visual": "progress"},
    )


# --- the problem map in the chat (spec Book 5, 4.4), behind response_rules.brain.map_share --------

WINDOW = timedelta(hours=24)
MAP_QUESTION = {
    "en": "Are the links right?",
    "roman_ur": "Kya ye jorr sahi hain?",
}
logger = logging.getLogger("platform")


async def _owner_texts(session: AsyncSession, conversation: PiConversation) -> list[str]:
    rows = await session.scalars(
        select(PiMessage.body)
        .where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "inbound",
        )
        .order_by(PiMessage.created_at)
    )
    return [str(t) for t in rows if t]


async def _pi_messages_since(
    session: AsyncSession, conversation: PiConversation, since: datetime
) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PiMessage)
        .where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "outbound",
            PiMessage.sender_type == "ai",
            PiMessage.created_at > since,
        )
    )
    return int(count or 0)


async def attach_map(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    conversation: PiConversation,
    outbound: list[str],
    language: str,
    *,
    asked: bool = False,
    at_offer: bool = False,
    await_review: bool = False,
) -> list[str]:
    """After pi's reply: the problem map as a picture with its caption and one question, when
    spec 4.4 says it is due. Only inside the 24-hour window; if the picture cannot be drawn the
    same map goes as the text with arrows. The caller checks `map_builder.share_enabled`.

    The alt text list is stored on the message (`media.alt`). The picture itself is drawn when
    WhatsApp fetches the signed link, from the saved version, so the chat and the dashboard show
    the same data. `await_review` marks the chat so the next reply is read as a review of the map
    (Solution Box B3, see `box_signals`). Returns the message ids to send, pi's reply first."""
    now = datetime.now(UTC)
    if conversation.customer_id is None or not outbound:
        return outbound
    if conversation.last_inbound_at is None or now - conversation.last_inbound_at > WINDOW:
        return outbound
    row, _ = await map_builder.save_if_changed(session, scope, conversation.customer_id)
    if row is None:
        return outbound
    texts = await _owner_texts(session, conversation)
    state = dials.estimate(texts)
    shared = await map_builder.last_shared(session, scope, conversation.customer_id)
    fresh, linked = map_builder.new_since(shared.map_json if shared else None, row.map_json)
    due, _why = map_builder.share_due(
        map_builder.ShareFacts(
            nodes=len(row.map_json.get("nodes") or []),
            links=len(row.map_json.get("links") or []),
            ever_shared=shared is not None,
            new_nodes=fresh,
            new_node_linked=linked,
            pi_messages_since_share=(
                await _pi_messages_since(session, conversation, shared.shared_at)
                if shared is not None and shared.shared_at is not None
                else None
            ),
            hurried=dials.posture(state) == "hurried",
            openness=state.openness,
            asked=asked,
            at_offer=at_offer,
        )
    )
    if not due:
        return outbound
    drawn = None
    try:
        drawn = map_render.render_map(row.map_json, language, owner_messages=texts)
    except Exception:  # a drawing fault must never cost the person their reply
        logger.warning("map_render_failed", exc_info=True)
    question = MAP_QUESTION.get(language, MAP_QUESTION["en"])
    inbound = conversation.last_inbound_at.isoformat()
    key = f"pi-map:{conversation.id}:{row.version}:{inbound}"  # a retry is idempotent
    if drawn is not None and drawn.images:
        image = drawn.images[0]
        link = brain_visuals.url(
            settings,
            brain_visuals.token(
                settings, conversation.id, "map", drawn.language, version=row.version
            ),
            "map",
        )
        media: dict[str, Any] = {
            "image": link,
            "visual": "map",
            "alt": image.alt,
            "map_version": row.version,
            "service_inbound_at": inbound,
        }
        body = f"{image.caption}\n{question}"
    else:
        text = drawn.text if drawn is not None else map_render.text_fallback(row.map_json, language)
        media = {"visual": "map_text", "map_version": row.version, "service_inbound_at": inbound}
        body = f"{text}\n\n{question}"
    message_id = await _queue_reply(session, scope, conversation, body, key, media)
    row.shared_at = now
    row.shared_message_id = UUID(message_id)
    if await_review:  # Solution Box on: the owner's next reply can confirm or change the map (B3)
        conversation.service_brief = {**(conversation.service_brief or {}), "map_awaiting": True}
    return [*outbound, message_id]
