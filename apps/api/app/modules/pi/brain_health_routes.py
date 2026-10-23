"""How pi's brain is doing, for the Workzap team (pi Brain spec 8.11.1, 8.13, Job 10).

Read-only: the learning metrics scored from real replies (text-free), whether learning is frozen,
and every tunable setting with its range. A dashboard or a morning digest reads this; nothing here
changes pi's behaviour.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app.modules.access.dependencies import Scope, Session
from app.modules.pi import brain_config, learning
from app.modules.pi.configuration import settings_row
from app.modules.pi.experience_scorer import health
from app.modules.pi.learning_models import (
    PiLearnedPack,
    PiLearningChange,
    PiLearningLesson,
    PiQuestionArm,
)
from app.modules.pi.service import require_pi

router = APIRouter(prefix="/pi/brain-health", tags=["pi-brain-health"])


@router.get("")
async def brain_health(scope: Scope, session: Session, days: int = 1) -> dict[str, Any]:
    """Learning metrics for the last `days` days (1 to 90), the freeze switch, and the settings."""
    await require_pi(session, scope, "pi.settings.manage")
    days = max(1, min(90, days))
    policy = await settings_row(session, scope)
    since = datetime.now(UTC) - timedelta(days=days)
    return {
        "days": days,
        "pi_mode": policy.response_rules.get("pi_mode", "standard"),
        "learning_frozen": learning.frozen(policy.response_rules),
        "metrics": await health(session, since, scope),
        "learning": await learning_numbers(session, scope, since),
        "settings": brain_config.describe(policy.response_rules),
    }


async def learning_numbers(session: Any, scope: Any, since: datetime) -> dict[str, Any]:
    """The rest of the spec 8.13 metrics: what learning did, and where things wait."""
    where = (
        PiLearningChange.tenant_id == scope.tenant_id,
        PiLearningChange.environment_id == scope.environment_id,
        PiLearningChange.created_at >= since,
    )
    changes = dict(
        (kind, n)
        for kind, n in (
            await session.execute(
                select(PiLearningChange.kind, func.count())
                .where(*where)
                .group_by(PiLearningChange.kind)
            )
        ).all()
    )
    promoted = int(changes.get("example_canary_promoted", 0))
    rolled_back = int(changes.get("example_canary_rolled_back", 0))
    packs = dict(
        (status, n)
        for status, n in (
            await session.execute(
                select(PiLearnedPack.status, func.count())
                .where(
                    PiLearnedPack.tenant_id == scope.tenant_id,
                    PiLearnedPack.environment_id == scope.environment_id,
                )
                .group_by(PiLearnedPack.status)
            )
        ).all()
    )
    arms = list(
        await session.scalars(
            select(PiQuestionArm).where(
                PiQuestionArm.tenant_id == scope.tenant_id,
                PiQuestionArm.environment_id == scope.environment_id,
                PiQuestionArm.status != "retired",
            )
        )
    )
    slots = {(a.slot, a.language) for a in arms}
    proven = {
        (a.slot, a.language) for a in arms if a.uses >= 50 and a.alpha / (a.alpha + a.beta) >= 0.5
    }
    lessons = dict(
        (key, n)
        for key, n in (
            await session.execute(
                select(PiLearningLesson.status, func.count())
                .where(
                    PiLearningLesson.tenant_id == scope.tenant_id,
                    PiLearningLesson.environment_id == scope.environment_id,
                )
                .group_by(PiLearningLesson.status)
            )
        ).all()
    )
    return {
        "changes_promoted": promoted,
        "changes_rolled_back": rolled_back,
        "packs_by_status": packs,
        "lessons_by_status": lessons,
        "questions_with_a_proven_best": round(len(proven) / len(slots), 2) if slots else 0.0,
        "waiting_for_review": int(lessons.get("review", 0)) + int(packs.get("draft", 0)),
    }
