"""Staff controls for the solutions pi learns (Addendum 2 to the pi Brain v3, Parts 3.5 and 3.7).

The Solutions panel lists every industry with its versions (`solutions/{industry}@1.N`), each
version's evidence and a rollback that undoes only that industry's latest learned change. The
review queue holds what a person decides: ideas that touch money or a regulated topic, and
catalogue gaps the problems keep showing. Nothing here edits a seed, the value line or a build
line, and the decision on a build fit never reaches the chat reward (Part 3.6).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.modules.access.dependencies import Scope, Session
from app.modules.pi import solution_ideas, solution_rules, solution_versions, solutions
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.service import require_pi
from app.modules.pi.solution_models import PiCatalogueProposal, PiIdeaArm, PiSolutionVersion
from app.shared.errors import ResourceNotFound

router = APIRouter(prefix="/pi/solutions", tags=["pi-solutions"])
PERMISSION = "pi.settings.manage"


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    reason: str = ""


def _version(v: PiSolutionVersion) -> dict[str, Any]:
    return {
        "version": v.version,
        "status": v.status,
        "changes": sorted(v.diff or {}),
        "evidence": v.evidence,
        "created_at": v.created_at,
        "rolled_back_at": v.rolled_back_at,
    }


def _arm(a: PiIdeaArm) -> dict[str, Any]:
    stats = a.stats or {}
    return {
        "id": a.id,
        "industry": a.industry_key,
        "problem": a.problem_id,
        "language": a.language,
        "text": a.text,
        "kind": a.kind,
        "status": a.status,
        "uses": a.uses,
        "source": a.source,
        "traffic_cap": a.traffic_cap,
        "feedback": int(stats.get("n", 0)),
        "retired_reason": a.retired_reason,
    }


@router.get("")
async def overview(scope: Scope, session: Session) -> dict[str, Any]:
    """Industries that have learned something, newest change first."""
    await require_pi(session, scope, PERMISSION)
    rows = list(
        await session.scalars(
            select(PiSolutionVersion)
            .where(
                PiSolutionVersion.tenant_id == scope.tenant_id,
                PiSolutionVersion.environment_id == scope.environment_id,
                PiSolutionVersion.version != solution_versions.BASE,
            )
            .order_by(PiSolutionVersion.created_at.desc())
        )
    )
    by_industry: dict[str, list[PiSolutionVersion]] = {}
    for row in rows:
        by_industry.setdefault(row.industry_key, []).append(row)
    return {
        "industries": [
            {
                "industry": key,
                "seeded": solutions.load(key) is not None,
                "latest": _version(items[0]),
                "versions": len(items),
            }
            for key, items in by_industry.items()
        ]
    }


@router.get("/review")
async def review_queue(scope: Scope, session: Session) -> dict[str, Any]:
    """What a person decides: ideas waiting for review, and open catalogue proposals."""
    await require_pi(session, scope, PERMISSION)
    arms = await session.scalars(
        select(PiIdeaArm)
        .where(*solution_ideas._where_arm(scope), PiIdeaArm.status == "review")
        .order_by(PiIdeaArm.created_at)
        .limit(100)
    )
    proposals = await session.scalars(
        select(PiCatalogueProposal)
        .where(
            PiCatalogueProposal.tenant_id == scope.tenant_id,
            PiCatalogueProposal.environment_id == scope.environment_id,
            PiCatalogueProposal.status == "open",
        )
        .order_by(PiCatalogueProposal.count.desc())
        .limit(50)
    )
    return {
        "ideas": [_arm(a) for a in arms],
        "proposals": [
            {
                "id": p.id,
                "need": p.need_text,
                "industries": p.industries,
                "count": p.count,
            }
            for p in proposals
        ],
    }


@router.get("/arms")
async def arms(
    scope: Scope, session: Session, industry: str | None = None, status: str | None = None
) -> dict[str, Any]:
    """The ideas with their numbers, of one industry when given (at most 500)."""
    await require_pi(session, scope, PERMISSION)
    query = select(PiIdeaArm).where(*solution_ideas._where_arm(scope))
    if industry:
        query = query.where(PiIdeaArm.industry_key == industry)
    if status:
        query = query.where(PiIdeaArm.status == status)
    rows = await session.scalars(query.order_by(PiIdeaArm.problem_id, PiIdeaArm.arm_key).limit(500))
    return {"items": [_arm(a) for a in rows]}


@router.get("/{industry}")
async def industry_detail(industry: str, scope: Scope, session: Session) -> dict[str, Any]:
    """One industry: the sample reply in force and every version with its evidence."""
    await require_pi(session, scope, PERMISSION)
    if solutions.load(industry) is None:
        raise ResourceNotFound
    return {
        "industry": industry,
        "sample_reply": await solution_versions.current_sample(session, scope, industry),
        "versions": [
            _version(v)
            for v in reversed(await solution_versions.versions(session, scope, industry))
        ],
        "ideas": int(
            await session.scalar(
                select(func.count())
                .select_from(PiIdeaArm)
                .where(*solution_ideas._where_arm(scope), PiIdeaArm.industry_key == industry)
            )
            or 0
        ),
    }


@router.post("/{industry}/rollback")
async def rollback(industry: str, scope: Scope, session: Session) -> dict[str, Any]:
    """Undo this industry's latest learned version. Other industries are untouched."""
    await require_pi(session, scope, PERMISSION)
    if solutions.load(industry) is None:
        raise ResourceNotFound
    undone = await solution_versions.rollback(session, scope, industry)
    await session.commit()
    return {"industry": industry, "rolled_back": undone.version}


@router.post("/ideas/{arm_id}/decide")
async def decide_idea(
    arm_id: UUID, data: Decision, scope: Scope, session: Session
) -> dict[str, Any]:
    """A reviewer approves an idea that touches money or a regulated topic (it then starts in
    testing like any new idea) or rejects it."""
    await require_pi(session, scope, PERMISSION)
    arm = await session.get(PiIdeaArm, arm_id)
    if (
        arm is None
        or arm.tenant_id != scope.tenant_id
        or arm.environment_id != scope.environment_id
        or arm.status != "review"
    ):
        raise ResourceNotFound
    arm.status = "testing" if data.approve else "retired"
    arm.retired_reason = (
        "" if data.approve else (solution_rules.redacted(data.reason) or "rejected in review")[:200]
    )
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="idea_reviewed",
            target_id=arm.id,
            before={"status": "review"},
            after={"status": arm.status},
            reason=solution_rules.redacted(data.reason)[:200],
            status="live",
            decided_by=scope.user_id,
        )
    )
    await session.commit()
    return _arm(arm)


@router.post("/proposals/{proposal_id}/decide")
async def decide_proposal(
    proposal_id: UUID, data: Decision, scope: Scope, session: Session
) -> dict[str, Any]:
    """Approve or reject a catalogue proposal. Approving records the need for the people who
    maintain the catalogue; it adds nothing to the catalogue pi may name (Part 3.5)."""
    await require_pi(session, scope, PERMISSION)
    row = await session.get(PiCatalogueProposal, proposal_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
        or row.status != "open"
    ):
        raise ResourceNotFound
    row.status = "approved" if data.approve else "rejected"
    row.reviewer, row.decided_at = scope.user_id, datetime.now(UTC)
    await session.commit()
    return {"id": row.id, "status": row.status}
