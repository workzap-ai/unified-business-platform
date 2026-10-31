# ruff: noqa: E501
"""PS-10: the typed records of the self-review gate.

Spec: platform spec v1.6 section 18 "checks run in code before every send; on failure regenerate with
the reason; fail twice means a safe fallback plus a human alert" (v1.6 lines 10194 and 3643), and the
rules turnCoverage, noAssumedIndustry, canOffer, alreadyAnswered, noEmptyOpener (v1.6 18.3, 18.5).

Pure data: no database, no model, no wording rules. `None` on an optional input means "the caller did
not supply it" (which is UNKNOWN, never PASS); an empty tuple means "supplied, and there are none".
Nothing here is wired into the conversation: the flow lead calls `self_review.review` between the
draft and the send.
"""

from __future__ import annotations

from dataclasses import dataclass

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"
STATUSES = (PASS, FAIL, NOT_APPLICABLE, UNKNOWN)

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"
BLOCKED = "BLOCKED"  # an unknown in a critical check (the spec's BLOCKED_UNKNOWN)
VERDICTS = (COMPLETE, INCOMPLETE, BLOCKED)

LANGS = ("en", "roman_ur", "ur", "ar")

# Relevance verdict kinds (the PS-3 idea filter's vocabulary).
LINKED = "LINKED"
UNLINKED = "UNLINKED"
GENERIC = "GENERIC"
REPEATS_TRIED = "REPEATS_TRIED"
VIOLATES = "VIOLATES"
REL_UNKNOWN = "UNKNOWN"
RELEVANCE_KINDS = (LINKED, UNLINKED, GENERIC, REPEATS_TRIED, VIOLATES, REL_UNKNOWN)

# Fact and cause statuses.
OWNER_SAID = "owner_said"
CONFIRMED = "confirmed"
PI_INFERRED = "pi_inferred"
HYPOTHESIS = "hypothesis"
GROUNDED_FACT = (OWNER_SAID, CONFIRMED)
CAUSE_STATUSES = (OWNER_SAID, CONFIRMED, PI_INFERRED, HYPOTHESIS)

# Constraint gate statuses.
SATISFIED = "satisfied"
VIOLATED = "violated"
GATE_UNKNOWN = "unknown"
GATE_STATUSES = (SATISFIED, VIOLATED, GATE_UNKNOWN)

CONTEXT_SOURCES = (
    "conversation",
    "problems",
    "solutions",
    "documents",
    "tried",
    "rejected",
    "decisions",
)

# Caps: every input is cut to these before it is read, so the work is linear in what is looked at.
MAX_TEXT = 4000
MAX_ITEMS = 50
MAX_ITEM_TEXT = 400


@dataclass(frozen=True)
class ContextIn:
    retrieved: bool | None = None
    sources: tuple[str, ...] = ()
    records_exist: bool | None = None


@dataclass(frozen=True)
class ProblemIn:
    id: str
    title: str = ""
    owner_worded: bool = False  # the title uses the owner's words, not only a keyword category
    fact_count: int = 0  # stated facts (figures, since, how often) held for this problem


@dataclass(frozen=True)
class FactIn:
    text: str
    status: str = ""  # owner_said / confirmed / pi_inferred


@dataclass(frozen=True)
class CauseIn:
    id: str
    text: str = ""
    status: str = ""  # owner_said / confirmed / pi_inferred / hypothesis
    evidence: tuple[str, ...] = ()
    problem_id: str = ""


@dataclass(frozen=True)
class ConstraintIn:
    id: str
    text: str = ""
    gate: str = ""  # satisfied / violated / unknown ("" = no status given)
    shown: str = ""  # how the draft shows it: satisfied / clear / approved / unknown / ""


@dataclass(frozen=True)
class OptionIn:
    id: str
    text: str = ""
    gate: str = ""  # aggregate constraint gate: satisfied / violated / unknown / "" (not given)
    relevance: str = ""  # LINKED / UNLINKED / GENERIC / REPEATS_TRIED / UNKNOWN / VIOLATES
    rank: int = 0
    viable: bool = True  # listed to the owner as a workable option
    addresses: tuple[str, ...] = ()  # problem ids this option addresses
    cause_id: str = ""  # the root cause this option addresses
    labelled_unchecked: bool = False  # the draft says "not yet checked" for this option
    learn_first: bool = False  # the draft presents it as a learn-first step
    improves_on_tried: bool = False  # the draft labels what is different from a failed attempt


@dataclass(frozen=True)
class BlueprintIn:
    sections: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    none_known_dependencies: bool = False
    none_known_risks: bool = False
    unlinked_items: tuple[str, ...] = ()  # items not tied to a problem, constraint or cause
    unknowns: tuple[str, ...] = ()  # the blueprint's own list of what is not yet known


@dataclass(frozen=True)
class QuestionsIn:
    count: int | None = None
    last_sentence: str = ""
    already_answered: bool = False  # the question asks what the records already answer


@dataclass(frozen=True)
class DraftResult:
    """What the flow is about to say, as structure. Every field is optional."""

    owner_language: str = ""  # en / roman_ur / ur / ar
    owner_script: str = ""  # latin / arabic (used only when owner_language is empty)
    owner_text: str = ""  # the owner's latest message (used only when both are empty)
    reply_text: str = ""
    reply_language: str = ""  # what the caller says the reply is in (never trusted alone)
    kind: str = ""  # question / solution / blueprint / ""
    context: ContextIn | None = None
    noted_problems: tuple[ProblemIn, ...] | None = None
    connected_problems: tuple[tuple[str, str], ...] = ()
    problems_unrelated: bool = False
    main_problem_id: str = ""
    facts: tuple[FactIn, ...] | None = None
    root_causes: tuple[CauseIn, ...] | None = None
    stored_constraint_ids: tuple[str, ...] | None = None
    constraints: tuple[ConstraintIn, ...] | None = None  # the constraint table in the draft
    options: tuple[OptionIn, ...] = ()
    recommended: OptionIn | None = None
    tried_solutions: tuple[str, ...] | None = None
    blueprint: BlueprintIn | None = None
    questions: QuestionsIn | None = None
    next_steps: int | None = None  # how many next steps the draft gives the owner
    implementation_status: str = ""  # proposed / approved / implemented / "" (= proposed)


@dataclass(frozen=True)
class CheckResult:
    id: str
    name: str
    status: str
    evidence: tuple[str, ...] = ()
    repair: str = ""  # a repair code, see self_review.REPAIRS
    repair_arg: str = ""
    tag: str = ""  # "claim" marks the SR-14 invented-claim failure (critical)


@dataclass(frozen=True)
class ReviewReport:
    checks: tuple[CheckResult, ...]
    verdict: str
    reasons: tuple[str, ...]
    next_actions: tuple[str, ...]  # at most one: the single most useful repair
    repair_code: str = ""
    repair_arg: str = ""
    warnings: tuple[str, ...] = ()  # non-critical failures

    def by_id(self, check_id: str) -> CheckResult | None:
        for c in self.checks:
            if c.id == check_id:
                return c
        return None
