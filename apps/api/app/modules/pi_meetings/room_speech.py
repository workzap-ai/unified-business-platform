"""What happens to one finished spoken turn in a video room: hear it, decide, speak (or stay quiet).

turn -> speech to text -> redact -> `room_turns.decide` -> the words (the AI disclosure composed in
code for pi's first turn, then `voice.reply_to`, which runs the reply linter and the safe line) ->
(an emergency is answered first, with the fixed emergency numbers, and then pi stops the flow)
-> text to speech -> audio to the room, in small pieces so that anyone
who starts talking, or a mute, cuts pi off at the next piece.

Everything outside is injected (the AI gateway, the audio output, the clock), so the whole path is
unit-tested without the video provider's SDK. No audio is stored: a turn is transcribed and dropped.
"""

import asyncio
import io
import logging
import wave
from array import array
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.errors import GatewayUnavailable
from app.modules.pi import safety
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import room_turns, voice
from app.modules.pi_meetings.recording_routes import join_spoken_digits
from app.modules.pi_meetings.room_turns import Mode, RoomState, Utterance
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

STT_ALIAS = "stt_multi"
STT_PURPOSE = "meeting_room_stt"
STT_RATE = 16000  # a turn is sent to speech to text at this rate
TTS_RATE = 24000  # the rate of raw speech from the text to speech service
PIECE_S = 0.2  # pi's audio goes out in pieces this long; a cut-off takes effect at the next one
HEARD_CHARS = 600
SAFETY_CHARS = 580  # the emergency line must fit one spoken turn (the gateway refuses 600+)


class AudioOut(Protocol):
    """Where pi's voice goes: the room's audio track."""

    async def write(self, pcm: bytes, sample_rate: int) -> None: ...

    async def flush(self) -> None: ...


@dataclass
class Settings:
    mode: Mode = "off"
    intake: bool = False
    language: str = ""
    voice: str = "alloy"


@dataclass
class Session:
    """What pi remembers of this one call."""

    settings: Settings
    muted: bool = False
    disclosed: bool = False
    halted: bool = False  # an emergency was voiced: pi says the numbers once and then stops
    spoken: int = 0
    last_spoke_at: float | None = None
    history: list[voice.Said] = field(default_factory=list)


