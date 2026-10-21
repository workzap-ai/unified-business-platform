"""pi's conversation flow: the states, the legal moves between them and what pi may do in each
(pi Brain spec, Part 3). Pure and deterministic, so a guard can be unit-tested move by move.

The code, not the model, decides whether a move happens: the model asks, `advance` accepts or
raises. Only conversations of a workspace with response_rules.pi_mode = "brain" have a state.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class State(StrEnum):
    S0_NEW = "S0_NEW"
    S1_LISTENING = "S1_LISTENING"
    S2_CLARIFYING = "S2_CLARIFYING"
    S3_NOTED = "S3_NOTED"
    S4_SORTED_SUMMARY = "S4_SORTED_SUMMARY"
    S5_READINESS = "S5_READINESS"
    S5B_DECLINED = "S5b_DECLINED"
    S6_PREPARING = "S6_PREPARING"
    S7_DELIVERED = "S7_DELIVERED"
    S8_REVIEW = "S8_REVIEW"
    S8B_CHANGES_REQUESTED = "S8b_CHANGES_REQUESTED"
    S9_APPROVED = "S9_APPROVED"
    S9B_DECLINED_QUOTE = "S9b_DECLINED_QUOTE"
    S10_AWAITING_PAYMENT = "S10_AWAITING_PAYMENT"
    S11_PAYMENT_CONFIRMED = "S11_PAYMENT_CONFIRMED"
    S12_KICKOFF = "S12_KICKOFF"
    S13_IN_BUILD = "S13_IN_BUILD"
    X_EMERGENCY = "X_EMERGENCY"
    X_HUMAN = "X_HUMAN"
    X_PAUSED = "X_PAUSED"
    X_OUT_OF_SCOPE = "X_OUT_OF_SCOPE"
    X_BLOCKED = "X_BLOCKED"


S = State
EXCEPTIONS = frozenset({S.X_EMERGENCY, S.X_HUMAN, S.X_PAUSED, S.X_OUT_OF_SCOPE, S.X_BLOCKED})
NORMAL = frozenset(set(State) - EXCEPTIONS)

# The listening states: pi notes and sorts, and never suggests, sells or mentions a quote.
LISTENING = frozenset({S.S0_NEW, S.S1_LISTENING, S.S2_CLARIFYING, S.S3_NOTED, S.S4_SORTED_SUMMARY})
# Where pi must not raise a solution document or quote on its own (R-SELL-01, 02, 05).
NO_OFFER = LISTENING | {S.S5B_DECLINED}

TRANSITIONS: dict[State, frozenset[State]] = {
    S.S0_NEW: frozenset({S.S1_LISTENING}),
    S.S1_LISTENING: frozenset({S.S2_CLARIFYING, S.S3_NOTED}),
    S.S2_CLARIFYING: frozenset({S.S1_LISTENING, S.S3_NOTED}),
    S.S3_NOTED: frozenset({S.S1_LISTENING, S.S4_SORTED_SUMMARY}),
    S.S4_SORTED_SUMMARY: frozenset({S.S1_LISTENING, S.S5_READINESS}),
    S.S5_READINESS: frozenset({S.S6_PREPARING, S.S5B_DECLINED, S.S1_LISTENING}),
    S.S5B_DECLINED: frozenset({S.S1_LISTENING, S.S5_READINESS}),
    S.S6_PREPARING: frozenset({S.S7_DELIVERED}),
    S.S7_DELIVERED: frozenset({S.S8_REVIEW}),
    S.S8_REVIEW: frozenset({S.S8B_CHANGES_REQUESTED, S.S9_APPROVED, S.S9B_DECLINED_QUOTE}),
    S.S8B_CHANGES_REQUESTED: frozenset({S.S7_DELIVERED}),
    S.S9_APPROVED: frozenset({S.S10_AWAITING_PAYMENT}),
    S.S9B_DECLINED_QUOTE: frozenset({S.S1_LISTENING, S.S5_READINESS}),
    # Cancelling after approval but before payment is confirmed (R-DEC-05).
    S.S10_AWAITING_PAYMENT: frozenset({S.S11_PAYMENT_CONFIRMED, S.S9B_DECLINED_QUOTE}),
    S.S11_PAYMENT_CONFIRMED: frozenset({S.S12_KICKOFF}),
    S.S12_KICKOFF: frozenset({S.S13_IN_BUILD}),
    S.S13_IN_BUILD: frozenset(),
    # Back from an exception: a person resumes where it makes sense; pi starts listening again.
    S.X_EMERGENCY: frozenset({S.S1_LISTENING}),
    S.X_HUMAN: NORMAL - {S.S0_NEW},
    S.X_PAUSED: NORMAL - {S.S0_NEW},
    S.X_OUT_OF_SCOPE: frozenset({S.S1_LISTENING}),
    S.X_BLOCKED: frozenset({S.S1_LISTENING}),
}

GUIDANCE: dict[State, str] = {
    S.S0_NEW: "Nothing sent yet. Open with who you are (an AI from Workzap) and invite them to say "
    "what is going wrong. Ask nothing else.",
    S.S1_LISTENING: "They are describing problems. Acknowledge briefly, ask one question at most. "
    "Never suggest a fix, product, service, document or quote.",
    S.S2_CLARIFYING: "You asked one question. Take the answer, or let them move on. Never ask a "
    "second question in the same message.",
    S.S3_NOTED: "A problem was noted. Confirm it in their words, then ask if anything else is "
    "getting in the way. Do not repeat what you already know.",
    S.S4_SORTED_SUMMARY: "Show what is noted and sorted, grouped, and say none of it is solved. "
    "Invite corrections. Do not offer a document in this message.",
    S.S5_READINESS: "Ask once whether they would like a solution document and a quote. They can "
    "say no. Accept only an explicit yes.",
    S.S5B_DECLINED: "They said no. Answer questions and note new problems; do not offer again "
    "unless they raise it.",
    S.S6_PREPARING: "Workzap is preparing the document and quote. Say so; invent no content "
    "or price.",
    S.S7_DELIVERED: "The document and quote were sent. Explain sections in plain words; no "
    "pressure.",
    S.S8_REVIEW: "They are reading. Answer only from the document and quote. Never change price "
    "or scope yourself.",
    S.S8B_CHANGES_REQUESTED: "Note the requested changes exactly, confirm them back, pass them to "
    "Workzap. Agree to nothing before Workzap revises.",
    S.S9_APPROVED: "Approved. Explain payment is by bank transfer with details on the approved "
    "quote. Never type bank details or take payment.",
    S.S9B_DECLINED_QUOTE: "They said no to the quote. Accept it; nothing is charged. Do not argue.",
    S.S10_AWAITING_PAYMENT: "Waiting for Workzap to confirm payment. Never say it was received.",
    S.S11_PAYMENT_CONFIRMED: "Workzap confirmed payment. Tell them and offer kickoff times.",
    S.S12_KICKOFF: "Kickoff is booked. Remind within WhatsApp rules; say only that it is to "
    "agree the details.",
    S.S13_IN_BUILD: "Workzap is building. Note new problems as new problems; route project "
    "questions to the project owner.",
    S.X_EMERGENCY: "Possible emergency. Tell them to call local emergency services; note "
    "nothing else.",
    S.X_HUMAN: "A Workzap person has taken over. Stay silent unless handed back.",
    S.X_PAUSED: "They asked to pause. One gentle follow-up per policy, never a nag.",
    S.X_OUT_OF_SCOPE: "Not a business problem. Say once what pi is for; do not engage at length.",
    S.X_BLOCKED: "Blocked after abuse or fraud. Minimal replies; a human decides.",
}

OPENING = {
    "en": "Hi, I'm pi, an AI from Workzap. Tell me what's going wrong in your business and I'll "
    "start on it.",
    "roman_ur": "Hi, main pi hoon, Workzap ka AI. Business mein jo bhi masla chal raha hai, bata "
    "dein, main usay note kar lunga.",
}


class IllegalTransition(ValueError):
    def __init__(self, source: State, target: State) -> None:
        super().__init__(f"{source.value} cannot move to {target.value}")
        self.source = source
        self.target = target


def parse(value: str | None) -> State | None:
    try:
        return State(value) if value else None
    except ValueError:
        return None


def can_move(source: State, target: State) -> bool:
    """Any state may go to an exception state; otherwise only the moves in the table."""
    return source == target or target in EXCEPTIONS or target in TRANSITIONS[source]


def advance(source: State, target: State) -> State:
    """The new state, or IllegalTransition. Staying where you are is always fine."""
    if not can_move(source, target):
        raise IllegalTransition(source, target)
    return target


def allowed_next(source: State) -> list[State]:
    moves = set(TRANSITIONS[source]) | EXCEPTIONS
    moves.discard(source)
    return sorted(moves, key=list(State).index)


def initial_state(pi_has_replied: bool) -> State:
    """Where an existing chat starts when the workspace turns brain mode on."""
    return State.S1_LISTENING if pi_has_replied else State.S0_NEW


def after_turn(source: State, *, asked_question: bool) -> State:
    """The state after a turn, from what only the listening loop can know. Later states are
    moved by their own events (offer, document, approval, payment), never by the model."""
    if source == State.S0_NEW:
        return State.S1_LISTENING  # the opening went out
    if source in (State.S1_LISTENING, State.S2_CLARIFYING):
        return State.S2_CLARIFYING if asked_question else State.S1_LISTENING
    return source


def brain_mode(rules: Mapping[str, Any] | None) -> bool:
    return (rules or {}).get("pi_mode") == "brain"


def strict_voice(rules: Mapping[str, Any] | None) -> bool:
    """The constitution linter runs in brain mode, or when a workspace turned it on alone."""
    return brain_mode(rules) or bool((rules or {}).get("constitution"))


def prompt_view(state: State) -> dict[str, Any]:
    return {
        "state": state.value,
        "allowed_next": [s.value for s in allowed_next(state)],
        "guidance": GUIDANCE[state],
    }
