"""PS-8: the read-only memory and evidence layer. Everything pi already knows about this owner,
assembled BEFORE any diagnosis, question or recommendation.

`build_context` gathers, for ONE customer of ONE workspace (tenant AND environment AND customer on
every query): the owner's own messages (this chat and a few earlier ones), the noted problems with
all stored fields (including the B2a columns), the solution records with their exact stored state,
stored files, tried solutions, rejected ideas, decisions, owner-confirmed facts and the correction
history. Pure helpers read the bundle: `answered_from_records`, `what_is_already_known`,
`implementation_summary`, `known_records`.

Guarantees (spec: platform v1.6 18.5 alreadyAnswered; brain v3 R-MEM-01..06, R-CORR, R-PRIV-06):
* Read only: only SELECT is ever issued. Explicit column selects, never ORM objects, so no deferred
  column is ever lazy-loaded (an async session cannot do that).
* Never raises: a failing sub-query is rolled back in its own savepoint and recorded as
  "unavailable: <source>"; the rest still returns. Undefined column (42703, B2a before 0053) marks
  requirements unavailable (`requirements_available=False`), it is not an empty "nothing said".
* Erased customers (brain_erase) return an empty bundle with erased=True.
* Stored text is already redacted; it is redacted again defensively and never un-redacted.
* Caps with explicit `truncated` names; deterministic ordering (explicit tie-breakers).
* Owner-confirmed facts and pi hypotheses stay apart (`status`); scans are labelled derived.
* A proposed solution is never reported as implemented.
Logs carry counts only, never the owner's words.
"""

import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from functools import partial
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import CustomerFile
from app.modules.pi import memory_ledger_read, safety
from app.modules.pi.box_models import PiBoxTransition, PiOfferLog, PiSolutionBox
from app.modules.pi.brain_docs_models import PiBrainDocument, PiBrainPayment
from app.modules.pi.business_profile_models import PiBusinessProfile, PiProfileFact
from app.modules.pi.context_memory_types import (
    IMPLEMENTED_STATES,
    IN_PROGRESS_STATES,
    OWNER_STATUSES,
    Answer,
    ContextBundle,
    CorrectionHistory,
    DecisionItem,
    FactItem,
    FileItem,
    LimitItem,
    Limits,
    MessageItem,
    PriorValue,
    ProblemItem,
    RejectionItem,
    SolutionItem,
    TriedEntry,
)
from app.modules.pi.models import PiConversation, PiMemory, PiMessage
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi.problem_models import PiProblem, PiProblemRevision
from app.modules.pi.requirements_read import parse_cause, parse_constraints, parse_tried
from app.modules.pi.solution_models import PiIdeaArm, PiSolutionMemory
from app.modules.pi_saas.deal_models import PiDocument
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

ERASED_MARK = "[deleted at the customer's request]"  # brain_erase.ERASED, kept by value
UNDEFINED_COLUMN = "42703"
OWNER_MESSAGE_TYPES = ("text", "audio", "interactive")
CONVERSATION_FETCH = 200
JSON_TEXT_CAP = 200


# --------------------------------------------------------------------------- small pure helpers


def normalise_language(value: Any) -> str:
    """One of en, roman_ur, ur, ar. Anything unknown reads as English."""
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in ("roman_ur", "roman_urdu", "roman-ur", "romanurdu", "ur-latn", "ur_latn", "ru"):
        return "roman_ur"
    if raw.startswith("ur"):
        return "ur"
    if raw.startswith("ar"):
        return "ar"
    return "en"


def _cap(text: Any, size: int) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[: max(size, 0)].strip()


def _safe(text: Any, size: int) -> str:
    """Capped, whitespace-normalised, and redacted again (a no-op on text redacted at storage)."""
    value = _cap(text, size * 2)
    if not value:
        return ""
    try:
        value = safety.redact_pii(value).text
    except Exception:  # noqa: BLE001 - redaction must never take the read down
        pass
    return _cap(value, size)


def _iso(value: Any) -> str:
    try:
        return value.isoformat() if value is not None else ""
    except Exception:  # noqa: BLE001
        return ""


def _clean_json(value: Any, depth: int = 0) -> Any:
    """A JSON value reduced to plain scalars, short strings and small lists/dicts."""
    if depth > 3:
        return None
    if isinstance(value, str):
        return _safe(value, JSON_TEXT_CAP)
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(k)[:40]: _clean_json(v, depth + 1) for k, v in list(value.items())[:20]}
    if isinstance(value, list | tuple):
        return [_clean_json(v, depth + 1) for v in list(value)[:20]]
    return None


def _dict(value: Any) -> dict[str, Any]:
    cleaned = _clean_json(value)
    return cleaned if isinstance(cleaned, dict) else {}


def _strs(value: Any, size: int = 120) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    out = [_safe(v, size) for v in value[:20] if isinstance(v, str)]
    return tuple(x for x in out if x)


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _sqlstate_is_undefined_column(error: ProgrammingError) -> bool:
    orig = error.orig
    for candidate in (orig, getattr(orig, "__cause__", None)):
        if candidate is None:
            continue
        if UNDEFINED_COLUMN in (
            getattr(candidate, "sqlstate", None),
            getattr(candidate, "pgcode", None),
        ):
            return True
        if type(candidate).__name__ == "UndefinedColumnError":
            return True
    return False


def _limit(raw: Any) -> LimitItem | None:
    if raw is None:
        return None
    text = _safe(getattr(raw, "text", ""), 160)
    if not text:
        return None
    return LimitItem(
        text,
        getattr(raw, "msg", None),
        str(getattr(raw, "status", "") or ""),
        str(getattr(raw, "valid_from", "") or ""),
        str(getattr(raw, "valid_to", "") or ""),
        str(getattr(raw, "key", "") or ""),
    )


# --------------------------------------------------------------------------- cue scans (derived)

_REJECT_LATIN = (
    r"no thanks|no thank you|not interested|i don'?t want|we don'?t want|do not want|"
    r"won'?t work|will not work|not for us|doesn'?t suit|does not suit|"
    r"nahi chahiye|nahin chahiye|nahi chahie|zaroorat nahi|zarurat nahi|pasand nahi|"
    r"kaam nahi kare|nahi chalega|nahi hoga|mushkil hai nahi|mut chahiye|"
    r"mish ?mohtam|ma abgha|mish 3ayez|la urid|la nurid"
)
_REJECT_SCRIPT = (
    "نہیں چاہیے|نہیں چاہئے|ضرورت نہیں|پسند نہیں|کام نہیں کرے گا|نہیں چلے گا|"
    "لا أريد|لا نريد|لا اريد|لا نبغى|ما أبغى|غير مهتم|لا يناسبنا|مش عايز|مو مهتم"
)
_TRIED_LATIN = (
    r"i tried|we tried|i have tried|we have tried|already tried|i already did|tried that|"
    r"try kiya|try kar chuka|try kar chuke|kar chuka hoon|kar chuke hain|pehle kiya|"
    r"koshish ki|aazmaya|azmaya|ho chuka hai"
)
_TRIED_SCRIPT = "کوشش کی|آزمایا|پہلے کیا|جربت|جربنا|حاولنا|حاولت|سبق وجربنا"
_REJECT = re.compile(rf"(?<![a-z])(?:{_REJECT_LATIN})(?![a-z])|{_REJECT_SCRIPT}", re.IGNORECASE)
_TRIED = re.compile(rf"(?<![a-z])(?:{_TRIED_LATIN})(?![a-z])|{_TRIED_SCRIPT}", re.IGNORECASE)


