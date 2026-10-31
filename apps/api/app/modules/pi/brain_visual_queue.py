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
from app.modules.pi import (
    brain_visuals,
    dials,
    map_builder,
    map_render,
    map_share,
    problems,
)
from app.modules.pi.box_models import PiMapVersion
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
    groups = brain_visuals.groups_of(rows, language)  # the board as sent (spec v1.6, 19.8)
    link = brain_visuals.url(
        settings,
        brain_visuals.token(
            settings, conversation.id, "board", language, message=str(summary.id)
        ),
        "board",
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
        {
            "image": link,
            "visual": "board",
            "board_snapshot": brain_visuals.snapshot_of(groups),
            **({"service_inbound_at": inbound} if inbound else {}),
        },
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
# the overview and up to four cluster pictures go in the chat; the rest are on the page
MAX_MAP_IMAGES = 5
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


async def _previous_inbound(
    session: AsyncSession, conversation: PiConversation, message: PiMessage | None
) -> datetime | None:
    """When the owner last wrote before this message (None for a first message)."""
    if message is None or message.created_at is None:
        return None
    found: datetime | None = await session.scalar(
        select(func.max(PiMessage.created_at)).where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "inbound",
            PiMessage.created_at < message.created_at,
        )
    )
    return found


async def _picture_in(session: AsyncSession, outbound: list[str]) -> bool:
    """A board or map picture is already queued for this turn (never two pictures in one turn)."""
    for message_id in outbound:
        row = await session.scalar(select(PiMessage).where(PiMessage.id == message_id))
        if row is not None and (row.media or {}).get("visual") in ("board", "map"):
            return True
    return False


async def _times_shared(session: AsyncSession, scope: WorkspaceScope, customer_id: UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PiMapVersion)
        .where(
            PiMapVersion.tenant_id == scope.tenant_id,
            PiMapVersion.environment_id == scope.environment_id,
            PiMapVersion.customer_id == customer_id,
            PiMapVersion.shared_at.is_not(None),
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
    inbound: PiMessage | None = None,
) -> list[str]:
    """After pi's reply: the problem map as a picture with its caption and one question, when
    spec 4.4 says it is due (first map, an update, on request, the check-in at the offer, or the
    owner coming back after a day). Only inside the 24-hour window; if the picture cannot be drawn
    the same map goes as the text with arrows. The caller checks `map_builder.share_enabled`.

    A map with more than nine problems goes as the overview and the cluster pictures, the question
    on the last one. A share carries three reply buttons (right, wrong, missing); the share at the
    offer carries none and goes before the offer, so the offer's question stays last; a returning
    owner gets continuity words and one open question (Part 6). Never two pictures in one turn: if
    the board picture is queued the map waits for the next turn.

    The alt text list is stored on the message (`media.alt`). The picture itself is drawn when
    WhatsApp fetches the signed link, from the saved version, so the chat and the dashboard show
    the same data, with every node where the owner saw it last time. `await_review` marks the chat
    so the next reply is read as a review of the map (Solution Box B3, see `box_signals`). Returns
    the message ids to send."""
    now = datetime.now(UTC)
    if conversation.customer_id is None or not outbound:
        return outbound
    if conversation.last_inbound_at is None or now - conversation.last_inbound_at > WINDOW:
        return outbound
    if await _picture_in(session, outbound):
        return outbound
    row, _ = await map_builder.save_if_changed(session, scope, conversation.customer_id)
    if row is None:
        return outbound
    texts = await _owner_texts(session, conversation)
    state = dials.estimate(texts)
    shared = await map_builder.last_shared(session, scope, conversation.customer_id)
    fresh, linked = map_builder.new_since(shared.map_json if shared else None, row.map_json)
    returning = map_share.is_return(await _previous_inbound(session, conversation, inbound), now)
    due, why = map_builder.share_due(
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
            returning=returning,
            changed_since_share=shared is None or shared.version != row.version,
        )
    )
    if not due:
        return outbound
    language = map_render.share_language(language)  # one script across picture, question, buttons
    before = map_builder.slots_of(row.positions) or await map_builder.previous_positions(
        session, scope, conversation.customer_id, row.version
    )
    drawn = None
    try:
        drawn = map_render.render_map(row.map_json, language, previous=before, owner_messages=texts)
    except Exception:  # a drawing fault must never cost the person their reply
        logger.warning("map_render_failed", exc_info=True)
    times = await _times_shared(session, scope, conversation.customer_id)
    last_inbound = conversation.last_inbound_at.isoformat()
    key = f"pi-map:{conversation.id}:{row.version}:{last_inbound}"  # a retry is idempotent
    base_media: dict[str, Any] = {"map_version": row.version, "service_inbound_at": last_inbound}
    at_the_offer = why.startswith("offer")
    if why == "return":  # continuity, the link, what is old, then one open question (Part 6)
        closing = map_share.return_text(
            language,
            stale=bool(map_builder.stale_ids(row.map_json)),
            link=map_share.dashboard_link(settings.pi_app_public_url),
        )
    elif at_the_offer:
        closing = ""  # the offer that follows carries the question and stays last
    else:
        closing = map_share.question(language, times)
    buttons = [] if why == "return" or at_the_offer else map_share.buttons(language)
    ids: list[str] = []
    if drawn is not None and drawn.images:
        pictures = drawn.images[:MAX_MAP_IMAGES]
        for index, image in enumerate(pictures):
            token = brain_visuals.token(
                settings, conversation.id, "map", drawn.language, version=row.version, part=index
            )
            media: dict[str, Any] = {
                **base_media,
                "image": brain_visuals.url(settings, token, "map"),
                "visual": "map",
                "alt": image.alt,
            }
            body = image.caption
            if index == len(pictures) - 1:
                asks = map_share.caption_asks(body)
                if asks and (why == "return" or at_the_offer):
                    body = map_share.without_ask(body)  # the return or offer line asks instead
                    asks = False
                if closing and not asks:  # a caption that asks is already the one question
                    body = f"{body}\n{closing}"
                if buttons and (closing or asks) and len(body) <= LIST_BODY_LIMIT:
                    media["buttons"] = buttons
            part_key = key if index == 0 else f"{key}:{index}"
            ids.append(await _queue_reply(session, scope, conversation, body, part_key, media))
        if drawn.positions:
            map_builder.remember_positions(row, drawn.positions)
    else:
        text = drawn.text if drawn is not None else map_render.text_fallback(row.map_json, language)
        media = {**base_media, "visual": "map_text"}
        body = f"{text}\n\n{closing}" if closing else text
        if buttons and len(body) <= LIST_BODY_LIMIT:
            media["buttons"] = buttons
        ids.append(await _queue_reply(session, scope, conversation, body, key, media))
    row.shared_at = now
    row.shared_message_id = UUID(ids[-1])
    if await_review and not at_the_offer:
        # Solution Box on: the owner's next reply can confirm or change the map (B3)
        conversation.service_brief = {**(conversation.service_brief or {}), "map_awaiting": True}
    return [*ids, *outbound] if at_the_offer else [*outbound, *ids]
