"""L2-1: the owner's structured requirements as plain, frozen dataclasses (no database, no model).

`requirements_read` fills them from the four B2a columns of `pi_problems`; `constraint_check` and
`option_gate` read them. Shapes follow `problem_fields.py`. NULL in the database, or an empty or
malformed value, is "not said": it becomes None or an empty tuple, never a guess.
"""

from dataclasses import dataclass, field
from uuid import UUID

OWNER_STATUSES = ("owner_said", "confirmed")


@dataclass(frozen=True, slots=True)
class Limit:
    """One thing the owner said about a limit: its text, and the message it came from."""

    text: str
    msg: str | None = None


@dataclass(frozen=True, slots=True)
class Constraints:
    budget: Limit | None = None
    staff: Limit | None = None
    deadline: Limit | None = None
    cannot_change: tuple[Limit, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.budget or self.staff or self.deadline or self.cannot_change)


@dataclass(frozen=True, slots=True)
class TriedItem:
    """Something the owner already tried, and what came of it."""

    what: str
    outcome: str = ""
    msg: str | None = None


@dataclass(frozen=True, slots=True)
class Cause:
    text: str
    status: str = "pi_inferred"
    evidence_words: tuple[str, ...] = ()
    evidence_msgs: tuple[str, ...] = ()

    @property
    def owner_said(self) -> bool:
        """True only for a cause the owner said or agreed to; a guess is never a fact."""
        return self.status in OWNER_STATUSES


@dataclass(frozen=True, slots=True)
class ProblemRequirements:
    problem_id: UUID | None = None
    number: int = 0
    title: str = ""
    constraints: Constraints = field(default_factory=Constraints)
    tried: tuple[TriedItem, ...] = ()
    cause: Cause | None = None
    expected_outcome: str = ""

    @property
    def empty(self) -> bool:
        return (
            self.constraints.empty
            and not self.tried
            and self.cause is None
            and not self.expected_outcome
        )


@dataclass(frozen=True, slots=True)
class Requirements:
    """The requirements of every active problem of one customer.

    `columns_available` is False when the database has no 0053 columns yet: the problems tuple is
    then empty, and a caller can tell "nothing said" from "could not read".
    """

    problems: tuple[ProblemRequirements, ...] = ()
    columns_available: bool = True

    @property
    def budgets(self) -> tuple[Limit, ...]:
        return tuple(p.constraints.budget for p in self.problems if p.constraints.budget)

    @property
    def staff(self) -> tuple[Limit, ...]:
        return tuple(p.constraints.staff for p in self.problems if p.constraints.staff)

    @property
    def deadlines(self) -> tuple[Limit, ...]:
        return tuple(p.constraints.deadline for p in self.problems if p.constraints.deadline)

    @property
    def cannot_change(self) -> tuple[Limit, ...]:
        return tuple(limit for p in self.problems for limit in p.constraints.cannot_change)

    @property
    def tried(self) -> tuple[TriedItem, ...]:
        return tuple(t for p in self.problems for t in p.tried)

    @property
    def empty(self) -> bool:
        return all(p.empty for p in self.problems)


def as_requirements(value: "Requirements | ProblemRequirements | None") -> Requirements:
    if value is None:
        return Requirements()
    if isinstance(value, ProblemRequirements):
        return Requirements(problems=(value,))
    return value
