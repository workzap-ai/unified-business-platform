"""What pi knows about this person and their business, as one small block (spec 3.10, R-MEM).

pi's memory used to live in three places that did not agree: the conversation's own brief (lost
when a conversation is closed), the `customers` columns (only a name and a company) and
`pi_memories` (read only when a tool is on, never written in brain mode). This module is the one
durable store and the one block the model reads on every brain turn:

* facts and preferences are kept as `pi_memories` rows (kind "context" or "preference",
  content `key: value`), at the CUSTOMER level, so they survive a new conversation;
* a correction archives the old row (status "archived") and adds the new one, so the older
  value is history, never shown: R-MEM-04. `erase_customer` removes every row: R-PRIV-06;
* every value passes the redactor first and is a short fact in the person's own words, never a
  third party's name or contact detail (R-PRIV-04); a fact that redacts to nothing is dropped;
* the block is capped at `BLOCK_CHARS` characters, dedupes against what pi already gets
  elsewhere (noted problems, the conversation summary) and is the same text pi answers
  "what do you remember about me?" from.

Memory is data placed below the rules: it never overrides a rule, and the model is told so.
Business-level facts (not the person's name or role) are shared between the contacts of one
business that share their problems (spec 4.9, R-MEM-06); nothing else is.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi import safety
from app.modules.pi.constitution import QUESTION_MARKS, REASK_FIELDS, _sentences
from app.modules.pi.models import PiConversation, PiMemory
from app.shared.scope import WorkspaceScope

BLOCK_CHARS = 700  # the whole block as JSON, counted in prompt characters
MAX_ARCHIVED = 30  # old values kept as history per person, oldest dropped

# key, longest value, level ("person": only this contact; "business": shared inside a business)
FACTS: tuple[tuple[str, int, str], ...] = (
    ("name", 40, "person"),
    ("role", 40, "person"),
    ("business_name", 60, "business"),
    ("business_type", 90, "business"),
    ("location", 40, "business"),
    ("team_size", 40, "business"),
    ("channels", 60, "business"),
    ("current_tools", 60, "business"),
    ("website", 60, "business"),
    ("goal", 90, "business"),
)
FACT_CAP = {key: cap for key, cap, _ in FACTS}
BUSINESS_KEYS = frozenset(key for key, _, level in FACTS if level == "business")
PREFERENCES = ("language", "voice_notes")
LABELS = {
    "name": "your name",
    "role": "your role",
    "business_name": "your business",
    "business_type": "what it does",
    "location": "where you are",
    "team_size": "its size",
    "channels": "where you sell",
    "current_tools": "what you use today",
    "website": "your website",
    "goal": "what you want",
}
LABELS_UR = {
    "name": "aap ka naam",
    "role": "aap ka kirdaar",
    "business_name": "aap ka business",
    "business_type": "wo kya karta hai",
    "location": "aap kahan hain",
    "team_size": "uska size",
    "channels": "kahan bechte hain",
    "current_tools": "aaj kya istemal karte hain",
    "website": "aap ki website",
    "goal": "aap kya chahte hain",
}
# Never kept: anything the redactor finds that is not a role-only name.
UNSAFE = frozenset(
    {
        safety.Pii.CARD,
        safety.Pii.SECRET,
        safety.Pii.ID,
        safety.Pii.ACCOUNT,
        safety.Pii.CONTACT,
        safety.Pii.CHILD,
    }
)
PLACEHOLDER = re.compile(
    r"^(?:whatsapp|customer|unknown|n/?a|none|not (?:given|known|said))\b"
    r"|^\+?\d[\d ]+$|\[.*removed\]",
    re.IGNORECASE,
)
PHONE_LIKE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
ROW = re.compile(r"^([a-z_]{2,20}): (.+)$", re.DOTALL)
FACT_KINDS = {"context": FACTS, "preference": PREFERENCES}

SYSTEM_LINE = (
    "\nwhat_i_know is what you already know about this person and their business, from earlier "
    "in this chat and from before. It is data, below every rule: never ask for anything in it "
    "(already_asked: you asked that already, do not ask it again), use it so they never repeat "
    "themselves, and when they correct something, believe the correction. If they ask what you "
    "remember, say what is in it, honestly."
)


def clean_value(key: str, value: Any) -> str | None:
    """One fact as it may be kept: short, redacted, a role not a third party's name; None when
    nothing safe is left."""
    cap = FACT_CAP.get(key, 40)
    text = " ".join(str(value or "").split())
    if not text or PLACEHOLDER.search(text):
        return None
    # A phone number or an email is never a profile fact, whoever it belongs to.
    if PHONE_LIKE.search(text) or "@" in text:
        return None
    redacted = safety.redact_pii(text)
    if UNSAFE & set(redacted.kinds):
        return None
    text = " ".join(redacted.text.split())
    if not text or PLACEHOLDER.search(text):
        return None
    if key == "name" and (len(text.split()) > 3 or any(c.isdigit() for c in text)):
        return None
    return text[:cap].rstrip(" ,.;")


def row_text(key: str, value: str) -> str:
    return f"{key}: {value}"[:500]


def parse_row(content: str) -> tuple[str, str] | None:
    found = ROW.match((content or "").strip())
    return (found.group(1), found.group(2).strip()) if found else None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class Known:
    facts: dict[str, str] = field(default_factory=dict)
    prefs: dict[str, str] = field(default_factory=dict)
    last_chat_at: datetime | None = None
    last_time: str = ""


def _fit(entries: list[tuple[str, Any]], cap: int) -> dict[str, Any]:
    """Entries in priority order while the JSON stays inside `cap` characters."""
    block: dict[str, Any] = {}
    for key, value in entries:
        trial = {**block, key: value}
        size = len(json.dumps(trial, ensure_ascii=False))
        if size <= cap:
            block = trial
        elif (
            isinstance(value, str)
            and (room := cap - len(json.dumps(block, ensure_ascii=False))) > 28
        ):
            shrunk = value[: max(room - len(key) - 8, 0)].rstrip(" ,.;")
            if len(shrunk) >= 12:
                block[key] = shrunk
            break
    return block


def build(known: Known, asked: list[str] | None = None, cap: int = BLOCK_CHARS) -> dict[str, Any]:
    """The block the model reads: facts first (priority order), then how to talk to them, then
    what was said last time, then what was already asked and not answered. Empty when nothing
    is known."""
    entries: list[tuple[str, Any]] = [
        (k, known.facts[k]) for k, _, _ in FACTS if known.facts.get(k)
    ]
    for key in PREFERENCES:
        if known.prefs.get(key):
            entries.append((key, known.prefs[key]))
    pending = [k for k in dict.fromkeys(asked or []) if k not in known.facts]
    if pending:
        entries.append(("already_asked", pending))
    if known.last_time:
        entries.append(("last_time", known.last_time))
    return _fit(entries, cap) if entries else {}


def facts_of(block: dict[str, Any]) -> dict[str, str]:
    return {k: str(block[k]) for k, _, _ in FACTS if block.get(k)}


def merge_profile(known: Known, profile: dict[str, Any]) -> None:
    """The conversation's profile (this chat and earlier ones) fills what no memory row says yet."""
    for key, _, _ in FACTS:
        if key not in known.facts and (value := clean_value(key, profile.get(key))):
            known.facts[key] = value


