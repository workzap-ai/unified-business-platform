from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.navigation.service import badge_provider
from app.modules.notifications.models import Notification, NotificationRead
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository


class NotificationView(BaseModel):
    id: UUID
    kind: str
    severity: str
    title: str
    body: str
    link: str | None
    read: bool
    created_at: datetime


async def notify(
    session: AsyncSession,
    scope: WorkspaceScope,
    kind: str,
    title: str,
    body: str = "",
    *,
    link: str | None = None,
    permission: str | None = None,
    recipient_user_id: UUID | None = None,
    severity: str = "info",
    dedupe_key: str | None = None,
) -> None:
    """Record a permission-scoped notification; duplicates by dedupe_key are ignored."""
    if permission is None and recipient_user_id is None:
        raise ValueError("A notification needs an audience")
    notification_id = await session.scalar(
        insert(Notification)
        .values(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind=kind,
            title=title[:160],
            body=body[:500],
            link=link,
            required_permission=permission,
            recipient_user_id=recipient_user_id,
            severity=severity,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing()
        .returning(Notification.id)
    )
    if notification_id is not None:
        from app.integrations.outbox import EntityRef, emit

        await emit(
            session,
            scope,
            "notification.created",
            {"title": title[:160], "body": body[:500], "severity": severity},
            EntityRef("notification", notification_id),
        )


class NotificationService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.notifications = WorkspaceRepository(session, Notification, scope)

    def _audience(self) -> ColumnElement[bool]:
        return and_(
            self.notifications.predicate(),
            or_(
                Notification.recipient_user_id == self.scope.user_id,
                and_(
                    Notification.recipient_user_id.is_(None),
                    Notification.required_permission.in_(sorted(self.scope.permissions)),
                ),
            ),
        )

    def _read(self) -> ColumnElement[bool]:
        return exists(
            select(NotificationRead.id).where(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == self.scope.user_id,
            )
        )

    async def search(self, page: Pagination, unread_only: bool = False) -> Page[NotificationView]:
        statement = select(Notification, self._read().label("read")).where(self._audience())
        if unread_only:
            statement = statement.where(~self._read())
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await self.session.execute(
            statement.order_by(Notification.created_at.desc(), Notification.id)
            .offset(page.offset)
            .limit(page.page_size)
        )
        items = [
            NotificationView(
                id=n.id,
                kind=n.kind,
                severity=n.severity,
                title=n.title,
                body=n.body,
                link=n.link,
                read=bool(read),
                created_at=n.created_at,
            )
            for n, read in rows
        ]
        return Page(items=items, total=int(total or 0), page=page.page, page_size=page.page_size)

    async def unread_count(self) -> int:
        if self.scope.user_id is None:
            return 0
        count = await self.session.scalar(
            select(func.count()).select_from(Notification).where(self._audience(), ~self._read())
        )
        return int(count or 0)

    async def mark_read(self, ids: list[UUID] | None) -> None:
        if self.scope.user_id is None:
            return
        statement = select(
            Notification.tenant_id,
            Notification.id,
            literal(self.scope.user_id),
            func.now(),
        ).where(self._audience(), ~self._read())
        if ids is not None:
            statement = statement.where(Notification.id.in_(ids))
        # Let PostgreSQL insert every visible unread row without a client-side cap
        # or a large parameter list. Server defaults generate a distinct id per row.
        await self.session.execute(
            insert(NotificationRead)
            .from_select(
                ["tenant_id", "notification_id", "user_id", "read_at"],
                statement.order_by(Notification.id),
                include_defaults=False,
            )
            .on_conflict_do_nothing()
        )


@badge_provider("notifications.unread")
async def unread_badge(session: AsyncSession, scope: WorkspaceScope) -> int | None:
    count = await NotificationService(session, scope).unread_count()
    return count or None