def scan_rejections(messages: tuple[MessageItem, ...], size: int = 20) -> tuple[RejectionItem, ...]:
    """Explicit rejections in the owner's own messages (en, Roman Urdu, Urdu, Arabic cues). This is
    a READING, labelled derived: the repo stores no owner-message rejection. Newest first."""
    out: list[RejectionItem] = []
    for message in reversed(messages):
        if len(out) >= size:
            break
        if _REJECT.search(message.text):
            out.append(
                RejectionItem(
                    text=_cap(message.text, 200),
                    ref=f"msg:{message.id}",
                    derived=True,
                    at=message.at,
                )
            )
    return tuple(out)


def scan_tried(messages: tuple[MessageItem, ...], size: int = 20) -> tuple[TriedEntry, ...]:
    """Earlier owner messages saying they already tried something (derived, not a stored field).
    The cues are positive phrases, so "never tried" does not match. Newest first."""
    out: list[TriedEntry] = []
    for message in reversed(messages):
        if len(out) >= size:
            break
        if _TRIED.search(message.text):
            out.append(TriedEntry(what=_cap(message.text, 160), msg=str(message.id), derived=True))
    return tuple(out)


# --------------------------------------------------------------------------- fetching


async def _guard(
    session: AsyncSession,
    name: str,
    unavailable: list[str],
    fetch: Callable[[], Awaitable[Any]],
    default: Any,
) -> Any:
    """Run one sub-query in its own savepoint; a failure is recorded, never raised."""
    try:
        async with session.begin_nested():
            return await fetch()
    except Exception as error:  # noqa: BLE001 - a read layer never raises
        unavailable.append(f"unavailable: {name}")
        logger.warning(
            "pi_context_unavailable", extra={"source": name, "error": type(error).__name__}
        )
        return default


def _mine(model: Any, scope: WorkspaceScope) -> tuple[Any, ...]:
    return (model.tenant_id == scope.tenant_id, model.environment_id == scope.environment_id)


