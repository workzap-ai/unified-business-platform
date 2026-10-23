"""The example bank: real replies that went well, kept as redacted reference (pi Brain spec 8.4.3,
8.5 job 2, 8.8).

What gets in: a reply from the listening loop (S1 to S3, written by the model, never a fixed line)
that scored well and was followed by a good turn, whose text and the message it answered both pass
the redaction gate (nothing that looks like a name, number, link or contact detail) and the
never-learn list, with no rule break. What comes out: at most three, for a similar situation, as
reference material the prompt says is below the rules. Learned text can only ever be a style
example; the reply linter still judges what pi finally sends.
"""

import math
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    constitution,
    learning,
    learning_canary,
    learning_gate,
    learning_grader,
    learning_review,
    learning_rules,
    learning_situation,
    safety,
)
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_embed import Embedder
from app.modules.pi.learning_models import PiLearningChange, PiLearningExample
from app.modules.pi.models import PiConversation, PiMessage
from app.shared.scope import WorkspaceScope

LISTENING_STATES = ("S1_LISTENING", "S2_CLARIFYING", "S3_NOTED")
ACTIVATE_AFTER = timedelta(hours=24)
WINDOW_DAYS = 14

# Words that look like names but are not (brand and language names pi may say).
KNOWN_CAPITALS = frozenset(
    {"Workzap", "WhatsApp", "Urdu", "English", "Arabic", "Roman", "Hindi", "Thanks", "Noted"}
)
SENTENCE_START = re.compile(r"(?:^|[.!?؟:\n•]\s*)$")
CAPITALISED = re.compile(r"\b[A-Z][a-z]{2,}\b")
TOKEN = re.compile(r"[a-z؀-ۿ]{3,}")


def redaction_confidence(text: str) -> float:
    """How sure we are that no personal data is left. Deliberately blunt: anything redacted,
    any digit, link or address-like token, and any capitalised word that is not at the start of
    a sentence (a possible name) lowers it below the 0.98 bar. A rejected example costs nothing."""
    said = text or ""
    if safety.redact_pii(said).kinds:
        return 0.0
    score = 1.0
    if re.search(r"\d", said):
        score -= 0.3
    if re.search(r"https?://|www\.|@", said):
        score -= 0.5
    for match in CAPITALISED.finditer(said):
        if match.group() in KNOWN_CAPITALS:
            continue
        if SENTENCE_START.search(said[: match.start()]):
            continue
        score -= 0.4
        break
    return max(0.0, round(score, 3))


LISTENING = {
    "pi_mode": "brain",
    "strict_voice": True,
    "flow": {"state": "S2_CLARIFYING"},
    "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
}


def rubric_proxy(reply: str) -> float:
    """Until a grader model scores conversations: 2.0 when the reply breaks no rule or style point
    the linter knows, 1.0 otherwise."""
    return 2.0 if not constitution.lint(reply, dict(LISTENING)) else 1.0


def strip_opening(text: str) -> str:
    """The reply without the fixed "I'm pi, an AI from Workzap" introduction: that line is written
    by the application, not learned from, and must not count for or against an example."""
    said = (text or "").strip()
    for line in constitution.OPENING.values():
        if said.startswith(line):
            return said[len(line) :].strip()
    return said


def tokens(text: str) -> set[str]:
    return set(TOKEN.findall((text or "").lower()))


def similarity(a: str, b: str) -> float:
    left, right = tokens(a), tokens(b)
    return len(left & right) / len(left | right) if left and right else 0.0


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


async def _answered(session: AsyncSession, reply: PiMessage) -> PiMessage | None:
    """The customer message pi's reply was an answer to."""
    found: PiMessage | None = await session.scalar(
        select(PiMessage)
        .where(
            PiMessage.conversation_id == reply.conversation_id,
            PiMessage.direction == "inbound",
            PiMessage.created_at < reply.created_at,
        )
        .order_by(PiMessage.created_at.desc())
        .limit(1)
    )
    return found


