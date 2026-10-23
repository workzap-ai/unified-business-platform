# ruff: noqa: E501  (the slot patterns read better one per line)
"""Starting material for the learning brain (pi Brain spec 11.7 step 8).

* Example candidates from the illustrative exchanges of the industry packs (Part 7) and from the
  golden conversations (Part 10.1). They are filed under the pack's industry, enter as
  `candidate` with `source` "pack" or "golden", and then go through exactly the gate live examples
  go through: the never-learn list, the redaction bar (0.98), the rubric (the reply linter) and,
  after a day, the canary. Nothing is ever put straight to `active`. An exchange that fails a gate
  is skipped, not rewritten.
* Question wordings from each pack's Questions, filed under the industry, in the slot they ask
  about (scope, frequency, impact, since, workaround). They enter as `testing` with a tenth of the
  traffic, like any new wording, after the same never-learn and one-question checks.
"""

import re
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    industry_packs,
    learning,
    learning_bank,
    learning_rules,
    learning_situation,
    spec_handbook,
)
from app.modules.pi.language import detect_language
from app.modules.pi.learning_models import PiLearningChange, PiLearningExample, PiQuestionArm
from app.shared.scope import WorkspaceScope

SEED_REWARD = learning_rules.PROMOTE_REWARD  # a seed has no outcome yet: the bar is the rest
LISTENING_GOLDEN = ("G1", "G2", "G3", "G4", "G6", "G7", "G8")
TURN = re.compile(r"(?:(?<=\s)|^)(Person|pi):\s*")

SLOT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "since",
        re.compile(
            r"\b(?:since when|how long (?:has|have)|always (?:been|like)|started|kab se)\b", re.I
        ),
    ),
    (
        "frequency",
        re.compile(
            r"\b(?:how often|how many times|every (?:day|week|month)|daily|weekly|kitni baar)\b",
            re.I,
        ),
    ),
    (
        "impact",
        re.compile(
            r"\b(?:what does it cost|how much|how badly|hurt|lose|losing|cost you|nuqsan)\b", re.I
        ),
    ),
    (
        "workaround",
        re.compile(
            r"\b(?:how do you (?:handle|cope|manage|deal)|what do you do|workaround|today\b.*\b(?:handle|track))\b",
            re.I,
        ),
    ),
    (
        "scope",
        re.compile(
            r"\b(?:which|where|who|every (?:shop|branch|site|route|clinic|farm)|only some|all of|kahan|kaun)\b",
            re.I,
        ),
    ),
)


def slot_of(question: str) -> str | None:
    """The question slot a pack question asks about, or None when it fits none."""
    for slot, pattern in SLOT_PATTERNS:
        if pattern.search(question):
            return slot
    return None


def split_turns(text: str) -> list[tuple[str, str]]:
    """(who, said) turns of a golden conversation, up to its "Must:" line."""
    body = text.split("Must:")[0]
    parts = TURN.split(body)
    return [
        (who, " ".join(said.split()))
        for who, said in zip(parts[1::2], parts[2::2], strict=False)
        if said.strip()
    ]


