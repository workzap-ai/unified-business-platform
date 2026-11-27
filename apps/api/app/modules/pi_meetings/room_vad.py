"""Cuts each person's live audio into spoken turns, so pi can hear one finished turn at a time.

The room agent receives raw audio frames per person (the provider's captions cannot be trusted for
Urdu). This is the plain energy gate that turns those frames into turns: a turn starts when the
voice has been loud for a moment, ends after a short silence, is cut at a maximum length, and a
blip that is too short to be speech is dropped. No audio leaves this object except a finished turn,
which the caller transcribes and then drops: nothing here stores audio.

Pure Python on 16-bit mono PCM (no numpy), so it is unit-tested without the provider's SDK.
"""

import math
from array import array
from dataclasses import dataclass, field

LOUD_RMS = 450  # 16-bit samples; a quiet room is below this, a speaking voice above it
MIN_LOUD_RMS = 170  # a quiet microphone in a quiet room: never listen below this
FLOOR_FACTOR = 4.0  # speech must be this many times louder than the room's own noise
FLOOR_LEARN_S = 0.6  # quiet heard before the room's noise level is trusted
LEARN_CEIL = 120  # only frames this quiet are room noise: a soft voice is never learned as noise
START_S = 0.12  # the voice must stay loud this long to start a turn
END_SILENCE_S = (
    0.65  # a pause this long ends the turn (shorter: pi answers sooner; pieces are rejoined)
)
MIN_TURN_S = 0.5  # a shorter turn is a cough or a click: dropped
MAX_TURN_S = 15.0  # a longer turn is cut here and a new one starts
NOD_AFTER_S = 5.0  # a person who has talked this long without a break may get a small "mm-hm"
NOD_PAUSE_S = 0.3  # ...in a breath between words (a pause this long, shorter than a turn's end)
PRE_ROLL_S = 0.25  # audio kept from just before the voice started, so no word is clipped


@dataclass(frozen=True)
class Turn:
    speaker_id: str
    pcm: bytes  # 16-bit little-endian mono
    sample_rate: int
    started_at: float  # seconds on the caller's clock
    ended_at: float


