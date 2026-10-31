"""L2-3: the typed records of a solution blueprint's options part (design: docs/pi-saas/
pi-solution-blueprint-design.md section 3, "Part B: options, compared").

Pure data, no database, no model, no wording. Language-neutral: ids, enums and short texts that a
later step writes in the owner's language. The rules live in `blueprint_rules`. Nothing here is
wired into the conversation or the document yet.

  Option         one thing the owner could do or Workzap could build, with its fit, trade-offs,
                 dependencies, risks, expected outcome, effort class, evidence refs and status
  OptionSet      the options compared for an offer, with the honest "single option" flag
  RootCause      the cause of a problem: text, status (pi_inferred / owner_said / confirmed) and
                 the evidence for and against; never confirmed without the owner
  ConstraintsView  what the owner said they can and cannot do (the B2a JSON shapes of
                 `problem_fields`: constraints, tried, cause), read into one typed view

The cost of an option always comes from staff: `Cost.amount` is None in every record pi writes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.modules.pi import problem_fields as pf

KINDS = ("owner_action", "process_change", "workzap_build", "custom_automation", "learn_first")
BUILD_KINDS = ("workzap_build", "custom_automation")
LEARN_FIRST = "learn_first"
EFFORTS = ("none", "small", "medium", "large")  # smallest first
REVERSIBILITY = ("reversible", "partly", "hard")  # easiest to undo first
STATUSES = ("recommended", "alternative", "rejected")
CHECK_RESULTS = ("ok", "violates", "unknown")
DEPENDENCY_KINDS = ("owner_input", "access", "data", "person", "other_option", "other")
RISK_LEVELS = ("low", "medium", "high")
CAUSE_STATUSES = pf.CAUSE_STATUSES
OWNER_STATUSES = pf.OWNER_STATUSES
EVIDENCE_CAP = 3  # evidence strength is a small count, never a score to game
COST_SOURCE = "staff"


@dataclass(frozen=True)
class Evidence:
    """Where the owner said it: a message id and the owner's own words from it."""

    msg: str
    words: tuple[str, ...] = ()


@dataclass(frozen=True)
class Fit:
    """How the option links to the problem (filled by code, never by the model)."""

    problem_link: tuple[str, ...] = ()
    facts_reused: tuple[str, ...] = ()  # message ids of owner facts the option reuses
    generic: bool = False


@dataclass(frozen=True)
class Dependency:
    kind: str
    text: str
    blocking: bool = False


@dataclass(frozen=True)
class Risk:
    text: str
    level: str = "low"


@dataclass(frozen=True)
class ConstraintCheck:
    """One stated constraint checked against the option: "budget", "staff", "deadline",
    "cannot_change#2", "tried#1" (see `ConstraintsView.labels`)."""

    constraint: str
    result: str
    why: str = ""


@dataclass(frozen=True)
class Cost:
    """The source is always staff and the amount is never pi's: it stays None."""

    source: str = COST_SOURCE
    amount: None = None


