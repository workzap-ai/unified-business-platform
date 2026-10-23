# ruff: noqa: E501  (the drafting prompt reads better in long lines)
"""Voice variants (pi Brain spec 8.5 job 6, 2.3).

For a few canonical meanings pi keeps several phrasings and is shown one as a hint, chosen with the
same Thompson sampling as question wordings. A phrasing is credited only when the reply really used
it and the person answered without confusion or correction. The canonical wording is the baseline:
a variant that stays clearly worse than it for two weeks is retired, and a model writes new ones to
replace it, each starting with a tenth of the traffic. The opening line, the offer and every other
fixed line are never varied: only the moments listed in `SEEDS` are here, and a hint never
overrides a rule (the reply linter still judges every reply).

The variants live in the question-wording table under the slots `voice_<moment>`, so nothing needs
a migration.
"""

import json
import logging
import random
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning, learning_arms
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_bank import LISTENING_STATES, tokens
from app.modules.pi.learning_models import PiLearningChange, PiQuestionArm
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("app.pi.learning")

PREFIX = "voice_"
# The first wording of each list is the canonical one: the baseline the others are judged against.
SEEDS: dict[str, dict[str, list[str]]] = {
    "acknowledge": {
        "en": [
            "That's a real problem.",
            "That sounds costly.",
            "That's worth sorting.",
            "Got it.",
        ]
    },
    "correct": {
        "en": [
            "You're right, I've changed it.",
            "Fixed, it now says the new wording.",
        ]
    },
}
MIN_USES = 30  # before a variant's rate means anything
BELOW_BASELINE = 0.10
RETIRE_AFTER = timedelta(days=14)
MIN_LIVE = 3  # variants kept per moment and language, the miner fills the gap
MAX_PER_RUN = 4
USED_SHARE = 0.75  # of a variant's words that must be in the reply for it to count as used
MAX_WORDS = 14

CORRECTION = re.compile(
    r"^\W*(?:(?:no|nahi|nahin|nope|actually)\b"
    r"|(?:galat|ghalat|glt|wrong)\W*(?:$|(?:hai|he|h|baat|wo|woh|ye|yeh)\b))"
    r"|\b(?:i meant|it'?s actually|i never said)\b",
    re.IGNORECASE,
)
Writer = Callable[[str, str, list[str]], Awaitable[list[str]]]


def slot_of(moment: str) -> str:
    return PREFIX + moment


def moment_of(said: str, state: str, has_notes: bool = True) -> str | None:
    """Which moment this turn is, from the person's own message, or None when none applies. A
    correction needs something already noted to correct, and a short "no" is an answer, not one."""
    text = " ".join((said or "").split())
    if CORRECTION.search(text):
        return "correct" if has_notes and len(text.split()) >= 4 else None
    if state in LISTENING_STATES and len(text.split()) >= 4:
        return "acknowledge"
    return None


def _scoped(scope: WorkspaceScope) -> tuple[Any, ...]:
    return (
        PiQuestionArm.tenant_id == scope.tenant_id,
        PiQuestionArm.environment_id == scope.environment_id,
    )


async def ensure_seeded(session: AsyncSession, scope: WorkspaceScope) -> int:
    have = {
        (a.slot, a.language, a.text)
        for a in await session.scalars(
            select(PiQuestionArm).where(*_scoped(scope), PiQuestionArm.slot.like(PREFIX + "%"))
        )
    }
    added = 0
    for moment, by_language in SEEDS.items():
        for language, texts in by_language.items():
            for text in texts:
                if (slot_of(moment), language, text) in have:
                    continue
                session.add(
                    PiQuestionArm(
                        tenant_id=scope.tenant_id,
                        environment_id=scope.environment_id,
                        slot=slot_of(moment),
                        language=language,
                        text=text,
                        status="active",
                        created_by="seed",
                    )
                )
                added += 1
    await session.flush()
    return added


async def _live(
    session: AsyncSession, scope: WorkspaceScope, moment: str, language: str
) -> list[PiQuestionArm]:
    return list(
        await session.scalars(
            select(PiQuestionArm).where(
                *_scoped(scope),
                PiQuestionArm.slot == slot_of(moment),
                PiQuestionArm.language == language,
                PiQuestionArm.status != "retired",
            )
        )
    )