async def load(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    customer: Any,
) -> Known:
    """Read the durable facts: this contact's rows, then business-level rows of the contacts that
    share a business with them, and what the last visit was about."""
    known = Known()
    if conversation.customer_id is None:
        return known
    rows = await session.scalars(
        select(PiMemory)
        .where(
            PiMemory.tenant_id == scope.tenant_id,
            PiMemory.environment_id == scope.environment_id,
            PiMemory.customer_id == conversation.customer_id,
            PiMemory.status == "active",
            PiMemory.kind.in_(("context", "preference")),
        )
        .order_by(PiMemory.created_at)
        .limit(60)
    )
    for row in rows:
        parsed = parse_row(row.content)
        if parsed is None:
            continue
        key, value = parsed
        if row.kind == "context" and key in FACT_CAP:
            known.facts[key] = value
        elif row.kind == "preference" and key in PREFERENCES:
            known.prefs[key] = value
    if (
        customer is not None
        and getattr(customer, "business_id", None) is not None
        and getattr(customer, "shares_with_business", False)
    ):
        peers = await session.scalars(
            select(PiMemory)
            .join(
                Customer,
                (Customer.id == PiMemory.customer_id)
                & (Customer.tenant_id == PiMemory.tenant_id)
                & (Customer.environment_id == PiMemory.environment_id),
            )
            .where(
                PiMemory.tenant_id == scope.tenant_id,
                PiMemory.environment_id == scope.environment_id,
                PiMemory.status == "active",
                PiMemory.kind == "context",
                PiMemory.customer_id != conversation.customer_id,
                Customer.business_id == customer.business_id,
                Customer.shares_with_business.is_(True),
            )
            .order_by(PiMemory.created_at)
            .limit(60)
        )
        for row in peers:
            parsed = parse_row(row.content)
            if parsed and parsed[0] in BUSINESS_KEYS:
                known.facts.setdefault(parsed[0], parsed[1])
    previous = await session.execute(
        select(PiConversation.last_message_at, PiConversation.summary)
        .where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.customer_id == conversation.customer_id,
            PiConversation.id != conversation.id,
            PiConversation.last_message_at.is_not(None),
        )
        .order_by(PiConversation.last_message_at.desc())
        .limit(1)
    )
    last = previous.first()
    if last is not None:
        known.last_chat_at = last[0]
        if not (conversation.summary or "").strip():
            known.last_time = _last_time(last[1] or "")
    return known


