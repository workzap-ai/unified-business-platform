# ruff: noqa: E501  (the drafting prompt reads better in long lines)
"""Industry packs pi drafts for businesses that fit none of the 211 (pi Brain spec 8.5 job 5, 8.6).

When five different businesses describe themselves in similar words and no existing pack recognises
them, pi drafts a new pack from what they said and the kinds of problems they noted (never names or
numbers). The draft is stored as a proposal and is inert until a person acts:

* a person approves the listening sections (recognise, words, questions, problems): the pack then
  runs in shadow, counted but never shown, until 20 conversations scored at least as well as pi does
  without a pack (`learning_rules.pack_may_go_live`);
* a person separately approves the care sections (what pi refuses and protects). A pack never goes
  live without that approval, and the care text is the person's, not the model's.

A live learned pack adds the same kind of listening brief a built-in pack does, below the rules.
"""

import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi import industry_packs, learning, learning_rules, taxonomy
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearnedPack, PiLearningChange
from app.modules.pi.models import PiConversation
from app.modules.pi.problem_models import PiProblem
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("app.pi.learning")

DRAFT_EVERY = timedelta(days=7)
MAX_LABELS = 12
MAX_TERMS = 24
DIGITS = re.compile(r"\d")
PERSONAL = re.compile(r"@|https?://|www\.", re.IGNORECASE)


class PackProblem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    category: str = ""
    subtype: str = Field(default="", max_length=60)
    phrase: str = Field(default="", max_length=160)


class PackDraft(BaseModel):
    """What the model is asked to write. Every field is checked before anything is stored."""

    model_config = ConfigDict(extra="ignore")
    name: str = Field(default="", max_length=100)
    signals: list[str] = Field(default_factory=list)
    vocabulary: dict[str, str] = Field(default_factory=dict)
    questions: dict[str, list[str]] = Field(default_factory=dict)
    problems: list[PackProblem] = Field(default_factory=list)
    shape_facts: list[str] = Field(default_factory=list)
    care: list[str] = Field(default_factory=list)
    scope_rule: str = Field(default="", max_length=600)


Writer = Callable[[dict[str, Any]], Awaitable[PackDraft | None]]

SYSTEM = """You draft a listening guide for pi, Workzap's WhatsApp AI, for one kind of business that
has no guide yet. You are given how several different owners described their business and the kinds
of problems they raised. Write: a short name for the trade; 8 to 20 signals (words and phrases owners
of this trade use, in English and Roman Urdu where natural); up to 10 vocabulary entries (term: plain
meaning); questions grouped by area (stock, sales, cash, staff, operations, customers, systems),
each ONE short plain question, never about prices, cards, passwords or ID numbers; up to 8 problems
as {category, subtype, phrase} with category one of the allowed categories; up to 6 shape_facts (what
to learn only from what they say); care: things pi must be careful about in this trade (never advice,
never regulated opinions); scope_rule: one short paragraph on what pi notes and what it refuses.
Use no names, numbers, links or contact details. Do not pitch Workzap products. Plain words."""


# --- clustering ----------------------------------------------------------------------------------


def label_key(label: str) -> str:
    """A stable key for similar descriptions: the three most telling words, sorted."""
    words = {
        w
        for w in industry_packs._normal(label).split()
        if len(w) >= 4 and w not in industry_packs.NAME_STOP
    }
    return " ".join(sorted(words, key=lambda w: (-len(w), w))[:3]) if len(words) >= 1 else ""