async def choose(
    session: AsyncSession,
    scope: WorkspaceScope,
    moment: str,
    language: str,
    rng: random.Random | None = None,
) -> PiQuestionArm | None:
    """Thompson sampling among this moment's live variants in the person's own language. There is
    no fallback to English: a Roman Urdu speaker is never offered an English phrasing."""
    rows = await _live(session, scope, moment, language)
    if not rows:
        return None
    picked = learning.choose_arm([learning_arms.as_arm(r) for r in rows], rng)
    return next(r for r in rows if r.text == picked.text)


def used_in(reply: str, wording: str) -> bool:
    """The reply really used the variant: most of its words are there."""
    words = tokens(wording)
    return bool(words) and len(words & tokens(reply)) / len(words) >= USED_SHARE


def valid(moment: str, text: str) -> list[str]:
    """Why a proposed variant is refused (empty when it may be tried)."""
    wording = " ".join((text or "").split())
    why = learning.never_learn(wording)
    if moment not in SEEDS:
        why.append("unknown moment")
    if "?" in wording or "؟" in wording:
        why.append("a phrasing for this moment is not a question")
    if not 2 <= len(wording.split()) <= MAX_WORDS:
        why.append(f"2 to {MAX_WORDS} words")
    return why


async def propose(
    session: AsyncSession, scope: WorkspaceScope, moment: str, language: str, text: str, by: str
) -> tuple[PiQuestionArm | None, list[str]]:
    wording = " ".join((text or "").split())
    if why := valid(moment, wording):
        return None, why
    arm = PiQuestionArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        slot=slot_of(moment),
        language=language,
        text=wording[:300],
        status="testing",
        traffic_cap=0.10,
        created_by=by,
    )
    session.add(arm)
    await session.flush()
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="voice_variant_added",
            target_id=arm.id,
            risk="low",
            before={},
            after={"moment": moment, "language": language, "text": wording, "by": by},
            status="live",
            reason=f"proposed by {by}",
        )
    )
    await session.flush()
    return arm, []


async def _stamped_arm(session: AsyncSession, exp: PiExperience) -> UUID | None:
    """The voice variant that was shown when this reply was written, from the stamp the context
    builder left on the conversation, or None."""
    conversation = await session.get(PiConversation, exp.conversation_id)
    stamps = ((conversation.service_brief if conversation else None) or {}).get("learning_used")
    run = await session.scalar(
        select(PiAgentRun).where(PiAgentRun.response_message_id == exp.message_id)
    )
    if not stamps or run is None:
        return None
    stamp = next((s for s in reversed(stamps) if s.get("message_id") == str(run.message_id)), None)
    if not stamp or not stamp.get("voice_arm"):
        return None
    return UUID(stamp["voice_arm"])


async def _credit(session: AsyncSession, scope: WorkspaceScope, since: datetime) -> int:
    rows = await session.scalars(
        select(PiExperience).where(
            PiExperience.tenant_id == scope.tenant_id,
            PiExperience.environment_id == scope.environment_id,
            PiExperience.scored_at >= since,
        )
    )
    credited = 0
    for exp in rows:
        arm_id = await _stamped_arm(session, exp)
        if arm_id is None:
            continue
        arm = await session.get(PiQuestionArm, arm_id)
        reply = await session.get(PiMessage, exp.message_id)
        if arm is None or reply is None or not used_in(reply.body or "", arm.text):
            continue  # shown but not used: no credit, or the reward would teach the wrong thing
        await learning_arms.record(session, scope, arm.id, learning_arms.was_useful(exp.signals))
        credited += 1
    return credited


def _rate(arm: PiQuestionArm) -> float:
    return arm.alpha / (arm.alpha + arm.beta)


async def _latest_flag(
    session: AsyncSession, scope: WorkspaceScope, arm_id: UUID
) -> PiLearningChange | None:
    found: PiLearningChange | None = await session.scalar(
        select(PiLearningChange)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.target_id == arm_id,
            PiLearningChange.kind.in_(("voice_below_baseline", "voice_recovered")),
        )
        .order_by(PiLearningChange.created_at.desc())
        .limit(1)
    )
    return found


