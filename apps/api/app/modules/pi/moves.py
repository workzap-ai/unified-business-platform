# ruff: noqa: E501
"""The sixteen moves, how one is chosen, the hypothesis ledger and the plan object
(Engagement Engine, Book 5, Part 3.2 to 3.5).

pi runs a private thinking step before it writes (hear, know, don't know, notice, hypothesise,
choose a move, check). The step produces a `Plan` that the writer follows. This module is the pure
part: the move list, the choice rules (`choose`) and the ledger. It never writes a word to the owner.

Choice rules (spec 3.4), all enforced in `choose`:
  * choose by the dials first (Listen: M1, M16, M8; Think: M3, M4, M10, M11, M12; Fix: ideas, M11,
    M13; Buy: honour the request, the offer gates in decisions.py decide whether it may be made);
  * no move more than twice in the last four messages;
  * at least one message in three carries no question;
  * never two question-only messages in a row (give before you take);
  * fatigue wins over method: give value or a fork;
  * a move that did not land is not repeated (if M4 was ignored, try M2 or M13).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.modules.pi.dials import Dials, Mode, Trust

WINDOW = 4  # "in the last four messages"
MAX_IN_WINDOW = 2  # no move more than twice in the window
NO_QUESTION_EVERY = 3  # at least one in three without a question
NOTICE_ABSENCE_EVERY = 3  # spec 3.8: noticing what is missing, at most once per three messages


class Move(StrEnum):
    M1 = "M1_reflect"
    M2 = "M2_work_the_number"
    M3 = "M3_reframe"
    M4 = "M4_hypothesis"
    M5 = "M5_contrast"
    M6 = "M6_consequence"
    M7 = "M7_scenario"
    M8 = "M8_connect"
    M9 = "M9_notice_absence"
    M10 = "M10_gentle_challenge"
    M11 = "M11_prioritise"
    M12 = "M12_name_the_tension"
    M13 = "M13_fork"
    M14 = "M14_teach"
    M15 = "M15_show_the_map"
    M16 = "M16_hold_space"
    # "Other plain moves, also valid" (spec 3.3)
    ASK = "ask"
    INVITE = "invite"
    GIVE_IDEAS = "give_ideas"
    SUMMARISE = "summarise"
    HONOUR = "honour_request"  # Buy mode (Part 5.4)


@dataclass(frozen=True)
class MoveInfo:
    move: Move
    does: str
    # True when the move can be written with no question at all (it carries the "so what")
    question_free: bool
    # True when the move is a question by its nature (a fork, a hypothesis to be corrected)
    asks: bool = False


INFO: dict[Move, MoveInfo] = {
    i.move: i
    for i in (
        MoveInfo(Move.M1, "Says back what it means, not what was said", True),
        MoveInfo(Move.M2, "Arithmetic on their own figures", True),
        MoveInfo(Move.M3, "Splits one problem into two, or changes the question", True),
        MoveInfo(Move.M4, "States a guess and asks to be corrected", False, True),
        MoveInfo(Move.M5, "Finds where it works, to expose the cause", False, True),
        MoveInfo(Move.M6, "Second-order effect: what this causes next", True),
        MoveInfo(Move.M7, '"If this continues", using only their numbers', True),
        MoveInfo(Move.M8, "Links to another problem on the map", True),
        MoveInfo(Move.M9, "Points out what they did not mention", False, True),
        MoveInfo(Move.M10, "Tests an assumption respectfully", False, True),
        MoveInfo(Move.M11, "Says what first and why", True),
        MoveInfo(Move.M12, "Says the trade-off out loud", True),
        MoveInfo(Move.M13, "Two paths, the owner picks", False, True),
        MoveInfo(Move.M14, 'A general, true principle, "aam tor par"', True),
        MoveInfo(Move.M15, "Sends or updates the problem map with a short caption", False, True),
        MoveInfo(Move.M16, "Pause, acknowledge, permission", True),
        MoveInfo(Move.ASK, "The smart question", False, True),
        MoveInfo(Move.INVITE, "A door to the next likely problem", False, True),
        MoveInfo(Move.GIVE_IDEAS, "Two ideas on request", True),
        MoveInfo(Move.SUMMARISE, "A check-in", True),
        MoveInfo(Move.HONOUR, "Honours a request for a document or a price", True),
    )
}

MOVE_KEYS = frozenset(m.value for m in Move)

# Spec 3.4, first row: the pool for each mode, in order of preference.
BY_MODE: dict[Mode, tuple[Move, ...]] = {
    Mode.LISTEN: (Move.M1, Move.M16, Move.M8),
    Mode.THINK: (Move.M3, Move.M4, Move.M10, Move.M11, Move.M12),
    Mode.FIX: (Move.GIVE_IDEAS, Move.M11, Move.M13),
    Mode.BUY: (Move.HONOUR,),
}
# What fatigue gets (spec 3.4): value or a fork.
FATIGUE_POOL = (Move.M13, Move.M11, Move.M2, Move.M1)
# Used when the pool for the mode is exhausted by the variety rules.
FALLBACK_POOL = (
    Move.M1,
    Move.M11,
    Move.M12,
    Move.M14,
    Move.M6,
    Move.M3,
    Move.M16,
    Move.M13,
    Move.M4,
)


def question_free(move: Move) -> bool:
    return INFO[move].question_free


def parse_move(key: str | None) -> Move | None:
    for m in Move:
        if key in (m.value, m.name):
            return m
    return None


@dataclass(frozen=True)
class Turn:
    """One earlier pi message, as far as the variety rules need it."""

    move: Move
    question: bool  # it ended in a question
    gave: bool = True  # it also gave something (a reading, a number, a link, a fork, an idea)
    landed: bool | None = None  # the owner's reply used it (None: not known yet)

    @property
    def question_only(self) -> bool:
        return self.question and not self.gave


@dataclass(frozen=True)
class Situation:
    """What the choice needs besides the dials and the last turns. All flags come from code or
    from the thinking step; none is a label about the person."""

    dials: Dials
    recent: Sequence[Turn] = ()
    heavy: bool = False  # the latest message was a sensitive disclosure or strong feeling
    upset: bool = False  # the owner is upset (no challenge, spec 3.7)
    corrected: bool = False  # the owner has just corrected pi (no challenge)
    has_number: bool = False  # the owner gave figures to work with (M2, M7)
    fresh_number: bool = False  # the latest message gave a figure or fraction to combine with one
    other_problem: bool = False  # another problem is on the map to link to (M8)
    map_ready: bool = False  # a map is worth sending now (M15)
    has_hypothesis: bool = False  # something to put to the owner (M4)
    absence_to_notice: bool = False  # the pack's neighbours offer a gap to point at (M9)
    ideas_asked: bool = False  # the owner asked for ideas ("solution dein"): ideas, not questions


@dataclass(frozen=True)
class Choice:
    move: Move
    reason: str
    question_allowed: bool  # a question may be the last sentence (it is never required)
    question_forbidden: bool  # at least one in three carries none: this must not ask
    must_give: bool  # the last message was question-only: this one must give something


def _count(recent: Sequence[Turn], move: Move) -> int:
    return sum(1 for t in recent[-WINDOW:] if t.move == move)


def _eligible(move: Move, s: Situation) -> bool:
    """Whether the facts allow this move at all (not the variety rules)."""
    if move in (Move.M2, Move.M7):
        return s.has_number
    if move == Move.GIVE_IDEAS:  # no solution while listening, except when they ask for ideas
        return s.ideas_asked
    if move == Move.M8:
        return s.other_problem
    if move == Move.M15:
        return s.map_ready
    if move == Move.M4:
        return s.has_hypothesis
    if move == Move.M9:
        return s.absence_to_notice and not any(
            t.move == Move.M9 for t in s.recent[-NOTICE_ABSENCE_EVERY:]
        )
    if (
        move == Move.M10
    ):  # spec 3.7: only when trust is flat or rising, never upset or just corrected
        return not (s.upset or s.corrected) and s.dials.trust_trend != Trust.FALLING
    return True


def _ignored(recent: Sequence[Turn]) -> Move | None:
    last = recent[-1] if recent else None
    return last.move if last is not None and last.landed is False else None


def choose(s: Situation) -> Choice:
    """The move for the next message and the question rules that go with it."""
    recent = list(s.recent)
    last = recent[-1] if recent else None
    last_two_asked = len(recent) >= 2 and all(t.question for t in recent[-2:])
    must_give = bool(last and last.question_only)
    no_question = last_two_asked  # one in three without a question
    ignored = _ignored(recent)

    if s.dials.mode == Mode.BUY:
        pool: tuple[Move, ...] = BY_MODE[Mode.BUY]  # honour the request, fatigue or not
        why = "Buy mode: honour the request"
    elif s.ideas_asked:
        pool = (Move.GIVE_IDEAS, Move.M11, Move.M13)
        why = "they asked for ideas: answer first, ideas before any question"
    elif s.heavy:
        pool = (Move.M16, Move.M1, Move.M8)
        why = "a heavy disclosure: hold space before anything else"
    elif s.dials.fatigue:
        pool = FATIGUE_POOL
        why = "fatigue wins over method: give value or a fork"
    else:
        pool = BY_MODE[s.dials.mode]
        why = f"{s.dials.mode.value} mode"
        prefer: tuple[Move, ...] = ()
        if s.map_ready:
            prefer = (Move.M15,)
            why += "; the picture is ready to show"
        elif s.fresh_number:
            prefer = (Move.M2,)
            why += "; they gave a figure to work"
        elif s.has_hypothesis and s.dials.mode == Mode.THINK:
            prefer = (Move.M4,)
            why += "; a hypothesis is ready to test"
        pool = prefer + tuple(m for m in pool if m not in prefer)
        if s.dials.mode == Mode.FIX:
            pool = tuple(m for m in pool if m != Move.GIVE_IDEAS) or pool
    if ignored == Move.M4:  # "If M4 was ignored, try M2 or M13"
        pool = (Move.M2, Move.M13) + tuple(m for m in pool if m != Move.M4)
        why += "; the last hypothesis was ignored, so a number or a fork"
    elif ignored is not None:
        pool = tuple(m for m in pool if m != ignored) or pool
        why += f"; {ignored.value} did not land"

    def acceptable(m: Move) -> bool:
        if not _eligible(m, s):
            return False
        if _count(recent, m) >= MAX_IN_WINDOW:
            return False
        if ignored is not None and m == ignored:
            return False
        return not (no_question and not question_free(m))

    for m in pool + FALLBACK_POOL:
        if acceptable(m):
            return Choice(
                m,
                why if m in pool else why + "; the pool is used up, a fallback move",
                question_allowed=not no_question,
                question_forbidden=no_question,
                must_give=must_give,
            )
    # Everything is used up (rare): the plainest question-free move.
    return Choice(
        Move.M1, "all moves used up", False if no_question else True, no_question, must_give
    )


# --- the hypothesis ledger (spec 3.5) -------------------------------------------------------


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"  # by the owner, never by pi
    DROPPED = "dropped"


@dataclass
class Hypothesis:
    text: str
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    cheapest_test: str = ""
    status: Status = Status.OPEN
    ignored: bool = False  # it was put to the owner and went unanswered: do not repeat it


class HypothesisLedger:
    """A per-problem list of what pi currently thinks might be going on.

    A hypothesis becomes confirmed only when the OWNER confirms it. pi states a hypothesis with
    humility and never presents it as a fact, nor builds the Solution Box on an unconfirmed one
    without labelling it (`solution_label`).
    """

    def __init__(self) -> None:
        self.items: list[Hypothesis] = []

    def add(
        self,
        text: str,
        *,
        evidence_for: Sequence[str] = (),
        confidence: Confidence = Confidence.LOW,
        cheapest_test: str = "",
    ) -> Hypothesis:
        for h in self.items:
            if h.text.strip().lower() == text.strip().lower():
                h.evidence_for.extend(e for e in evidence_for if e not in h.evidence_for)
                return h
        h = Hypothesis(text, list(evidence_for), [], confidence, cheapest_test)
        self.items.append(h)
        return h

    def confirm(self, h: Hypothesis, *, by: str) -> Hypothesis:
        """Only the owner confirms. Anything else (pi, a pack, a model) is refused."""
        if by != "owner":
            raise PermissionError("a hypothesis is confirmed only by the owner")
        h.status = Status.CONFIRMED
        h.confidence = Confidence.HIGH
        return h

    def against(self, h: Hypothesis, evidence: str) -> Hypothesis:
        """Evidence against lowers the confidence a step and drops a hypothesis already at low."""
        h.evidence_against.append(evidence)
        if h.confidence == Confidence.HIGH and h.status != Status.CONFIRMED:
            h.confidence = Confidence.MEDIUM
        elif h.confidence == Confidence.MEDIUM:
            h.confidence = Confidence.LOW
        elif h.status == Status.OPEN:
            h.status = Status.DROPPED
        return h

    def drop(self, h: Hypothesis) -> Hypothesis:
        h.status = Status.DROPPED
        return h

    def open(self) -> list[Hypothesis]:
        return [h for h in self.items if h.status == Status.OPEN]

    def leading(self) -> Hypothesis | None:
        """The open hypothesis to test next: highest confidence, not one that was ignored."""
        rank = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}
        candidates = [h for h in self.open() if not h.ignored]
        return max(candidates, key=lambda h: rank[h.confidence], default=None)

    @staticmethod
    def solution_label(h: Hypothesis) -> str | None:
        """What the Solution Box must say when it leans on this hypothesis (None: no label needed)."""
        return (
            None if h.status == Status.CONFIRMED else "unconfirmed: pi's reading, not yet confirmed"
        )

    @staticmethod
    def may_state_as_fact(h: Hypothesis) -> bool:
        return h.status == Status.CONFIRMED


# --- the plan object (spec 3.2) -------------------------------------------------------------

MAP_OPS = frozenset(
    {"add_node", "add_edge", "update_node", "update_edge", "remove_node", "remove_edge"}
)


@dataclass
class PlanHypothesis:
    text: str
    confidence: str = "low"
    test: str = ""


@dataclass
class MapUpdate:
    op: str
    node: str | None = None
    edge: str | None = None
    evidence: str = ""
    message_id: str | None = None


@dataclass
class Ask:
    rung: str = ""
    slot: str = ""
    text: str = ""


@dataclass
class Plan:
    """The output of the private thinking step; the writer follows it, the critic checks it."""

    dials: dict[str, Any] = field(default_factory=dict)
    known: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    hypotheses: list[PlanHypothesis] = field(default_factory=list)
    map_updates: list[MapUpdate] = field(default_factory=list)
    move: str = Move.M1.value
    one_line_reason: str = ""
    ask: Ask | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dials": self.dials,
            "known": self.known,
            "unknown": self.unknown,
            "hypotheses": [vars(h) for h in self.hypotheses],
            "map_updates": [
                {k: v for k, v in vars(u).items() if v is not None} for u in self.map_updates
            ],
            "move": self.move,
            "one_line_reason": self.one_line_reason,
            "ask": vars(self.ask) if self.ask else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Plan":
        """Tolerant parse of what a model returned: unknown keys are ignored, bad shapes become empty."""

        def rows(key: str) -> list[dict[str, Any]]:
            value = raw.get(key)
            return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []

        def strings(key: str) -> list[str]:
            value = raw.get(key)
            return [str(v) for v in value] if isinstance(value, list) else []

        ask = raw.get("ask")
        return cls(
            dials=dict(raw["dials"]) if isinstance(raw.get("dials"), dict) else {},
            known=strings("known"),
            unknown=strings("unknown"),
            hypotheses=[
                PlanHypothesis(
                    str(r.get("text", "")), str(r.get("confidence", "low")), str(r.get("test", ""))
                )
                for r in rows("hypotheses")
            ],
            map_updates=[
                MapUpdate(
                    str(r.get("op", "")),
                    r.get("node"),
                    r.get("edge"),
                    str(r.get("evidence", "")),
                    None if r.get("message_id") is None else str(r.get("message_id")),
                )
                for r in rows("map_updates")
            ],
            move=str(raw.get("move", "")),
            one_line_reason=str(raw.get("one_line_reason", "")),
            ask=Ask(str(ask.get("rung", "")), str(ask.get("slot", "")), str(ask.get("text", "")))
            if isinstance(ask, dict)
            else None,
        )


def check_plan(plan: Plan, choice: Choice | None = None) -> list[str]:
    """What is wrong with a plan (empty: it can be followed). Deterministic, no model."""
    problems: list[str] = []
    move = parse_move(plan.move)
    if move is None:
        problems.append(f"unknown move {plan.move!r}")
    for u in plan.map_updates:
        if u.op not in MAP_OPS:
            problems.append(f"unknown map op {u.op!r}")
        if not (u.node or u.edge):
            problems.append("a map update names no node or edge")
        if not u.evidence or not u.message_id:  # mapSupport: trace to the owner's messages
            problems.append("a map update has no evidence from the owner's messages")
    for h in plan.hypotheses:
        if h.confidence not in {c.value for c in Confidence}:
            problems.append(f"unknown confidence {h.confidence!r}")
    if plan.ask is not None and not plan.ask.text.strip():
        problems.append("ask is set but empty")
    if choice is not None and move is not None:
        if plan.ask is not None and choice.question_forbidden:
            problems.append("a question is not allowed in this message (one in three has none)")
    return problems
