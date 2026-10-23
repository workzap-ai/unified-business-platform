"""Queuing the visuals of spec 8.11.2 next to pi's text replies.

The problem board (a picture) and the tap-to-correct list go out with the sorted summary; the
progress card goes out with the approved documents. The summary text is always sent as well: it is
the body of the list message, or a plain message when it is too long for a list. Nothing is queued
for a language the picture font cannot draw, or when nothing is noted.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.pi import brain_visuals, problems
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
