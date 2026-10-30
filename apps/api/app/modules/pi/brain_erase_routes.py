"""Staff erase a customer's brain data when they ask (pi Brain spec R-PRIV-06).

Used after pi passes on a "delete everything you know about me" request. See brain_erase.py for
what is removed and what is kept.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.brain_erase import erase_customer
from app.modules.pi.service import require_pi
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/brain-erasure", tags=["pi-brain-erasure"])


class EraseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool = False  # nothing is erased unless this is exactly true


@router.post("/{customer_id}")
async def erase(
    customer_id: UUID, data: EraseInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """Erase what pi keeps about this customer. Cannot be undone."""
    await require_pi(session, scope, "pi.settings.manage")
    if data.confirm is not True:
        raise BusinessRuleViolation(
            "CONFIRMATION_REQUIRED", "Send confirm: true to erase this customer's data", 422
        )
    result = await erase_customer(session, scope, customer_id)
    if not result["complete"]:
        # only an undefined table is ever skipped; any other error fails the request instead
        result["warning"] = (
            "INCOMPLETE: these steps did not run because their table is missing in this "
            "database: " + ", ".join(result["skipped"])
        )
    await record(
        session,
        "pi.brain_data_erased",
        scope=scope,
        entity_type="customer",
        entity_id=customer_id,
        details={
            "removed": result["removed"],
            "kept": result["kept"],
            # the trail records what was left on purpose (share links: erase decision R1)
            # and which steps could not run, so a 200 never hides a step that did not erase
            "kept_reasons": result["kept_reasons"],
            "skipped": result["skipped"],
            "complete": result["complete"],
        },
    )
    await session.commit()
    return result
