"""Noting, sorting and showing problems (pi Brain spec, Part 4 and 3.3 to 3.7).

The model proposes `ProblemOp`s in its turn; this module checks them (`check_ops`), applies them
to the database (`apply_ops`), reads the noted problems back for the prompt (`noted_context`)
and builds the S4 summary (`summary_message`). Records keep the person's own words, never
names or card, phone or ID numbers (redacted first), and every change is a revision.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import business, taxonomy
from app.modules.pi.language import amount_value, date_estimate
from app.modules.pi.problem_models import (
    PiProblem,
    PiProblemGroup,
    PiProblemLink,
    PiProblemRevision,
)
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

TITLE_WORDS = 8
SUMMARY_LINE_WORDS = 10
SUMMARY_FULL_LIST = 12  # more than this and the summary shows two lines per group
SUMMARY_TRIGGER = 7  # problems since the last summary that make pi offer one
MAX_USER_WORDS = 6
FIELD_LIMITS = {"summary": 400, "workaround": 400, "trigger": 200, "who_notices": 200}

# Blame and judgement words never go in a title (R, spec 4.3).
BLAME = re.compile(
    r"\b(?:lazy|thief|thieves|useless|stupid|idiot|cheat|cheats|liar|corrupt|incompetent|"
    r"chor|nikamma|nikammay|kamchor|bewakoof)\b",
    re.IGNORECASE,
)
SOLUTION_TITLE = re.compile(
    r"\b(?:we need|need an?|want an?|should (?:use|buy)|get an?)\b.*\b(?:app|software|system|"
    r"website|tool|dashboard|erp|pos)\b",
    re.IGNORECASE,
)

# The person asking pi to prepare the document or quote is a decision, never a business problem
# (a real run noted "Document and quote creation is slow" from "yes, prepare the document").
DOCUMENT_REQUEST = re.compile(
    r"\b(?:prepare|send|make|give|get|create|bana(?:o|iye|dein|do|den)?|banwa(?:o|dein|do|iye)?|"
    r"bhej(?:o|iye|dein|do)?|tayyar)\b.{0,40}\b(?:document|quote|quotation|proposal)\b"
    r"|\b(?:document|quote|quotation|proposal)\b.{0,40}\b(?:bana(?:o|iye|dein|do|den)?|banwa|"
    r"bhej(?:o|iye|dein|do)?|chahiye|tayyar)\b",
    re.IGNORECASE,
)


def is_document_request(words: list[str]) -> bool:
    return bool(DOCUMENT_REQUEST.search(" ".join(words)))


REDACTIONS = (
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card number removed]"),
    (re.compile(r"\b784-\d{4}-\d{7}-\d\b"), "[ID removed]"),
    (re.compile(r"\b\d{5}-\d{7}-\d\b"), "[ID removed]"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{10,}\b"), "[account removed]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email removed]"),
    (re.compile(r"(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)"), "[phone removed]"),
)

LINK_TYPES = taxonomy.LINK_TYPES


class ProblemNote(BaseModel):
    """What the model says about one problem. Empty means not said (an update keeps the old)."""

    model_config = ConfigDict(extra="ignore")
    title: str = ""  # English, <= 8 words, starts with the subject, no names or blame
    title_local: str = ""  # the same in the person's language
    user_words: list[str] = Field(default_factory=list)  # their own words, verbatim
    summary: str = ""
    category: str = ""
    subtype: str = ""
    where: list[str] = Field(default_factory=list)
    of_total: str = ""  # "2 of 4 shops"
    frequency: str = ""  # daily weekly monthly seasonal once unknown
    frequency_text: str = ""
    since_text: str = ""
    trigger: str = ""
    impact_types: list[str] = Field(default_factory=list)
    money_text: str = ""
    currency: str = ""  # PKR, AED or CAD, from where they are or what they said (R-LANG-05)
    time_text: str = ""  # "two hours every day"
    people_affected: str = ""  # "all cashiers", "about 10 customers a week"
    products: str = ""  # "best-sellers"
    channel: str = ""  # "in-store", "WhatsApp orders"
    frequency_pattern: str = ""  # "worse on weekends"
    severity_stated: str = ""  # only from their words: low medium high critical
    workaround: str = ""
    systems: list[str] = Field(default_factory=list)
    who_notices: str = ""
    believes_cause: str = ""
    requested_solution: str = ""
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)


class ProblemOp(BaseModel):
    """One change to the noted problems. `ref` is a problem's short ref from noted_problems."""

    model_config = ConfigDict(extra="ignore")
    op: Literal["create", "update", "merge", "split", "link", "withdraw", "rename_group"]
    ref: str = ""  # update, split, withdraw: the problem; merge: the one kept; link: from
    refs: list[str] = Field(default_factory=list)  # merge: the duplicates folded into ref
    to: str = ""  # link: the other problem
    link_type: str = ""
    note: ProblemNote | None = None  # create and update
    notes: list[ProblemNote] = Field(default_factory=list)  # split: the new problems
    reason: str = ""  # update: "correction" or "enrichment"
    name: str = ""  # rename_group: ref is the category key
    confidence: float = Field(default=0.6, ge=0, le=1)  # link


def tolerate_ops(raw: Any) -> list[Any]:
    """Keep only the ops that parse, so one bad op never costs the customer their reply."""
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    kept: list[Any] = []
    for item in raw[:12]:
        if isinstance(item, ProblemOp):
            kept.append(item)
            continue
        if not isinstance(item, dict):
            continue
        try:
            ProblemOp.model_validate(item)
        except ValueError:
            continue
        kept.append(item)
    return kept


