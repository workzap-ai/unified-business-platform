"""PS-4: the typed records of a solution blueprint.

Design: docs/pi-saas/pi-solution-blueprint-design.md section 5, the software and automation
blueprint.

Pure data: no database, no model, no wording rules. The builder is `blueprint_build`, the honesty
checks are `blueprint_checks`, the text is `blueprint_render`. Nothing here is wired into the
conversation or the documents yet.

Two groups of records:

  INPUT  (`OptionIn`, `StepIn`, `DepIn`, `RiskIn`, `CheckIn`, `ProblemIn`, `ConstraintIn`,
          `TriedIn`, `StaffInputs`): small dataclasses this module owns. They are NOT the L2-3
          option models (`blueprint_models.Option`); `blueprint_build.option_from` is the one
          documented adapter, so the coupling is a single function that reads attributes by name.
  OUTPUT (`Blueprint` and the section records): everything a reader needs, each element carrying
          where it came from. A number that is not in the owner's facts or the staff inputs does not
          get in; money exists only as a staff-supplied `CostLine`.

A blueprint never executes anything: `executes_nothing` is always True and every phase with an
action sits behind an owner approval step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LANGS = ("en", "roman_ur", "ur", "ar")
ROLES = ("owner", "staff", "pi", "reviewer")
READY = "ready"
INSUFFICIENT = "insufficient_information"
REFUSED = "refused"
STATUSES = (READY, INSUFFICIENT, REFUSED)
STEP_KINDS = ("measure", "approval", "action", "review", "rollback")
RESULTS = ("ok", "violates", "unknown")
GROUNDED = "grounded"  # the element comes from the owner, the option or staff
UNKNOWN = "unknown"  # the element says honestly that something is not known yet

# Limits. Every input is cut to these before anything is read, so work is linear in the input
# actually looked at and bounded for any input size.
MAX_TEXT = 300
MAX_FACT_TEXT = 1500
MAX_PROBLEMS = 8
MAX_STEPS = 12
MAX_DEPS = 12
MAX_RISKS = 8
MAX_CONSTRAINTS = 12
MAX_TRIED = 8
MAX_STAFF = 12
MAX_FACT_STRINGS = 200
MAX_PHASES = 4


@dataclass(frozen=True)
class StepIn:
    text: str
    role: str = ""
    done_check: str = ""
    after: tuple[str, ...] = ()
    phase: int = 0
    id: str = ""


@dataclass(frozen=True)
class DepIn:
    kind: str = "other"
    text: str = ""
    blocking: bool = False


@dataclass(frozen=True)
class RiskIn:
    text: str
    level: str = "low"


@dataclass(frozen=True)
class CheckIn:
    constraint: str
    result: str = "unknown"
    why: str = ""


@dataclass(frozen=True)
class OptionIn:
    id: str = ""
    kind: str = ""
    what: str = ""
    addresses: tuple[str, ...] = ()
    benefit: str = ""
    effort: str = ""
    catalogue_key: str = ""
    modules: tuple[str, ...] = ()
    steps: tuple[StepIn, ...] = ()
    dependencies: tuple[DepIn, ...] = ()
    risks: tuple[RiskIn, ...] = ()
    limits: tuple[str, ...] = ()
    checks: tuple[CheckIn, ...] = ()
    expected_outcome: str = ""
    status: str = ""  # recommended | alternative | rejected (empty when not stated)


@dataclass(frozen=True)
class ProblemIn:
    id: str
    title: str = ""
    words: tuple[str, ...] = ()
    figure: str = ""  # the owner's own count or amount of cases, in the owner's words
    frequency: str = ""
    since: str = ""
    expected_outcome: str = ""


@dataclass(frozen=True)
class ConstraintIn:
    label: str
    kind: str  # budget | staff | deadline | cannot_change | other
    text: str
    blocks: tuple[str, ...] = ()  # phrases that, found in a step, make this constraint violated
    hard: bool = True


@dataclass(frozen=True)
class TriedIn:
    what: str
    outcome: str = ""


@dataclass(frozen=True)
class StaffCost:
    item: str
    amount: float
    currency: str
    source: str


@dataclass(frozen=True)
class StaffDuration:
    text: str
    source: str
    step: str = ""  # a step id, or empty for the whole plan


@dataclass(frozen=True)
class StaffInputs:
    costs: tuple[StaffCost, ...] = ()
    durations: tuple[StaffDuration, ...] = ()
    roles: tuple[tuple[str, str], ...] = ()  # (step id, role)
    dropped: tuple[str, ...] = ()  # what was ignored and why (a cost without a source ...)


# ---- output --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Summary:
    text: str
    problem_ids: tuple[str, ...]
    option_id: str = ""


@dataclass(frozen=True)
class Module:
    id: str
    name: str
    problems: tuple[str, ...]
    not_changed: tuple[str, ...] = ()
    source: str = "option"


@dataclass(frozen=True)
class Step:
    id: str
    kind: str
    text: str
    role: str
    done_check: str
    phase: int
    problems: tuple[str, ...] = ()
    source: str = "option"  # option | scaffold (a fixed safety step pi adds in every blueprint)


@dataclass(frozen=True)
class Edge:
    before: str
    after: str


@dataclass(frozen=True)
class ExternalDep:
    id: str
    kind: str
    text: str
    status: str = UNKNOWN  # unknown until the owner supplies it
    blocking: bool = False


@dataclass(frozen=True)
class Responsibility:
    role: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class CostLine:
    item: str
    amount: float | None  # None unless staff supplied it
    currency: str = ""
    source: str = "staff"
    status: str = UNKNOWN  # unknown = "to be quoted by staff"


@dataclass(frozen=True)
class TimeLine:
    item: str  # a step id or "plan"
    duration: str  # "" when nobody gave one
    source: str = ""
    status: str = UNKNOWN  # unknown = "to be estimated by staff"


@dataclass(frozen=True)
class RiskLine:
    text: str
    level: str = "low"
    source: str = "option"  # option | missing_fact


@dataclass(frozen=True)
class Milestone:
    id: str
    name: str
    steps: tuple[str, ...]
    check: str


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    steps: tuple[str, ...]
    verified_by: str = "owner"
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class Measure:
    id: str
    problem: str
    what: str
    baseline: str  # the owner's own figure; "" when it is not known yet
    baseline_source: str  # "owner" or "step <id>" (record it first)
    target: str  # the owner's own words; "" until agreed with the owner
    target_source: str
    measured_by: str = "owner"


@dataclass(frozen=True)
class ConstraintRow:
    label: str
    kind: str
    text: str
    result: str  # ok | violates | unknown
    reason: str
    hard: bool = True


@dataclass(frozen=True)
class Missing:
    code: str
    text: str


@dataclass(frozen=True)
class Blueprint:
    status: str
    language: str
    summary: Summary | None = None
    modules: tuple[Module, ...] = ()
    steps: tuple[Step, ...] = ()
    edges: tuple[Edge, ...] = ()
    external: tuple[ExternalDep, ...] = ()
    responsibilities: tuple[Responsibility, ...] = ()
    costs: tuple[CostLine, ...] = ()
    timeline: tuple[TimeLine, ...] = ()
    risks: tuple[RiskLine, ...] = ()
    unknowns: tuple[str, ...] = ()
    milestones: tuple[Milestone, ...] = ()
    acceptance: tuple[Criterion, ...] = ()
    success: tuple[Measure, ...] = ()
    constraints: tuple[ConstraintRow, ...] = ()
    problem_ids: tuple[str, ...] = ()
    missing: tuple[Missing, ...] = ()
    next_question: str = ""  # one targeted question, only when information is missing
    refusal: tuple[str, ...] = ()
    known_numbers: tuple[str, ...] = field(default=(), compare=False)
    executes_nothing: bool = True

    @property
    def ready(self) -> bool:
        return self.status == READY
