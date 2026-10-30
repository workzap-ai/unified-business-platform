"""Staff view of open items and handoffs by age, colour-coded against the service level
(platform spec v1.4, 17.7). Read only, scoped to the workspace."""

from typing import Any

from fastapi import APIRouter

from app.modules.access.dependencies import Scope, Session
from app.modules.pi import open_items
from app.modules.pi.service import require_pi

router = APIRouter(prefix="/pi/open-items", tags=["pi-open-items"])


@router.get("")
async def open_items_by_age(scope: Scope, session: Session) -> dict[str, Any]:
    """Every open item and handoff, oldest first. `colour` is green, amber or red against
    `sla_minutes`."""
    await require_pi(session, scope, "pi.handoffs.manage")
    items = await open_items.age_view(session, scope)
    counts: dict[str, int] = {}
    for item in items:
        key = str(item["colour"])
        counts[key] = counts.get(key, 0) + 1
    return {"items": items, "count": len(items), "by_colour": counts}