def redact(text: str) -> tuple[str, bool]:
    """Remove card, ID, account, email and phone patterns; also says whether anything changed."""
    changed = False
    for pattern, replacement in REDACTIONS:
        text, count = pattern.subn(replacement, text)
        changed = changed or bool(count)
    return text, changed


def _tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z\u0600-\u06ff]{3,}", title.lower())}


def same_symptom(a: str, b: str, threshold: float = 0.8) -> bool:
    """Two titles that say the same thing in nearly the same words (spec 4.4, merge)."""
    left, right = _tokens(a), _tokens(b)
    if not (left and right):
        return False
    if len(left & right) / len(left | right) >= threshold:
        return True
    # One title is the other plus a qualifier ("running out" / "running out in shops"): the same
    # symptom told twice, which the summary must not list as two problems.
    smaller, larger = sorted((left, right), key=len)
    return len(smaller) >= 3 and smaller <= larger


GENERIC_TOKENS = frozenset(
    "problem problems issue issues customer customers business orders order sales sale kam hai "
    "hain nahi mein that this with from have when they them what about very more less".split()
)


def facet_overlap(existing: PiProblem, title: str, user_words: list[str] | None = None) -> bool:
    """The same symptom told with other words (spec 4.3, the facet rule with the word overlap the
    owner approved): three content words in common, or two that are half of the shorter one's, in
    any category, because the model files "price asked, then silence" under sales, customers and
    marketing in turn."""
    old = _tokens(" ".join([existing.title, *[str(w) for w in existing.user_words or []]]))
    new = _tokens(" ".join([title, *(user_words or [])]))
    old = {w for w in old if len(w) >= 4 and w not in GENERIC_TOKENS}
    new = {w for w in new if len(w) >= 4 and w not in GENERIC_TOKENS}
    common = old & new
    return len(common) >= 3 or (
        len(common) >= 2 and len(common) / max(1, min(len(old), len(new))) >= 0.5
    )


def json_safe(value: Any) -> Any:
    """`value` as something a JSONB column can store (UUIDs, dates and decimals become text)."""
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, datetime) or hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [json_safe(v) for v in value]
    return value


def short_ref(problem_id: UUID) -> str:
    return str(problem_id)[:8]


def clean_title(title: str) -> str:
    return " ".join(title.split()[:TITLE_WORDS]).strip(" .,:;-")


def title_problem(title: str) -> str | None:
    """Why a title is not allowed, or None."""
    words = title.split()
    if not words:
        return "the title is empty"
    if len(words) > TITLE_WORDS:
        return f'the title "{title}" is over {TITLE_WORDS} words'
    if BLAME.search(title):
        return f'the title "{title}" blames someone: describe the symptom'
    if SOLUTION_TITLE.search(title):
        return f'the title "{title}" is a solution: note the problem it would fix'
    return None


# Words that make a short message a problem ("udhaar", "late", "chori", "no stock"). A message of a
# few words without one is a fact ("60 bhainsein"), and no problem is made of it.
PROBLEM_CUE = re.compile(
    r"masla|masle|masail|problem|issue|complain|shikayat|nahi|nahin|nhi|\bno\b|\bnot\b|kam\b|"
    r"zyada|jyada|late|delay|dair|ghalat|galat|gadbad|ghalti|mistake|error|loss|nuksan|nuqsan|"
    r"udhaar|udhar|chori|theft|stolen|miss|khatam|expire|waste|kharab|damage|tang|mushkil|pareshan|"
    r"wapas|return|refund|jhagra|dispute|short|slow|dheela|band\b|down\b|bohat|bahut|\bcan'?t\b|"
    r"\bhard\b|difficult|confus|stuck|fail|\bwrong\b|\blow\b|bar bar|roz|hamesha|always|never",
    re.IGNORECASE,
)
THIN_MESSAGE_WORDS = 4


def thin_message(said: str) -> bool:
    """A few words with nothing in them that goes wrong: a fact, not a problem."""
    words = (said or "").split()
    return (
        bool(words)
        and len(words) <= THIN_MESSAGE_WORDS
        and not PROBLEM_CUE.search(said)
        and not is_document_request(words)
    )