def clusters(
    rows: list[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """(customer, label) pairs with no pack -> clusters of at least five different businesses."""
    by_key: dict[str, dict[str, Any]] = defaultdict(lambda: {"customers": set(), "labels": []})
    for customer, label in rows:
        key = label_key(label)
        if not key:
            continue
        by_key[key]["customers"].add(customer)
        if label not in by_key[key]["labels"]:
            by_key[key]["labels"].append(label)
    return {
        key: {"customers": sorted(c["customers"]), "labels": c["labels"][:MAX_LABELS]}
        for key, c in by_key.items()
        if learning_rules.should_draft_pack(len(c["customers"]))
    }


def clean_text(text: str, limit: int = 160) -> str | None:
    """A label or term that is safe to learn from, or None."""
    said = " ".join((text or "").split())[:limit]
    if not said or DIGITS.search(said) or PERSONAL.search(said) or learning.never_learn(said):
        return None
    return said


# --- gathering evidence --------------------------------------------------------------------------


async def unclassified(session: AsyncSession, scope: WorkspaceScope) -> list[tuple[str, str]]:
    """(customer id, how they described the business) for customers no pack recognises."""
    rows = await session.execute(
        select(PiConversation.customer_id, PiConversation.service_brief).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.customer_id.is_not(None),
        )
    )
    found: dict[str, str] = {}
    for customer_id, brief in rows:
        profile = (brief or {}).get("customer_profile") or {}
        label = clean_text(str(profile.get("business_type") or profile.get("industry") or ""), 120)
        if label and str(customer_id) not in found:
            found[str(customer_id)] = label
    if not found:
        return []
    classified = set(
        await session.scalars(
            select(Customer.id).where(
                Customer.tenant_id == scope.tenant_id,
                Customer.environment_id == scope.environment_id,
                Customer.industry_primary.is_not(None),
                Customer.industry_primary != "unclassified",
            )
        )
    )
    return [
        (cid, label)
        for cid, label in found.items()
        if UUID(cid) not in classified and not industry_packs.detect([label]).industries
    ]


async def evidence_for(
    session: AsyncSession, scope: WorkspaceScope, cluster: dict[str, Any]
) -> dict[str, Any]:
    """What the model sees: descriptions and problem kinds, never names, numbers or contacts."""
    ids = [UUID(c) for c in cluster["customers"]]
    problems = await session.execute(
        select(PiProblem.category, PiProblem.subtype, PiProblem.title).where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
            PiProblem.customer_id.in_(ids),
        )
    )
    seen: set[tuple[str, str]] = set()
    kinds: list[dict[str, str]] = []
    for category, subtype, title in problems:
        text = clean_text(title, 100)
        if text is None or (category, text) in seen:
            continue
        seen.add((category, text))
        kinds.append({"category": category, "subtype": subtype or "", "title": text})
    return {
        "descriptions": cluster["labels"],
        "businesses": len(ids),
        "problems": kinds[:30],
        "allowed_categories": sorted(taxonomy.KEYS),
    }


# --- checking the draft --------------------------------------------------------------------------


def one_question(text: str) -> str | None:
    said = clean_text(text, 200)
    if said is None or said.count("?") != 1 or not said.endswith("?"):
        return None
    if re.search(r"\b(price|cost|card|password|otp|cnic|passport)\b", said, re.IGNORECASE):
        return None
    return said


def validated(draft: PackDraft) -> dict[str, Any] | None:
    """The pack content to store, with everything unsafe dropped; None when too little is left."""
    name = clean_text(draft.name, 100)
    signals = [s for s in (clean_text(x, 60) for x in draft.signals) if s][:MAX_TERMS]
    vocabulary = {
        t: m
        for t, m in (
            (clean_text(k, 60), clean_text(v, 160)) for k, v in list(draft.vocabulary.items())[:10]
        )
        if t and m
    }
    questions: dict[str, list[str]] = {}
    for area, asked in draft.questions.items():
        good = [q for q in (one_question(x) for x in asked[:6]) if q]
        if good and clean_text(area, 30):
            questions[area.strip().lower()[:30]] = good
    problems = [
        {"category": p.category, "subtype": p.subtype, "phrase": phrase}
        for p in draft.problems[:8]
        if p.category in taxonomy.KEYS and (phrase := clean_text(p.phrase, 160))
    ]
    shape = [s for s in (clean_text(x, 160) for x in draft.shape_facts[:6]) if s]
    care = [s for s in (clean_text(x, 240) for x in draft.care[:6]) if s]
    scope_rule = clean_text(draft.scope_rule, 600) or ""
    if not name or len(signals) < 5 or not questions:
        return None
    return {
        "key": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60],
        "name": name,
        "kind": "industry",
        "signals": signals,
        "vocabulary": vocabulary,
        "questions": questions,
        "problems": problems,
        "shape_facts": shape,
        "care": care,
        "scope_rule": scope_rule,
    }


# --- drafting ------------------------------------------------------------------------------------


