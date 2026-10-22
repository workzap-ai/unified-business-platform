"""How pi's brain is doing, for the Workzap team (pi Brain spec 8.11.1, 8.13, Job 10).

Read-only: the learning metrics scored from real replies (text-free), whether learning is frozen,
and every tunable setting with its range. A dashboard or a morning digest reads this; nothing here
changes pi's behaviour.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter

from app.modules.access.dependencies import Scope, Session
from app.modules.pi import brain_config, learning
from app.modules.pi.configuration import settings_row
from app.modules.pi.experience_scorer import health
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
        "settings": brain_config.describe(policy.response_rules),
    }