def check_ops(
    ops: list[ProblemOp], known_refs: set[str], noted_in_reply: bool, said: str = ""
) -> str | None:
    """What is wrong with the model's ops, for a rewrite, or None when they can go through."""
    issues: list[str] = []
    for op in ops:
        if op.op == "create":
            note = op.note
            if note is None or not note.title.strip():
                issues.append("a create op has no title")
                continue
            if thin_message(said):
                issues.append(
                    f'"{note.title}" is not something they said: a short message with no problem '
                    "in it makes no problem record, so ask what is going wrong instead"
                )
            if (why := title_problem(note.title)) is not None:
                issues.append(why)
            if not note.user_words:
                issues.append(f'"{note.title}" has no user_words (their own words, verbatim)')
            if not note.category.strip():
                issues.append(f'"{note.title}" has no category')
            if is_document_request(note.user_words):
                issues.append(
                    f'"{note.title}" is their request for the document or quote, not a problem: '
                    "do not note it"
                )
            if Decimal(str(note.confidence)) < taxonomy.CONFIRM_BELOW and not noted_in_reply:
                issues.append(
                    f'"{note.title}" has low confidence: ask one question to confirm it first'
                )
        elif op.op in ("update", "withdraw", "split") and op.ref not in known_refs:
            issues.append(f'{op.op} refers to an unknown problem ref "{op.ref}"')
        elif op.op == "update" and op.note is not None and op.note.title.strip():
            if (why := title_problem(op.note.title)) is not None:
                issues.append(why)
        elif op.op == "merge":
            if op.ref not in known_refs or not op.refs or any(r not in known_refs for r in op.refs):
                issues.append("merge needs a kept ref and the duplicate refs, all known")
        elif op.op == "link" and (op.ref not in known_refs or op.to not in known_refs):
            issues.append("link needs two known refs")
        if op.op == "split" and len(op.notes) < 2:
            issues.append("split needs at least two new problems")
        if op.op == "split":
            for part in op.notes:
                if (why := title_problem(part.title)) is not None:
                    issues.append(why)
                elif not part.user_words:
                    issues.append(f'"{part.title}" has no user_words (their own words, verbatim)')
    return "; ".join(issues) if issues else None


def scope_class(where: list[str], of_total: str) -> str:
    """all / most / some / one / unknown, for the severity score."""
    lowered = of_total.lower()
    if re.search(r"\b(?:all|every|sab|har)\b", lowered):
        return "all"
    if re.search(r"\bmost\b", lowered):
        return "most"
    ratio = re.search(r"(\d+)\s*(?:of|out of)\s*(\d+)", lowered)
    if ratio:
        part, total = int(ratio.group(1)), max(int(ratio.group(2)), 1)
        if part >= total:
            return "all"
        if part == 1:
            return "one"
        return "most" if part / total > 0.5 else "some"
    if len(where) == 1:
        return "one"
    return "some" if len(where) > 1 else "unknown"


def _words(values: list[str]) -> tuple[list[str], bool]:
    out: list[str] = []
    changed = False
    for value in values[:MAX_USER_WORDS]:
        cleaned, did = redact(str(value).strip()[:500])
        changed = changed or did
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out, changed


def _snake(value: str) -> str:
    return value if re.fullmatch(r"[a-z0-9_]{1,60}", value or "") else ""


def _frequency(note: ProblemNote) -> str:
    return note.frequency if note.frequency in taxonomy.FREQUENCIES else "unknown"


@dataclass
class Applied:
    created: list[PiProblem] = field(default_factory=list)
    updated: list[PiProblem] = field(default_factory=list)
    merged: list[PiProblem] = field(default_factory=list)
    split: list[PiProblem] = field(default_factory=list)
    withdrawn: list[PiProblem] = field(default_factory=list)
    links: list[PiProblemLink] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    @property
    def touched(self) -> set[UUID]:
        every = [*self.created, *self.updated, *self.merged, *self.split, *self.withdrawn]
        return {p.id for p in every}


