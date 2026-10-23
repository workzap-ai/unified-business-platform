"""The picture links pi sends on WhatsApp (spec 8.11.2). The signed token names one conversation,
so the link works for the person who was sent it and says nothing about them."""

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app.core import rate_limit
from app.modules.access.dependencies import Session
from app.modules.pi import brain_visuals, taxonomy
from app.modules.pi.models import PiConversation
from app.modules.pi.problem_models import PiProblem

public_router = APIRouter(prefix="/brain-visuals", tags=["pi-brain-visuals"])


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
    if claims["kind"] == "progress":
        png = brain_visuals.render_progress(claims["step"], language)
    else:
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