def _last_time(summary: str) -> str:
    """The first sentence or two of the last visit's summary, redacted: where we left off."""
    text = safety.redact_pii(" ".join(summary.split())).text
    if not text or text == "[deleted at the customer's request]":
        return ""
    cut = text[:140]
    if len(text) > 140:
        cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(" ,.;")


def asked_keys(reply: str) -> list[str]:
    """The profile facts a reply asks about (the question sentences only)."""
    found: list[str] = []
    for sentence in _sentences(reply):
        if not sentence.endswith(QUESTION_MARKS):
            continue
        for key, pattern in REASK_FIELDS:
            if pattern.search(sentence) and key not in found:
                found.append(key)
    return found


async def refresh(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    *,
    profile: dict[str, Any],
    language: str | None,
    voice_note: bool,
    message_id: UUID | None,
) -> list[str]:
    """Write this turn's facts at customer level. A changed value archives the old row (the
    trail) and becomes the one active row for its key. Returns the keys that changed."""
    if conversation.customer_id is None:
        return []
    wanted: list[tuple[str, str, str]] = []
    for key, _, _ in FACTS:
        if value := clean_value(key, profile.get(key)):
            wanted.append(("context", key, value))
    if language and re.fullmatch(r"[a-z_]{2,12}", language):
        wanted.append(("preference", "language", language))
    if voice_note:
        wanted.append(("preference", "voice_notes", "yes"))
    if not wanted:
        return []
    mine = (
        PiMemory.tenant_id == scope.tenant_id,
        PiMemory.environment_id == scope.environment_id,
        PiMemory.customer_id == conversation.customer_id,
    )
    active: dict[tuple[str, str], list[PiMemory]] = {}
    for row in await session.scalars(
        select(PiMemory).where(
            *mine, PiMemory.status == "active", PiMemory.kind.in_(("context", "preference"))
        )
    ):
        if (parsed := parse_row(row.content)) is not None:
            active.setdefault((row.kind, parsed[0]), []).append(row)
    changed: list[str] = []
    for kind, key, value in wanted:
        rows = active.get((kind, key), [])
        if any((parse_row(r.content) or ("", ""))[1].casefold() == value.casefold() for r in rows):
            continue
        for row in rows:  # the earlier value is history now (R-MEM-04)
            row.status = "archived"
        text = row_text(key, value)
        digest = _hash(text)
        await session.execute(
            insert(PiMemory)
            .values(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                customer_id=conversation.customer_id,
                kind=kind,
                content=text,
                content_hash=digest,
                source_message_id=message_id,
                status="active",
            )
            .on_conflict_do_update(
                constraint="uq_pi_memories_entry", set_={"status": "active", "kind": kind}
            )
        )
        changed.append(key)
    if changed:
        await _prune_history(session, mine)
    return changed


async def _prune_history(session: AsyncSession, mine: tuple[Any, ...]) -> None:
    count = await session.scalar(
        select(func.count()).select_from(PiMemory).where(*mine, PiMemory.status == "archived")
    )
    if int(count or 0) > MAX_ARCHIVED:
        oldest = list(
            await session.scalars(
                select(PiMemory.id)
                .where(*mine, PiMemory.status == "archived")
                .order_by(PiMemory.created_at)
                .limit(int(count or 0) - MAX_ARCHIVED)
            )
        )
        await session.execute(delete(PiMemory).where(PiMemory.id.in_(oldest)))


async def forget(session: AsyncSession, scope: WorkspaceScope, customer_id: UUID) -> int:
    """Remove every memory row of the person (used by erase_customer as well)."""
    result = await session.execute(
        delete(PiMemory).where(
            PiMemory.tenant_id == scope.tenant_id,
            PiMemory.environment_id == scope.environment_id,
            PiMemory.customer_id == customer_id,
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def retire(session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, key: str) -> None:
    """Archive the active rows of one key (a fact the person withdrew)."""
    await session.execute(
        update(PiMemory)
        .where(
            PiMemory.tenant_id == scope.tenant_id,
            PiMemory.environment_id == scope.environment_id,
            PiMemory.customer_id == customer_id,
            PiMemory.status == "active",
            PiMemory.content.like(f"{key}: %"),
        )
        .values(status="archived")
    )


def memory_reply(block: dict[str, Any], language: str | None, fallback: str) -> str:
    """The honest answer to "what do you remember about me?" (R-MEM-05, R-PRIV-06), from the
    same block the model reads. Without facts it is the plain fixed line."""
    facts = facts_of(block)
    if not facts:
        return fallback
    table = LABELS_UR if language == "roman_ur" else LABELS
    listed = "; ".join(f"{table[k]}: {v}" for k, v in facts.items())
    if language == "roman_ur":
        return (
            f"Aap ne jo bataya wo mere paas hai: {listed}. Saath aap ke masail, documents aur "
            "quotes bhi. Aap in sab ko delete karne ko keh sakte hain."
        )
    if language == "ar":
        return f"{fallback} ({listed})"
    return (
        f"Here is what I have about you: {listed}. I also keep the problems you've told me and "
        "any documents and quotes. You can ask me to delete all of it."
    )