async def retire_worse(
    session: AsyncSession, scope: WorkspaceScope, now: datetime
) -> dict[str, int]:
    """Flag a variant that is clearly worse than the canonical wording; retire it when it is still
    worse two weeks later. The canonical wording itself is never retired."""
    flagged = retired = 0
    for moment, by_language in SEEDS.items():
        for language, texts in by_language.items():
            live = await _live(session, scope, moment, language)
            baseline = next((a for a in live if a.text == texts[0]), None)
            if baseline is None:
                continue
            for arm in live:
                if arm is baseline or (arm.created_by == "seed" and arm.uses < MIN_USES):
                    continue
                below = arm.uses >= MIN_USES and _rate(baseline) - _rate(arm) >= BELOW_BASELINE
                last = await _latest_flag(session, scope, arm.id)
                open_flag = last is not None and last.kind == "voice_below_baseline"
                if below and not open_flag:
                    session.add(
                        _note(
                            scope, "voice_below_baseline", arm, "worse than the canonical wording"
                        )
                    )
                    flagged += 1
                elif below and last is not None and now - last.created_at >= RETIRE_AFTER:
                    arm.status = "retired"
                    session.add(
                        _note(
                            scope, "voice_variant_retired", arm, "worse than baseline for 2 weeks"
                        )
                    )
                    retired += 1
                elif not below and open_flag:
                    session.add(
                        _note(scope, "voice_recovered", arm, "back to the baseline's level")
                    )
    await session.flush()
    return {"flagged": flagged, "retired": retired}


def _note(scope: WorkspaceScope, kind: str, arm: PiQuestionArm, reason: str) -> PiLearningChange:
    return PiLearningChange(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        kind=kind,
        target_id=arm.id,
        risk="low",
        before={"text": arm.text, "uses": arm.uses},
        after={"status": "retired" if kind == "voice_variant_retired" else "live"},
        evidence={"rate": round(_rate(arm), 3)},
        status="live",
        reason=reason,
    )


async def learn_from(
    session: AsyncSession, scope: WorkspaceScope, since: datetime, now: datetime
) -> dict[str, int]:
    credited = await _credit(session, scope, since)
    return {"credited": credited, **await retire_worse(session, scope, now)}


class Phrasings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    phrases: list[str] = Field(default_factory=list, max_length=6)


SYSTEM = """You write alternative phrasings for pi, Workzap's WhatsApp AI, for one small moment in a
conversation (acknowledge: pi shows it heard a problem; correct: pi confirms it changed a note the
person corrected). You get the moment, a language and the phrasings already in use. Write 3 new ones
in that language with the same meaning: one short plain sentence each, everyday words, no question,
no price, no promise, no exclamation mark, never longer than 14 words. Roman Urdu stays Roman
Urdu. Return only the structured result."""


def make_writer(settings: Any, http: Any, scope: WorkspaceScope) -> Writer | None:
    if http is None:
        return None

    async def write(moment: str, language: str, current: list[str]) -> list[str]:
        from app.ai.manager import LLMManager
        from app.ai.types import Message
        from app.ai.usage import NullUsageStore

        try:
            manager = LLMManager(settings, http, usage=NullUsageStore())
            result = await manager.complete_structured(
                scope,
                Phrasings,
                alias="fast",
                purpose="pi_voice_miner",
                messages=[
                    Message.system(SYSTEM),
                    Message.user(
                        json.dumps(
                            {"moment": moment, "language": language, "in_use": current},
                            ensure_ascii=False,
                        )
                    ),
                ],
                temperature=0.6,
                max_tokens=400,
            )
        except Exception:  # noqa: BLE001 - mining is an extra, never a reason to fail a run
            logger.warning("pi_voice_miner_failed", exc_info=True)
            return []
        value = result.value
        return list(value.phrases) if isinstance(value, Phrasings) else []

    return write


async def mine(
    session: AsyncSession, scope: WorkspaceScope, writer: Writer | None
) -> dict[str, int]:
    """New variants where fewer than MIN_LIVE are left (a retired one is replaced this way)."""
    counts = {"proposed": 0, "refused": 0}
    if writer is None:
        return counts
    await ensure_seeded(session, scope)
    for moment, by_language in SEEDS.items():
        for language in by_language:
            live = await _live(session, scope, moment, language)
            if len(live) >= MIN_LIVE or counts["proposed"] >= MAX_PER_RUN:
                continue
            for text in (await writer(moment, language, [a.text for a in live]))[
                : MIN_LIVE - len(live)
            ]:
                arm, _ = await propose(session, scope, moment, language, text, "miner")
                counts["proposed" if arm is not None else "refused"] += 1
    return counts
