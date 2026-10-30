"""The picture links pi sends on WhatsApp (spec 8.11.2). The signed token names one conversation,
so the link works for the person who was sent it and says nothing about them."""

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.modules.access.dependencies import Session
from app.modules.pi import brain_visuals, map_builder, map_render, taxonomy
from app.modules.pi.box_models import PiMapVersion
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.problem_models import PiProblem
from app.shared.scope import WorkspaceScope

public_router = APIRouter(prefix="/brain-visuals", tags=["pi-brain-visuals"])


def _scope_of(conversation: PiConversation) -> WorkspaceScope:
    return WorkspaceScope.system(
        conversation.tenant_id, conversation.environment_id, frozenset(), "pi brain visual"
    )


async def _map_png(
    session: AsyncSession,
    conversation: PiConversation,
    version: int,
    language: str,
    part: int = 0,
) -> bytes:
    """The picture of one saved map version of this conversation's customer (spec 4.9: the same
    data as the dashboard). `part` picks the overview (0) or a cluster's detail picture when the
    map has more than nine problems. Nodes keep the places the owner saw them at."""
    row = await session.scalar(
        select(PiMapVersion).where(
            PiMapVersion.tenant_id == conversation.tenant_id,
            PiMapVersion.environment_id == conversation.environment_id,
            PiMapVersion.customer_id == conversation.customer_id,
            PiMapVersion.version == version,
        )
    )
    if row is None:
        raise HTTPException(status_code=404)
    # What this version already drew is reused as is; otherwise the version before it sets places.
    before = map_builder.slots_of(row.positions) or await map_builder.previous_positions(
        session, _scope_of(conversation), conversation.customer_id, version
    )
    drawn = map_render.render_map(row.map_json, language, previous=before)
    if part >= len(drawn.images):
        raise HTTPException(status_code=404)
    if not row.positions and drawn.positions:
        map_builder.remember_positions(row, drawn.positions)
        await session.commit()
    return drawn.images[part].png


async def _stored_board_png(
    session: AsyncSession, conversation: PiConversation, summary_id: str, language: str
) -> bytes | None:
    """19.8: the board exactly as sent, drawn from the snapshot stored on the queued image."""
    if not summary_id:
        return None
    sent = await session.scalar(
        select(PiMessage).where(
            PiMessage.conversation_id == conversation.id,
            PiMessage.idempotency_key == f"pi-board:{conversation.id}:{summary_id}",
        )
    )
    snapshot = (sent.media or {}).get("board_snapshot") if sent else None
    groups = brain_visuals.groups_from_snapshot(snapshot)
    return brain_visuals.render_board(groups, language) if groups else None


@public_router.get("/{token}/{name}")
async def visual(token: str, name: str, request: Request, session: Session) -> Response:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pi-brain-visual", f"{token[-24:]}:{ip}", 60, 3600):
        raise HTTPException(status_code=429)
    claims = brain_visuals.read(request.app.state.settings, token)
    if claims is None or name != f"{claims['kind']}.png":
        raise HTTPException(status_code=404)
    conversation = await session.scalar(
        select(PiConversation).where(PiConversation.id == claims["conversation_id"])
    )
    if conversation is None or conversation.customer_id is None:
        raise HTTPException(status_code=404)
    language = claims["language"]
    png: bytes | None
    if claims["kind"] == "map":
        png = await _map_png(session, conversation, claims["version"], language, claims["part"])
    elif claims["kind"] == "progress":
        png = brain_visuals.render_progress(claims["step"], language)
    else:
        png = await _stored_board_png(session, conversation, claims["message"], language)
    if png is None:  # an older link, or no stored snapshot: drawn from the current problems
        rows = list(
            await session.scalars(
                select(PiProblem)
                .where(
                    PiProblem.tenant_id == conversation.tenant_id,
                    PiProblem.environment_id == conversation.environment_id,
                    PiProblem.customer_id == conversation.customer_id,
                    PiProblem.status.in_(taxonomy.ACTIVE),
                )
                .order_by(PiProblem.number)
            )
        )
        if not rows:
            raise HTTPException(status_code=404)
        # The business is never named: the profile can be filled from a staff record, and a
        # picture may only carry a name the person gave in this chat.
        png = brain_visuals.render_board(brain_visuals.groups_of(rows, language), language)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