async def _conversations(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> list[Any]:
    rows = (
        await session.execute(
            select(
                PiConversation.id,
                PiConversation.last_message_at,
                PiConversation.flow_state,
                PiConversation.language,
                PiConversation.service_brief["erased"].as_string().label("erased"),
                PiConversation.service_brief["kickoff"]["at"].as_string().label("kickoff_at"),
            )
            .where(*_mine(PiConversation, scope), PiConversation.customer_id == customer_id)
            .order_by(PiConversation.last_message_at.desc(), PiConversation.id.desc())
            .limit(CONVERSATION_FETCH + 1)
        )
    ).all()
    return list(rows)


async def _owner_messages(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, size: int
) -> list[Any]:
    rows = (
        await session.execute(
            select(
                PiMessage.id,
                PiMessage.conversation_id,
                PiMessage.created_at,
                PiMessage.body,
                PiMessage.message_type,
            )
            .where(
                *_mine(PiMessage, scope),
                PiMessage.conversation_id == conversation_id,
                PiMessage.direction == "inbound",
                PiMessage.sender_type == "customer",
                PiMessage.message_type.in_(OWNER_MESSAGE_TYPES),
                PiMessage.body != "",
                PiMessage.body != ERASED_MARK,
            )
            .order_by(PiMessage.created_at.desc(), PiMessage.id.desc())
            .limit(size + 1)
        )
    ).all()
    return list(rows)


def _message_items(
    rows: list[Any], size: int, chars: int, current: bool
) -> tuple[list[MessageItem], bool]:
    cut = len(rows) > size
    items = [
        MessageItem(
            id=r.id,
            conversation_id=r.conversation_id,
            at=_iso(r.created_at),
            text=_safe(r.body, chars),
            current=current,
            message_type=str(r.message_type or "text"),
        )
        for r in rows[:size]
    ]
    items = [m for m in items if m.text]
    items.reverse()  # oldest first
    return items, cut


_PROBLEM_COLUMNS = (
    PiProblem.id,
    PiProblem.number,
    PiProblem.title,
    PiProblem.status,
    PiProblem.category,
    PiProblem.summary,
    PiProblem.subtype,
    PiProblem.conversation_id,
    PiProblem.user_words,
    PiProblem.systems_mentioned,
    PiProblem.scope,
    PiProblem.frequency,
    PiProblem.since,
    PiProblem.impact,
    PiProblem.trigger,
    PiProblem.current_workaround,
    PiProblem.who_notices,
    PiProblem.person_believes_cause,
    PiProblem.requested_solution,
    PiProblem.severity_stated,
    PiProblem.source_message_ids,
    PiProblem.revision,
)
_B2A_COLUMNS = (
    PiProblem.constraints,
    PiProblem.tried,
    PiProblem.cause,
    PiProblem.expected_outcome,
)


async def _problems(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> tuple[list[Any], bool]:
    """(rows, requirements_available). The B2a columns are read in the same select; on a database
    without migration 0053 the select fails with 42703 and is repeated without them."""

    def query(columns: tuple[Any, ...]) -> Any:
        return (
            select(*columns)
            .where(
                *_mine(PiProblem, scope),
                PiProblem.customer_id == customer_id,
                PiProblem.merged_into.is_(None),
                PiProblem.status != "merged",
            )
            .order_by(PiProblem.number, PiProblem.id)
            .limit(size + 1)
        )

    try:
        async with session.begin_nested():
            return list((await session.execute(query(_PROBLEM_COLUMNS + _B2A_COLUMNS))).all()), True
    except ProgrammingError as error:
        if not _sqlstate_is_undefined_column(error):
            raise
        logger.warning("pi_context_requirements_columns_missing")
    return list((await session.execute(query(_PROBLEM_COLUMNS))).all()), False


def _problem_item(row: Any, with_b2a: bool) -> ProblemItem:
    constraints = parse_constraints(getattr(row, "constraints", None)) if with_b2a else None
    cause = parse_cause(getattr(row, "cause", None)) if with_b2a else None
    ref = f"P{int(row.number or 0)}"
    tried = (
        tuple(
            TriedEntry(
                what=_safe(t.what, 160),
                outcome=_safe(t.outcome, 160),
                msg=t.msg,
                problem_ref=ref,
            )
            for t in parse_tried(getattr(row, "tried", None))
        )
        if with_b2a
        else ()
    )
    outcome = getattr(row, "expected_outcome", None)
    return ProblemItem(
        id=row.id,
        number=int(row.number or 0),
        title=_safe(row.title, 120),
        status=str(row.status or ""),
        category=str(row.category or ""),
        summary=_safe(row.summary, 300),
        subtype=_safe(row.subtype, 60),
        conversation_id=row.conversation_id,
        user_words=_strs(row.user_words),
        systems_mentioned=_strs(row.systems_mentioned, 60),
        scope=_dict(row.scope),
        frequency=_dict(row.frequency),
        since=_dict(row.since),
        impact=_dict(row.impact),
        trigger=_safe(row.trigger, 200),
        current_workaround=_safe(row.current_workaround, 300),
        who_notices=_safe(row.who_notices, 200),
        person_believes_cause=_safe(row.person_believes_cause, 300),
        requested_solution=_safe(row.requested_solution, 300),
        severity_stated=str(row.severity_stated or "unknown"),
        source_message_ids=tuple(
            str(x) for x in (row.source_message_ids or [])[:40] if isinstance(x, str)
        ),
        revision=int(row.revision or 1),
        budget=_limit(constraints.budget) if constraints else None,
        staff=_limit(constraints.staff) if constraints else None,
        deadline=_limit(constraints.deadline) if constraints else None,
        cannot_change=tuple(x for x in map(_limit, constraints.cannot_change) if x)
        if constraints
        else (),
        tried=tried,
        constraint_history=tuple(x for x in map(_limit, constraints.history) if x)
        if constraints
        else (),
        cause_text=_safe(cause.text, 300) if cause else "",
        cause_status=cause.status if cause else "",
        expected_outcome=_safe(outcome, 300) if isinstance(outcome, str) else "",
    )


def _revision_corrections(
    rows: list[Any], refs: dict[UUID, str], current: dict[UUID, dict[str, Any]], size: int
) -> tuple[list[CorrectionHistory], bool]:
    """Per (problem, field): the value now and every earlier value, oldest first. A first fill (an
    empty earlier value) is not a correction. History is never dropped except by the size cap."""
    changes: dict[tuple[UUID, str], list[PriorValue]] = {}
    last_new: dict[tuple[UUID, str], Any] = {}
    for row in rows:
        diff = row.diff if isinstance(row.diff, Mapping) else {}
        pairs: dict[str, tuple[Any, Any]] = {}
        for name, pair in diff.items():
            if not isinstance(pair, list | tuple) or len(pair) != 2:
                continue
            old, new = pair
            if name == "constraints" and (isinstance(old, Mapping) or isinstance(new, Mapping)):
                old_m = old if isinstance(old, Mapping) else {}
                new_m = new if isinstance(new, Mapping) else {}
                for sub in ("budget", "staff", "deadline"):
                    if old_m.get(sub) != new_m.get(sub):
                        pairs[f"constraints.{sub}"] = (old_m.get(sub), new_m.get(sub))
            elif name not in ("revision", "updated_at", "source_message_ids", "confidence"):
                pairs[str(name)] = (old, new)
        msg: str | None = None
        ids = diff.get("source_message_ids")
        if isinstance(ids, list | tuple) and len(ids) == 2 and isinstance(ids[1], list):
            old_ids = ids[0] if isinstance(ids[0], list) else []
            added = [i for i in ids[1] if isinstance(i, str) and i not in old_ids]
            msg = added[-1] if added else None
        for name, (old, new) in pairs.items():
            key = (row.problem_id, name)
            last_new[key] = new
            if _empty(old):
                continue
            new_msg = new.get("msg") if isinstance(new, Mapping) else None
            changes.setdefault(key, []).append(
                PriorValue(
                    value=_clean_json(old),
                    revision=int(row.revision or 0),
                    reason=str(row.reason or ""),
                    by=str(row.by or ""),
                    at=_iso(row.created_at),
                    msg=new_msg if isinstance(new_msg, str) else msg,
                )
            )
    out: list[CorrectionHistory] = []
    for (problem_id, name), prior in sorted(
        changes.items(), key=lambda kv: (refs.get(kv[0][0], ""), kv[0][1])
    ):
        now_value = current.get(problem_id, {}).get(name, last_new.get((problem_id, name)))
        out.append(
            CorrectionHistory(
                problem_ref=refs.get(problem_id, ""),
                field=name,
                current=_clean_json(now_value),
                prior=tuple(prior),
            )
        )
    return out[:size], len(out) > size


_DOC_STATE = {
    "draft": "drafted",
    "in_review": "in_review",
    "approved": "reviewer_approved",
    "sent": "issued",
    "superseded": "superseded",
}
_BOX_STATE = {
    "collecting": "not_offered",
    "ready": "not_offered",
    "offered": "proposed",
    "drafting": "drafted",
    "in_review": "in_review",
    "sent": "issued",
    "accepted": "accepted",
    "declined": "declined",
    "changes_asked": "changes_asked",
    "revised": "drafted",
}
_PAYMENT_STATE = {
    "pending": "awaiting_payment",
    "claimed": "payment_claimed",
    "confirmed": "paid",
    "failed": "payment_failed",
}
_FLOW_WORK = {"S11_PAYMENT_CONFIRMED": "paid", "S12_KICKOFF": "kickoff", "S13_IN_BUILD": "in_build"}


def _doc_ref(kind: str, number: int, version: int) -> str:
    base = f"{'SD' if kind == 'solution' else 'Q'}-{int(number):04d}"
    return base if int(version or 1) == 1 else f"{base}-v{int(version)}"


async def _solutions(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    conversations: list[Any],
    problem_refs: dict[str, str],
    size: int,
) -> tuple[list[SolutionItem], list[DecisionItem], bool]:
    solutions: list[SolutionItem] = []
    decisions: list[DecisionItem] = []
    docs = (
        await session.execute(
            select(
                PiBrainDocument.id,
                PiBrainDocument.kind,
                PiBrainDocument.number,
                PiBrainDocument.version,
                PiBrainDocument.status,
                PiBrainDocument.problem_ids,
                PiBrainDocument.total,
                PiBrainDocument.currency,
                PiBrainDocument.approved_at,
                PiBrainDocument.sent_at,
                PiBrainDocument.created_at,
                PiBrainDocument.conversation_id,
            )
            .where(*_mine(PiBrainDocument, scope), PiBrainDocument.customer_id == customer_id)
            .order_by(PiBrainDocument.created_at.desc(), PiBrainDocument.id.desc())
            .limit(size + 1)
        )
    ).all()
    quote_refs: dict[UUID, str] = {}
    for d in docs[:size]:
        ref = _doc_ref(d.kind, d.number, d.version)
        quote_refs[d.id] = ref
        stored = str(d.status or "")
        solutions.append(
            SolutionItem(
                kind="quote" if d.kind == "quote" else "document",
                ref=ref,
                implementation_status=_DOC_STATE.get(stored, "proposed"),
                stored_state=stored,
                at=_iso(d.created_at),
                problem_refs=tuple(
                    problem_refs[p] for p in (d.problem_ids or []) if p in problem_refs
                ),
                total="" if d.total is None else str(d.total),
                currency=str(d.currency or ""),
                conversation_id=d.conversation_id,
                reviewer_approved=stored in ("approved", "sent") or d.approved_at is not None,
            )
        )
        if stored in ("in_review",):
            decisions.append(DecisionItem("approval", ref, "pending", "", _iso(d.created_at)))
        elif d.approved_at is not None:
            decisions.append(DecisionItem("approval", ref, "approved", "", _iso(d.approved_at)))
    payments = (
        await session.execute(
            select(
                PiBrainPayment.id,
                PiBrainPayment.quote_id,
                PiBrainPayment.status,
                PiBrainPayment.created_at,
                PiBrainPayment.conversation_id,
            )
            .where(*_mine(PiBrainPayment, scope), PiBrainPayment.customer_id == customer_id)
            .order_by(PiBrainPayment.created_at.desc(), PiBrainPayment.id.desc())
            .limit(size)
        )
    ).all()
    for p in payments:
        stored = str(p.status or "")
        solutions.append(
            SolutionItem(
                kind="payment",
                ref=f"pay:{quote_refs.get(p.quote_id, str(p.quote_id)[:8])}",
                implementation_status=_PAYMENT_STATE.get(stored, "awaiting_payment"),
                stored_state=stored,
                at=_iso(p.created_at),
                conversation_id=p.conversation_id,
            )
        )
    boxes = (
        await session.execute(
            select(
                PiSolutionBox.id,
                PiSolutionBox.state,
                PiSolutionBox.version,
                PiSolutionBox.offered_at,
                PiSolutionBox.created_at,
            )
            .where(*_mine(PiSolutionBox, scope), PiSolutionBox.customer_id == customer_id)
            .order_by(PiSolutionBox.version.desc(), PiSolutionBox.id.desc())
            .limit(size)
        )
    ).all()
    box_ids = [b.id for b in boxes]
    for b in boxes:
        stored = str(b.state or "")
        solutions.append(
            SolutionItem(
                kind="box",
                ref=f"BOX-v{int(b.version or 1)}",
                implementation_status=_BOX_STATE.get(stored, "proposed"),
                stored_state=stored,
                at=_iso(b.offered_at or b.created_at),
            )
        )
        if stored in ("offered", "drafting", "in_review", "sent", "revised"):
            decisions.append(
                DecisionItem(
                    "offer", f"BOX-v{int(b.version or 1)}", "pending", stored, _iso(b.offered_at)
                )
            )
        elif stored in ("accepted", "declined", "changes_asked"):
            decisions.append(
                DecisionItem(
                    "offer",
                    f"BOX-v{int(b.version or 1)}",
                    "approved" if stored == "accepted" else stored,
                    stored,
                    _iso(b.offered_at),
                )
            )
    deals = (
        await session.execute(
            select(
                PiDocument.id,
                PiDocument.kind,
                PiDocument.response,
                PiDocument.delivery,
                PiDocument.created_at,
                PiDocument.conversation_id,
            )
            .where(*_mine(PiDocument, scope), PiDocument.customer_id == customer_id)
            .order_by(PiDocument.created_at.desc(), PiDocument.id.desc())
            .limit(size)
        )
    ).all()
    for dd in deals:
        response = str(dd.response or "")
        if dd.kind == "receipt":
            state = "paid"
        elif dd.kind == "invoice":
            state = "issued"
        elif response == "accepted":
            state = "accepted"
        elif response == "changes":
            state = "changes_asked"
        elif response == "rejected":
            state = "declined"
        else:
            state = "issued" if dd.delivery == "sent" else "drafted"
        ref = f"{dd.kind}:{str(dd.id)[:8]}"
        solutions.append(
            SolutionItem(
                kind="deal_document",
                ref=ref,
                implementation_status=state,
                stored_state=response or str(dd.delivery or ""),
                at=_iso(dd.created_at),
                conversation_id=dd.conversation_id,
            )
        )
        if response:
            decisions.append(
                DecisionItem(
                    "document",
                    ref,
                    "approved" if response == "accepted" else response,
                    "",
                    _iso(dd.created_at),
                )
            )
    for conv in conversations:
        work = _FLOW_WORK.get(str(conv.flow_state or ""))
        if work:
            solutions.append(
                SolutionItem(
                    kind="kickoff" if work == "kickoff" else "build",
                    ref=f"chat:{str(conv.id)[:8]}",
                    implementation_status=work,
                    stored_state=str(conv.flow_state),
                    at=str(conv.kickoff_at or ""),
                    conversation_id=conv.id,
                )
            )
    if box_ids:
        moves = (
            await session.execute(
                select(
                    PiBoxTransition.id,
                    PiBoxTransition.from_state,
                    PiBoxTransition.to_state,
                    PiBoxTransition.actor,
                    PiBoxTransition.created_at,
                )
                .where(*_mine(PiBoxTransition, scope), PiBoxTransition.box_id.in_(box_ids))
                .order_by(PiBoxTransition.created_at.desc(), PiBoxTransition.id.desc())
                .limit(size)
            )
        ).all()
        for m in moves:
            decisions.append(
                DecisionItem(
                    "box_move",
                    str(m.id)[:8],
                    str(m.to_state),
                    f"{m.from_state}>{m.to_state} by {m.actor}",
                    _iso(m.created_at),
                )
            )
    solutions.sort(key=lambda s: (s.at, s.ref, s.kind), reverse=True)
    cut = len(docs) > size or len(solutions) > size
    return solutions[:size], decisions, cut


async def _offer_and_open_decisions(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    conversation_ids: list[UUID],
    size: int,
) -> list[DecisionItem]:
    out: list[DecisionItem] = []
    if conversation_ids:
        logs = (
            await session.execute(
                select(
                    PiOfferLog.id,
                    PiOfferLog.rule,
                    PiOfferLog.allowed,
                    PiOfferLog.blocked_reason,
                    PiOfferLog.created_at,
                )
                .where(*_mine(PiOfferLog, scope), PiOfferLog.conversation_id.in_(conversation_ids))
                .order_by(PiOfferLog.created_at.desc(), PiOfferLog.id.desc())
                .limit(size)
            )
        ).all()
        for r in logs:
            out.append(
                DecisionItem(
                    "offer",
                    f"rule:{r.rule}",
                    "allowed" if r.allowed else "blocked",
                    _safe(r.blocked_reason, 160),
                    _iso(r.created_at),
                )
            )
    items = (
        await session.execute(
            select(
                PiOpenItem.id,
                PiOpenItem.kind,
                PiOpenItem.key,
                PiOpenItem.status,
                PiOpenItem.text,
                PiOpenItem.created_at,
            )
            .where(*_mine(PiOpenItem, scope), PiOpenItem.customer_id == customer_id)
            .order_by(PiOpenItem.created_at.desc(), PiOpenItem.id.desc())
            .limit(size)
        )
    ).all()
    for i in items:
        out.append(
            DecisionItem(
                "open_item",
                f"{i.kind}:{i.key}",
                str(i.status),
                _safe(i.text, 160),
                _iso(i.created_at),
            )
        )
    return out


async def _revisions(
    session: AsyncSession, scope: WorkspaceScope, problem_ids: list[UUID]
) -> list[Any]:
    if not problem_ids:
        return []
    return list(
        (
            await session.execute(
                select(
                    PiProblemRevision.problem_id,
                    PiProblemRevision.revision,
                    PiProblemRevision.diff,
                    PiProblemRevision.reason,
                    PiProblemRevision.by,
                    PiProblemRevision.created_at,
                )
                .where(
                    *_mine(PiProblemRevision, scope), PiProblemRevision.problem_id.in_(problem_ids)
                )
                .order_by(PiProblemRevision.problem_id, PiProblemRevision.revision)
                .limit(2000)
            )
        ).all()
    )


async def _files(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> tuple[list[FileItem], bool]:
    rows = (
        await session.execute(
            select(
                CustomerFile.id,
                CustomerFile.name,
                CustomerFile.mime,
                CustomerFile.size,
                CustomerFile.source,
                CustomerFile.created_at,
            )  # never CustomerFile.data (the bytes)
            .where(*_mine(CustomerFile, scope), CustomerFile.customer_id == customer_id)
            .order_by(CustomerFile.created_at.desc(), CustomerFile.id.desc())
            .limit(size + 1)
        )
    ).all()
    items = [
        FileItem(
            r.id,
            _safe(r.name, 120),
            str(r.mime or ""),
            int(r.size or 0),
            str(r.source or ""),
            _iso(r.created_at),
        )
        for r in rows[:size]
    ]
    return items, len(rows) > size


async def _idea_memory(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> tuple[list[RejectionItem], list[TriedEntry]]:
    rows = (
        await session.execute(
            select(
                PiSolutionMemory.id,
                PiSolutionMemory.reaction,
                PiSolutionMemory.said_will_try,
                PiSolutionMemory.reported_result,
                PiSolutionMemory.given_at,
                PiIdeaArm.text,
            )
            .join(
                PiIdeaArm,
                (PiIdeaArm.id == PiSolutionMemory.idea_arm_id)
                & (PiIdeaArm.tenant_id == PiSolutionMemory.tenant_id)
                & (PiIdeaArm.environment_id == PiSolutionMemory.environment_id),
            )
            .where(
                *_mine(PiSolutionMemory, scope),
                PiSolutionMemory.customer_id == customer_id,
                (PiSolutionMemory.reaction.in_(("rejected", "tried")))
                | PiSolutionMemory.said_will_try,
            )
            .order_by(PiSolutionMemory.given_at.desc(), PiSolutionMemory.id.desc())
            .limit(size)
        )
    ).all()
    rejected: list[RejectionItem] = []
    tried: list[TriedEntry] = []
    for r in rows:
        text = _safe(r.text, 200)
        if not text:
            continue
        if r.reaction == "rejected":
            rejected.append(
                RejectionItem(text, f"idea:{str(r.id)[:8]}", False, "", _iso(r.given_at))
            )
        elif r.reaction == "tried":
            result = str(r.reported_result or "")
            tried.append(TriedEntry(text, "" if result == "unknown" else result, None, ""))
    return rejected, tried


async def _profile_facts(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> list[FactItem]:
    out: list[FactItem] = []
    profiles = (
        await session.execute(
            select(
                PiBusinessProfile.id,
                PiBusinessProfile.what_they_do,
                PiBusinessProfile.city_area,
                PiBusinessProfile.size_band,
            )
            .where(*_mine(PiBusinessProfile, scope), PiBusinessProfile.customer_id == customer_id)
            .order_by(PiBusinessProfile.created_at, PiBusinessProfile.id)
            .limit(5)
        )
    ).all()
    for p in profiles:
        for key, value in (
            ("business", p.what_they_do),
            ("location", p.city_area),
            ("business_size", p.size_band),
        ):
            text = _safe(value, 160)
            if text:
                out.append(FactItem(key, text, "remembered", f"profile:{str(p.id)[:8]}"))
    ids = [p.id for p in profiles]
    if ids:
        facts = (
            await session.execute(
                select(
                    PiProfileFact.id,
                    PiProfileFact.key,
                    PiProfileFact.value,
                    PiProfileFact.source,
                    PiProfileFact.confirmed,
                )
                .where(*_mine(PiProfileFact, scope), PiProfileFact.profile_id.in_(ids))
                .order_by(PiProfileFact.key, PiProfileFact.id)
                .limit(size)
            )
        ).all()
        for f in facts:
            text = _safe(f.value, 160)
            if not text:
                continue
            if f.source == "owner":
                status = "confirmed" if f.confirmed else "owner_said"
            else:
                status = "page_read"  # read from a page or photo: not something the owner said
            out.append(FactItem(_safe(f.key, 32), text, status, f"fact:{str(f.id)[:8]}"))
    return out


async def _memories(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, size: int
) -> list[FactItem]:
    rows = (
        await session.execute(
            select(PiMemory.id, PiMemory.kind, PiMemory.content, PiMemory.source_message_id)
            .where(
                *_mine(PiMemory, scope),
                PiMemory.customer_id == customer_id,
                PiMemory.status == "active",
            )
            .order_by(PiMemory.created_at.desc(), PiMemory.id.desc())
            .limit(size)
        )
    ).all()
    return [
        FactItem(
            "memory",
            _safe(r.content, 300),
            "remembered",
            f"memory:{str(r.id)[:8]}",
            msg=str(r.source_message_id) if r.source_message_id else None,
        )
        for r in rows
        if _safe(r.content, 300)
    ]


def _scope_text(scope_json: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = scope_json.get(key)
        if isinstance(value, str) and value.strip():
            return _cap(value, 160)
    return ""


def facts_from_problems(problems: tuple[ProblemItem, ...]) -> list[FactItem]:
    """Facts the owner said, one per problem field, oldest problem first. A pi-inferred cause keeps
    its status and is never owner-confirmed."""
    out: list[FactItem] = []
    for p in problems:
        ref = p.ref
        base = f"problem:{ref}"
        for key, limit in (("budget", p.budget), ("staff", p.staff), ("deadline", p.deadline)):
            if limit:
                out.append(FactItem(key, limit.text, "owner_said", base, ref, limit.msg))
        for limit in p.cannot_change:
            out.append(FactItem("cannot_change", limit.text, "owner_said", base, ref, limit.msg))
        if p.cause_text:
            out.append(FactItem("cause", p.cause_text, p.cause_status or "pi_inferred", base, ref))
        if p.expected_outcome:
            out.append(FactItem("expected_outcome", p.expected_outcome, "owner_said", base, ref))
        if p.systems_mentioned:
            out.append(FactItem("tools", ", ".join(p.systems_mentioned), "owner_said", base, ref))
        if p.person_believes_cause:
            out.append(FactItem("owner_belief", p.person_believes_cause, "owner_said", base, ref))
        if p.requested_solution:
            out.append(
                FactItem("requested_solution", p.requested_solution, "owner_said", base, ref)
            )
        where = _scope_text(p.scope, "where", "location", "city", "branch")
        if where:
            out.append(FactItem("location", where, "owner_said", base, ref))
        for name, blob in (("since", p.since), ("frequency", p.frequency), ("impact", p.impact)):
            text = _scope_text(blob, "text", "value", "raw", "label")
            if text:
                out.append(FactItem(name, text, "owner_said", base, ref))
    return out


# --------------------------------------------------------------------------- build_context


def _with_marker(
    item: SolutionItem, markers: Mapping[tuple[str, int, int], tuple[str, str]]
) -> SolutionItem:
    """A document staff marked delivered reads as delivered, and as verified when staff verified
    it. The marker is the only way a stored solution reads as delivered from this source."""
    match = re.fullmatch(r"(SD|Q)-(\d+)(?:-v(\d+))?", item.ref)
    if match is None or item.kind not in ("document", "quote"):
        return item
    kind = "solution" if match.group(1) == "SD" else "quote"
    found = markers.get((kind, int(match.group(2)), int(match.group(3) or 1)))
    if found is None:
        return item
    return replace(
        item, implementation_status="delivered", delivered_at=found[0], verified_at=found[1]
    )


def _empty_bundle(
    scope: WorkspaceScope,
    customer_id: UUID,
    conversation_id: UUID | None,
    language: str,
    **extra: Any,
) -> ContextBundle:
    return ContextBundle(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        language=language,
        **extra,
    )


async def build_context(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    conversation_id: UUID | None = None,
    query_language: str | None = None,
    limits: Limits | None = None,
) -> ContextBundle:
    """Everything pi already knows about this customer in this workspace. Never raises."""
    lim = limits or Limits()
    language = normalise_language(query_language)
    try:
        return await _build(session, scope, customer_id, conversation_id, query_language, lim)
    except Exception as error:  # noqa: BLE001 - the last line of defence: never raise
        logger.warning("pi_context_failed", extra={"error": type(error).__name__})
        return _empty_bundle(
            scope, customer_id, conversation_id, language, unavailable=("unavailable: context",)
        )


async def _build(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    conversation_id: UUID | None,
    query_language: str | None,
    lim: Limits,
) -> ContextBundle:
    unavailable: list[str] = []
    truncated: list[str] = []
    conversations: list[Any] = await _guard(
        session,
        "conversations",
        unavailable,
        lambda: _conversations(session, scope, customer_id),
        [],
    )
    if len(conversations) > CONVERSATION_FETCH:
        truncated.append("conversations")
        conversations = conversations[:CONVERSATION_FETCH]
    language = normalise_language(
        query_language or next((c.language for c in conversations if c.language), None)
    )
    known_ids = {c.id for c in conversations}
    if conversation_id is not None and conversations and conversation_id not in known_ids:
        # the conversation is not this customer's in this workspace: nothing is returned
        return _empty_bundle(scope, customer_id, conversation_id, language)
    live = [c for c in conversations if c.erased != "true"]
    if conversations and not live:
        return _empty_bundle(scope, customer_id, conversation_id, language, erased=True)
    if conversation_id is not None and conversation_id not in {c.id for c in live}:
        return _empty_bundle(scope, customer_id, conversation_id, language, erased=True)
    all_ids = [c.id for c in conversations]

    # (a) messages: previous conversations (newest first, capped), then the current one
    current_id = conversation_id or (live[0].id if live else None)
    previous = [c for c in live if c.id != current_id][: lim.previous_conversations]
    if len([c for c in live if c.id != current_id]) > lim.previous_conversations:
        truncated.append("previous_conversations")
    messages: list[MessageItem] = []
    for conv in reversed(previous):
        rows = await _guard(
            session,
            "messages",
            unavailable,
            partial(_owner_messages, session, scope, conv.id, lim.messages_per_previous),
            [],
        )
        items, cut = _message_items(rows, lim.messages_per_previous, lim.chars_per_text, False)
        messages += items
        if cut and "messages" not in truncated:
            truncated.append("messages")
    if current_id is not None:
        rows = await _guard(
            session,
            "messages",
            unavailable,
            lambda: _owner_messages(session, scope, current_id, lim.messages),
            [],
        )
        items, cut = _message_items(rows, lim.messages, lim.chars_per_text, True)
        messages += items
        if cut and "messages" not in truncated:
            truncated.append("messages")
    total = sum(len(m.text) for m in messages)
    while messages and total > lim.total_chars:
        total -= len(messages[0].text)
        messages.pop(0)  # the oldest goes first
        if "messages" not in truncated:
            truncated.append("messages")
    messages_t = tuple(messages)

    # (b) problems with the B2a columns
    requirements_available = True
    problems: tuple[ProblemItem, ...] = ()
    got = await _guard(
        session,
        "problems",
        unavailable,
        lambda: _problems(session, scope, customer_id, lim.problems),
        None,
    )
    if got is not None:
        rows, requirements_available = got
        if len(rows) > lim.problems:
            truncated.append("problems")
        problems = tuple(_problem_item(r, requirements_available) for r in rows[: lim.problems])
        if not requirements_available:
            unavailable.append("unavailable: requirements")
    refs = {p.id: p.ref for p in problems}
    ref_by_str = {str(k): v for k, v in refs.items()}

    # (f) corrections from the stored revision history
    corrections: tuple[CorrectionHistory, ...] = ()
    revision_rows = await _guard(
        session, "corrections", unavailable, lambda: _revisions(session, scope, list(refs)), []
    )
    if revision_rows:
        current_values: dict[UUID, dict[str, Any]] = {}
        for p in problems:
            current_values[p.id] = {
                "title": p.title,
                "summary": p.summary,
                "trigger": p.trigger,
                "current_workaround": p.current_workaround,
                "who_notices": p.who_notices,
                "person_believes_cause": p.person_believes_cause,
                "requested_solution": p.requested_solution,
                "frequency": p.frequency,
                "since": p.since,
                "impact": p.impact,
                "scope": p.scope,
                "systems_mentioned": list(p.systems_mentioned),
                "constraints.budget": {"text": p.budget.text, "msg": p.budget.msg}
                if p.budget
                else None,
                "constraints.staff": {"text": p.staff.text, "msg": p.staff.msg}
                if p.staff
                else None,
                "constraints.deadline": {"text": p.deadline.text, "msg": p.deadline.msg}
                if p.deadline
                else None,
            }
        built, cut = _revision_corrections(revision_rows, refs, current_values, lim.corrections)
        corrections = tuple(built)
        if cut:
            truncated.append("corrections")

    # (c) solution records and (e) decisions
    solutions: tuple[SolutionItem, ...] = ()
    decisions: list[DecisionItem] = []
    got_solutions = await _guard(
        session,
        "solutions",
        unavailable,
        lambda: _solutions(session, scope, customer_id, live, ref_by_str, lim.solutions),
        None,
    )
    if got_solutions is not None:
        sol, dec, cut = got_solutions
        solutions = tuple(sol)
        decisions += dec
        if cut:
            truncated.append("solutions")
    decisions += await _guard(
        session,
        "decisions",
        unavailable,
        lambda: _offer_and_open_decisions(session, scope, customer_id, all_ids, lim.decisions),
        [],
    )
    decisions += await _guard(
        session,
        "decision_ledger",
        unavailable,
        lambda: memory_ledger_read.read_decisions(session, scope, customer_id, lim.decisions),
        [],
    )
    decisions.sort(key=lambda d: (d.at, d.kind, d.ref), reverse=True)
    if len(decisions) > lim.decisions:
        truncated.append("decisions")
    decisions_t = tuple(decisions[: lim.decisions])

    markers = await _guard(
        session,
        "delivery_markers",
        unavailable,
        lambda: memory_ledger_read.read_markers(session, scope, customer_id),
        {},
    )
    if markers:
        solutions = tuple(_with_marker(s, markers) for s in solutions)

    # (d) stored files
    files: tuple[FileItem, ...] = ()
    got_files = await _guard(
        session, "files", unavailable, lambda: _files(session, scope, customer_id, lim.files), None
    )
    if got_files is not None:
        files = tuple(got_files[0])
        if got_files[1]:
            truncated.append("files")
        refs = await _guard(
            session,
            "document_texts",
            unavailable,
            lambda: memory_ledger_read.read_text_refs(session, scope, customer_id),
            {},
        )
        if refs:
            files = tuple(
                replace(f, text_refs=refs[f.id], text_available=True) if f.id in refs else f
                for f in files
            )

    # (e) tried and rejected
    stored_rejections: list[RejectionItem] = []
    stored_tried: list[TriedEntry] = []
    got_ideas = await _guard(
        session,
        "rejections",
        unavailable,
        lambda: _idea_memory(session, scope, customer_id, lim.rejections),
        None,
    )
    if got_ideas is not None:
        stored_rejections, stored_tried = got_ideas
    ledger_rejections = await _guard(
        session,
        "rejection_ledger",
        unavailable,
        lambda: memory_ledger_read.read_rejections(session, scope, customer_id, lim.rejections),
        [],
    )
    rejections = tuple(
        (ledger_rejections + stored_rejections + list(scan_rejections(messages_t, lim.rejections)))[
            : lim.rejections
        ]
    )
    tried = tuple(
        [t for p in problems for t in p.tried]
        + stored_tried
        + list(scan_tried(messages_t, lim.rejections))
    )

    # (f) facts
    facts = facts_from_problems(problems)
    facts += await _guard(
        session,
        "facts",
        unavailable,
        lambda: _profile_facts(session, scope, customer_id, lim.facts),
        [],
    )
    facts += await _guard(
        session,
        "memory",
        unavailable,
        lambda: _memories(session, scope, customer_id, lim.facts),
        [],
    )
    if len(facts) > lim.facts:
        truncated.append("facts")
    logger.info(
        "pi_context_built",
        extra={
            "messages": len(messages_t),
            "problems": len(problems),
            "solutions": len(solutions),
            "unavailable": len(unavailable),
        },
    )
    return ContextBundle(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        conversation_id=conversation_id,
        language=language,
        messages=messages_t,
        problems=problems,
        corrections=corrections,
        solutions=solutions,
        files=files,
        tried=tried,
        rejections=rejections,
        decisions=decisions_t,
        facts=tuple(facts[: lim.facts]),
        requirements_available=requirements_available,
        unavailable=tuple(dict.fromkeys(unavailable)),
        truncated=tuple(dict.fromkeys(truncated)),
    )


# --------------------------------------------------------------------------- pure readers

_ALIASES = {
    "budget": "budget",
    "cost": "budget",
    "price": "budget",
    "staff": "staff",
    "team": "staff",
    "employees": "staff",
    "deadline": "deadline",
    "when": "deadline",
    "timeline": "deadline",
    "location": "location",
    "where": "location",
    "city": "location",
    "tools": "tools",
    "systems": "tools",
    "software": "tools",
    "tried": "tried",
    "attempts": "tried",
    "expected_outcome": "expected_outcome",
    "outcome": "expected_outcome",
    "goal": "expected_outcome",
    "cause": "cause",
    "root_cause": "cause",
}
ANSWER_KEYS = (
    "budget",
    "staff",
    "deadline",
    "location",
    "tools",
    "tried",
    "expected_outcome",
    "cause",
)
_ELIGIBLE = (*OWNER_STATUSES, "remembered")  # a pi guess (pi_inferred) or a page read never answers


def answered_from_records(question_key: str, bundle: ContextBundle | None) -> Answer | None:
    """The stored value that already answers `question_key`, with its source, or None. A pi-inferred
    cause or a page-read fact does NOT count as answered (it must still be asked or confirmed).
    Owner-said beats remembered; later problems beat earlier ones. Never raises."""
    try:
        if bundle is None or bundle.erased:
            return None
        key = _ALIASES.get(str(question_key).strip().lower().replace(" ", "_"))
        if key is None:
            return None
        if key == "tried":
            stored = [t for t in bundle.tried if not t.derived]
            pool = stored or list(bundle.tried)
            if not pool:
                return None
            t = pool[-1] if stored else pool[0]
            value = t.what + (f" - {t.outcome}" if t.outcome else "")
            status = "derived" if t.derived else "owner_said"
            return Answer(
                "tried",
                value,
                "problems" if t.problem_ref else "messages",
                t.problem_ref or (t.msg or ""),
                status,
                t.msg,
                t.problem_ref,
            )
        best: tuple[int, int, FactItem] | None = None
        for index, fact in enumerate(bundle.facts):
            if fact.key != key or fact.status not in _ELIGIBLE or not fact.value:
                continue
            rank = (1 if fact.owner_confirmed else 0, index)
            if best is None or rank > (best[0], best[1]):
                best = (rank[0], rank[1], fact)
        if best is None:
            return None
        f = best[2]
        source = "problems" if f.ref.startswith("problem:") else "facts"
        return Answer(key, f.value, source, f.ref, f.status, f.msg, f.problem_ref)
    except Exception:  # noqa: BLE001
        return None


_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "budget": "budget",
        "staff": "team size",
        "deadline": "deadline",
        "location": "location",
        "tools": "tools",
        "tried": "what you tried",
        "expected_outcome": "what you want to achieve",
        "cause": "the cause you described",
    },
    "roman_ur": {
        "budget": "budget",
        "staff": "team ka size",
        "deadline": "deadline",
        "location": "location",
        "tools": "tools",
        "tried": "jo aap ne try kiya",
        "expected_outcome": "aap ka maqsad",
        "cause": "wajah jo aap ne batayi",
    },
    "ur": {
        "budget": "بجٹ",
        "staff": "ٹیم کا سائز",
        "deadline": "ڈیڈ لائن",
        "location": "مقام",
        "tools": "ٹولز",
        "tried": "جو آپ نے آزمایا",
        "expected_outcome": "آپ کا مقصد",
        "cause": "وجہ جو آپ نے بتائی",
    },
    "ar": {
        "budget": "الميزانية",
        "staff": "حجم الفريق",
        "deadline": "الموعد النهائي",
        "location": "الموقع",
        "tools": "الأدوات",
        "tried": "ما جربتموه",
        "expected_outcome": "ما تريدون تحقيقه",
        "cause": "السبب الذي ذكرتموه",
    },
}
_KNOWN_TEMPLATE = {
    "en": "We already have from before: {items}.",
    "roman_ur": "Pehle se hamare paas hai: {items}.",
    "ur": "پہلے سے ہمارے پاس موجود ہے: {items}۔",
    "ar": "لدينا من قبل: {items}.",
}
_SEP = {"en": ", ", "roman_ur": ", ", "ur": "، ", "ar": "، "}


def what_is_already_known(bundle: ContextBundle | None, language: str | None = None) -> str:
    """One short line naming WHAT is already known (never the values), in the owner's language, from
    fixed templates (no question, no promise, no price). "" when nothing is known."""
    try:
        if bundle is None or bundle.erased:
            return ""
        lang = normalise_language(language or bundle.language)
        labels = [
            _LABELS[lang][k] for k in ANSWER_KEYS if answered_from_records(k, bundle) is not None
        ]
        if not labels:
            return ""
        return _KNOWN_TEMPLATE[lang].format(items=_SEP[lang].join(labels))
    except Exception:  # noqa: BLE001
        return ""


_SUMMARY = {
    "en": ("Proposed, not built yet", "In progress", "Delivered"),
    "roman_ur": ("Tajweez hui, abhi bani nahi", "Kaam jaari hai", "Mukammal ho chuka"),
    "ur": ("تجویز کیا گیا، ابھی بنایا نہیں گیا", "کام جاری ہے", "مکمل ہو چکا"),
    "ar": ("مقترح ولم يُنفَّذ بعد", "قيد التنفيذ", "تم التسليم"),
}
SUMMARY_ITEMS = 5


def implementation_summary(bundle: ContextBundle | None, language: str | None = None) -> str:
    """Proposed vs in progress vs delivered, each item with its exact stored state. A proposed
    solution is never worded as done. "" when there are no solution records."""
    try:
        if bundle is None or bundle.erased or not bundle.solutions:
            return ""
        lang = normalise_language(language or bundle.language)
        proposed_label, progress_label, done_label = _SUMMARY[lang]
        groups: tuple[list[str], list[str], list[str]] = ([], [], [])
        for s in bundle.solutions:
            line = f"{s.ref} ({s.stored_state or s.implementation_status})"
            if s.implementation_status in IMPLEMENTED_STATES:
                groups[2].append(line)
            elif s.implementation_status in IN_PROGRESS_STATES:
                groups[1].append(line)
            else:
                groups[0].append(line)
        parts = []
        for label, lines in zip((proposed_label, progress_label, done_label), groups, strict=True):
            if lines:
                parts.append(f"{label}: {', '.join(lines[:SUMMARY_ITEMS])}.")
        return " ".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def known_records(bundle: ContextBundle | None) -> list[dict[str, Any]]:
    """The compact view for the selector: [{source, text, scope ids, kind, status, ref}], in a fixed
    order (facts, problems, corrections, solutions, tried, rejections, decisions, files, messages).
    A record found by a scan has status "derived"; a pi guess keeps "pi_inferred"."""
    if bundle is None:
        return []
    ids = {
        "tenant_id": str(bundle.tenant_id),
        "environment_id": str(bundle.environment_id),
        "customer_id": str(bundle.customer_id),
        "conversation_id": str(bundle.conversation_id) if bundle.conversation_id else None,
    }
    out: list[dict[str, Any]] = []

    def add(source: str, text: str, kind: str, status: str, ref: str) -> None:
        if text:
            out.append(
                {"source": source, "text": text, "kind": kind, "status": status, "ref": ref, **ids}
            )

    try:
        for f in bundle.facts:
            add("facts", f"{f.key}: {f.value}", f.key, f.status, f.ref)
        for p in bundle.problems:
            add("problems", f"{p.ref} {p.title}", "problem", p.status, f"problem:{p.ref}")
        for c in bundle.corrections:
            prior = "; ".join(str(v.value) for v in c.prior)
            add(
                "corrections",
                f"{c.problem_ref} {c.field}: {c.current} (before: {prior})",
                "correction",
                "confirmed",
                f"problem:{c.problem_ref}",
            )
        for s in bundle.solutions:
            add(
                "solutions",
                f"{s.kind} {s.ref}: {s.implementation_status}",
                s.kind,
                s.implementation_status,
                s.ref,
            )
        for t in bundle.tried:
            add(
                "problems" if t.problem_ref else "messages",
                t.what + (f" - {t.outcome}" if t.outcome else ""),
                "tried",
                "derived" if t.derived else "owner_said",
                t.problem_ref or (t.msg or ""),
            )
        for r in bundle.rejections:
            if r.status in ("reversed", "expired"):
                taken = f"{r.text} (taken back: {r.status})"
                add("rejections", taken, "rejection", r.status, r.ref)
                continue
            add("rejections", r.text, "rejection", "derived" if r.derived else "owner_said", r.ref)
        for d in bundle.decisions:
            line = f"{d.kind} {d.ref}: {d.status}"
            if d.actor:  # a ledger decision: the words and where they came from
                line += (f' - "{d.text}"' if d.text else "") + f" ({d.source})"
            add("decisions", line, d.kind, d.status, d.ref)
        for fl in bundle.files:
            add("files", fl.name, "file", "stored", f"file:{str(fl.id)[:8]}")
        for m in bundle.messages:
            add("messages", m.text, "message", "owner_said", f"msg:{m.id}")
    except Exception:  # noqa: BLE001
        return out
    return out