@dataclass(frozen=True)
class Option:
    id: str
    kind: str
    what: str
    addresses: tuple[str, ...]  # ids of the stated problems it answers
    benefit: str
    effort: str
    reversibility: str
    status: str = "alternative"
    works_on: tuple[str, ...] = ()  # hypothesis ids it relies on
    catalogue_key: str | None = None
    fit: Fit = field(default_factory=Fit)
    limits: tuple[str, ...] = ()
    trade_offs: tuple[str, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    risks: tuple[Risk, ...] = ()
    constraint_checks: tuple[ConstraintCheck, ...] = ()
    expected_outcome: str = ""  # the owner's own words (B2a); never pi's claim
    evidence: tuple[Evidence, ...] = ()
    rejected_because: str = ""
    cost: Cost = field(default_factory=Cost)

    @property
    def blocking_dependencies(self) -> tuple[Dependency, ...]:
        return tuple(d for d in self.dependencies if d.blocking)

    @property
    def violated(self) -> tuple[ConstraintCheck, ...]:
        return tuple(c for c in self.constraint_checks if c.result == "violates")

    @property
    def unknown_checks(self) -> tuple[ConstraintCheck, ...]:
        return tuple(c for c in self.constraint_checks if c.result == "unknown")

    @property
    def evidence_strength(self) -> int:
        """How many distinct owner messages back this option: refs that carry words, plus reused
        facts, each message once, capped at EVIDENCE_CAP. A ref with no words proves nothing."""
        said = {e.msg for e in self.evidence if e.words}
        return min(len(said | set(self.fit.facts_reused)), EVIDENCE_CAP)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = _plain(asdict(self))
        return data


@dataclass(frozen=True)
class OptionSet:
    """The options compared for one offer. `single_option` is the honest flag for "the evidence
    supports only one"; `none_reason` is the honest reason when no option fits."""

    options: tuple[Option, ...]
    recommended_id: str | None = None
    single_option: bool = False
    single_reason: str = ""
    none_reason: str = ""


@dataclass(frozen=True)
class RootCause:
    """The cause of a problem. `evidence_for` and `evidence_against` are kept apart from the text;
    a hypothesis never writes into the evidence. The status can only be raised by the owner."""

    text: str
    status: str = pf.PI_INFERRED
    evidence_for: tuple[Evidence, ...] = ()
    evidence_against: tuple[Evidence, ...] = ()

    @property
    def stateable(self) -> bool:
        """A reader may state this cause as a fact only when the owner said or confirmed it."""
        return self.status in OWNER_STATUSES

    @classmethod
    def from_b2a(cls, stored: dict[str, Any] | None) -> RootCause | None:
        """Read the stored `problem.cause` ({"text", "status", "evidence": {"msgs", "words"}})."""
        if not stored or not str(stored.get("text") or "").strip():
            return None
        status = str(stored.get("status") or "")
        if status not in CAUSE_STATUSES:
            status = pf.PI_INFERRED  # an unknown status is never trusted
        proof = stored.get("evidence") or {}
        words = tuple(str(w) for w in proof.get("words") or [])
        msgs = [str(m) for m in proof.get("msgs") or []]
        refs = tuple(Evidence(m, words) for m in msgs) or ((Evidence("", words),) if words else ())
        return cls(text=str(stored["text"]).strip(), status=status, evidence_for=refs)


@dataclass(frozen=True)
class Tried:
    what: str
    outcome: str = ""


@dataclass(frozen=True)
class ConstraintsView:
    """What the owner said they can and cannot do, from the B2a columns. Every entry is the
    owner's own statement, so each counts as confirmed for the checks."""

    budget: str = ""
    staff: str = ""
    deadline: str = ""
    cannot_change: tuple[str, ...] = ()
    tried: tuple[Tried, ...] = ()
    cause: RootCause | None = None

    @classmethod
    def from_b2a(
        cls,
        constraints: dict[str, Any] | None,
        tried: list[dict[str, Any]] | None,
        cause: dict[str, Any] | None,
    ) -> ConstraintsView:
        said = constraints or {}

        def scalar(key: str) -> str:
            return str((said.get(key) or {}).get("text") or "").strip()

        return cls(
            budget=scalar("budget"),
            staff=scalar("staff"),
            deadline=scalar("deadline"),
            cannot_change=tuple(
                str(e.get("text")).strip() for e in said.get("cannot_change") or [] if e.get("text")
            ),
            tried=tuple(
                Tried(str(e["what"]).strip(), str(e.get("outcome") or "").strip())
                for e in tried or []
                if e.get("what")
            ),
            cause=RootCause.from_b2a(cause),
        )

    def labels(self) -> tuple[str, ...]:
        """One label per stated constraint, the names a `ConstraintCheck` uses."""
        out = [k for k in pf.SCALAR_KEYS if getattr(self, k)]
        out += [f"cannot_change#{i}" for i in range(1, len(self.cannot_change) + 1)]
        out += [f"tried#{i}" for i in range(1, len(self.tried) + 1)]
        return tuple(out)


def _plain(value: Any) -> Any:
    """Tuples become lists so a record is plain JSON."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    return value