class ProblemBook:
    """The problems of one customer's business, for one conversation turn."""

    def __init__(
        self, session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, language: str
    ) -> None:
        self.session, self.scope, self.customer_id = session, scope, customer_id
        self.language = language
        self.problems = WorkspaceRepository(session, PiProblem, scope)
        self.groups = WorkspaceRepository(session, PiProblemGroup, scope)

    async def active(self) -> list[PiProblem]:
        rows = await self.session.scalars(
            self.problems.select()
            .where(
                PiProblem.customer_id == self.customer_id,
                PiProblem.status.in_(taxonomy.ACTIVE),
            )
            .order_by(PiProblem.number)
        )
        return list(rows)

    async def by_ref(self) -> dict[str, PiProblem]:
        return {short_ref(p.id): p for p in await self.active()}

    async def _next_number(self) -> int:
        top = await self.session.scalar(
            select(func.max(PiProblem.number)).where(
                PiProblem.tenant_id == self.scope.tenant_id,
                PiProblem.environment_id == self.scope.environment_id,
                PiProblem.customer_id == self.customer_id,
            )
        )
        return int(top or 0) + 1

    async def group_for(self, category: str) -> PiProblemGroup:
        found = await self.groups.find(
            PiProblemGroup.customer_id == self.customer_id, PiProblemGroup.category == category
        )
        if found is not None:
            return found
        return await self.groups.add(
            self.groups.new(
                customer_id=self.customer_id,
                category=category,
                name=taxonomy.label(category, "en"),
            )
        )

    async def _revise(self, problem: PiProblem, diff: dict[str, Any], reason: str, by: str) -> None:
        await self.session.flush()
        self.session.add(
            PiProblemRevision(
                tenant_id=self.scope.tenant_id,
                environment_id=self.scope.environment_id,
                problem_id=problem.id,
                revision=problem.revision,
                diff=diff,
                reason=reason,
                by=by,
            )
        )

    def _score(self, problem: PiProblem) -> None:
        impact = (problem.impact or {}).get("types") or []
        scope = scope_class(
            (problem.scope or {}).get("where") or [], (problem.scope or {}).get("of_total") or ""
        )
        frequency = (problem.frequency or {}).get("normalised") or "unknown"
        score = taxonomy.severity_score(list(impact), frequency, scope, problem.severity_stated)
        problem.severity_score = score
        problem.severity_inferred = taxonomy.severity_band(score)

    async def create(
        self, note: ProblemNote, message_id: UUID | None, conversation_id: UUID | None
    ) -> tuple[PiProblem, bool]:
        """A new problem, or (when the same title is already noted) its enrichment."""
        title = clean_title(note.title)
        category_now = taxonomy.normalise_category(note.category.strip())
        for existing in await self.active():
            same = existing.title.casefold() == title.casefold()
            alike = existing.category == category_now and same_symptom(existing.title, title)
            # One symptom with several facets is one problem (spec 4.3): the same category and
            # sub-type is the same symptom, whatever words the model chose for the title.
            subtype_now = _snake(note.subtype)
            facet = bool(subtype_now) and (
                existing.category == category_now and existing.subtype == subtype_now
            )
            # Only across categories: the same category keeps the sub-type rule above, and two
            # problems of one category the person (or a reviewer) may merge by hand stay apart.
            overlap = existing.category != category_now and facet_overlap(
                existing, title, [str(w) for w in note.user_words or []]
            )
            if same or alike or facet or overlap:
                # The first title stands: a second wording of the same symptom adds detail, it
                # never renames the problem the person already saw confirmed.
                await self.update(
                    existing,
                    note.model_copy(update={"title": "", "title_local": ""}),
                    "enrichment",
                    message_id,
                )
                return existing, False
        words, redacted = _words(note.user_words)
        category = taxonomy.normalise_category(note.category.strip())
        tags = [t[:40] for t in note.tags[:8]]
        if category == taxonomy.OTHER and "taxonomy_review" not in tags:
            tags.append("taxonomy_review")
        group = await self.group_for(category)
        problem = self.problems.new(
            customer_id=self.customer_id,
            conversation_id=conversation_id,
            group_id=group.id,
            number=await self._next_number(),
            title=title,
            title_local=note.title_local.strip()[:200],
            summary=note.summary.strip()[: FIELD_LIMITS["summary"]],
            user_words=words,
            category=category,
            subtype=_snake(note.subtype),
            tags=tags,
            scope={
                "where": [w[:80] for w in note.where[:8]],
                "of_total": note.of_total[:80],
                "products": note.products[:120],
                "channel": note.channel[:60],
            },
            frequency={
                "text": note.frequency_text[:120],
                "normalised": _frequency(note),
                "pattern": note.frequency_pattern[:120],
            },
            since=date_estimate(note.since_text, datetime.now(UTC).date())
            if note.since_text
            else {"text": ""},
            trigger=note.trigger.strip()[: FIELD_LIMITS["trigger"]],
            impact={
                "types": [t for t in note.impact_types if t in taxonomy.IMPACT_TYPES],
                "money_text": note.money_text[:120],
                "money_value": amount_value(note.money_text),
                "currency": note.currency.strip().upper()[:3],
                "time_text": note.time_text[:120],
                "people_affected": note.people_affected[:120],
            },
            severity_stated=note.severity_stated
            if note.severity_stated in taxonomy.SEVERITIES
            else "unknown",
            current_workaround=note.workaround.strip()[: FIELD_LIMITS["workaround"]],
            systems_mentioned=[s[:60] for s in note.systems[:8]],
            who_notices=note.who_notices.strip()[: FIELD_LIMITS["who_notices"]],
            person_believes_cause=redact(note.believes_cause.strip()[:300])[0],
            requested_solution=redact(note.requested_solution.strip()[:300])[0],
            status="draft",
            confidence=Decimal(str(round(note.confidence, 2))),
            source_message_ids=[str(message_id)] if message_id else [],
            revision=1,
            pii_redacted=redacted,
            language=self.language,
        )
        self._score(problem)
        await self.problems.add(problem)
        await self._revise(problem, {"title": [None, problem.title]}, "created", "pi")
        return problem, True

    async def update(
        self, problem: PiProblem, note: ProblemNote, reason: str, message_id: UUID | None
    ) -> bool:
        """Apply what the note says; returns whether anything changed."""
        diff: dict[str, Any] = {}

        def put(name: str, value: Any) -> None:
            if getattr(problem, name) != value:
                # the revision diff is stored as JSON: a category change carries a group UUID
                diff[name] = [json_safe(getattr(problem, name)), json_safe(value)]
                setattr(problem, name, value)

        if note.title.strip():
            put("title", clean_title(note.title))
        if note.title_local.strip():
            put("title_local", note.title_local.strip()[:200])
        if note.summary.strip():
            put("summary", note.summary.strip()[: FIELD_LIMITS["summary"]])
        if note.category.strip():
            category = taxonomy.normalise_category(note.category.strip())
            if category != problem.category:
                put("category", category)
                put("group_id", (await self.group_for(category)).id)
        if _snake(note.subtype):
            put("subtype", _snake(note.subtype))
        words, redacted = _words(note.user_words)
        merged_words = [*problem.user_words, *[w for w in words if w not in problem.user_words]]
        put("user_words", merged_words[: MAX_USER_WORDS * 2])
        if redacted:
            put("pii_redacted", True)
        if note.where or note.of_total or note.products or note.channel:
            scope = dict(problem.scope or {})
            scope["products"] = note.products[:120] or scope.get("products", "")
            scope["channel"] = note.channel[:60] or scope.get("channel", "")
            scope["where"] = [w[:80] for w in note.where[:8]] or scope.get("where", [])
            scope["of_total"] = note.of_total[:80] or scope.get("of_total", "")
            put("scope", scope)
        if note.frequency_text or note.frequency or note.frequency_pattern:
            frequency = dict(problem.frequency or {})
            frequency["pattern"] = note.frequency_pattern[:120] or frequency.get("pattern", "")
            frequency["text"] = note.frequency_text[:120] or frequency.get("text", "")
            if note.frequency in taxonomy.FREQUENCIES:
                frequency["normalised"] = note.frequency
            put("frequency", frequency)
        if note.since_text:
            put("since", date_estimate(note.since_text, datetime.now(UTC).date()))
        if note.impact_types or note.money_text or note.time_text or note.people_affected:
            impact = dict(problem.impact or {})
            impact["currency"] = note.currency.strip().upper()[:3] or impact.get("currency", "")
            impact["time_text"] = note.time_text[:120] or impact.get("time_text", "")
            impact["people_affected"] = note.people_affected[:120] or impact.get(
                "people_affected", ""
            )
            kinds = [t for t in note.impact_types if t in taxonomy.IMPACT_TYPES]
            impact["types"] = kinds or impact.get("types", [])
            impact["money_text"] = note.money_text[:120] or impact.get("money_text", "")
            impact["money_value"] = amount_value(impact["money_text"])
            put("impact", impact)
        if note.severity_stated in taxonomy.SEVERITIES and note.severity_stated != "unknown":
            put("severity_stated", note.severity_stated)
        for name, value in (
            ("trigger", note.trigger),
            ("current_workaround", note.workaround),
            ("who_notices", note.who_notices),
        ):
            if value.strip():
                put(name, value.strip()[:400])
        if note.systems:
            put("systems_mentioned", sorted({*problem.systems_mentioned, *note.systems[:8]}))
        if note.believes_cause.strip():
            put("person_believes_cause", redact(note.believes_cause.strip()[:300])[0])
        if note.requested_solution.strip():
            put("requested_solution", redact(note.requested_solution.strip()[:300])[0])
        if message_id and str(message_id) not in problem.source_message_ids:
            put("source_message_ids", [*problem.source_message_ids, str(message_id)])
        if not diff:
            return False
        if reason == "correction":
            put("status", "corrected")
        self._score(problem)
        problem.revision += 1
        await self._revise(problem, diff, reason, "person" if reason == "correction" else "pi")
        return True

    async def merge(self, keep: PiProblem, others: list[PiProblem]) -> None:
        for other in others:
            if other.id == keep.id:
                continue
            for words in other.user_words:
                if words not in keep.user_words:
                    keep.user_words = [*keep.user_words, words]
            other.status = "merged"
            other.merged_into = keep.id
            other.revision += 1
            await self._revise(other, {"merged_into": [None, str(keep.id)]}, "merged", "pi")
        keep.revision += 1
        await self._revise(keep, {"merged": [short_ref(o.id) for o in others]}, "merged", "pi")

    async def confirm_drafts(self, keep: set[UUID], explicit: bool = False) -> int:
        """A noted line the person saw and did not object to becomes confirmed (spec 4.3). One
        pi was unsure of (confidence under 0.6) needs the person to say so: `explicit`."""
        count = 0
        for problem in await self.active():
            if (
                problem.status == "draft"
                and problem.id not in keep
                and (explicit or problem.confidence >= taxonomy.CONFIRM_BELOW)
            ):
                problem.status = "confirmed"
                count += 1
        return count


