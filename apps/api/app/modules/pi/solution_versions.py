"""Versions of an industry's solutions, and the way back (Addendum 2, Part 3.7).

Part 4 is loaded as solutions/{industry}@1.0. Every learned change to an industry (a new idea, a
retired one, a better sample reply, a new problem entry) is one more version (@1.1, @1.2) with the
evidence for it. Rolling an industry back undoes its latest live version, and only that industry's:
the others are untouched. The seed (@1.0) is never rolled back.
"""

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import solutions
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.solution_models import PiIdeaArm, PiSolutionVersion
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

BASE = "1.0"


def _where(scope: WorkspaceScope, industry_key: str) -> tuple[Any, ...]:
    return (
        PiSolutionVersion.tenant_id == scope.tenant_id,
        PiSolutionVersion.environment_id == scope.environment_id,
        PiSolutionVersion.industry_key == industry_key,
    )


def _minor(version: str) -> int:
    return int(version.split(".")[1])


async def versions(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str
) -> list[PiSolutionVersion]:
    """Oldest first."""
    rows = list(
        await session.scalars(select(PiSolutionVersion).where(*_where(scope, industry_key)))
    )
    return sorted(rows, key=lambda v: _minor(v.version))


async def ensure_base(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str
) -> PiSolutionVersion:
    found = next(
        (v for v in await versions(session, scope, industry_key) if v.version == BASE), None
    )
    if found is not None:
        return found
    seed = solutions.load(industry_key) or {}
    row = PiSolutionVersion(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        industry_key=industry_key,
        version=BASE,
        diff={},
        evidence={"seed": True, "problems": len(seed.get("problems") or [])},
        status="live",
    )
    session.add(row)
    await session.flush()
    return row


async def bump(
    session: AsyncSession,
    scope: WorkspaceScope,
    industry_key: str,
    diff: dict[str, Any],
    evidence: dict[str, Any],
    status: str = "live",
) -> PiSolutionVersion:
    """Record one learned change as the next version of the industry."""
    await ensure_base(session, scope, industry_key)
    top = max((_minor(v.version) for v in await versions(session, scope, industry_key)), default=0)
    row = PiSolutionVersion(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        industry_key=industry_key,
        version=f"1.{top + 1}",
        diff=diff,
        evidence=evidence,
        status=status,
    )
    session.add(row)
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="solution_version",
            risk="low",
            before={"industry": industry_key},
            after={"version": row.version, "changes": sorted(diff)},
            evidence=evidence,
            status="live" if status == "live" else status,
            reason=f"solutions/{industry_key}@{row.version}",
        )
    )
    await session.flush()
    return row


async def current_sample(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str
) -> dict[str, Any] | None:
    """The sample reply in force: the latest live learned one, else the seed's."""
    for row in reversed(await versions(session, scope, industry_key)):
        if row.status == "live" and (row.diff or {}).get("sample_reply"):
            return dict(row.diff["sample_reply"]["to"])
    seed = solutions.load(industry_key)
    return dict(seed["sample_reply"]) if seed else None


SAMPLE_SOURCES = ("solution_sample", "solution_learned")  # example-bank sources of sample replies
_OFFER = re.compile(r"solution document|quote|say no|mana bhi|banwa", re.IGNORECASE)
_MARKER = re.compile(r"(?:(?<=\s)|^)[1-9][.)]?\s+(?=[A-Za-z\"'])")


def sample_body(pi_text: str) -> str:
    """What a sample reply teaches the example bank: the reply without the offer sentences (the
    application appends the offer, the model never writes it) and with numbered ideas as bullets
    (a list marker is not a figure the redaction check should mistrust)."""
    sentences = re.split(r"(?<=[.?!])\s+", (pi_text or "").strip())
    while sentences and _OFFER.search(sentences[-1]):
        sentences.pop()
    return _MARKER.sub("• ", " ".join(sentences))[:500]


async def sample_examples(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str, pi_text: str | None = None
) -> list[Any]:
    """The example-bank rows a sample reply of this industry fed (all of them, or the one whose
    reply is `pi_text`)."""
    from app.modules.pi.learning_models import PiLearningExample

    rows = list(
        await session.scalars(
            select(PiLearningExample).where(
                PiLearningExample.tenant_id == scope.tenant_id,
                PiLearningExample.environment_id == scope.environment_id,
                PiLearningExample.source.in_(SAMPLE_SOURCES),
            )
        )
    )
    wanted = sample_body(pi_text) if pi_text else None
    return [
        r
        for r in rows
        if (r.situation or {}).get("industry") == industry_key
        and (wanted is None or r.reply_text == wanted)
    ]


async def _undo_sample(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str, sample: dict[str, Any]
) -> None:
    """Rolling back a sample_reply version: the example it fed leaves the bank and the one it
    replaced (a learned one; the seed's own never left) comes back as a candidate."""
    for row in await sample_examples(
        session, scope, industry_key, (sample.get("to") or {}).get("pi")
    ):
        row.status = "retired"
    before = (sample.get("from") or {}).get("pi")
    if before:
        for row in await sample_examples(session, scope, industry_key, before):
            if row.status == "retired":
                row.status = "candidate"


async def rollback(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str
) -> PiSolutionVersion:
    """Undo the latest live learned version of one industry. Returns the version rolled back."""
    live = [
        v
        for v in await versions(session, scope, industry_key)
        if v.status in ("live", "shadow") and v.version != BASE
    ]
    if not live:
        raise BusinessRuleViolation(
            "NOTHING_TO_ROLL_BACK", "This industry is already on its starting version", 409
        )
    return await undo(
        session,
        scope,
        industry_key,
        live[-1],
        live[-2].version if len(live) > 1 else BASE,
        kind="solution_rollback",
    )


async def undo(
    session: AsyncSession,
    scope: WorkspaceScope,
    industry_key: str,
    target: PiSolutionVersion,
    back_to: str,
    *,
    kind: str,
    why: str = "",
) -> PiSolutionVersion:
    """Undo one learned version of an industry: its added and retired ideas, its drafted problem
    entry and its sample reply (the sample reply in force falls back to the one before it, and the
    example the version fed to the bank is retired). Also the way an automatic rollback goes."""
    diff = target.diff or {}
    for entry in diff.get("added") or []:
        arm = await session.get(PiIdeaArm, UUID(str(entry)))
        if arm is not None and arm.status != "retired":
            arm.status, arm.retired_reason = "retired", f"rolled back from @{target.version}"
    for entry in diff.get("retired") or []:
        arm = await session.get(PiIdeaArm, UUID(str(entry["id"])))
        if arm is not None and arm.status == "retired":
            arm.status, arm.retired_reason = entry.get("from", "active"), ""
    problem = diff.get("add_problem") or {}
    for arm_id in problem.get("arm_ids") or []:
        arm = await session.get(PiIdeaArm, UUID(str(arm_id)))
        if arm is not None and arm.status != "retired":
            arm.status, arm.retired_reason = "retired", f"rolled back from @{target.version}"
    sample = diff.get("sample_reply") or {}
    if sample:
        await _undo_sample(session, scope, industry_key, sample)
    target.status, target.rolled_back_at = "rolled_back", datetime.now(UTC)
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind=kind,
            risk="low",
            before={"industry": industry_key, "version": target.version},
            after={"industry": industry_key, "version": back_to},
            status="live",
            reason=(why or f"rolled back solutions/{industry_key}@{target.version}")[:300],
        )
    )
    await session.flush()
    return target