def pairs(turns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(person, pi) exchanges: each person turn with the pi turn that answers it."""
    return [
        (turns[i][1], turns[i + 1][1])
        for i in range(len(turns) - 1)
        if turns[i][0].lower() == "person" and turns[i + 1][0].lower() == "pi"
    ]


def pack_pairs(pack: dict[str, Any]) -> list[tuple[str, str]]:
    turns = [(str(t.get("role", "")), str(t.get("text", ""))) for t in pack.get("exchange") or []]
    return pairs([(who, " ".join(said.split())) for who, said in turns])


def golden_pairs() -> list[tuple[str, str, str]]:
    """(golden id, person, pi) for the listening golden conversations."""
    out: list[tuple[str, str, str]] = []
    sections = spec_handbook.sections()
    for gid in LISTENING_GOLDEN:
        item = sections.get(gid)
        if item is None:
            continue
        out += [(gid, person, pi) for person, pi in pairs(split_turns(item.get("text", "")))]
    return out


def admit(person: str, reply: str) -> tuple[bool, float]:
    """The live gate, applied to a seed: never-learn on both sides, redaction at least 0.98, the
    rubric (the linter) at least 1.8. Returns (admitted, redaction confidence)."""
    said = learning_bank.strip_opening(reply)
    confidence = min(
        learning_bank.redaction_confidence(said), learning_bank.redaction_confidence(person)
    )
    ok = (
        bool(person.strip())
        and bool(said)
        and not learning.never_learn(said)
        and not learning.never_learn(person.rstrip("?") + ".")
        and learning_rules.should_promote_example(
            SEED_REWARD, learning_bank.rubric_proxy(said), False, confidence
        )
    )
    return ok, confidence


def state_of(reply: str) -> str:
    return "S3_NOTED" if re.search(r"\bnote[sd]?\b|note kar", reply, re.I) else "S2_CLARIFYING"


async def seed_examples(
    session: AsyncSession,
    scope: WorkspaceScope,
    industries: set[str] | None = None,
    *,
    golden: bool = True,
) -> dict[str, int]:
    """Candidate examples from the packs of `industries` (every pack when None) and the golden
    conversations. Idempotent: an exchange already seeded is skipped."""
    have = {
        (e.situation.get("industry", ""), e.person_text)
        for e in await session.scalars(
            select(PiLearningExample).where(
                PiLearningExample.tenant_id == scope.tenant_id,
                PiLearningExample.environment_id == scope.environment_id,
                PiLearningExample.source != "live",
            )
        )
    }
    counts = {"added": 0, "rejected": 0, "skipped": 0}
    work: list[tuple[str, str, str, str]] = []  # (source, industry, person, reply)
    for key, pack in sorted(industry_packs.load_packs().items()):
        if industries is not None and key not in industries:
            continue
        work += [("pack", key, p, r) for p, r in pack_pairs(pack)]
    if golden:
        work += [("golden", "", p, r) for _, p, r in golden_pairs()]
    for source, industry, person, reply in work:
        if (industry, person[:500]) in have:
            counts["skipped"] += 1
            continue
        ok, confidence = admit(person, reply)
        if not ok:
            counts["rejected"] += 1
            continue
        language = detect_language(person) or "en"
        said = learning_bank.strip_opening(reply)
        sit = {
            "state": state_of(said),
            "language": language,
            "turn_kind": "question" if said.rstrip().endswith(("?", "؟")) else "statement",
            **learning_situation.extras(industry, "", None),
        }
        session.add(
            PiLearningExample(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                message_id=None,
                source=source,
                situation=sit,
                language=language,
                person_text=person[:500],
                reply_text=said[:500],
                reward=0,
                status="candidate",
                source_contacts=[f"seed:{industry or 'golden'}"],
                redaction_confidence=Decimal(str(confidence)),
            )
        )
        have.add((industry, person[:500]))
        counts["added"] += 1
    if counts["added"]:
        session.add(
            PiLearningChange(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                kind="examples_seeded",
                risk="low",
                after=dict(counts),
                reason=f"seeded {counts['added']} example candidates from packs and golden",
                status="live",
            )
        )
    await session.flush()
    return counts


async def seed_arms(
    session: AsyncSession, scope: WorkspaceScope, industries: set[str] | None = None
) -> dict[str, int]:
    """Question wordings from the packs' Questions, filed under the industry and the slot they ask
    about, in the language they are written in (Roman Urdu where a pack has it)."""
    have = {
        (a.slot, a.language, a.industry, a.text)
        for a in await session.scalars(
            select(PiQuestionArm).where(
                PiQuestionArm.tenant_id == scope.tenant_id,
                PiQuestionArm.environment_id == scope.environment_id,
                PiQuestionArm.industry != "",
            )
        )
    }
    counts = {"added": 0, "refused": 0, "no_slot": 0}
    for key, pack in sorted(industry_packs.load_packs().items()):
        if industries is not None and key not in industries:
            continue
        for questions in (pack.get("questions") or {}).values():
            for raw in questions or []:
                text = " ".join(str(raw).split())
                slot = slot_of(text)
                if slot is None:
                    counts["no_slot"] += 1
                    continue
                language = detect_language(text) or "en"
                if (
                    learning.never_learn(text)
                    or not text.endswith(("?", "؟"))
                    or (slot, language, key, text) in have
                ):
                    counts["refused"] += 1
                    continue
                session.add(
                    PiQuestionArm(
                        tenant_id=scope.tenant_id,
                        environment_id=scope.environment_id,
                        slot=slot,
                        language=language,
                        text=text[:300],
                        status="testing",
                        traffic_cap=0.10,
                        created_by="pack",
                        industry=key,
                    )
                )
                have.add((slot, language, key, text))
                counts["added"] += 1
    if counts["added"]:
        session.add(
            PiLearningChange(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                kind="question_arms_seeded",
                risk="low",
                after=dict(counts),
                reason=f"seeded {counts['added']} industry question wordings from the packs",
                status="live",
            )
        )
    await session.flush()
    return counts


async def customer_industries(session: AsyncSession, scope: WorkspaceScope) -> set[str]:
    """The industries of this workspace's customers: what is worth seeding for."""
    from app.modules.customers.models import Customer

    rows = await session.scalars(
        select(Customer.industry_primary)
        .where(
            Customer.tenant_id == scope.tenant_id,
            Customer.environment_id == scope.environment_id,
            Customer.industry_primary.is_not(None),
        )
        .distinct()
    )
    return {k for k in (learning_situation.clean_industry(r) for r in rows) if k}