async def _taxonomy_review(
    session: AsyncSession, scope: WorkspaceScope, problem: PiProblem
) -> None:
    """A problem that fits no category goes to a person (spec 4.6): the category list is theirs."""
    from app.modules.notifications.service import notify

    await notify(
        session,
        scope,
        "pi.taxonomy_review",
        "pi noted a problem that fits no category",
        f"{problem.title}. Choose the right category, or tell pi's team if one is missing.",
        link="/pi/inbox",
        permission="pi.read",
        dedupe_key=f"pi-taxonomy:{problem.id}",
    )


async def apply_ops(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    conversation_id: UUID | None,
    message_id: UUID | None,
    ops: list[ProblemOp],
    language: str,
    link_min: Decimal = Decimal(0),
) -> Applied:
    """Apply the model's ops in order. Bad ones are skipped and listed, never raised."""
    book = ProblemBook(session, scope, customer_id, language)
    result = Applied()
    refs = await book.by_ref()
    for op in ops:
        try:
            if op.op == "create" and op.note and op.note.title.strip():
                problem, fresh = await book.create(op.note, message_id, conversation_id)
                (result.created if fresh else result.updated).append(problem)
                refs[short_ref(problem.id)] = problem
                if fresh and problem.category == taxonomy.OTHER:
                    await _taxonomy_review(session, scope, problem)  # 4.6 rule 4
                if fresh:
                    await business.link_duplicates_for_problem(session, scope, problem)
            elif op.op == "update" and op.ref in refs and op.note:
                changed = await book.update(
                    refs[op.ref],
                    op.note,
                    "correction" if op.reason == "correction" else "enrichment",
                    message_id,
                )
                if changed:
                    result.updated.append(refs[op.ref])
            elif op.op == "merge" and op.ref in refs and op.refs:
                others = [refs[r] for r in op.refs if r in refs and r != op.ref]
                if others:
                    await book.merge(refs[op.ref], others)
                    result.merged.extend(others)
                    result.updated.append(refs[op.ref])
            elif op.op == "split" and op.ref in refs and len(op.notes) >= 2:
                original = refs[op.ref]
                original.status = "split"
                original.revision += 1
                await book._revise(original, {"status": ["draft", "split"]}, "split", "pi")
                for note in op.notes:
                    problem, _ = await book.create(note, message_id, conversation_id)
                    result.created.append(problem)
                    refs[short_ref(problem.id)] = problem
                result.split.append(original)
            elif op.op == "withdraw" and op.ref in refs:
                problem = refs[op.ref]
                problem.status = "withdrawn"
                problem.revision += 1
                await book._revise(
                    problem, {"status": ["active", "withdrawn"]}, "withdrawn", "person"
                )
                result.withdrawn.append(problem)
            elif (
                op.op == "link"
                and op.ref in refs
                and op.to in refs
                and op.ref != op.to
                and Decimal(str(round(op.confidence, 2))) >= link_min
            ):
                kind = op.link_type if op.link_type in LINK_TYPES else "same_root_suspected"
                a, b = refs[op.ref], refs[op.to]
                found = await session.scalar(
                    select(PiProblemLink.id).where(
                        PiProblemLink.tenant_id == scope.tenant_id,
                        PiProblemLink.environment_id == scope.environment_id,
                        PiProblemLink.from_id == a.id,
                        PiProblemLink.to_id == b.id,
                        PiProblemLink.type == kind,
                    )
                )
                if found is None:
                    link = PiProblemLink(
                        tenant_id=scope.tenant_id,
                        environment_id=scope.environment_id,
                        from_id=a.id,
                        to_id=b.id,
                        type=kind,
                        confidence=Decimal(str(round(op.confidence, 2))),
                    )
                    session.add(link)
                    result.links.append(link)
            elif op.op == "rename_group" and op.name.strip() and op.ref in taxonomy.KEYS:
                group = await book.group_for(op.ref)
                group.name = op.name.strip()[:120]
                group.created_by = "person"
            else:
                result.rejected.append(f"{op.op}:{op.ref or op.note and op.note.title or ''}")
        except ValueError:
            result.rejected.append(op.op)
    await session.flush()
    await book.confirm_drafts(result.touched)
    await session.flush()
    return result


