"""When pi may speak in a video room: one pure decision, no I/O, so every rule is a unit test.

pi speaks only when ALL of these hold, and the reason is always returned so it can be logged:
the meeting is in 'speak' mode, a person has not muted pi, the utterance is final and has a known
speaker, nobody is talking right now, pi has not spoken a moment ago, the per-call cap is not
reached, and one of the two triggers fires:
  * someone says pi's name (a staff member's command is the same trigger: staff are people too, the
    difference is only that staff may also ask pi to stay quiet), or
  * 'intake' is on, exactly one customer is in the room, and that customer has just finished a turn.
The first thing pi ever says in a call is the AI disclosure, composed in code, never by the model.
What pi says is then checked by the same gate as every spoken reply (voice.allowed).
"""

import re
from dataclasses import dataclass
from typing import Literal

Mode = Literal["off", "suggest", "speak"]
Action = Literal["silent", "disclose", "speak"]

MAX_SPOKEN = 20  # pi's turns in one call
COOLDOWN_S = 6.0  # after pi spoke
REPLY_GAP_S = 1.5  # the least pause before pi answers an answer: nobody can chain pi's turns
ANSWER_S = 20.0  # a person's first words after pi's last line are an answer for this long
INTRO_PATIENCE_S = 6.0  # a customer who has waited this long for pi's introduction gets it
INTAKE_MIN_WORDS = 3  # a customer's turn this short ("ok", "hmm") is not a reason to speak
# pi's name, as a whole word, in the scripts the rooms are used in
NAME = re.compile(r"(?<!\w)(?:pi|p\.\s?i\.?|پائی|پی\s*آئی|पाई|पाय)(?!\w)", re.IGNORECASE)
QUIET = re.compile(
    r"(?<!\w)(?:stop|quiet|mute|be\s+quiet|chup|chup\s*kar|khamosh|خاموش|چپ|चुप)(?!\w)",
    re.IGNORECASE,
)
WORD = re.compile(r"\w+", re.UNICODE)
# words that are a murmur, not a reason for pi to speak, even after a long silence
FILLERS = frozenset(
    "ok okay hmm hm mm um uh yes yeah yep no haan han acha achha theek thik ji thanks thank you "
    "bye so and".split()
)


def is_filler_only_noise(text: str) -> bool:
    """Nothing readable in the text (no letters at all)."""
    return not WORD.findall(text)


def is_filler(text: str) -> bool:
    words = [w.lower() for w in WORD.findall(text)]
    return not words or all(w in FILLERS for w in words)


@dataclass(frozen=True)
class Utterance:
    speaker_id: str  # the room's user id: s_... staff, g_... guest; empty when unknown
    text: str
    final: bool
    at: float  # seconds, any monotonic clock


@dataclass(frozen=True)
class RoomState:
    mode: Mode
    muted: bool
    disclosed: bool  # the AI disclosure has already been spoken in this call
    spoken: int  # pi's turns so far
    last_spoke_at: float | None
    someone_speaking: bool
    customers: int  # different non-staff people in the room right now
    intake: bool  # the meeting lets pi lead the conversation with a lone customer
    # pi's last question was "Am I speaking with <name>?" and nobody has answered yet: even a short
    # "yes" from the lone customer is a reply to pi, not a murmur
    answering: bool = False
    # pi spoke less than ANSWER_S ago and nobody has said anything since: what is said now is an
    # answer to pi, so the pause after pi spoke does not apply and a group may be answered
    replying: bool = False
    # pi has spoken before and nothing was said for a while: a person speaking up again (even
    # "hello, are you there?") is picking the conversation back up
    resumed: bool = False
    # seconds since a customer first said something short that pi let pass, with no
    # introduction yet: a person who keeps saying 'hello?' is waiting for pi, not murmuring
    waited_s: float = 0.0


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str


def _silent(reason: str) -> Decision:
    return Decision("silent", reason)


# how speech-to-text often spells the name; only trusted at the start or after a greeting
SPELLED = re.compile(r"^\s*(?:(?:hey|hi|hello|ok|okay)\s+)?(?:pie|pye|pai)(?!\w)", re.IGNORECASE)


def addressed(text: str) -> bool:
    return bool(NAME.search(text) or SPELLED.search(text))


def asks_quiet(text: str) -> bool:
    """A staff member telling pi to stop talking. The room's mute switch is the real control; this
    only lets pi stay silent for that turn."""
    return addressed(text) and bool(QUIET.search(text))


def decide(utterance: Utterance, state: RoomState) -> Decision:
    if state.mode != "speak":
        return _silent("mode")
    if state.muted:
        return _silent("muted")
    if not utterance.final:
        return _silent("not_final")
    if not utterance.speaker_id:
        return _silent("unknown_speaker")
    if state.spoken >= MAX_SPOKEN:
        return _silent("cap")
    if state.someone_speaking:
        return _silent("someone_speaking")
    pause = REPLY_GAP_S if state.replying else COOLDOWN_S
    if state.last_spoke_at is not None and utterance.at - state.last_spoke_at < pause:
        return _silent("cooldown")
    if asks_quiet(utterance.text):
        return _silent("asked_to_be_quiet")
    named = addressed(utterance.text)
    from_staff = utterance.speaker_id.startswith("s_")
    # pi asked a question a moment ago: even a one-word answer is an answer, not a murmur
    enough = (
        len(WORD.findall(utterance.text)) >= INTAKE_MIN_WORDS
        or state.answering
        or state.replying
        or (state.resumed and not is_filler(utterance.text))
    )
    lone_customer = state.intake and state.customers == 1 and not from_staff and enough
    # with more people pi still introduces itself on its own (everyone should know an AI is
    # in the room, whoever speaks first), and afterwards it answers whoever answers its own
    # question; people talking among themselves, unaddressed, are left alone
    waiting = state.waited_s >= INTRO_PATIENCE_S and not is_filler_only_noise(utterance.text)
    intro = state.intake and state.customers >= 1 and not state.disclosed and (enough or waiting)
    group_answer = (
        state.intake and state.customers >= 2 and not from_staff and state.replying and enough
    )
    if not (named or lone_customer or intro or group_answer):
        return _silent("not_addressed")
    if not state.disclosed:
        return Decision("disclose", "named" if named else "intake")
    return Decision("speak", "named" if named else "intake")