async def _transcript(session: AsyncSession, conversation_id: UUID) -> list[tuple[str, str]]:
    """The conversation as (who, redacted text), oldest first, for the grader."""
    rows = await session.scalars(
        select(PiMessage)
        .where(PiMessage.conversation_id == conversation_id)
        .order_by(PiMessage.created_at.desc())
        .limit(learning_grader.MAX_MESSAGES)
    )
    return [  # the newest messages, oldest first: a break late in a long chat must be seen
        ("person" if m.direction == "inbound" else "pi", safety.redact_pii(m.body or "").text)
        for m in reversed(list(rows))
        if (m.body or "").strip()
    ]


async def curate(
    session: AsyncSession,
    scope: WorkspaceScope,
    now: datetime | None = None,
    limit: int = 200,
    embedder: Embedder | None = None,
    grader: learning_grader.Grader | None = None,
) -> dict[str, int]:
    """New candidates from yesterday's good listening-loop replies. Returns counts."""
    now = now or datetime.now(UTC)
    seen = select(PiLearningExample.message_id).where(
        PiLearningExample.tenant_id == scope.tenant_id,
        PiLearningExample.environment_id == scope.environment_id,
        PiLearningExample.message_id.is_not(None),  # a NULL in NOT IN would match nothing
    )
    rows = list(
        await session.scalars(
            select(PiExperience)
            .where(
                PiExperience.tenant_id == scope.tenant_id,
                PiExperience.environment_id == scope.environment_id,
                PiExperience.reward >= 2,
                PiExperience.scored_at >= now - timedelta(days=WINDOW_DAYS),
                PiExperience.message_id.not_in(seen),
            )
            .order_by(PiExperience.scored_at)
            .limit(limit)
        )
    )
    counts = {"looked_at": len(rows), "added": 0, "rejected": 0}
    fresh: list[PiLearningExample] = []
    graded: dict[UUID, learning_grader.Grade | None] = {}
    for exp in rows:
        if exp.situation.get("state") not in LISTENING_STATES:
            continue  # fixed lines (offer, summary, documents) are never examples
        reply = await session.get(PiMessage, exp.message_id)
        if reply is None or not (reply.body or "").strip():
            continue
        following = await session.scalar(
            select(PiExperience)
            .join(PiMessage, PiMessage.id == PiExperience.message_id)
            .where(
                PiExperience.conversation_id == exp.conversation_id,
                PiMessage.created_at > reply.created_at,
            )
            .order_by(PiMessage.created_at)
            .limit(1)
        )
        total = exp.reward + (following.reward if following is not None else 0)
        asked = await _answered(session, reply)
        person, said = (asked.body if asked is not None else ""), strip_opening(reply.body)
        confidence = min(redaction_confidence(said), redaction_confidence(person))
        rubric, defect = rubric_proxy(said), False
        if grader is not None and bool(person.strip()):
            if exp.conversation_id not in graded:
                graded[exp.conversation_id] = await grader(
                    await _transcript(session, exp.conversation_id)
                )
                if (g := graded[exp.conversation_id]) is not None and g.rule_break:
                    counts["defects"] = counts.get("defects", 0) + 1
                    session.add(
                        PiLearningChange(
                            tenant_id=scope.tenant_id,
                            environment_id=scope.environment_id,
                            kind="grader_defect",
                            risk="high",
                            target_id=exp.conversation_id,
                            evidence={"reasons": g.reasons},
                            status="review",
                            reason="the grader found a rule break: " + "; ".join(g.reasons)[:240],
                        )
                    )
            if (g := graded[exp.conversation_id]) is not None:
                rubric, defect = min(rubric, g.mean), g.rule_break
        ok = (
            bool(person.strip())
            and not learning.never_learn(said)
            and not learning.never_learn(person.rstrip("?") + ".")  # their words, as a statement
            and learning_rules.should_promote_example(
                total,
                rubric,
                defect or "rule_break" in (exp.signals or []),
                confidence,
            )
        )
        if ok and await learning_review.blocked(
            session, scope, "example", learning_canary.signature(said)
        ):
            ok = False  # rolled back twice and not yet looked at (spec 8.6)
        if not ok:
            counts["rejected"] += 1
            continue
        conversation = await session.get(PiConversation, exp.conversation_id)
        example = PiLearningExample(
            tenant_id=exp.tenant_id,
            environment_id=exp.environment_id,
            message_id=exp.message_id,
            situation=exp.situation,
            language=exp.situation.get("language", "en"),
            person_text=person[:500],
            reply_text=said[:500],
            reward=total,
            status="candidate",
            source_contacts=[str(conversation.customer_id)]
            if conversation is not None and conversation.customer_id
            else [],
            redaction_confidence=Decimal(str(confidence)),
        )
        session.add(example)
        fresh.append(example)
        counts["added"] += 1
    if embedder is not None and fresh:
        vectors = await embedder([e.person_text for e in fresh])
        for example, vector in zip(fresh, vectors or [], strict=False):
            example.embedding = vector
        counts["embedded"] = len(vectors or [])
    await session.flush()
    return counts


