"""The Nori Platform board's HTTP faces.

``router``       /pi/nori-board: the team's own API (numbers, a requirement by hand), mounted for
                 Owner OS and the pi app like the team board. Reading needs ``pi.work.read``,
                 changing ``pi.work.manage``.
``door_router``  POST /api/pi/nori-board: nori pushes an item (signed; see door.py). Exists in every
                 deployment, answers 503 until the bridge variables and the board flag are on.
"""

from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.service import require_pi
from app.modules.pi_saas import team_board
from app.modules.pi_saas.nori_board import door, service
from app.modules.pi_saas.nori_board.models import ITEM_KINDS

router = APIRouter(prefix="/pi/nori-board", tags=["pi-nori-board"])
door_router = APIRouter(tags=["pi-nori-board"])

ItemKind = Literal["feature", "problem", "feedback", "module", "question", "change", "note"]
assert set(ITEM_KINDS) == set(ItemKind.__args__)  # type: ignore[attr-defined]


@door_router.post("/nori-board", include_in_schema=False)
async def nori_board_door(request: Request, session: Session) -> JSONResponse:
    return await _door(request, session, "board")


@door_router.post("/nori-numbers", include_in_schema=False)
async def nori_numbers_door(request: Request, session: Session) -> JSONResponse:
    return await _door(request, session, "numbers")


@door_router.get("/nori-media/{token}", include_in_schema=False)
async def nori_media(token: str, request: Request, session: Session) -> Response:
    """The photo or file behind a card, for nori's team (signed link, see media_link.py). Every
    refusal is the same plain 404, so a probe learns nothing."""
    from fastapi import HTTPException

    from app.modules.pi_saas.nori_board import media_link

    content = await media_link.fetch(session, request.app.state, token)
    if content is None:
        raise HTTPException(404, "Not found")
    data, mime, name = content
    safe = "".join(c for c in name if c.isalnum() or c in "._- ")[:80] or "file"
    return Response(
        data,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


async def _door(request: Request, session: Any, mode: str) -> JSONResponse:
    declared = request.headers.get("content-length")
    length = int(declared) if declared and declared.isdigit() else None
    body = bytearray()
    if length is None or length <= door.MAX_BODY_BYTES:
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > door.MAX_BODY_BYTES:
                break
    result = await door.handle(
        session,
        request.app.state.settings,
        bytes(body),
        request.headers.get("x-workzap-signature"),
        declared_length=length,
        mode=mode,
    )
    return JSONResponse(result.body, status_code=result.status)


# ---- Numbers ----------------------------------------------------------------------------------


@router.get("/numbers")
async def get_numbers(scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.read")
    full = scope.can("pi.work.manage")
    rows = await service.list_numbers(session, scope)
    workspaces = await service.known_workspaces(session, scope)
    await session.commit()
    return {
        "numbers": [service.number_view(row, full=full) for row in rows],
        "workspaces": workspaces,
    }


class NewNumber(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    phone: str = Field(min_length=1, max_length=40)
    workspace: str = Field(min_length=1, max_length=120)
    person: str = Field("", max_length=120)
    department: str = Field("", max_length=80)


@router.post("/numbers", status_code=201)
async def add_number(data: NewNumber, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    row = await service.add_number(
        session,
        scope,
        phone=data.phone,
        workspace=data.workspace,
        person=data.person,
        department=data.department,
    )
    await record(
        session, "pi.nori_number_added", scope=scope, entity_type="pi_nori_number", entity_id=row.id
    )
    await session.commit()
    return service.number_view(row, full=True)


class NumberChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    workspace: str | None = Field(None, min_length=1, max_length=120)
    person: str | None = Field(None, max_length=120)
    department: str | None = Field(None, max_length=80)
    active: bool | None = None


@router.patch("/numbers/{number_id}")
async def change_number(
    number_id: UUID, data: NumberChange, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    row = await service.update_number(session, scope, number_id, values)
    await record(
        session,
        "pi.nori_number_updated",
        scope=scope,
        entity_type="pi_nori_number",
        entity_id=row.id,
        details={k: str(v) for k, v in values.items()},
    )
    await session.commit()
    return service.number_view(row, full=True)


@router.delete("/numbers/{number_id}", status_code=204)
async def remove_number(number_id: UUID, scope: Scope, session: Session) -> Response:
    await require_pi(session, scope, "pi.work.manage")
    await service.delete_number(session, scope, number_id)
    await record(
        session,
        "pi.nori_number_removed",
        scope=scope,
        entity_type="pi_nori_number",
        entity_id=number_id,
    )
    await session.commit()
    return Response(status_code=204)


# ---- A requirement added by hand ---------------------------------------------------------------


class NewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=service.TITLE_MAX)
    text: str = Field("", max_length=service.TEXT_MAX)
    kind: ItemKind = "note"
    workspace: str = Field("", max_length=120)
    person: str = Field("", max_length=120)
    department: str = Field("", max_length=80)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


@router.post("/items", status_code=201)
async def add_item(data: NewItem, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    task, _ = await service.file_item(
        session,
        scope,
        ref=f"manual:{uuid4().hex[:24]}",
        kind=data.kind,
        title=data.title,
        text=data.text,
        workspace=data.workspace,
        person=data.person,
        department=data.department,
        source="manual",
        priority=data.priority,
        created_by_label=scope.actor_label[:80],
        created_by_user_id=scope.user_id,
    )
    await record(
        session, "pi.nori_item_added", scope=scope, entity_type="pi_task", entity_id=task.id
    )
    await session.commit()
    return await team_board.card(session, scope, task)