async def noted_context(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, limit: int = 40
) -> list[dict[str, Any]]:
    """The noted problems as compact JSON for the prompt: ref, title, group, status, gaps."""
    book = ProblemBook(session, scope, customer_id, "en")
    compact: list[dict[str, Any]] = []
    renamed = {
        g.category: g.name
        for g in await session.scalars(
            select(PiProblemGroup).where(
                PiProblemGroup.tenant_id == scope.tenant_id,
                PiProblemGroup.environment_id == scope.environment_id,
                PiProblemGroup.customer_id == customer_id,
                PiProblemGroup.created_by == "person",
            )
        )
        if g.name
    }
    for problem in (await book.active())[:limit]:
        missing = [
            name
            for name, known in (
                (
                    "where",
                    (problem.scope or {}).get("where") or (problem.scope or {}).get("of_total"),
                ),
                ("how_often", (problem.frequency or {}).get("normalised") not in (None, "unknown")),
                (
                    "impact",
                    (problem.impact or {}).get("types") or (problem.impact or {}).get("money_text"),
                ),
                ("since", (problem.since or {}).get("text")),
            )
            if not known
        ]
        compact.append(
            {
                "ref": short_ref(problem.id),
                "title": problem.title,
                "title_local": problem.title_local or "",
                "user_words": [str(w)[:200] for w in (problem.user_words or [])[:2]],
                "where": list((problem.scope or {}).get("where") or [])[:4],
                "group": problem.category,
                "subtype": problem.subtype or "",
                "goal_verb": problem.goal_verb or "",
                "cause": problem.person_believes_cause or "",
                "group_name": renamed.get(problem.category, ""),
                "score": float(problem.severity_score) if problem.severity_score else None,
                "status": problem.status,
                "missing": missing,
            }
        )
    return compact


# --- the S4 summary ---------------------------------------------------------------------

ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")

SUMMARY_TEXT = {
    "en": (
        "Here's what I've noted and sorted so far. None of it is solved yet.",
        "…and {n} more. I can send the full list.",
        "Is anything wrong or missing?",
    ),
    "roman_ur": (
        "Ab tak jo maine note aur sort kiya hai, ye hai. Inme se abhi kuch bhi hal nahi hua.",
        "…aur {n} aur hain. Poori list bhej di ja sakti hai.",
        "Kuch ghalat hai ya reh gaya hai?",
    ),
    "ur": (
        "اب تک جو میں نے نوٹ اور ترتیب دیا ہے، یہ ہے۔ ان میں سے ابھی کچھ بھی حل نہیں ہوا۔",
        "…اور {n} مزید ہیں۔ پوری فہرست بھیج سکتا ہوں۔",
        "کیا کچھ غلط ہے یا رہ گیا ہے؟",
    ),
    "ar": (
        "هذا ما سجلته ورتبته حتى الآن. لم يُحل أي منها بعد.",
        "…و{n} أخرى. يمكنني إرسال القائمة كاملة.",
        "هل هناك شيء خاطئ أو ناقص؟",
    ),
}  # fmt: skip


