# ruff: noqa: E501  (question wordings read better on one line each)
"""Question arms: which wording of the next question works best (pi Brain spec 8.4.5, 8.5 job 3).

pi's question policy (spec 3.5) says what to ask next: scope, then frequency, then impact, then
since when, then the workaround. This module only chooses among several ways to put that one
question, learning from how people answered. A new wording must pass the never-learn list (one
question, no personal data request, no pitch) before it is ever tried, starts with a 10% traffic
cap, and is retired when it is clearly worse. The question policy itself never changes here.
"""

import random
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearningChange, PiQuestionArm
from app.shared.scope import WorkspaceScope

# problem fields pi may still be missing (problems.noted_context "missing") -> question slot
SLOT_OF_MISSING = {
    "where": "scope",
    "how_often": "frequency",
    "impact": "impact",
    "since": "since",
}
ORDER = ("scope", "frequency", "impact", "since")

SEEDS: dict[str, dict[str, list[str]]] = {
    "scope": {
        "en": [
            "Is it everywhere in the business, or only in some places?",
            "Where do you notice it most?",
            "Which team or place does it hit hardest?",
        ],
        "roman_ur": [
            "Ye har jagah hota hai, ya sirf kuch jagah?",
            "Ye sab se zyada kahan nazar aata hai?",
        ],
    },
    "frequency": {
        "en": [
            "How often does it happen?",
            "Is it daily, weekly, or only at certain times?",
        ],
        "roman_ur": [
            "Ye kitni baar hota hai?",
            "Ye roz hota hai, hafte mein, ya kuch khaas waqt par?",
        ],
    },
    "impact": {
        "en": [
            "What does it cost you: time, money, or stress?",
            "Roughly how much does it hurt: a little, or a lot?",
        ],
        "roman_ur": [
            "Is se aap ka kya nuqsan hota hai: waqt, paisa, ya pareshani?",
            "Ye kitna nuqsan karta hai: thora, ya bohat?",
        ],
    },
    "since": {
        "en": [
            "Has it always been like this, or did something change?",
            "Since when has it been happening?",
        ],
        "roman_ur": [
            "Ye hamesha se aisa hai, ya kuch badla hai?",
            "Ye kab se ho raha hai?",
        ],
    },
}


# Generic seed wordings that said "shop" for every industry; retired when found (spec 8.2).
LEGACY_SEEDS = frozenset(
    {
        "Is it every shop, or only some?",
        "Which shop or team does it hit hardest?",
        "Ye har dukan mein hota hai, ya sirf kuch mein?",
        "What does it cost you: time, sales, or stress?",
        "Is se aap ka kya nuqsan hota hai: waqt, sales, ya pareshani?",
    }
)


def slot_for(missing: list[str]) -> str | None:
    """The next question slot for what is still missing about the latest problem."""
    slots = {SLOT_OF_MISSING[m] for m in missing if m in SLOT_OF_MISSING}
    return next((s for s in ORDER if s in slots), None)


def _scoped(scope: WorkspaceScope) -> tuple[Any, ...]:
    return (
        PiQuestionArm.tenant_id == scope.tenant_id,
        PiQuestionArm.environment_id == scope.environment_id,
    )


async def ensure_seeded(session: AsyncSession, scope: WorkspaceScope) -> int:
    """The starting wordings, created once per workspace. Returns how many were added."""
    have = {
        (a.slot, a.language, a.text)
        for a in await session.scalars(select(PiQuestionArm).where(*_scoped(scope)))
    }
    added = 0
    for row in await session.scalars(
        select(PiQuestionArm).where(
            *_scoped(scope),
            PiQuestionArm.created_by == "seed",
            PiQuestionArm.status != "retired",
            PiQuestionArm.text.in_(LEGACY_SEEDS),
        )
    ):
        row.status = "retired"
    for slot, by_language in SEEDS.items():
        for language, texts in by_language.items():
            for text in texts:
                if (slot, language, text) in have:
                    continue
                session.add(
                    PiQuestionArm(
                        tenant_id=scope.tenant_id,
                        environment_id=scope.environment_id,
                        slot=slot,
                        language=language,
                        text=text,
                        status="active",
                        created_by="seed",
                    )
                )
                added += 1
    await session.flush()
    return added


def as_arm(row: PiQuestionArm) -> learning.Arm:
    return learning.Arm(
        row.text, row.alpha, row.beta, row.uses, row.traffic_cap if row.status == "testing" else 1.0
    )


async def choose(
    session: AsyncSession,
    scope: WorkspaceScope,
    slot: str,
    language: str,
    rng: random.Random | None = None,
    industry: str = "",
) -> PiQuestionArm | None:
    """Thompson sampling among the live wordings for this slot and language (English when the
    language has none). Wordings for the person's industry compete with the general ones; a
    wording for another industry is never used (spec 8.2 situation key)."""
    for lang in dict.fromkeys([language, "en"]):
        rows = list(
            await session.scalars(
                select(PiQuestionArm).where(
                    *_scoped(scope),
                    PiQuestionArm.slot == slot,
                    PiQuestionArm.language == lang,
                    PiQuestionArm.status != "retired",
                    PiQuestionArm.industry.in_(("", industry) if industry else ("",)),
                )
            )
        )
        if rows:
            picked = learning.choose_arm([as_arm(r) for r in rows], rng)
            return next(r for r in rows if r.text == picked.text)
    return None