def resample(pcm: bytes, src: int, dst: int) -> bytes:
    """16-bit mono PCM from one rate to another: averaging down, repeating up. Only whole-number
    ratios are used here (48000 to 16000, 24000 to 48000); any other pair comes back unchanged."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if src == dst or not samples:
        return samples.tobytes()
    if src % dst == 0:
        step = src // dst
        out = array(
            "h",
            (
                sum(samples[i : i + step]) // len(samples[i : i + step])
                for i in range(0, len(samples), step)
            ),
        )
        return out.tobytes()
    if dst % src == 0:
        up = dst // src
        return array("h", (s for s in samples for _ in range(up))).tobytes()
    return samples.tobytes()


def wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buffer.getvalue()


class RoomSpeech:
    def __init__(
        self,
        *,
        manager: Any,
        scope: WorkspaceScope,
        session: Session,
        out: AudioOut,
        customers: Callable[[], int],
        someone_speaking: Callable[[], bool],
        clock: Callable[[], float],
        is_muted: Callable[[], Awaitable[bool]] | None = None,
        what_i_know: Callable[[], dict[str, Any]] | None = None,
        on_line: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self.manager = manager
        self.scope = scope
        self.session = session
        self.out = out
        self.customers = customers
        self.someone_speaking = someone_speaking
        self.clock = clock
        self.is_muted = is_muted
        self.what_i_know = what_i_know
        self.on_line = (
            on_line  # (speaker_id, text) for every line heard and said, for the transcript
        )
        self._lock = asyncio.Lock()
        self._cut = asyncio.Event()
        self.speaking = False

    def barge_in(self) -> None:
        """Someone started talking: pi stops at the next piece."""
        if self.speaking:
            self._cut.set()

    async def _muted(self) -> bool:
        if self.session.muted:
            return True
        return bool(self.is_muted and await self.is_muted())

    async def hear(self, turn: Turn) -> str:
        """The words of one finished turn, redacted. Empty when it could not be read."""
        audio = wav(resample(turn.pcm, turn.sample_rate, STT_RATE), STT_RATE)
        try:
            result = await self.manager.transcribe(
                self.scope,
                audio,
                "audio/wav",
                alias=STT_ALIAS,
                purpose=STT_PURPOSE,
                language=self.session.settings.language or None,
            )
        except GatewayUnavailable:
            logger.warning("room_speech_stt_unavailable")
            return ""
        return redacted(join_spoken_digits(result.text or ""), HEARD_CHARS)

    async def on_turn(self, turn: Turn) -> str:
        """Handle a finished turn. Returns what happened: the reason pi stayed silent, or
        'disclosed' or 'spoke'."""
        text = await self.hear(turn)
        if not text:
            return "unheard"
        if self.on_line:
            await self.on_line(turn.speaker_id, text)
        async with self._lock:
            state = self.session
            if state.halted:
                state.history.append(voice.Said(False, text))
                return "halted"
            emergency = safety.emergency(text) if state.settings.mode == "speak" else None
            if emergency is not None:
                # an emergency is never left to the model, to the name trigger or to the cooldown;
                # only the host's mute (and the speech cap) still hold
                state.halted = True
                state.history.append(voice.Said(False, text))
                numbers = safety.emergency_reply(emergency, None, state.settings.language or None)[
                    :SAFETY_CHARS
                ]
                if state.spoken >= room_turns.MAX_SPOKEN:
                    return "cap"
                return "emergency" if await self._say(numbers) == "complete" else "not_spoken"
            decision = room_turns.decide(
                Utterance(turn.speaker_id, text, True, self.clock()),
                RoomState(
                    mode=state.settings.mode,
                    muted=await self._muted(),
                    disclosed=state.disclosed,
                    spoken=state.spoken,
                    last_spoke_at=state.last_spoke_at,
                    someone_speaking=self.someone_speaking() or self.speaking,
                    customers=self.customers(),
                    intake=state.settings.intake,
                ),
            )
            if decision.action == "silent":
                state.history.append(voice.Said(False, text))
                return decision.reason
            if decision.action == "disclose":
                line = voice.opening(language=state.settings.language)
            else:
                reply = await voice.reply_to(
                    self.manager,
                    self.scope,
                    state.history,
                    text,
                    language=state.settings.language,
                    what_i_know=self.what_i_know() if self.what_i_know else None,
                )
                line = reply.text
            state.history.append(voice.Said(False, text))
            said = await self._say(line)
            if said == "none":
                return "not_spoken"
            if said == "cut":
                return "cut_off"  # a disclosure that was cut off was not made: it is made again
            state.disclosed = True
            return "disclosed" if decision.action == "disclose" else "spoke"

    async def _say(self, line: str) -> str:
        """Speak one line. 'complete' when every piece went out, 'cut' when it was stopped part of
        the way (by a mute or a person talking), 'none' when nothing was said."""
        if not line or await self._muted():
            return "none"
        try:
            speech = await self.manager.synthesize(
                self.scope, line, voice=self.session.settings.voice, audio_format="pcm"
            )
        except (GatewayUnavailable, ValueError):
            logger.warning("room_speech_tts_unavailable")
            return "none"
        pcm = resample(speech.audio, TTS_RATE, TTS_RATE * 2)
        piece = int(TTS_RATE * 2 * PIECE_S) * 2  # bytes
        self._cut.clear()
        self.speaking = True
        spoke = False
        finished = False
        try:
            for i in range(0, len(pcm), piece):
                # re-checked before every piece, the first included: synthesis takes seconds, and
                # someone may have started talking meanwhile
                if self._cut.is_set() or self.someone_speaking() or await self._muted():
                    await self.out.flush()
                    break
                await self.out.write(pcm[i : i + piece], TTS_RATE * 2)
                spoke = True
            else:
                finished = True
        finally:
            self.speaking = False
        if spoke:
            self.session.spoken += 1
            self.session.last_spoke_at = self.clock()
            self.session.history.append(voice.Said(True, line))
            if self.on_line:
                await self.on_line(voice.PI_LABEL, line)
        if not spoke:
            return "none"
        return "complete" if finished else "cut"
