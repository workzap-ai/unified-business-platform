from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.notifications.service import NotificationService, NotificationView
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/notifications", tags=["notifications"])
Read = Annotated[WorkspaceScope, Depends(require("notifications.read"))]
Paging = Annotated[Pagination, Depends()]


class MarkRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[UUID] | None = Field(default=None, max_length=500)


class UnreadCount(BaseModel):
    unread: int


@router.get("", response_model=Page[NotificationView])
async def notifications(
    scope: Read, session: Session, pagination: Paging, unread_only: bool = False
) -> Page[NotificationView]:
    return await NotificationService(session, scope).search(pagination, unread_only)


@router.get("/unread-count", response_model=UnreadCount)
async def unread(scope: Read, session: Session) -> UnreadCount:
    return UnreadCount(unread=await NotificationService(session, scope).unread_count())


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(data: MarkRead, scope: Read, session: Session) -> Response:
    await NotificationService(session, scope).mark_read(data.ids)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