def summary_message(problems: list[dict[str, Any]], language: str = "en") -> str:
    """The sorted list, grouped, biggest group first (spec 3.7). Each item is
    {category, title, score?}. Over 12 problems it shows two lines per group."""
    intro, more, close = SUMMARY_TEXT.get(language, SUMMARY_TEXT["en"])
    groups: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    for item in problems:
        groups.setdefault(item["category"], []).append(item)
        if item.get("group_name"):
            names[item["category"]] = str(item["group_name"])
    order = sorted(groups, key=lambda key: (-len(groups[key]), taxonomy.OTHER == key, key))
    long = len(problems) > SUMMARY_FULL_LIST
    lines = [intro, ""]
    hidden = 0
    for key in order:
        items = sorted(groups[key], key=lambda i: -float(i.get("score") or 0))
        heading = names.get(key) if language == "en" else ""
        lines.append(f"*{heading or taxonomy.label(key, language)}* ({len(items)})")
        shown = items[:2] if long else items
        hidden += len(items) - len(shown)
        for item in shown:
            own = str(item.get("title_local") or "") if language != "en" else ""
            if own and bool(ARABIC_SCRIPT.search(own)) != (language in ("ur", "ar")):
                own = ""  # a title in another script than the chat's is not shown in it
            words = (own or str(item["title"])).split()[:SUMMARY_LINE_WORDS]
            lines.append("• " + " ".join(words))
        lines.append("")
    if hidden:
        lines.append(more.format(n=hidden))
        lines.append("")
    lines.append(close)
    return "\n".join(lines)


DONE = re.compile(
    r"\b(?:that'?s (?:all|it|everything)|that is (?:all|it)|nothing else|no(?:thing)? more|"
    r"i'?m done|bas(?: yahi| itna| ye ?hi| yehi)?|yahi (?:hai|sab)|aur kuch nahi|kuch aur nahi|"
    r"nahi aur kuch|that's it for now)\b",
    re.IGNORECASE,
)
ASKS_DOCUMENT = re.compile(
    r"\b(?:send|give|prepare|make|bana|banao|chahiye)\b.{0,25}\b(?:document|quote|quotation|proposal)\b"
    r"|\b(?:document|quote|quotation|proposal)\b.{0,25}\b(?:chahiye|bana|banao|bhejo|do)\b",
    re.IGNORECASE,
)
DONE_SHORT = re.compile(
    r"\b(?:abh?|abhi) (?:nh|nhi|nahi|nahin)\b"
    r"|\b(?:bas|aur|or|kuch) (?:nh|nhi|nahi|nahin)\b|\b(?:nh|nhi) bas\b",
    re.IGNORECASE,
)
ASKS_SUMMARY = re.compile(r"\b(?:summary|khulasa|khulasah|summery)\b", re.IGNORECASE)


def what_now(text: str | None) -> bool:
    """The person pushes for the fix or asks "so what now?". The owner's own loss ("I am not sure
    how much we lose", "kitna nuksan hota hai") is a statement, not that question: reading it as one
    gave early summaries and ideas in real chats."""
    from app.modules.pi.decisions import OWN_MONEY

    return bool(WHAT_NOW.search(OWN_MONEY.sub(" ", text or "")))


WHAT_NOW = re.compile(
    r"\b(?:what now|so what can you do|what can you do|what next|how much|how much would|"
    r"ab kya|aage kya|kitna (?:lagega|kharcha)|kya kar sakte)\b"
    # Pushing for the fix, always addressed to pi ("jaldi solution do", "sawal hi poochti
    # rahogi?", "just give me the solution"): the same "so what can you do?", so pi shows what it
    # noted instead of asking more. A customer describing THEIR customers asking too many
    # questions, or saying "koi hal hai nahi", is still describing a problem.
    r"|\bkuch kar sakte (?:ho|hain? ya nahi)\b"
    r"|\bkya solution (?:hai|he|hy)\b|\b(?:tumhare|aapke|apke) paas (?:koi )?(?:solution|hal)\b"
    r"|\bsolution (?:do|dw|dein|de do|dedo|dena|dijiye|dijie|batao|btao|bataen|chahiye)\b"
    # Asking pi to build it ("yehi bnwao", "ye bana do", "can you build this for me").
    r"|\b(?:ye|yeh|yehi|yahi|ise|isay|wo|woh)(?: \w+){0,2} "
    r"(?:bnwao|banwao|bnao|banao|bana do|bna do|bnwa do|banwa do)\b"
    r"|\b(?:ap|aap|tum) (?:ye |yeh |mere liye )?(?:bnwa|banwa|bana|bna)(?:o| do| dein| den)\b"
    r"|\b(?:can|could) you (?:build|make|create) (?:it|this|that)\b"
    r"|\bsawal(?:at)? hi (?:pooch|puch)\w*\s+(?:rah|rh)(?:o|oge|ogi|ega|egi)\b"
    r"|\b(?:aap|ap|tum) (?:itne|kitne) sawal\b"
    r"|\b(?:give|tell) me (?:a |the |your )?(?:solution|fix|answer)\W*$"
    r"|\bwhy (?:so|are you asking so) many questions\b"
    r"|\byou (?:ask|keep asking|are asking) (?:too|so) many questions\b"
    r"|\bstop asking (?:me|questions)\b|\benough (?:with )?(?:the |of the )?questions\b"
    r"|\bdo you have a (?:solution|fix)\b",
    re.IGNORECASE,
)


