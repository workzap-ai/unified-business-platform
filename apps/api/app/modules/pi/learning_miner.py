# ruff: noqa: E501  (the drafting prompt reads better in long lines)
"""Question miner (pi Brain spec 8.5 job 3, "generate new arms").

For a question slot whose best wording is still below target after real use, a model writes two or
three new candidate questions in that slot's language. Each one goes through `learning_arms.propose`
(one question, no personal-data request, no pitching, never-learn list) and starts with a weak prior
and 10% of the traffic until it has 50 uses. Nothing here touches a rule or a fixed line.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning_arms
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("app.pi.learning")

TARGET_RATE = 0.5  # the share of useful answers a slot's best wording should reach
MIN_USES = 30  # before a wording's rate means anything
MAX_TESTING = 3  # candidates in test per slot and language at a time
MAX_PER_RUN = 6

QuestionWriter = Callable[[str, str, list[str]], Awaitable[list[str]]]

SYSTEM = """You write candidate questions for pi, Workzap's WhatsApp AI, which listens to problems in a
business. You are given one slot (what the question is about: scope, frequency, impact, since,
workaround), a language and the wordings already in use. Write 3 new questions for the same slot in
that language. Each is ONE short plain question, everyday words, no jargon, no price, no request for
personal or payment details, no pitching, never more than one question mark. Roman Urdu stays Roman
Urdu. Return only the structured result."""


class Wordings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[str] = Field(default_factory=list, max_length=6)


def make_writer(settings: Any, http: Any, scope: WorkspaceScope) -> QuestionWriter | None:
    """A question writer over the platform's model, or None without an HTTP client."""
    if http is None:
        return None

    async def write(slot: str, language: str, current: list[str]) -> list[str]:
        from app.ai.manager import LLMManager
        from app.ai.types import Message
        from app.ai.usage import NullUsageStore

        try:
            manager = LLMManager(settings, http, usage=NullUsageStore())
            result = await manager.complete_structured(
                scope,
                Wordings,
                alias="fast",
                purpose="pi_question_miner",
                messages=[
                    Message.system(SYSTEM),
                    Message.user(
                        json.dumps(
                            {"slot": slot, "language": language, "in_use": current},
                            ensure_ascii=False,
                        )
                    ),
                ],
                temperature=0.5,
                max_tokens=600,
            )
        except Exception:  # noqa: BLE001 - mining is an extra, never a reason to fail a run
            logger.warning("pi_question_miner_failed", exc_info=True)
            return []
        value = result.value
        return list(value.questions) if isinstance(value, Wordings) else []

    return write


async def mine(
    session: AsyncSession, scope: WorkspaceScope, writer: QuestionWriter | None
) -> dict[str, int]:
    """New candidate wordings for slots whose best wording is below target."""
    counts = {"slots_checked": 0, "proposed": 0, "refused": 0}
    if writer is None:
        return counts
    await learning_arms.ensure_seeded(session, scope)
    for slot in learning_arms.SEEDS:
        languages = {a.language for a in await learning_arms._live(session, scope, slot)}
        for language in sorted(languages):
            if counts["proposed"] >= MAX_PER_RUN:
                return counts
            live = await learning_arms._live(session, scope, slot, language)
            counts["slots_checked"] += 1
            best = max(live, key=lambda a: a.alpha / (a.alpha + a.beta))
            rate = best.alpha / (best.alpha + best.beta)
            if best.uses < MIN_USES or rate >= TARGET_RATE:
                continue
            if sum(1 for a in live if a.status == "testing") >= MAX_TESTING:
                continue
            for text in (await writer(slot, language, [a.text for a in live]))[:3]:
                arm, _ = await learning_arms.propose(session, scope, slot, language, text, "miner")
                counts["proposed" if arm is not None else "refused"] += 1
    return counts
