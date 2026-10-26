"""The Solution Box guards (pi platform spec Book 5, Part 5 and 11.3): when pi may offer it,
which state changes are legal, and the value-line check on section 3.

Pure functions only. Nothing here reads the database or sends a message; the caller supplies the
facts and acts on the answer. Wiring into the conversation is behind `response_rules.pi_mode =
"brain"` AND `response_rules.brain.box_offer` (default false), see `box_offer_enabled`.
"""

from dataclasses import dataclass
from typing import Any

# Readiness numbers (spec 5.4).
MIN_PROBLEMS = 3  # B1
MIN_UNDERSTOOD = 2  # B2
MIN_PI_MESSAGES = 8  # B6
DECLINE_QUIET_MESSAGES = 8  # B7, and "no new offer for 8 messages" after a decline
IDEAS_PER_PROBLEM = 2  # value line, section 3

TRUST_FALLING = "falling"


@dataclass(frozen=True)
class OfferFacts:
    problem_count: int = 0
    understood_count: int = 0  # what, size, since, why at least partial
    map_reviewed: bool = False  # confirmed or changed at least once (B3)
    ranked: bool = False  # ranked, or said where to start (B4)
    voluntary_count: int = 0  # problems the owner raised on their own (B5)
    pi_message_count: int = 0  # across one or more days (B6)
    trust_trend: str = "steady"  # "rising" | "steady" | "falling" (B7)
    upset: bool = False
    declined_recently: bool = False  # an offer declined within the last 8 messages
    asked_for_document_or_price: bool = False  # R1
    said_yes: bool = False  # R2, to an offer or check-in
    asked_who_or_how_long: bool = False  # R3
    no_other_problems: bool = False  # the owner said there are no others (B1)
    # "Never offer when" (spec 5.4); the defaults do not block, the caller sets what it knows.
    main_cause_known: bool = True
    just_corrected: bool = False
    in_a_hurry: bool = False


def can_offer(facts: OfferFacts) -> tuple[bool, str, str]:
    """(allowed, rule, reason). The exceptions R1 to R3 are always honoured, in that order; the
    rule is then "R1", "R2" or "R3". Otherwise every one of B1 to B7 must hold: the rule is "B"
    and the reason says which condition held it back ("B3: ..."). The caller logs all of it."""
    if facts.asked_for_document_or_price:
        return True, "R1", "the owner asked for the document, quote or price"
    if facts.said_yes:
        return True, "R2", "the owner said yes to an offer or check-in"
    if facts.asked_who_or_how_long:
        return True, "R3", "the owner asked who, how long or whether Workzap can do it"

    if not (facts.problem_count >= MIN_PROBLEMS or facts.no_other_problems):
        return False, "B", f"B1: fewer than {MIN_PROBLEMS} problems and no 'nothing else' yet"
    if facts.understood_count < MIN_UNDERSTOOD:
        return False, "B", f"B2: fewer than {MIN_UNDERSTOOD} problems understood"
    if not facts.map_reviewed:
        return False, "B", "B3: the owner has not reviewed or confirmed the map"
    if not facts.ranked:
        return False, "B", "B4: the owner has not ranked the problems or said where to start"
    if facts.voluntary_count < 1:
        return False, "B", "B5: the owner has not raised a problem on their own"
    if facts.pi_message_count < MIN_PI_MESSAGES:
        return False, "B", f"B6: pi has sent fewer than {MIN_PI_MESSAGES} messages"
    if facts.trust_trend == TRUST_FALLING:
        return False, "B", "B7: trust is falling"
    if facts.upset:
        return False, "B", "B7: the owner is upset"
    if facts.declined_recently:
        return (
            False,
            "B",
            f"B7: an offer was declined in the last {DECLINE_QUIET_MESSAGES} messages",
        )
    if not facts.main_cause_known:
        return False, "B", "never offer: the cause of the main problem is unknown"
    if facts.just_corrected:
        return False, "B", "never offer: the owner has just corrected pi"
    if facts.in_a_hurry:
        return False, "B", "never offer: the owner is in a hurry about something else"
    return True, "B", "B1 to B7 hold"


def box_offer_enabled(response_rules: dict[str, Any] | None) -> bool:
    """The Solution Box offer is on only in brain mode with response_rules.brain.box_offer true."""
    rules = response_rules or {}
    if rules.get("pi_mode") != "brain":
        return False
    return (rules.get("brain") or {}).get("box_offer") is True