async def record(
    session: AsyncSession, scope: WorkspaceScope, arm_id: UUID, useful: bool
) -> PiQuestionArm | None:
    """One more use of this wording and whether the answer was useful without confusion."""
    row = await session.get(PiQuestionArm, arm_id)
    if (
        row is None
        or row.tenant_id != scope.tenant_id
        or row.environment_id != scope.environment_id
    ):
        return None
    arm = as_arm(row)
    learning.update_arm(arm, useful)
    row.alpha, row.beta, row.uses = arm.alpha, arm.beta, arm.uses
    if row.status == "testing" and arm.traffic_cap >= 1.0:
        row.status, row.traffic_cap = "active", 1.0
    await session.flush()
    return row


async def propose(
    session: AsyncSession,
    scope: WorkspaceScope,
    slot: str,
    language: str,
    text: str,
    by: str,
    industry: str = "",
) -> tuple[PiQuestionArm | None, list[str]]:
    """A new wording (from staff or a miner). It must pass the never-learn list and be a question;
    it starts as "testing" with 10% of the traffic until it has 50 uses. Returns the arm, or None
    with the reasons it was refused."""
    wording = " ".join((text or "").split())
    why = learning.never_learn(wording)
    if slot not in SEEDS:
        why.append("unknown question slot")
    if not wording.endswith(("?", "؟")):
        why.append("a question ends with a question mark")
    if by in ("miner", "pi") and await _was_retired(session, scope, slot, language, wording):
        why.append("a person retired this wording: the miner does not propose it again (8.6)")
    if why:
        return None, why
    arm = PiQuestionArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        slot=slot,
        language=language,
        text=wording[:300],
        status="testing",
        traffic_cap=0.10,
        created_by=by,
        industry=industry,
    )
    session.add(arm)
    await session.flush()
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="question_arm_added",
            target_id=arm.id,
            risk=learning.risk(wording).lower(),
            before={},
            after={"slot": slot, "language": language, "text": wording, "by": by},
            status="live",
            reason=f"proposed by {by}",
        )
    )
    await session.flush()
    return arm, []


def _norm(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


async def _was_retired(
    session: AsyncSession, scope: WorkspaceScope, slot: str, language: str, wording: str
) -> bool:
    """The same wording (ignoring case and punctuation) was already retired in this slot."""
    gone = await session.scalars(
        select(PiQuestionArm.text).where(
            *_scoped(scope),
            PiQuestionArm.slot == slot,
            PiQuestionArm.language == language,
            PiQuestionArm.status == "retired",
        )
    )
    return _norm(wording) in {_norm(t) for t in gone}


def was_useful(signals: list[str]) -> bool:
    """A useful answer without confusion (spec 8.5 job 3): the person gave detail or confirmed, and
    did not correct, get confused, repeat themselves or drop off."""
    bad = {"confusion", "correction", "repeat_question", "drop_off", "frustration", "opt_out"}
    good = {"rich_reply", "confirmed_first_time", "self_continued", "thanked"}
    return bool(good & set(signals)) and not (bad & set(signals))


async def learn_from(
    session: AsyncSession, scope: WorkspaceScope, since: datetime
) -> dict[str, int]:
    """Update every arm from the replies scored since the last run (each experience once)."""
    rows = list(
        await session.scalars(
            select(PiExperience).where(
                PiExperience.tenant_id == scope.tenant_id,
                PiExperience.environment_id == scope.environment_id,
                PiExperience.arm_id.is_not(None),
                PiExperience.scored_at >= since,
            )
        )
    )
    for exp in rows:
        assert exp.arm_id is not None
        await record(session, scope, exp.arm_id, was_useful(exp.signals))
    retired = 0
    for slot in SEEDS:
        for lang in {a.language for a in await _live(session, scope, slot)}:
            live = await _live(session, scope, slot, lang)
            if len(live) < 2:
                continue
            best = max(live, key=lambda a: a.alpha / (a.alpha + a.beta))
            for arm in live:
                if arm is not best and _clearly_worse(arm, best):
                    arm.status = "retired"
                    session.add(
                        PiLearningChange(
                            tenant_id=scope.tenant_id,
                            environment_id=scope.environment_id,
                            kind="question_arm_retired",
                            target_id=arm.id,
                            before={"status": "active"},
                            after={"status": "retired"},
                            reason="clearly worse after 200 uses",
                            status="live",
                        )
                    )
                    retired += 1
    await session.flush()
    return {"arms_updated": len(rows), "arms_retired": retired}


async def _live(
    session: AsyncSession, scope: WorkspaceScope, slot: str, language: str | None = None
) -> list[PiQuestionArm]:
    query = select(PiQuestionArm).where(
        *_scoped(scope), PiQuestionArm.slot == slot, PiQuestionArm.status != "retired"
    )
    if language is not None:
        query = query.where(PiQuestionArm.language == language)
    return list(await session.scalars(query))


def _clearly_worse(arm: PiQuestionArm, best: PiQuestionArm) -> bool:
    return learning.arm_should_retire(as_arm(arm), as_arm(best))


__all__ = ["choose", "ensure_seeded", "learn_from", "propose", "record", "slot_for", "was_useful"]