SHOW_ME = re.compile(
    r"\b(?:show me (?:what|everything|all)|what (?:have|did) you (?:noted?|got|written|understood)|"
    r"dikhao|kya (?:kya )?note kiya)\b"
    # "I already told you" (R-MEM-02): show what is noted instead of asking again. Only when it
    # is said to pi; "I already told the supplier" is part of the story.
    r"|\balready (?:told|said|mentioned)(?: it)? (?:to )?you\b"
    r"|\btold you (?:above|before|earlier)\b"
    r"|\bscroll up\b|\b(?:look at|read) (?:the |our )?(?:chat|conversation)\b"
    r"|\bup(?:p?e|a)?r (?:bata\w*|bta\w*|likha|likh\w*)|\bdekho (?:ye |yeh |is )?chat\b"
    r"|\bchat (?:dekho|dekh lo|dekhen|dekhein|parho|padho)\b"
    r"|^\W*(?:main |mai |maine )?(?:aap ko |apko |aapko )?(?:pehle|phele|pehly) (?:hi )?"
    r"(?:bata|bta|likh)\w* (?:chuka|chuki|diya|dia)\b"
    r"|\b(?:aap ko|apko|aapko|tumhe) (?:\w+ )?(?:bata|bta) (?:chuka|chuki|diya|dia)\b",
    re.IGNORECASE,
)

# "That's wrong, I never said that" about something pi attributed to them (R-CORR-01): pi
# withdraws or corrects that note and says so; it never answers that it did not understand.
# "Galat order deliver ho jata hai" is a problem, not a correction: the word must stand alone.
CORRECTED = re.compile(
    r"^\W*(?:galat|ghalat|glt|ghlt|wrong|not true)\W*(?:$|(?:hai|he|h|baat|wo|woh|ye|yeh|nahi)\b)"
    r"|\b(?:maine|main ne|mai ne|ma ?ny|mein ne|mene|meine) (?:aisa|asa|esa|ye|yeh)"
    r"(?: (?:kuch|kch))?(?: (?:bhi|bh))? (?:nahi|nhi|nh|nahin|nai) (?:kaha|kha|bola|likha)\b"
    r"|\bi (?:never|didn'?t|did not) (?:say|said) (?:that|this|so|it|anything)\b"
    r"|\bthat'?s not what i said\b",
    re.IGNORECASE,
)


def says_wrong(text: str) -> bool:
    """They say pi got something wrong, whether or not anything is noted yet."""
    return bool(CORRECTED.search(" ".join((text or "").split())))


def corrects_noted(text: str, noted: int) -> bool:
    """They say something already noted is wrong (there must be a note to correct)."""
    return noted > 0 and says_wrong(text)


def asks_for_map(text: str) -> bool:
    """The person asks for their problem map (pi Customer's wording, shared with that module)."""
    from app.modules.pi_customer.engine import MAP_ASK  # local: pi_customer imports this module

    return bool(MAP_ASK.search(text or ""))


def summary_due(
    text: str,
    noted: int,
    since_summary: int,
    trigger: int = SUMMARY_TRIGGER,
    quiet_replies: int = 0,
    quiet_limit: int = 2,
) -> str | None:
    """Why pi should show the sorted summary now (spec 3.7), or None."""
    if noted < 1:
        return None
    if DONE.search(text):
        return "done"
    short = len((text or "").split()) <= 4
    if short and DONE_SHORT.search(text):
        return "done"  # "abh nh", "bas nh": the answer to "anything else?" in Roman Urdu
    if len((text or "").split()) <= 6 and ASKS_SUMMARY.search(text):
        return "show"  # "summary kosni", "summary dikhao"
    if what_now(text):
        return "what_now"
    if SHOW_ME.search(text):
        return "show"
    if asks_for_map(text):
        return "map"  # "show my problem map": the sorted summary, with the board picture
    if ASKS_DOCUMENT.search(text):
        return "document_asked"  # the offer comes after a confirmed summary, never before
    if since_summary >= trigger:
        return "many"
    if quiet_replies >= quiet_limit and since_summary >= 1:
        return "quiet"
    return None


def shape_question_due(noted: int, industry_known: bool, already_asked: bool) -> bool:
    """After two problems, if pi still does not know the trade, it may ask once (spec 7.0)."""
    return noted >= 2 and not industry_known and not already_asked


PATTERN_AT = 3  # problems in one group, or at one place, before pi may point it out


def pattern_hint(noted: list[dict[str, Any]], already_said: list[str]) -> dict[str, Any] | None:
    """A pattern worth saying once (spec 4.8): a group of three or more problems, or one place that
    appears in three or more problems across groups. None when nothing new is worth saying."""
    by_group: dict[str, int] = {}
    by_place: dict[str, int] = {}
    for item in noted:
        by_group[item["group"]] = by_group.get(item["group"], 0) + 1
        for place in {str(w).strip().casefold() for w in item.get("where") or [] if str(w).strip()}:
            by_place[place] = by_place.get(place, 0) + 1
    for group, count in sorted(by_group.items(), key=lambda kv: -kv[1]):
        key = f"group:{group}"
        if count >= PATTERN_AT and key not in already_said:
            return {"kind": "group", "group": group, "count": count, "key": key}
    for place, count in sorted(by_place.items(), key=lambda kv: -kv[1]):
        key = f"place:{place}"
        if count >= PATTERN_AT and key not in already_said:
            return {"kind": "location", "where": place, "count": count, "key": key}
    return None