# Box lifecycle (spec 5.3).
STATES = (
    "collecting",
    "ready",
    "offered",
    "drafting",
    "in_review",
    "sent",
    "accepted",
    "declined",
    "changes_asked",
    "revised",
)
ACTORS = ("pi", "owner", "staff")

_MOVES: dict[str, frozenset[str]] = {
    "collecting": frozenset({"ready"}),
    "ready": frozenset({"offered", "collecting"}),  # the map can change under it
    "offered": frozenset({"drafting", "collecting"}),  # a decline returns it to collecting
    "drafting": frozenset({"in_review"}),
    "in_review": frozenset({"sent"}),
    "sent": frozenset({"accepted", "declined", "changes_asked", "revised"}),
    "accepted": frozenset({"revised"}),  # a new problem after sending makes a new version
    "declined": frozenset({"collecting"}),  # nothing is sent, the map stays
    "changes_asked": frozenset({"revised", "in_review"}),
    "revised": frozenset({"in_review"}),
}
# Only these actors may make a move to these states (any actor may make the rest).
_ONLY: dict[str, frozenset[str]] = {
    "sent": frozenset({"staff"}),
    "accepted": frozenset({"owner", "staff"}),
    "declined": frozenset({"owner", "staff"}),
    "changes_asked": frozenset({"owner", "staff"}),
}


def can_move(current: str, target: str, actor: str) -> tuple[bool, str]:
    """(legal, reason). Only staff can move a box to Sent; the owner answers; pi never sends."""
    if current not in _MOVES or target not in STATES:
        return False, f"unknown state {current!r} -> {target!r}"
    if actor not in ACTORS:
        return False, f"unknown actor {actor!r}"
    if target not in _MOVES[current]:
        return False, f"{current} cannot move to {target}"
    allowed = _ONLY.get(target)
    if allowed is not None and actor not in allowed:
        who = " or ".join(sorted(allowed))
        return False, f"only {who} can move a box to {target}"
    return True, "ok"


def legal_targets(current: str) -> tuple[str, ...]:
    return tuple(s for s in STATES if s in _MOVES.get(current, frozenset()))


def value_line(ideas_by_problem: dict[str, list[str]]) -> tuple[bool, list[str]]:
    """Section 3 of the box (spec 5.7, valueLine): exactly two ideas per problem, each passing the
    idea check (an action for the owner, one line, no how-to, no tools, no figures). Returns
    (ok, reasons); a problem with no ideas fails too."""
    from app.modules.pi import solution_rules  # heavy; the models import this module

    reasons: list[str] = []
    if not ideas_by_problem:
        return False, ["section 3 has no problems"]
    for problem, ideas in ideas_by_problem.items():
        given = [i for i in ideas if (i or "").strip()]
        if len(given) != IDEAS_PER_PROBLEM:
            reasons.append(f"{problem}: {len(given)} ideas, needs {IDEAS_PER_PROBLEM}")
            continue
        for idea in given:
            verdict = solution_rules.check_idea(idea)
            if verdict.reject:
                reasons.append(f"{problem}: {verdict.reject[0]}")
    return not reasons, reasons


_UNDERSTOOD_KEYS = ("since", "impact", "scope", "cause", "person_believes_cause")


def offer_facts(context: dict[str, Any], *, asked_for_document: bool = False) -> OfferFacts:
    """The readiness facts from what the conversation already holds. Keys the map work will set
    later (`map_reviewed`, `ranked`, `voluntary_problems`, `declined_recently`, `trust_trend`,
    `upset`) are read from the conversation brief; until something sets them, B3 and B4 hold the
    offer back, which is what the spec asks for (R1 to R3 still go through)."""
    noted = context.get("noted_problems") or []
    brief = context.get("brief") or {}
    history = context.get("history") or []
    return OfferFacts(
        problem_count=len(noted),
        understood_count=sum(1 for p in noted if any(p.get(k) for k in _UNDERSTOOD_KEYS)),
        map_reviewed=bool(brief.get("map_reviewed")),
        ranked=bool(brief.get("ranked")),
        voluntary_count=int(brief.get("voluntary_problems") or 0),
        pi_message_count=sum(1 for h in history if h.get("role") == "ai"),
        trust_trend=str(brief.get("trust_trend") or "steady"),
        upset=bool(brief.get("upset")),
        declined_recently=bool(brief.get("declined_recently")),
        asked_for_document_or_price=asked_for_document,
        no_other_problems=bool(brief.get("no_other_problems")),
    )
