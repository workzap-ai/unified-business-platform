"""The decision rules of the nightly learning jobs (pi Brain spec 8.5, 8.6, 8.8, 9.10, 11.9).

Pure functions: given numbers, they say promote, hold, roll back or reject. They change nothing and
store nothing. The jobs that read and write data call them, so the rules can be tested alone and a
change in a rule is one visible diff. Anything touching the constitution, money, privacy, the offer
or care sections is never decided here: it goes to the weekly human queue.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.modules.pi import brain_config

# --- the example bank (8.5 job 2, 8.8) -----------------------------------------------------------

PROMOTE_REWARD = 3  # over the next two turns
PROMOTE_RUBRIC = 1.8
PROMOTE_REDACTION = 0.98
MAX_PER_SITUATION = 30


def should_promote_example(
    reward_next_two_turns: int, rubric: float, rule_break: bool, redaction_confidence: float
) -> bool:
    """A real exchange may become a candidate example only when it went well, broke no rule, and
    was redacted with high confidence (nothing enters the bank below 0.98)."""
    return (
        not rule_break
        and reward_next_two_turns >= PROMOTE_REWARD
        and rubric >= PROMOTE_RUBRIC
        and redaction_confidence >= PROMOTE_REDACTION
    )


def balance_examples(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """At most one example per business per situation and MAX_PER_SITUATION per situation, best
    reward first, so one chatty customer cannot dominate."""
    chosen: list[dict[str, object]] = []
    seen: set[tuple[object, object]] = set()
    per_situation: dict[object, int] = {}
    for row in sorted(rows, key=lambda r: -float(str(r.get("reward", 0)))):
        key = (row.get("situation"), row.get("business"))
        if key in seen or per_situation.get(row.get("situation"), 0) >= MAX_PER_SITUATION:
            continue
        seen.add(key)
        per_situation[row.get("situation")] = per_situation.get(row.get("situation"), 0) + 1
        chosen.append(row)
    return chosen


def without_contact(
    rows: list[dict[str, object]], contact: str
) -> tuple[list[dict[str, object]], int]:
    """Deletion cascade (R-PRIV-06, eval L11): every learning row that came from this contact is
    dropped. Returns what is left and how many went, so the statistics can be recomputed."""
    kept = [r for r in rows if contact not in (r.get("source_contacts") or [])]  # type: ignore[operator]
    return kept, len(rows) - len(kept)


# --- vocabulary (8.5 job 4) ----------------------------------------------------------------------

LEXICON_BUSINESSES = 5
LEXICON_AGREEMENT = 0.90


def lexicon_terms(observations: Iterable[tuple[str, str, str]]) -> dict[str, str]:
    """(term, business, category) seen in messages, after corrections. A term is added when at least
    5 different businesses used it and at least 90% of the time it ended up in one category."""
    by_term: dict[str, list[tuple[str, str]]] = {}
    for term, business, category in observations:
        by_term.setdefault(term.strip().lower(), []).append((business, category))
    added: dict[str, str] = {}
    for term, seen in by_term.items():
        if len({business for business, _ in seen}) < LEXICON_BUSINESSES:
            continue
        counts: dict[str, int] = {}
        for _, category in seen:
            counts[category] = counts.get(category, 0) + 1
        top, hits = max(counts.items(), key=lambda kv: kv[1])
        if hits / len(seen) >= LEXICON_AGREEMENT:
            added[term] = top
    return added


# --- the gate for every automatic change (8.5 job 9) ---------------------------------------------

MIN_CANARY = 300  # conversations per arm before deciding (9.10 rule 3)


@dataclass(frozen=True)
class Rates:
    """Per-conversation rates for one arm (control or canary)."""

    conversations: int
    reward: float
    rule_break: float = 0.0
    opt_out: float = 0.0
    complaint: float = 0.0
    confusion: float = 0.0
    correction: float = 0.0


GUARDRAIL_MARGIN = {  # how far above the control a rate may rise before the change is rolled back
    "rule_break": 0.0,  # any rise at all
    "opt_out": 0.005,
    "complaint": 0.005,
    "confusion": 0.02,
    "correction": 0.02,
}


def breached(control: Rates, canary: Rates) -> list[str]:
    return [
        name
        for name, margin in GUARDRAIL_MARGIN.items()
        if getattr(canary, name) > getattr(control, name) + margin
    ]


def canary_decision(control: Rates, canary: Rates, min_conversations: int = MIN_CANARY) -> str:
    """ "rollback" the moment any guardrail rises (eval L9, even on a small sample), "promote" when
    the canary has enough conversations, is at least as good, and every guardrail holds,
    otherwise "continue"."""
    if breached(control, canary):
        return "rollback"
    if canary.conversations >= min_conversations and canary.reward >= control.reward:
        return "promote"
    return "continue"


# --- settings tuning (8.5 job 7, 9.10) -----------------------------------------------------------

ONE_WEEK = timedelta(days=7)


def next_setting_value(
    key: str, current: int, direction: int, last_changed: datetime | None, now: datetime
) -> int:
    """Move a tunable one step towards `direction` (+1 or -1), inside its tested range, and at most
    once a week. Returns the current value when it may not move yet."""
    default, low, high = brain_config.TUNABLES[key]
    if last_changed is not None and now - last_changed < ONE_WEEK:
        return current
    return max(low, min(high, current + (1 if direction > 0 else -1)))


# --- industry packs (8.5 job 5, 8.6) -------------------------------------------------------------

CLUSTER_SIZE = 5  # businesses that fit no pack before one is drafted
SHADOW_CONVERSATIONS = 20

LISTENING_SECTIONS = ("Recognise", "Shape facts", "Words", "Problems", "Questions", "Seasons")
CARE_SECTIONS = ("Scope rule", "Handle with care")


def should_draft_pack(unclassified_in_cluster: int) -> bool:
    return unclassified_in_cluster >= CLUSTER_SIZE


def pack_may_go_live(
    section: str, shadow_conversations: int, shadow_score: float, fallback_score: float
) -> bool:
    """Listening sections go live after 20 shadow conversations that score at least as well as the
    generic fallback. Care sections (what pi refuses and protects) never do: a human decides."""
    if section in CARE_SECTIONS or section not in LISTENING_SECTIONS:
        return False
    return shadow_conversations >= SHADOW_CONVERSATIONS and shadow_score >= fallback_score


def needs_human_review(section: str) -> bool:
    return section in CARE_SECTIONS or section not in LISTENING_SECTIONS
