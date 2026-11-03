"""What the weekly human queue adds on top of high-risk lessons and care sections (spec 8.6).

"Any automatic change that was rolled back twice (needs a human look)": the same change (an
example, a lesson or a wording with the same text, ignoring case and punctuation) that the canary
rolled back two or more times is listed here, and `blocked` tells the jobs not to propose or
activate it again until a person has looked. A person looks by deciding the change-log row
(`decide`), which closes it.
"""

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.learning_models import PiLearningChange
from app.shared.scope import WorkspaceScope

TIMES = 2
KIND_PREFIXES = ("example_canary_", "lesson_canary_")
LOOKED_AT = "looked_at"


def _family(kind: str) -> str:
    return kind.split("_canary_")[0]


def _signature(change: PiLearningChange) -> str:
    return str((change.evidence or {}).get("signature") or change.target_id or "")


async def rolled_back_twice(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    """Changes rolled back at least twice that nobody has looked at yet."""
    rows = list(
        await session.scalars(
            select(PiLearningChange)
            .where(
                PiLearningChange.tenant_id == scope.tenant_id,
                PiLearningChange.environment_id == scope.environment_id,
                PiLearningChange.status.in_(("rolled_back", LOOKED_AT)),
            )
            .order_by(PiLearningChange.created_at)
        )
    )
    groups: dict[tuple[str, str], list[PiLearningChange]] = defaultdict(list)
    for row in rows:
        if row.kind.startswith(KIND_PREFIXES) and row.kind.endswith("rolled_back"):
            if sig := _signature(row):
                groups[(_family(row.kind), sig)].append(row)
    out: list[dict[str, Any]] = []
    for (family, sig), items in groups.items():
        open_items = [r for r in items if r.status == "rolled_back"]
        if len(items) >= TIMES and open_items:
            out.append(
                {
                    "kind": family,
                    "signature": sig,
                    "times": len(items),
                    "change_ids": [r.id for r in items],
                    "reasons": [r.reason for r in items][-3:],
                    "reason": f"rolled back {len(items)} times: needs a human look (8.6)",
                }
            )
    return out


async def blocked(
    session: AsyncSession, scope: WorkspaceScope, family: str, signature: str
) -> bool:
    """True while a change of this family and text sits in the queue, rolled back twice and not yet
    looked at: the jobs must not bring it back."""
    return any(
        item["kind"] == family and item["signature"] == signature
        for item in await rolled_back_twice(session, scope)
    )


async def decide(
    session: AsyncSession, scope: WorkspaceScope, change_ids: list[UUID], by: UUID | None
) -> int:
    """A person looked at it: the rows stop counting as open (they stay in the log)."""
    done = 0
    for change_id in change_ids:
        row = await session.get(PiLearningChange, change_id)
        if (
            row is not None
            and row.tenant_id == scope.tenant_id
            and row.environment_id == scope.environment_id
            and row.status == "rolled_back"
        ):
            row.status = LOOKED_AT
            row.decided_by = by
            done += 1
    await session.flush()
    return done