def _log(
    scope: WorkspaceScope, kind: str, target: UUID, before: str, after: str, reason: str, **ev: Any
) -> PiLearningChange:
    return PiLearningChange(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        kind=kind,
        target_id=target,
        before={"status": before},
        after={"status": after},
        evidence=ev,
        reason=reason[:300],
    )


async def activate(
    session: AsyncSession, scope: WorkspaceScope, now: datetime | None = None
) -> dict[str, int]:
    """Candidates a day old (and never flagged) become canaries, which the nightly canary check
    promotes or rolls back; then the bank is balanced: one example per business per situation, at
    most 30 per situation (the best by reward stay)."""
    now = now or datetime.now(UTC)
    where = (
        PiLearningExample.tenant_id == scope.tenant_id,
        PiLearningExample.environment_id == scope.environment_id,
    )
    ripe = list(
        await session.scalars(
            select(PiLearningExample).where(
                *where,
                PiLearningExample.status == "candidate",
                PiLearningExample.created_at <= now - ACTIVATE_AFTER,
            )
        )
    )
    held = not await learning_gate.allows(session, scope)  # job 9: nothing starts while it fails
    if held:
        ripe = []
    for example in ripe:
        learning_canary.start(example, now)  # a small share of chats first (spec 9.10 rule 3)
        session.add(
            _log(scope, "example_activated", example.id, "candidate", "canary", "a day old")
        )
    await session.flush()
    active = list(
        await session.scalars(
            select(PiLearningExample).where(*where, PiLearningExample.status == "active")
        )
    )
    rows = [
        {
            "id": e.id,
            "situation": "|".join(f"{k}={v}" for k, v in sorted(e.situation.items())),
            "business": (e.source_contacts or [""])[0],
            "reward": e.reward,
        }
        for e in active
    ]
    keep = {r["id"] for r in learning_rules.balance_examples(rows)}
    retired = 0
    for example in active:
        if example.id not in keep:
            example.status, example.retired_reason = "retired", "balance"
            session.add(_log(scope, "example_retired", example.id, "active", "retired", "balance"))
            retired += 1
    await session.flush()
    return {"activated": len(ripe), "retired_for_balance": retired, "held_by_gate": int(held)}


async def retire_poor(session: AsyncSession, scope: WorkspaceScope) -> int:
    """Active examples that were shown at least 10 times and whose replies scored below zero on
    average stop being used (spec 8.5 job 2, demote)."""
    active = list(
        await session.scalars(
            select(PiLearningExample).where(
                PiLearningExample.tenant_id == scope.tenant_id,
                PiLearningExample.environment_id == scope.environment_id,
                PiLearningExample.status == "active",
                PiLearningExample.uses >= 10,
            )
        )
    )
    gone = 0
    for example in active:
        rewards = [
            r
            for r in await session.scalars(
                select(PiExperience.reward).where(
                    PiExperience.tenant_id == scope.tenant_id,
                    PiExperience.environment_id == scope.environment_id,
                    PiExperience.example_ids.contains([str(example.id)]),
                )
            )
        ]
        if len(rewards) >= 10 and sum(rewards) / len(rewards) < 0:
            example.status, example.retired_reason = "retired", "below average reward"
            session.add(
                _log(
                    scope,
                    "example_retired",
                    example.id,
                    "active",
                    "retired",
                    "below average reward",
                    average=round(sum(rewards) / len(rewards), 2),
                    shown=len(rewards),
                )
            )
            gone += 1
    await session.flush()
    return gone