def rms(frame: bytes) -> float:
    samples = array("h")
    samples.frombytes(frame[: len(frame) - len(frame) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


@dataclass
class _Person:
    pre: list[tuple[bytes, float]] = field(default_factory=list)  # recent quiet frames
    pre_s: float = 0.0
    loud_s: float = 0.0  # consecutive loud time before a turn has started
    held: list[bytes] = field(default_factory=list)  # the loud frames while it is deciding
    frames: list[bytes] = field(default_factory=list)  # the turn in progress
    quiet_s: float = 0.0
    length_s: float = 0.0
    started_at: float = 0.0
    speaking: bool = False
    last_at: float = 0.0  # when the last frame came
    nod_at_s: float = 0.0  # how far into this turn the last nod was
    peak: float = 0.0  # loudest frame since the last report (a level, never any sound)
    floor: float = 0.0  # this person's background noise level, learned from quiet frames
    floor_s: float = 0.0  # seconds of quiet heard so far


class TurnCutter:
    """Feed it frames; it returns the turns that have just ended."""

    def __init__(self, sample_rate: int = 48000, loud_rms: float = LOUD_RMS) -> None:
        self.sample_rate = sample_rate
        self.loud_rms = loud_rms
        self._people: dict[str, _Person] = {}

    def speaking(self) -> bool:
        """True while anyone is in the middle of a turn (pi must not talk over them)."""
        return any(p.speaking for p in self._people.values())

    def is_speaking(self, speaker_id: str) -> bool:
        """True while this one person is in the middle of a turn."""
        person = self._people.get(speaker_id)
        return bool(person and person.speaking)

    def nod_ready(self, speaker_id: str) -> bool:
        """True once per stretch of long speech, in a small pause: a listener's "mm-hm" fits
        here. It only says the moment is right; the caller decides whether pi nods at all."""
        person = self._people.get(speaker_id)
        if (
            person is None
            or not person.speaking
            or person.length_s - person.nod_at_s < NOD_AFTER_S
            or not NOD_PAUSE_S <= person.quiet_s < END_SILENCE_S
        ):
            return False
        person.nod_at_s = person.length_s
        return True

    def _threshold(self, person: _Person) -> float:
        """How loud a frame must be to count as a voice for this person. Never above the default,
        so a noisy room is no worse off; lower for a quiet microphone once its background level is
        known, so a soft speaker is still heard (found live: pi did not answer a quiet customer)."""
        if person.floor_s < FLOOR_LEARN_S:
            return self.loud_rms
        return min(self.loud_rms, max(MIN_LOUD_RMS, person.floor * FLOOR_FACTOR))

    @staticmethod
    def _learn(person: _Person, level: float, seconds: float) -> None:
        """Track the quiet level slowly (a few seconds), so a cough or a click does not move it."""
        person.floor_s += seconds
        weight = min(0.5, seconds / 3.0)
        person.floor = (
            level if person.floor == 0.0 else person.floor + (level - person.floor) * weight
        )

    def peaks(self) -> dict[str, int]:
        """The loudest frame of each person since the last call (numbers only), to tell
        'too quiet to be heard' from 'heard but not addressed' in the logs."""
        out = {who: int(p.peak) for who, p in self._people.items() if p.peak}
        for p in self._people.values():
            p.peak = 0.0
        return out

    def forget(self, speaker_id: str) -> None:
        self._people.pop(speaker_id, None)

    def feed(self, speaker_id: str, frame: bytes, at: float) -> list[Turn]:
        """One frame (16-bit mono PCM at the cutter's rate) from one person, at time `at`."""
        if not speaker_id or len(frame) < 2:
            return []
        seconds = (len(frame) // 2) / self.sample_rate
        person = self._people.setdefault(speaker_id, _Person())
        person.last_at = at
        level = rms(frame)
        person.peak = max(person.peak, level)
        loud = level >= self._threshold(person)
        if not loud and not person.speaking and level < LEARN_CEIL:
            self._learn(person, level, seconds)
        out: list[Turn] = []
        if not person.speaking:
            self._before_turn(person, frame, seconds, loud, at)
            return out
        person.frames.append(frame)
        person.length_s += seconds
        person.quiet_s = 0.0 if loud else person.quiet_s + seconds
        if person.quiet_s >= END_SILENCE_S or person.length_s >= MAX_TURN_S:
            turn = self._finish(speaker_id, person, at)
            if turn is not None:
                out.append(turn)
        return out

    def idle(self, at: float) -> list[Turn]:
        """Turns that ended because the frames stopped. A browser or a server may send nothing
        while someone is silent: a turn is then finished by the clock, not by quiet frames,
        or it would never end and pi would think the person is still talking."""
        out: list[Turn] = []
        for speaker_id, person in self._people.items():
            gap = at - person.last_at
            if person.speaking and gap >= END_SILENCE_S:
                person.quiet_s += gap
                person.length_s += gap
                turn = self._finish(speaker_id, person, at)
                if turn is not None:
                    out.append(turn)
        return out

    def flush(self, speaker_id: str, at: float) -> Turn | None:
        """The person left: whatever they were saying is a finished turn."""
        person = self._people.pop(speaker_id, None)
        if person is None or not person.speaking:
            return None
        return self._finish(speaker_id, person, at)

    def _before_turn(
        self, person: _Person, frame: bytes, seconds: float, loud: bool, at: float
    ) -> None:
        if not loud:
            person.loud_s = 0.0
            person.held.clear()
            person.pre.append((frame, seconds))
            person.pre_s += seconds
            while person.pre_s > PRE_ROLL_S and person.pre:
                person.pre_s -= person.pre.pop(0)[1]
            return
        person.held.append(frame)
        person.loud_s += seconds
        if person.loud_s >= START_S:
            person.speaking = True
            person.frames = [f for f, _ in person.pre] + person.held
            person.length_s = person.pre_s + person.loud_s
            person.started_at = at - person.length_s
            person.quiet_s = 0.0
            person.pre.clear()
            person.pre_s = 0.0
            person.held = []

    def _finish(self, speaker_id: str, person: _Person, at: float) -> Turn | None:
        voiced = person.length_s - person.quiet_s
        turn = Turn(
            speaker_id=speaker_id,
            pcm=b"".join(person.frames),
            sample_rate=self.sample_rate,
            started_at=person.started_at,
            ended_at=at,
        )
        person.frames = []
        person.nod_at_s = 0.0
        person.speaking = False
        person.length_s = 0.0
        person.quiet_s = 0.0
        person.loud_s = 0.0
        return turn if voiced >= MIN_TURN_S else None
