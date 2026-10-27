"""pi's conversation flow: the states, the legal moves between them and what pi may do in each
(pi Brain spec, Part 3). Pure and deterministic, so a guard can be unit-tested move by move.

The code, not the model, decides whether a move happens: the model asks, `advance` accepts or
raises. Only conversations of a workspace with response_rules.pi_mode = "brain" have a state.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
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
    S_LISTEN_THINK = "S_LISTEN_THINK"
    S_MAP_SHARE = "S_MAP_SHARE"
    S_BOX_OFFER = "S_BOX_OFFER"
    S_BOX_DRAFT = "S_BOX_DRAFT"
    S_RETURN = "S_RETURN"
    S_HOLD = "S_HOLD"
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
# Where pi must not raise a solution document or quote on its own (nothing sold while listening).
# S_LISTEN_THINK is not here: ideas and the offer are its job. S_HOLD is: no ideas, no offer.
# S_RETURN and S_MAP_SHARE are: a returning owner or a map is never met with a pitch (R-SELL-01).
NO_OFFER = LISTENING | {S.S5B_DECLINED, S.S_HOLD, S.S_RETURN, S.S_MAP_SHARE}

TRANSITIONS: dict[State, frozenset[State]] = {
    S.S0_NEW: frozenset({S.S1_LISTENING}),
    S.S1_LISTENING: frozenset(
        {S.S2_CLARIFYING, S.S3_NOTED, S.S_LISTEN_THINK, S.S_MAP_SHARE, S.S_RETURN, S.S_HOLD}
    ),
    S.S2_CLARIFYING: frozenset(
        {S.S1_LISTENING, S.S3_NOTED, S.S_LISTEN_THINK, S.S_MAP_SHARE, S.S_RETURN, S.S_HOLD}
    ),
    S.S3_NOTED: frozenset(
        {
            S.S1_LISTENING,
            S.S4_SORTED_SUMMARY,
            S.S_LISTEN_THINK,
            S.S_MAP_SHARE,
            S.S_RETURN,
            S.S_HOLD,
        }
    ),
    S.S4_SORTED_SUMMARY: frozenset(
        {S.S1_LISTENING, S.S5_READINESS, S.S_LISTEN_THINK, S.S_MAP_SHARE, S.S_RETURN, S.S_HOLD}
    ),
    # The default (Book 5, 11.1): each turn thinks, picks a move and updates the map. A solution ask
    # from any listening state lands here (the old S_ADVISE moves): ideas, then the offer.
    S.S_LISTEN_THINK: frozenset(
        {
            S.S1_LISTENING,
            S.S5_READINESS,
            S.S6_PREPARING,
            S.S5B_DECLINED,
            S.S_MAP_SHARE,
            S.S_BOX_OFFER,
            S.S_RETURN,
            S.S_HOLD,
        }
    ),
    # A map version is drawn and sent; pi waits for the reply and applies the edits.
    S.S_MAP_SHARE: frozenset(
        {S.S_LISTEN_THINK, S.S1_LISTENING, S.S_BOX_OFFER, S.S_RETURN, S.S_HOLD}
    ),
    # Entered only through can_offer: one offer, one answer.
    S.S_BOX_OFFER: frozenset(
        {S.S_BOX_DRAFT, S.S5_READINESS, S.S5B_DECLINED, S.S_LISTEN_THINK, S.S_HOLD}
    ),
    # The owner said yes: pi drafts, then hands over to staff.
    S.S_BOX_DRAFT: frozenset({S.S6_PREPARING, S.S_LISTEN_THINK}),
    # The returning owner (Book 5, Part 6): continuity and the map, never a restart.
    S.S_RETURN: frozenset({S.S_LISTEN_THINK, S.S1_LISTENING, S.S_MAP_SHARE, S.S_HOLD}),
    # After a heavy disclosure or distress: no ideas, no offer.
    S.S_HOLD: frozenset({S.S_LISTEN_THINK, S.S1_LISTENING}),
    S.S5_READINESS: frozenset({S.S6_PREPARING, S.S5B_DECLINED, S.S1_LISTENING}),
    S.S5B_DECLINED: frozenset({S.S1_LISTENING, S.S5_READINESS, S.S_LISTEN_THINK, S.S_RETURN}),
    S.S6_PREPARING: frozenset({S.S7_DELIVERED}),
    S.S7_DELIVERED: frozenset({S.S8_REVIEW}),
    S.S8_REVIEW: frozenset({S.S8B_CHANGES_REQUESTED, S.S9_APPROVED, S.S9B_DECLINED_QUOTE}),
    S.S8B_CHANGES_REQUESTED: frozenset({S.S7_DELIVERED}),
    S.S9_APPROVED: frozenset({S.S10_AWAITING_PAYMENT}),
    S.S9B_DECLINED_QUOTE: frozenset({S.S1_LISTENING, S.S5_READINESS, S.S_RETURN}),
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

# Where an owner who comes back after a day or more is met as a returning owner (Book 5, Part 6).
# A declined offer, a quote in progress and the exceptions are not here: they keep their own state.
RETURNABLE = frozenset(
    {
        S.S1_LISTENING,
        S.S2_CLARIFYING,
        S.S3_NOTED,
        S.S4_SORTED_SUMMARY,
        S.S_LISTEN_THINK,
        S.S_MAP_SHARE,
    }
)

GUIDANCE: dict[State, str] = {
    S.S0_NEW: "Nothing sent yet. Open with who you are (an AI from Workzap) and invite them to say "
    "what is going wrong. Ask nothing else.",
    S.S1_LISTENING: "They are describing problems. Acknowledge briefly, ask one question at most. "
    "Do not volunteer a fix, product, service, document or quote; if they ask for one, in any "
    "words, answer it in your first sentence (Solution Mode).",
    S.S2_CLARIFYING: "You asked one question. Take the answer, or let them move on. Never ask a "
    "second question in the same message.",
    S.S3_NOTED: "A problem was noted. Confirm it in their words, then ask if anything else is "
    "getting in the way. Do not repeat what you already know.",
    S.S4_SORTED_SUMMARY: "Show what is noted and sorted, grouped, and say none of it is solved. "
    "Invite corrections. Do not offer a document in this message.",
    S.S_LISTEN_THINK: "They asked for a solution, or you are thinking about the next move. Answer "
    "in your first sentence if they asked, give the free ideas you were handed (two at most, none "
    "repeated), note any new problem, and let the application make any offer. No price, no "
    "promised result, one question at most.",
    S.S_MAP_SHARE: "A map version was drawn and sent. Wait for their reply and apply their "
    "edits in their words. Do not offer anything in this message.",
    S.S_BOX_OFFER: "The offer was made, for the whole set and never for one problem. They can "
    "say no. Answer questions about it; do not repeat it and do not name a price.",
    S.S_BOX_DRAFT: "They said yes. Say what happens next in plain words: Workzap's team reviews "
    "and prepares the quote. Invent no content, no price and no time.",
    S.S_RETURN: "They are back after a day or more. Open with continuity, not with a fresh "
    "greeting, and answer what they wrote. Do not assume old problems are still true. The map from "
    "last time follows in its own message with the open question, so ask no question yourself. "
    "Offer nothing unless they ask for it.",
    S.S_HOLD: "They shared something heavy or are distressed. Be kind and brief. No ideas, no "
    "offer, no question that pushes.",
    S.S5_READINESS: "The offer was sent: a solution document and a quote, and they can say no. "
    "Answer questions about it. Cost depends on what is built and is written on the quote; "
    "the quote is free and is not a charge; never give a range. Do not repeat the offer.",
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
    "dein, usay note kar liya jayega.",
}


class IllegalTransition(ValueError):
    def __init__(self, source: State, target: State) -> None:
        super().__init__(f"{source.value} cannot move to {target.value}")
        self.source = source
        self.target = target


# Stored states that no longer exist read as their replacement, so old rows and stored context load.
RETIRED = {"S_ADVISE": State.S_LISTEN_THINK}


def parse(value: str | None) -> State | None:
    if value in RETIRED:
        return RETIRED[str(value)]
    try:
        return State(value) if value else None
    except ValueError:
        return None


def hand_to_human(conversation: Any) -> None:
    """A person took the chat over (R-DISC-04): remember the state and sit in X_HUMAN. Chats that
    never entered brain mode have no state and are left alone."""
    state = parse(conversation.flow_state)
    if state is None or state == State.X_HUMAN:
        return
    brief = dict(conversation.service_brief or {})
    brief["resume_state"] = state.value
    conversation.service_brief = brief
    conversation.flow_state = State.X_HUMAN.value
    conversation.flow_state_since = datetime.now(UTC)


def hand_back(conversation: Any) -> None:
    """The chat went back to pi: return to the state it was in (listening if unknown)."""
    if parse(conversation.flow_state) != State.X_HUMAN:
        return
    brief = dict(conversation.service_brief or {})
    back = parse(brief.pop("resume_state", None)) or State.S1_LISTENING
    brief["handback_notice"] = True  # pi's first line after a person hands back (R-DISC-04)
    conversation.service_brief = brief
    conversation.flow_state = back.value
    conversation.flow_state_since = datetime.now(UTC)


KICKOFF_LENGTH = timedelta(hours=1)  # a kickoff call is over this long after it starts


def kickoff_done(conversation: Any, now: datetime | None = None) -> bool:
    """S12 to S13 (spec 3.2: "Kickoff done" moves to "Workzap building"). The kickoff time is in
    the brief when the slot was booked; an hour after it starts the call is over. Chats without a
    known kickoff time stay where they are. Returns True when the chat moved."""
    state = parse(conversation.flow_state)
    if state != State.S12_KICKOFF:
        return False
    now = now or datetime.now(UTC)
    brief = dict(conversation.service_brief or {})
    kickoff = dict(brief.get("kickoff") or {})
    raw = kickoff.get("at")
    try:
        at = datetime.fromisoformat(raw) if isinstance(raw, str) and raw else None
    except ValueError:
        at = None
    if at is None:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    if now < at + KICKOFF_LENGTH:
        return False
    kickoff["done_at"] = now.isoformat()
    brief["kickoff"] = kickoff
    conversation.service_brief = brief
    conversation.flow_state = advance(state, State.S13_IN_BUILD).value
    conversation.flow_state_since = now
    return True


def can_move(source: State, target: State) -> bool:
    """Any state may go to an exception state; otherwise only the moves in the table."""
    return source == target or target in EXCEPTIONS or target in TRANSITIONS[source]


def advance(source: State, target: State) -> State:
    """The new state, or IllegalTransition. Staying where you are is always fine."""
    if not can_move(source, target):
        raise IllegalTransition(source, target)
    return target


def path(source: State, target: State) -> list[State] | None:
    """The legal steps from source to target (excluding source), found breadth-first; [] when
    already there, None when there is no way. A turn can note a problem and show the summary
    in one go, which is several moves."""
    if source == target:
        return []
    seen = {source}
    queue: list[tuple[State, list[State]]] = [(source, [])]
    while queue:
        state, steps = queue.pop(0)
        for nxt in TRANSITIONS[state]:
            if nxt in seen:
                continue
            if nxt == target:
                return [*steps, nxt]
            seen.add(nxt)
            queue.append((nxt, [*steps, nxt]))
    return [target] if target in EXCEPTIONS else None


def allowed_next(source: State) -> list[State]:
    moves = set(TRANSITIONS[source]) | EXCEPTIONS
    moves.discard(source)
    return sorted(moves, key=list(State).index)


def initial_state(pi_has_replied: bool) -> State:
    """Where an existing chat starts when the workspace turns brain mode on."""
    return State.S1_LISTENING if pi_has_replied else State.S0_NEW


def after_turn(
    source: State, *, asked_question: bool, noted: bool = False, summary: bool = False
) -> State:
    """The state after a turn, from what only the listening loop can know: a new problem was
    noted, the sorted summary was shown, or pi asked a question. Later states are moved by
    their own events (offer, document, approval, payment), never by the model."""
    state = source
    if state == State.S_RETURN:
        state = State.S1_LISTENING  # the returning owner was met; from here the loop is the same
    if state == State.S0_NEW:
        state = State.S1_LISTENING  # the opening went out
        if not (noted or summary):
            return state
    if state in (State.S4_SORTED_SUMMARY, State.S5_READINESS, State.S5B_DECLINED) and noted:
        state = State.S1_LISTENING  # a new problem after the summary or offer: back to listening
    if state in (State.S1_LISTENING, State.S2_CLARIFYING):
        if not (noted or summary):
            return State.S2_CLARIFYING if asked_question else State.S1_LISTENING
        state = State.S3_NOTED
    if state == State.S3_NOTED and summary:
        state = State.S4_SORTED_SUMMARY
    return state


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
