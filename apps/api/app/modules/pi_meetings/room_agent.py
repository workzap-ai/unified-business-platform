"""pi in one video room: the part of the room agent that does not touch the video provider's SDK.

`RoomRun` gets the room's raw audio frames (one person at a time), cuts them into spoken turns,
hands each finished turn to the speech pipeline, tracks who is in the room, and applies the host's
orders (mute, mode, intake) the moment the heartbeat brings them. The SDK glue (`room_agent_sdk`)
only joins the call, feeds frames in here and plays what comes out, so this part is unit-tested on
plain bytes.

Rules that live here: pi never hears itself, a mute cuts pi off at once, a person who is talking
stops pi (barge-in), and at most a few turns are being processed at a time (a flood of turns is
dropped, never queued without limit).
"""

import asyncio
import logging
from array import array
from collections.abc import Callable
from typing import Any

from app.modules.pi_meetings import room_speech
from app.modules.pi_meetings.room_agent_claim import Orders
from app.modules.pi_meetings.room_speech import RoomSpeech
from app.modules.pi_meetings.room_vad import Turn, TurnCutter

logger = logging.getLogger(__name__)

AGENT_USER = "pi_agent"  # the agent's own id in the room: never s_ (staff) or g_ (guest)
MAX_PENDING = 3  # turns being transcribed or answered at once; more are dropped
ACTIVE_S = 45.0  # a person who sent no sound for this long no longer counts as in the room


def mono(pcm: bytes, channels: int) -> bytes:
    """16-bit interleaved PCM to mono (the average of the channels)."""
    if channels <= 1:
        return pcm
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % (2 * channels)])
    return array(
        "h",
        (sum(samples[i : i + channels]) // channels for i in range(0, len(samples), channels)),
    ).tobytes()


class RoomRun:
    def __init__(
        self,
        speech: RoomSpeech,
        *,
        clock: Callable[[], float],
        cutter: TurnCutter | None = None,
        user_id: str = AGENT_USER,
    ) -> None:
        self.speech = speech
        self.clock = clock
        self.user_id = user_id
        self.cutter = cutter or TurnCutter(sample_rate=48000)
        self.people: set[str] = set()
        self._tasks: set[asyncio.Task[Any]] = set()
        self.dropped = 0
        self._ticks = 0
        self.frames: dict[str, int] = {}  # frames heard per person since the last report
        self.seen: dict[str, float] = {}  # when each person last joined or made a sound
        speech.customers = self.customers
        speech.someone_speaking = self.cutter.speaking
        speech.speaker_active = self.cutter.is_speaking

    def customers(self) -> int:
        """Different people in the room who are not staff (and not pi itself) and who joined or
        made a sound lately. A guest who closed the page keeps a seat at the provider for a while
        and must not make one customer look like a crowd."""
        now = self.clock()
        return sum(
            1
            for p in self.people
            if p != self.user_id
            and not p.startswith("s_")
            and now - self.seen.get(p, 0.0) <= ACTIVE_S
        )

    def joined(self, speaker_id: str) -> None:
        if speaker_id and speaker_id != self.user_id:
            self.people.add(speaker_id)
            self.seen[speaker_id] = self.clock()

    def left(self, speaker_id: str) -> None:
        self.people.discard(speaker_id)
        turn = self.cutter.flush(speaker_id, self.clock())
        if turn is not None:
            self._start(turn)

    def apply(self, orders: Orders) -> None:
        """The heartbeat's orders. A mute (or leaving speech mode) stops pi mid-sentence."""
        session = self.speech.session
        session.muted = orders.muted or not orders.speak
        session.settings.mode = "speak" if orders.speak else "off"
        session.settings.intake = orders.intake
        session.settings.language = orders.language
        session.persona = orders.persona
        if session.muted:
            self.speech.barge_in()

    def on_audio(self, speaker_id: str, pcm: bytes, sample_rate: int, channels: int = 1) -> None:
        """One frame of one person's voice. Frames of the agent itself are ignored."""
        if not speaker_id or speaker_id == self.user_id:
            return
        self.joined(speaker_id)
        self.frames[speaker_id] = self.frames.get(speaker_id, 0) + 1
        self.seen[speaker_id] = self.clock()
        frame = room_speech.resample(mono(pcm, channels), sample_rate, self.cutter.sample_rate)
        if not frame:
            return
        for turn in self.cutter.feed(speaker_id, frame, self.clock()):
            self._start(turn)
        if self.speech.speaking and self.cutter.speaking():
            self.speech.barge_in()  # a person started talking: pi stops
        elif self.cutter.nod_ready(speaker_id) and len(self._tasks) < MAX_PENDING:
            task = asyncio.ensure_future(self.speech.nod())  # a quiet "mm-hm" while they talk
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def tick(self) -> None:
        """Called a few times a second: a turn whose frames stopped coming is finished here."""
        for turn in self.cutter.idle(self.clock()):
            self._start(turn)
        if self.speech.speaking and self.cutter.speaking():
            self.speech.barge_in()
        self._ticks += 1
        if self._ticks % 10 == 0 and len(self._tasks) < MAX_PENDING:  # every couple of seconds
            task = asyncio.ensure_future(self.speech.nudge())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def report(self) -> dict[str, int]:
        """How many frames each person sent since the last report (counts only, no sound)."""
        out, self.frames = self.frames, {}
        return out

    def _start(self, turn: Turn) -> None:
        if len(self._tasks) >= MAX_PENDING:
            self.dropped += 1
            return
        task = asyncio.ensure_future(self._handle(turn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, turn: Turn) -> None:
        try:
            reason = await self.speech.on_turn(turn)
            # why pi spoke or not, and how many people it counts: never the words
            logger.info("room_turn reason=%s customers=%d", reason, self.customers())
        except Exception:  # noqa: BLE001 - one bad turn must not stop the agent
            logger.exception("room_agent_turn_failed")

    async def drain(self) -> None:
        """Wait for the turns in flight (when leaving the room, and in tests)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