def make_writer(settings: Any, http: Any, scope: WorkspaceScope) -> Writer | None:
    """A drafting function over the platform's model, or None when there is no HTTP client."""
    if http is None:
        return None

    async def write(evidence: dict[str, Any]) -> PackDraft | None:
        import json

        from app.ai.manager import LLMManager
        from app.ai.types import Message
        from app.ai.usage import NullUsageStore

        try:
            manager = LLMManager(settings, http, usage=NullUsageStore())
            result = await manager.complete_structured(
                scope,
                PackDraft,
                alias="balanced",
                purpose="pi_pack_draft",
                messages=[
                    Message.system(SYSTEM),
                    Message.user(json.dumps(evidence, ensure_ascii=False)),
                ],
                temperature=0.3,
                max_tokens=3000,
            )
        except Exception:  # noqa: BLE001 - drafting is an extra, never a reason to fail a run
            logger.warning("pi_pack_draft_failed", exc_info=True)
            return None
        return result.value if isinstance(result.value, PackDraft) else None

    return write


async def draft_new(
    session: AsyncSession,
    scope: WorkspaceScope,
    writer: Writer | None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Draft packs for new clusters. At most one run a week, one draft per cluster, ever."""
    now = now or datetime.now(UTC)
    counts = {"clusters": 0, "drafted": 0, "rejected": 0}
    where = (
        PiLearnedPack.tenant_id == scope.tenant_id,
        PiLearnedPack.environment_id == scope.environment_id,
    )
    last = await session.scalar(
        select(PiLearnedPack.created_at).where(*where).order_by(PiLearnedPack.created_at.desc())
    )
    if writer is None or (last is not None and now - last < DRAFT_EVERY):
        return counts
    existing = {k for k in await session.scalars(select(PiLearnedPack.key).where(*where))}
    found = clusters(await unclassified(session, scope))
    counts["clusters"] = len(found)
    for key, cluster in found.items():
        if f"cluster:{key}" in {
            (p.evidence or {}).get("cluster")
            for p in await session.scalars(select(PiLearnedPack).where(*where))
        }:
            continue
        evidence = await evidence_for(session, scope, cluster)
        content = validated(await writer(evidence) or PackDraft())
        if (
            content is None
            or content["key"] in existing
            or content["key"] in industry_packs.load_packs()
        ):
            counts["rejected"] += 1
            continue
        pack = PiLearnedPack(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            key=content["key"],
            title=content["name"],
            content=content,
            evidence={
                "cluster": f"cluster:{key}",
                "businesses": len(cluster["customers"]),
                "descriptions": cluster["labels"],
                "shadow_ids": [],
            },
            status="draft",
        )
        session.add(pack)
        await session.flush()
        session.add(
            PiLearningChange(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                kind="pack_drafted",
                risk="high",
                target_id=pack.id,
                before={},
                after={"status": "draft", "title": pack.title},
                evidence={"businesses": len(cluster["customers"])},
                status="review",
                reason="five businesses fit no pack: a person decides",
            )
        )
        existing.add(content["key"])
        counts["drafted"] += 1
    await session.flush()
    return counts


# --- people decide -------------------------------------------------------------------------------


def _log(
    scope: WorkspaceScope, pack: PiLearnedPack, kind: str, before: str, by: UUID | None
) -> PiLearningChange:
    return PiLearningChange(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        kind=kind,
        risk="high",
        target_id=pack.id,
        before={"status": before},
        after={"status": pack.status, "care_approved": pack.care_approved},
        status="live" if pack.status == "live" else pack.status,
        reason=kind.replace("_", " "),
        decided_by=by,
    )


async def approve_listening(
    session: AsyncSession, scope: WorkspaceScope, pack: PiLearnedPack, by: UUID | None
) -> PiLearnedPack:
    """The listening sections are fine: the pack starts its shadow run."""
    if pack.status != "draft":
        raise BusinessRuleViolation("PACK_NOT_DRAFT", "Only a draft can be approved", 409)
    pack.status, pack.decided_by = "shadow", by
    session.add(_log(scope, pack, "pack_listening_approved", "draft", by))
    await session.flush()
    return pack


async def approve_care(
    session: AsyncSession,
    scope: WorkspaceScope,
    pack: PiLearnedPack,
    by: UUID | None,
    care: list[str],
    scope_rule: str,
) -> PiLearnedPack:
    """A person writes or confirms the care sections. Their text replaces the model's."""
    if pack.status in ("rejected", "retired"):
        raise BusinessRuleViolation("PACK_CLOSED", "This pack is closed", 409)
    items = [s for s in (clean_text(x, 240) for x in care) if s]
    if not items or not clean_text(scope_rule, 600):
        raise BusinessRuleViolation(
            "CARE_REQUIRED", "Write at least one care point and a scope rule", 422
        )
    pack.content = {**pack.content, "care": items, "scope_rule": clean_text(scope_rule, 600)}
    pack.care_approved = True
    session.add(_log(scope, pack, "pack_care_approved", pack.status, by))
    await session.flush()
    return pack


async def close(
    session: AsyncSession,
    scope: WorkspaceScope,
    pack: PiLearnedPack,
    by: UUID | None,
    status: str,
) -> PiLearnedPack:
    before = pack.status
    pack.status, pack.decided_by = status, by
    session.add(_log(scope, pack, f"pack_{status}", before, by))
    await session.flush()
    return pack


# --- shadow and live -----------------------------------------------------------------------------


def matches(pack: PiLearnedPack, text: str) -> bool:
    """Whether what the person said fits this pack (two of its signals, or one rare term)."""
    padded = f" {industry_packs._normal(text)} "
    terms = {industry_packs._normal(t) for t in pack.content.get("signals", [])}
    terms |= {industry_packs._normal(t) for t in pack.content.get("vocabulary", {})}
    hits = [t for t in terms if len(t) >= 3 and f" {t} " in padded]
    return len(hits) >= 2


async def note_shadow(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, text: str
) -> None:
    """Count (never show) a conversation a shadow pack would have recognised."""
    packs = await session.scalars(
        select(PiLearnedPack).where(
            PiLearnedPack.tenant_id == scope.tenant_id,
            PiLearnedPack.environment_id == scope.environment_id,
            PiLearnedPack.status == "shadow",
        )
    )
    for pack in packs:
        ids: list[str] = list((pack.evidence or {}).get("shadow_ids") or [])
        if str(conversation_id) not in ids and matches(pack, text):
            pack.evidence = {**pack.evidence, "shadow_ids": [*ids, str(conversation_id)][-200:]}


async def promote_shadows(
    session: AsyncSession, scope: WorkspaceScope, now: datetime | None = None
) -> int:
    """Shadow packs with a human-approved care section, 20 conversations and a score at least as
    good as pi without a pack go live. Anything else keeps waiting."""
    now = now or datetime.now(UTC)
    gone = 0
    packs = list(
        await session.scalars(
            select(PiLearnedPack).where(
                PiLearnedPack.tenant_id == scope.tenant_id,
                PiLearnedPack.environment_id == scope.environment_id,
                PiLearnedPack.status == "shadow",
                PiLearnedPack.care_approved.is_(True),
            )
        )
    )
    window = list(
        await session.scalars(
            select(PiExperience).where(
                PiExperience.tenant_id == scope.tenant_id,
                PiExperience.environment_id == scope.environment_id,
                PiExperience.scored_at >= now - timedelta(days=28),
            )
        )
    )
    for pack in packs:
        ids = set((pack.evidence or {}).get("shadow_ids") or [])
        inside = [r.reward for r in window if str(r.conversation_id) in ids]
        outside = [r.reward for r in window if str(r.conversation_id) not in ids]
        shadow = sum(inside) / len(inside) if inside else 0.0
        fallback = sum(outside) / len(outside) if outside else 0.0
        if learning_rules.pack_may_go_live("Recognise", len(ids), shadow, fallback):
            pack.status = "live"
            pack.evidence = {**pack.evidence, "shadow_score": round(shadow, 2)}
            session.add(_log(scope, pack, "pack_live", "shadow", None))
            gone += 1
    await session.flush()
    return gone


async def live_brief(
    session: AsyncSession, scope: WorkspaceScope, text: str, max_chars: int = 1800
) -> str:
    """The listening brief of the live learned pack this person's words fit, or ''."""
    packs = await session.scalars(
        select(PiLearnedPack).where(
            PiLearnedPack.tenant_id == scope.tenant_id,
            PiLearnedPack.environment_id == scope.environment_id,
            PiLearnedPack.status == "live",
            PiLearnedPack.care_approved.is_(True),
        )
    )
    for pack in packs:
        if matches(pack, text):
            return industry_packs.brief(pack.content, max_chars=max_chars)
    return ""
