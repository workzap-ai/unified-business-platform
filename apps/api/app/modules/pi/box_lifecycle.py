"""The Solution Box lifecycle on the database (pi platform spec Book 5, 5.3 to 5.7).

`box.py` holds the pure rules (states, legal moves, who may move what). This module applies them:
it finds or opens the customer's box, moves it only along a legal move, keeps every move as a row
(`pi_box_transitions`, the time is created_at) and adds the guards the table cannot show:

- the offer is made once per box version (a second move to "offered" is refused);
- "drafting" needs the owner's explicit yes (the caller says so; "ok", "hmm" are not one);
- pi never prices and never sends: "sent" is staff only and is refused without an approved
  document and a named reviewer; the reviewer is recorded when staff approve;
- the owner answers (accepted, declined, changes asked); payment is confirmed by staff elsewhere.

Everything here runs only when `response_rules.pi_mode = "brain"` and `brain.box_offer` is true;
`enabled_for` is the one check and every hook below calls it first, so other workspaces behave
exactly as before. Nothing here sends a message.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import box
from app.modules.pi.box_models import PiBoxTransition, PiOfferLog, PiSolutionBox
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger("app.pi.box")

QUIET_MESSAGES = box.DECLINE_QUIET_MESSAGES  # no box follow-up or new offer for 8 messages
BOX_FOLLOWUP_KINDS = ("documents", "map")  # follow-ups whose text mentions the box
DECLINE_KEY = "box_declined_at_pi"  # brief key: pi's sent-message count when the owner declined


@dataclass(frozen=True)
class Move:
    box: PiSolutionBox
    from_state: str
    to_state: str


def enabled_for(response_rules: dict[str, Any] | None) -> bool:
    return box.box_offer_enabled(response_rules)


def quiet_after_decline(brief: dict[str, Any], pi_sent: int) -> bool:
    """True while fewer than 8 pi messages have gone since the owner declined (spec 5.4, 6.3)."""
    marker = brief.get(DECLINE_KEY)
    if not isinstance(marker, int) or isinstance(marker, bool):
        return False
    return pi_sent - marker < QUIET_MESSAGES


async def latest_box(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> PiSolutionBox | None:
    found: PiSolutionBox | None = await session.scalar(
        WorkspaceRepository(session, PiSolutionBox, scope)
        .select()
        .where(PiSolutionBox.customer_id == customer_id)
        .order_by(PiSolutionBox.version.desc())
        .limit(1)
    )
    return found


async def ensure_box(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> PiSolutionBox:
    """The box exists from the first problem (5.3): the latest one, or a new Collecting box."""
    found = await latest_box(session, scope, customer_id)
    if found is not None:
        return found
    repo = WorkspaceRepository(session, PiSolutionBox, scope)
    return await repo.add(repo.new(customer_id=customer_id, state="collecting", owner_ranking=[]))


async def transitions_of(
    session: AsyncSession, scope: WorkspaceScope, box_id: UUID
) -> list[PiBoxTransition]:
    return list(
        await session.scalars(
            WorkspaceRepository(session, PiBoxTransition, scope)
            .select()
            .where(PiBoxTransition.box_id == box_id)
            .order_by(PiBoxTransition.created_at, PiBoxTransition.id)
        )
    )


async def _offered_before(session: AsyncSession, scope: WorkspaceScope, row: PiSolutionBox) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(PiBoxTransition)
        .where(
            PiBoxTransition.tenant_id == scope.tenant_id,
            PiBoxTransition.environment_id == scope.environment_id,
            PiBoxTransition.box_id == row.id,
            PiBoxTransition.to_state == "offered",
        )
    )
    return bool(count) or row.offered_at is not None


def _refuse(message: str) -> BusinessRuleViolation:
    return BusinessRuleViolation("BOX_MOVE_REFUSED", message, 409)


async def move(
    session: AsyncSession,
    scope: WorkspaceScope,
    row: PiSolutionBox,
    target: str,
    actor: str,
    *,
    reason: str = "",
    actor_ref: str | None = None,
    explicit_yes: bool = False,
    approved_document: bool = False,
    now: datetime | None = None,
) -> Move:
    """Move the box one step. Raises BusinessRuleViolation (409, BOX_MOVE_REFUSED) for an illegal
    move or a guard that does not hold; otherwise writes the transition row and returns it."""
    current = row.state
    legal, why = box.can_move(current, target, actor)
    if not legal:
        raise _refuse(why)
    if target == "offered" and await _offered_before(session, scope, row):
        raise _refuse("the offer is made once for this box")
    if target == "drafting" and not explicit_yes:
        raise _refuse("drafting needs the owner's explicit yes")
    if target == "sent":
        reviewer = (actor_ref or row.reviewer or "").strip()
        if not approved_document or not reviewer:
            raise _refuse("a reviewer must approve the document and quote before it is sent")
        row.reviewer = reviewer[:120]
    stamp = now or datetime.now(UTC)
    if target == "offered":
        row.offered_at = stamp
    row.state = target
    repo = WorkspaceRepository(session, PiBoxTransition, scope)
    await repo.add(
        repo.new(
            box_id=row.id,
            from_state=current,
            to_state=target,
            actor=actor,
            actor_ref=actor_ref[:120] if actor_ref else None,
            reason=reason[:500],
            created_at=stamp,
        )
    )
    return Move(row, current, target)


async def new_version(
    session: AsyncSession, scope: WorkspaceScope, parent: PiSolutionBox, *, reason: str = ""
) -> PiSolutionBox:
    """Box v2, v3 (5.6): a problem arrived after the box was sent. The earlier version stays; the
    new one starts Collecting and may be offered once. A sent parent is marked Revised."""
    if parent.state not in ("sent", "accepted"):
        raise _refuse("only a sent or accepted box gets a new version")
    newest = await session.scalar(
        select(func.max(PiSolutionBox.version)).where(
            PiSolutionBox.tenant_id == scope.tenant_id,
            PiSolutionBox.environment_id == scope.environment_id,
            PiSolutionBox.customer_id == parent.customer_id,
        )
    )
    repo = WorkspaceRepository(session, PiSolutionBox, scope)
    fresh = await repo.add(
        repo.new(
            customer_id=parent.customer_id,
            state="collecting",
            version=int(newest or parent.version) + 1,
            parent_box_id=parent.id,
            map_version_id=parent.map_version_id,
            owner_ranking=list(parent.owner_ranking or []),
        )
    )
    await move(session, scope, parent, "revised", "pi", reason=reason or "new problem after send")
    return fresh


async def log_offer(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, facts: box.OfferFacts
) -> tuple[bool, str, str]:
    """Run canOffer and keep the rule and the reason (5.7), allowed or blocked."""
    allowed, rule, reason = box.can_offer(facts)
    repo = WorkspaceRepository(session, PiOfferLog, scope)
    await repo.add(
        repo.new(
            conversation_id=conversation_id,
            rule=rule,
            allowed=allowed,
            blocked_reason=None if allowed else reason,
        )
    )
    return allowed, rule, reason


async def offer(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    conversation_id: UUID,
    facts: box.OfferFacts,
) -> tuple[bool, str]:
    """pi may make the offer: canOffer holds (logged) and none was made yet for this box. Moves the
    box to Ready then Offered. Returns (made, why); a blocked offer changes nothing."""
    allowed, rule, reason = await log_offer(session, scope, conversation_id, facts)
    if not allowed:
        return False, f"{rule}: {reason}"
    row = await ensure_box(session, scope, customer_id)
    if await _offered_before(session, scope, row):
        return False, "already offered"
    if row.state == "collecting":
        await move(session, scope, row, "ready", "pi", reason=f"{rule}: {reason}")
    if row.state != "ready":
        return False, f"box is {row.state}"
    await move(session, scope, row, "offered", "pi", reason=f"{rule}: {reason}")
    return True, rule


async def pi_sent_count(session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID) -> int:
    from app.modules.pi.models import PiMessage

    total = await session.scalar(
        select(func.count())
        .select_from(PiMessage)
        .where(
            PiMessage.tenant_id == scope.tenant_id,
            PiMessage.environment_id == scope.environment_id,
            PiMessage.conversation_id == conversation_id,
            PiMessage.direction == "outbound",
            PiMessage.sender_type == "ai",
        )
    )
    return int(total or 0)


async def on_decision(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: Any,
    decision: Any,
    brief: dict[str, Any],
    response_rules: dict[str, Any] | None,
) -> None:
    """Called by `apply_decision` after the brief changed. Mirrors what the decision gates already
    decided onto the box; it never decides anything itself. A no-op unless the box is on."""
    if not enabled_for(response_rules) or conversation.customer_id is None:
        return
    change = decision.brief or {}
    effects = decision.effects or []
    try:
        row = await ensure_box(session, scope, conversation.customer_id)
        if change.get("offer_asked") and row.state in ("collecting", "ready"):
            if row.state == "collecting":
                await move(session, scope, row, "ready", "pi", reason="offer made")
            if not await _offered_before(session, scope, row):
                await move(session, scope, row, "offered", "pi", reason="offer made")
        if "request_solution" in effects and row.state == "offered":
            await move(
                session, scope, row, "drafting", "pi", reason="owner said yes", explicit_yes=True
            )
        if change.get("offer_declined") and row.state == "offered":
            await move(session, scope, row, "collecting", "owner", reason="owner declined")
            brief[DECLINE_KEY] = await pi_sent_count(session, scope, conversation.id)
            brief["box_declined_at"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        if "request_revision" in effects and row.state == "sent":
            await move(session, scope, row, "changes_asked", "owner", reason="changes asked")
        if "record_approval" in effects and row.state == "sent":
            await move(session, scope, row, "accepted", "owner", reason="owner approved the quote")
    except BusinessRuleViolation as refused:
        logger.info("pi_box_move_refused: %s", refused)


async def _on(session: AsyncSession, scope: WorkspaceScope) -> bool:
    from app.modules.pi.configuration import settings_row

    return enabled_for((await settings_row(session, scope)).response_rules)


async def on_draft_ready(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID | None
) -> None:
    """pi finished drafting sections 1 to 7: the box goes to review (a Workzap person checks)."""
    if customer_id is None or not await _on(session, scope):
        return
    row = await latest_box(session, scope, customer_id)
    if row is not None and row.state == "drafting":
        await move(session, scope, row, "in_review", "pi", reason="draft ready for the reviewer")


async def on_approved(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID | None, reviewer: str
) -> None:
    """Record who approved (the reviewer); the move to Sent happens only when staff send."""
    if customer_id is None or not reviewer or not await _on(session, scope):
        return
    row = await latest_box(session, scope, customer_id)
    if row is not None and row.state == "in_review":
        row.reviewer = reviewer[:120]


async def on_sent(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID | None,
    staff_ref: str | None,
    *,
    approved_document: bool = False,
) -> None:
    """Staff sent the approved pair: in_review (or a revised or changes-asked box) to Sent.
    The caller says whether both documents of the latest pair were approved; without it nothing
    moves."""
    if customer_id is None or not await _on(session, scope):
        return
    row = await latest_box(session, scope, customer_id)
    if row is None:
        return
    if row.state in ("changes_asked", "revised"):
        await move(session, scope, row, "in_review", "staff", reason="revised version")
    if row.state == "in_review":
        await move(
            session,
            scope,
            row,
            "sent",
            "staff",
            actor_ref=staff_ref,
            approved_document=approved_document,
            reason="approved PDF delivered",
        )
