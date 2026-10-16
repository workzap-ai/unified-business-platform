"""Team board API (/pi/team-board), mounted for Owner OS and the pi app. See
``team_board`` for how the cards are made. Reading needs ``pi.work.read``; adding,
moving and assigning cards ``pi.work.manage`` (and ``orders.write`` to start or deliver
a deal's work from its card).

Team members' WhatsApp numbers (``/members``) and the alerts pi sends them when a card
is given to them or due soon: see ``team_alerts``."""

import logging
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.dependencies import Scope, Session
from app.modules.access.service import membership_grants
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.memberships.models import Membership
from app.modules.navigation.service import badge_provider
from app.modules.notifications.service import notify
from app.modules.orders.models import Order
from app.modules.pi.service import require_pi
from app.modules.pi_saas import team_alerts, team_board
from app.modules.pi_saas.deal_routes import _enqueue, advance_work
from app.modules.pi_saas.models import PiTask
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pi/team-board", tags=["pi-team-board"])

Kind = Literal[
    "price", "approve", "payment", "request", "reply", "start", "deliver", "feedback", "task"
]


@router.get("")
async def get_board(
    scope: Scope,
    session: Session,
    who: str = "all",
    kind: Kind | None = None,
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.read")
    if who not in {"all", "me", "unassigned"}:
        try:
            who = str(UUID(who))
        except ValueError:
            raise BusinessRuleViolation("FILTER_INVALID", "Pick someone on your team") from None
    try:
        async with session.begin_nested():
            await team_board.sync_board(session, scope)
    except Exception:  # noqa: BLE001 - the board still shows what's there
        logger.warning("pi_team_board_sync_failed", exc_info=True)
    view = await team_board.board(session, scope, who=who, kind=kind)
    await session.commit()
    return view


async def _check_assignee(session: AsyncSession, scope: WorkspaceScope, user_id: UUID) -> None:
    """Cards go only to active members who can see the board."""
    membership = await session.scalar(
        select(Membership).where(
            Membership.tenant_id == scope.tenant_id,
            Membership.user_id == user_id,
            Membership.status == "active",
        )
    )
    if membership is None:
        raise BusinessRuleViolation("ASSIGNEE_NOT_MEMBER", "Pick someone on your team")
    grants, _ = await membership_grants(session, scope.tenant_id, membership.id)
    if "pi.work.read" not in grants:
        raise BusinessRuleViolation(
            "ASSIGNEE_NO_ACCESS", "This person can't see the team board. Change their role first."
        )


async def _tell_assignee(session: AsyncSession, scope: WorkspaceScope, task: PiTask) -> bool:
    """In-app notification for the new assignee; True when they should also hear on
    WhatsApp (someone else gave them the card)."""
    if task.assignee_user_id is None or task.assignee_user_id == scope.user_id:
        return False
    await notify(
        session,
        scope,
        "pi.task.assigned",
        f"For you: {task.title}"[:160],
        f"{scope.actor_label} gave you this card on the team board.",
        link="/pi/team",
        recipient_user_id=task.assignee_user_id,
        permission="pi.work.read",
        dedupe_key=(
            f"pi-task-assigned:{task.id}:{task.assignee_user_id}:"
            f"{datetime.now(UTC).timestamp():.0f}"
        ),
    )
    return True


class NewTask(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=4000)
    customer_id: UUID | None = None
    assignee_user_id: UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_at: datetime | None = None


@router.post("/tasks", status_code=201)
async def add_task(
    data: NewTask, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    if data.customer_id is not None:
        await WorkspaceRepository(session, Customer, scope).get(data.customer_id)
    if data.assignee_user_id is not None:
        await _check_assignee(session, scope, data.assignee_user_id)
    repo = WorkspaceRepository(session, PiTask, scope)
    task = await repo.add(
        repo.new(
            title=data.title,
            description=data.description,
            customer_id=data.customer_id,
            assignee_user_id=data.assignee_user_id,
            priority=data.priority,
            due_at=data.due_at,
            created_by_user_id=scope.user_id,
            created_by_label=scope.actor_label[:80],
        )
    )
    await session.flush()
    tell = await _tell_assignee(session, scope, task)
    await record(session, "pi.task_created", scope=scope, entity_type="pi_task", entity_id=task.id)
    await session.commit()
    if tell and task.assignee_user_id is not None:
        await team_alerts.enqueue(
            request.app.state.queue, scope, "assigned", task.id, task.assignee_user_id
        )
    return await team_board.card(session, scope, task)


class MoveTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "in_progress", "blocked", "done", "cancelled"] | None = None
    assignee_user_id: UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    due_at: datetime | None = None


async def _move_work(
    session: AsyncSession, scope: WorkspaceScope, task: PiTask, status: str
) -> list[str] | None:
    """A deal's card moved: start or deliver its work, so pi tells the customer exactly
    as the deal page's buttons do. Returns the customer messages to send, or None when
    the card's move doesn't touch the order."""
    kind = team_board.kind_of(task)
    step = None
    if kind == "start" and status in {"in_progress", "done"}:
        step = "start"
    elif kind == "deliver" and status == "done":
        step = "delivered"
    if step is None:
        return None
    scope.require("orders.write")
    order = await WorkspaceRepository(session, Order, scope).get(UUID(team_board.source_of(task)))
    if step == "start" and order.status != "confirmed":
        return None  # Already started elsewhere.
    if step == "delivered" and order.status not in {"processing", "shipped"}:
        return None
    _, ids = await advance_work(session, scope, order.id, step)
    return ids


@router.patch("/tasks/{task_id}")
async def move_task(
    task_id: UUID, data: MoveTask, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    task = await WorkspaceRepository(session, PiTask, scope).get(task_id, for_update=True)
    values = data.model_dump(exclude_unset=True)
    moved: list[str] | None = None
    if values.get("status") and values["status"] != task.status:
        moved = await _move_work(session, scope, task, values["status"])
    assigned = "assignee_user_id" in values and values["assignee_user_id"] != task.assignee_user_id
    if assigned and values["assignee_user_id"] is not None:
        await _check_assignee(session, scope, values["assignee_user_id"])
    for field, value in values.items():
        if field == "status" and value is None:
            continue
        if field == "priority" and value is None:
            continue
        setattr(task, field, value)
    task.updated_at = datetime.now(UTC)
    await session.flush()
    tell = assigned and await _tell_assignee(session, scope, task)
    if moved is not None:
        # The order moved on: the board follows (a started deal gets its "Deliver" card).
        try:
            async with session.begin_nested():
                await team_board.sync_board(session, scope)
        except Exception:  # noqa: BLE001 - the next sync catches up
            logger.warning("pi_team_board_sync_failed", exc_info=True)
    await record(
        session,
        "pi.task_updated",
        scope=scope,
        entity_type="pi_task",
        entity_id=task.id,
        details={k: str(v) if v is not None else None for k, v in values.items()},
    )
    await session.commit()
    await _enqueue(request, moved or [])
    if tell and task.assignee_user_id is not None:
        await team_alerts.enqueue(
            request.app.state.queue, scope, "assigned", task.id, task.assignee_user_id
        )
    return await team_board.card(session, scope, task)


# ---- Team members' WhatsApp numbers ----------------------------------------------------


@router.get("/members")
async def get_members(scope: Scope, session: Session) -> dict[str, Any]:
    """Active members with their WhatsApp number (managers see all numbers, everyone
    sees their own) and whether their 24-hour chat with the business number is open."""
    await require_pi(session, scope, "pi.work.read")
    view = await team_alerts.team_view(session, scope, show_numbers=scope.can("pi.work.manage"))
    await session.commit()
    return view


class TeamAlertsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: bool | None = None
    # user id -> WhatsApp number with country code ("" removes it).
    numbers: dict[str, str] | None = Field(default=None, max_length=200)
    template_name: str | None = Field(default=None, max_length=512)
    template_language: str | None = Field(default=None, max_length=12)


@router.put("/members")
async def put_members(data: TeamAlertsInput, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.work.manage")
    if data.numbers is not None and any(len(v) > 32 for v in data.numbers.values()):
        raise BusinessRuleViolation("PHONE_INVALID", "Enter the WhatsApp number with country code")
    await team_alerts.save_config(
        session,
        scope,
        enabled=data.enabled,
        numbers=data.numbers,
        template_name=data.template_name,
        template_language=data.template_language,
    )
    await session.commit()
    view = await team_alerts.team_view(session, scope, show_numbers=True)
    await session.commit()
    return view


@router.post("/members/{user_id}/test")
async def test_member(
    user_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Send a test message to one member's saved number, by the same rules as alerts.
    Returns how it will go: "sent" (open chat), "template", or "no_window"."""
    await require_pi(session, scope, "pi.work.manage")
    view = await team_alerts.team_view(session, scope, show_numbers=True)
    member = next((m for m in view["members"] if m["id"] == user_id), None)
    if member is None:
        raise BusinessRuleViolation("MEMBER_UNKNOWN", "Pick someone on your team")
    if not member["whatsapp"]:
        raise BusinessRuleViolation("PHONE_MISSING", "Save their WhatsApp number first")
    if not view["business_number"]:
        raise BusinessRuleViolation("WHATSAPP_NOT_CONNECTED", "Connect WhatsApp first")
    if not view["enabled"]:
        raise BusinessRuleViolation("TEAM_ALERTS_OFF", "Turn on WhatsApp alerts first")
    if member["window_open"]:
        delivery = "sent"
    elif view["template_name"]:
        delivery = "template"
    else:
        delivery = "no_window"
    await session.commit()
    if delivery != "no_window":
        await team_alerts.enqueue(request.app.state.queue, scope, "test", None, user_id)
    return {"delivery": delivery, "business_number": view["business_number"]}


@badge_provider("pi.my_tasks")
async def my_tasks(session: AsyncSession, scope: WorkspaceScope) -> int | None:
    """Open cards given to the signed-in person (the "Team board" nav count)."""
    if scope.user_id is None or not scope.can("pi.work.read"):
        return None
    count = await session.scalar(
        WorkspaceRepository(session, PiTask, scope)
        .select()
        .with_only_columns(func.count())
        .where(
            PiTask.assignee_user_id == scope.user_id,
            PiTask.status.in_(team_board.LIVE),
        )
    )
    return int(count or 0) or None
