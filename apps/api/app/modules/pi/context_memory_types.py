"""PS-8: what pi already knows about one owner, as plain frozen dataclasses (no DB, no model).

`context_memory.build_context` fills a `ContextBundle`; pure helpers in `context_memory` read it.
Spec: platform v1.6 section 18.5 (alreadyAnswered), brain v3 R-MEM-01..06 (memory, corrections
keep history), R-PRIV-06 (erase), R-ISO tenant and contact isolation.

Rules the types carry:
* An owner-confirmed fact (`status` owner_said / confirmed) is never mixed with a pi hypothesis
  (`pi_inferred`, `derived`): every record names its status and whether it was derived by a scan.
* `SolutionItem.implementation_status` is the exact stored state. A proposed solution is never
  "implemented"; only the stored states in `IMPLEMENTED_STATES` mean the work happened.
* Every text here was redacted when it was stored; nothing is ever un-redacted.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

# Statuses that mean the owner said it or agreed to it. Anything else is pi's own guess or a
# derived reading and must be worded as such.
OWNER_STATUSES = ("owner_said", "confirmed")

# exact stored states of a solution record, from the first to the last
IMPLEMENTED_STATES = ("delivered",)
IN_PROGRESS_STATES = ("kickoff", "in_build")
PROPOSED_STATES = (
    "not_offered",
    "proposed",
    "awaiting_payment",
    "payment_claimed",
    "payment_failed",
    "paid",
    "drafted",
    "in_review",
    "reviewer_approved",
    "issued",
    "accepted",
    "declined",
    "changes_asked",
    "superseded",
)

SOURCES = (
    "messages",
    "problems",
    "requirements",
    "corrections",
    "solutions",
    "files",
    "rejections",
    "decisions",
    "facts",
)


@dataclass(frozen=True, slots=True)
class MessageItem:
    id: UUID
    conversation_id: UUID
    at: str  # ISO time
    text: str  # the owner's own words (text or voice transcript), never pi's reply
    current: bool  # in the conversation being served
    message_type: str = "text"


@dataclass(frozen=True, slots=True)
class LimitItem:
    text: str
    msg: str | None = None


@dataclass(frozen=True, slots=True)
class TriedEntry:
    what: str
    outcome: str = ""
    msg: str | None = None
    problem_ref: str = ""
    derived: bool = False  # True: found by a scan of owner messages, not a stored field


@dataclass(frozen=True, slots=True)
class ProblemItem:
    """One noted problem with every stored field (the 30-field record plus the B2a columns)."""

    id: UUID
    number: int
    title: str
    status: str
    category: str
    summary: str = ""
    subtype: str = ""
    conversation_id: UUID | None = None
    user_words: tuple[str, ...] = ()
    systems_mentioned: tuple[str, ...] = ()
    scope: dict[str, Any] = field(default_factory=dict)
    frequency: dict[str, Any] = field(default_factory=dict)
    since: dict[str, Any] = field(default_factory=dict)
    impact: dict[str, Any] = field(default_factory=dict)
    trigger: str = ""
    current_workaround: str = ""
    who_notices: str = ""
    person_believes_cause: str = ""
    requested_solution: str = ""
    severity_stated: str = "unknown"
    source_message_ids: tuple[str, ...] = ()
    revision: int = 1
    # B2a (migration 0053). None means "not said"; `requirements_available` tells "not said" from
    # "could not read" for the whole bundle.
    budget: LimitItem | None = None
    staff: LimitItem | None = None
    deadline: LimitItem | None = None
    cannot_change: tuple[LimitItem, ...] = ()
    tried: tuple[TriedEntry, ...] = ()
    cause_text: str = ""
    cause_status: str = ""  # owner_said | confirmed | pi_inferred | "" (no cause)
    expected_outcome: str = ""

    @property
    def ref(self) -> str:
        return f"P{self.number}"


@dataclass(frozen=True, slots=True)
class PriorValue:
    value: Any
    revision: int
    reason: str
    by: str
    at: str
    msg: str | None = None  # the message the corrected value came from, when it was stored


@dataclass(frozen=True, slots=True)
class CorrectionHistory:
    """One field of one problem that was changed: the value now, and every earlier value."""

    problem_ref: str
    field: str
    current: Any
    prior: tuple[PriorValue, ...]  # oldest first; never deleted


@dataclass(frozen=True, slots=True)
class SolutionItem:
    kind: str  # document | quote | box | deal_document | payment | kickoff
    ref: str
    implementation_status: str  # the exact stored state (see the *_STATES tuples)
    stored_state: str  # the raw value in the table, for audit
    at: str = ""
    problem_refs: tuple[str, ...] = ()
    total: str = ""
    currency: str = ""
    conversation_id: UUID | None = None
    reviewer_approved: bool = False

    @property
    def implemented(self) -> bool:
        return self.implementation_status in IMPLEMENTED_STATES

    @property
    def in_progress(self) -> bool:
        return self.implementation_status in IN_PROGRESS_STATES


@dataclass(frozen=True, slots=True)
class FileItem:
    id: UUID
    name: str
    mime: str
    size: int
    source: str
    at: str
    # Stored extracted text. The repo keeps none for customer files (bytes only), so this is
    # empty; it is filled only when a text source is added later.
    text: str = ""
    text_available: bool = False


@dataclass(frozen=True, slots=True)
class RejectionItem:
    text: str
    ref: str
    derived: bool  # True: found by a scan of owner messages (a reading, not a stored decision)
    problem_ref: str = ""
    at: str = ""


@dataclass(frozen=True, slots=True)
class DecisionItem:
    kind: str  # offer | approval | box_move | document | open_item
    ref: str
    status: str  # pending | approved | declined | allowed | blocked | open | answered ...
    text: str = ""
    at: str = ""


@dataclass(frozen=True, slots=True)
class FactItem:
    key: str  # budget, staff, deadline, location, tools, business, ...
    value: str
    status: str  # owner_said | confirmed | pi_inferred | page_read | remembered
    ref: str
    problem_ref: str = ""
    msg: str | None = None

    @property
    def owner_confirmed(self) -> bool:
        return self.status in OWNER_STATUSES


@dataclass(frozen=True, slots=True)
class Limits:
    """Caps. Every cap that bites sets a flag in `ContextBundle.truncated`."""

    messages: int = 40
    previous_conversations: int = 3
    messages_per_previous: int = 12
    problems: int = 20
    solutions: int = 20
    files: int = 20
    rejections: int = 20
    decisions: int = 30
    facts: int = 40
    corrections: int = 40
    chars_per_text: int = 600
    total_chars: int = 24000


@dataclass(frozen=True, slots=True)
class Answer:
    """A stored value that answers a question, with where it came from (so nobody re-asks)."""

    key: str
    value: str
    source: str  # a SOURCES name
    ref: str
    status: str
    msg: str | None = None
    problem_ref: str = ""

    @property
    def owner_confirmed(self) -> bool:
        return self.status in OWNER_STATUSES


@dataclass(frozen=True, slots=True)
class ContextBundle:
    tenant_id: UUID
    environment_id: UUID
    customer_id: UUID
    conversation_id: UUID | None = None
    erased: bool = False
    language: str = "en"
    messages: tuple[MessageItem, ...] = ()
    problems: tuple[ProblemItem, ...] = ()
    corrections: tuple[CorrectionHistory, ...] = ()
    solutions: tuple[SolutionItem, ...] = ()
    files: tuple[FileItem, ...] = ()
    tried: tuple[TriedEntry, ...] = ()
    rejections: tuple[RejectionItem, ...] = ()
    decisions: tuple[DecisionItem, ...] = ()
    facts: tuple[FactItem, ...] = ()
    requirements_available: bool = True
    unavailable: tuple[str, ...] = ()  # "unavailable: <source>" for every failed sub-query
    truncated: tuple[str, ...] = ()  # names of the sources a cap cut

    @property
    def empty(self) -> bool:
        return not (
            self.messages
            or self.problems
            or self.solutions
            or self.files
            or self.rejections
            or self.decisions
            or self.facts
        )

    def to_dict(self) -> dict[str, Any]:
        def plain(value: Any) -> Any:
            if hasattr(value, "__dataclass_fields__"):
                return {k: plain(getattr(value, k)) for k in value.__dataclass_fields__}
            if isinstance(value, UUID):
                return str(value)
            if isinstance(value, dict):
                return {str(k): plain(v) for k, v in value.items()}
            if isinstance(value, tuple | list):
                return [plain(v) for v in value]
            return value

        return {k: plain(getattr(self, k)) for k in self.__dataclass_fields__}

    def known_records(self) -> list[dict[str, Any]]:
        """The compact view Agent 4's selector reads: a list of
        {source, text, scope ids, kind, status, ref}. Owner-confirmed and pi-guess records are told
        apart by `status`; a derived record says so in `status` ("derived")."""
        from app.modules.pi.context_memory import known_records

        return known_records(self)