def _backoff(
    state: str,
    language: str,
    turn_kind: str,
    industry: str = "",
    category: str = "",
    person_type: str = "",
) -> list[dict[str, str]]:
    """Broader and broader situations (spec 8.2): drop the person type, the problem category, the
    kind of turn, the state, then the industry. The language stays in every level."""
    return learning_situation.backoff(
        state=state,
        language=language,
        turn_kind=turn_kind,
        industry=industry,
        category=category,
        person_type=person_type,
    )


def _matches(example: PiLearningExample, level: dict[str, str]) -> bool:
    return learning_situation.fits(example.situation, level)


async def retrieve(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    state: str,
    language: str,
    said: str,
    turn_kind: str = "question",
    k: int = 3,
    query_embedding: list[float] | None = None,
    exclude_contact: str | None = None,
    embedder: Embedder | None = None,
    conversation_id: UUID | str | None = None,
    canary_percent: int = 0,
    industry: str = "",
    category: str = "",
    person_type: str = "",
) -> list[PiLearningExample]:
    """The best active examples for this situation (plus canaries, for the canary share of
    conversations): only matching or backed-off situations (eval L1), never from the same person,
    one per business, ranked by how alike the person's words are, then by reward. An example filed
    under an industry is shown only for that industry (or, at the last step, its sector); a general
    one fits everyone. Anything that no longer passes the never-learn list is left out."""
    if state not in LISTENING_STATES:
        return []
    industry = learning_situation.clean_industry(industry)
    sector = learning_situation.sector_of(industry)
    active = list(
        await session.scalars(
            select(PiLearningExample).where(
                PiLearningExample.tenant_id == scope.tenant_id,
                PiLearningExample.environment_id == scope.environment_id,
                PiLearningExample.status.in_(("active", "canary")),
                PiLearningExample.language == language,
            )
        )
    )
    shown_canary = conversation_id is not None and learning_canary.in_canary(
        conversation_id, canary_percent
    )
    active = [e for e in active if e.status == "active" or shown_canary]
    levels = _backoff(state, language, turn_kind, industry, category, person_type)
    for number, level in enumerate(levels):
        last = number == len(levels) - 1
        pool = [
            e
            for e in active
            if _matches(e, level)
            and learning_situation.industry_allowed(e.situation, industry, sector, sector_ok=last)
            and not (exclude_contact and exclude_contact in (e.source_contacts or []))
            and not learning.never_learn(e.reply_text)
        ]
        if not pool:
            continue
        if query_embedding is None and embedder is not None and any(e.embedding for e in pool):
            got = await embedder([said])  # only asked when there is something to compare with
            query_embedding = got[0] if got else None

        def score(e: PiLearningExample, vector: list[float] | None = query_embedding) -> float:
            alike = similarity(said, e.person_text)
            if vector is not None and e.embedding and len(vector) == len(e.embedding):
                alike = max(alike, cosine(vector, e.embedding))
            own = 0.15 if industry and e.situation.get("industry") == industry else 0.0
            return alike + 0.05 * min(e.reward, 6) + own

        chosen: list[PiLearningExample] = []
        seen: set[str] = set()
        for example in sorted(pool, key=score, reverse=True):
            business = (example.source_contacts or [str(example.id)])[0]
            if business in seen:
                continue
            seen.add(business)
            chosen.append(example)
            if len(chosen) == k:
                break
        return chosen
    return []


async def touch(session: AsyncSession, examples: Iterable[PiLearningExample]) -> None:
    for example in examples:
        await session.execute(
            update(PiLearningExample)
            .where(PiLearningExample.id == example.id)
            .values(uses=PiLearningExample.uses + 1)
        )
