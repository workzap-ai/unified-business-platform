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
import os
import re
import wave
from array import array
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.errors import GatewayUnavailable
from app.modules.pi import safety
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import meeting_memory, room_noise, room_turns, voice
from app.modules.pi_meetings.recording_routes import join_spoken_digits
from app.modules.pi_meetings.room_turns import Mode, RoomState, Utterance
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

STT_ALIAS = "stt_multi"
# speech-to-text writes "pi" as "hi", "pie" or "bye"; a spelling hint fixes most of it
STT_HINT = "Workzap, pi."
STT_HINT_ECHOES = frozenset({"workzap pi", "pi workzap"})
STT_PURPOSE = "meeting_room_stt"
STT_RATE = 16000  # a turn is sent to speech to text at this rate
TTS_RATE = 24000  # the rate of raw speech from the text to speech service
# a person's short pieces of one sentence are joined for this long (a pause ends a turn at 0.65 s,
# and people pause inside a sentence): pi answers the whole sentence, not its first breath
CARRY_S = 10.0
# when someone is still talking at the moment pi is ready, pi waits this long for them to
# finish instead of throwing its answer away
START_WAIT_S = 2.0
CARRY_REASONS = frozenset({"someone_speaking", "not_addressed"})
CARRY_CHARS = 600
# how pi sounds: a text-to-speech model that takes instructions is told the tone, the pace and,
# for Urdu, the accent; the line's script picks which (Urdu or Arabic letters mean Urdu)
STYLE_EN = (
    "Speak as a warm, calm, friendly assistant. Natural conversational pace with small pauses "
    "between sentences and a gentle smile in the voice. Never robotic, never rushed."
)
STYLE_UR = (
    "Speak natural, warm Pakistani Urdu with a native accent, as a kind and attentive person "
    "would. Calm conversational pace with small pauses and a gentle tone."
)
ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")
SPEECH_CACHE_MAX = 32  # fixed lines (the introduction) are kept as audio so they start at once
PIECE_S = 0.2  # pi's audio goes out in pieces this long; a cut-off takes effect at the next one
HEARD_CHARS = 600
SAFETY_CHARS = 580  # the emergency line must fit one spoken turn (the gateway refuses 600+)


_SPEECH_CACHE: dict[tuple[str, str, str], bytes] = {}


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
    # the last words of a person pi did not answer yet, with when they were said
    carry: dict[str, tuple[str, float]] = field(default_factory=dict)


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
        on_state: Callable[[Session], Awaitable[None]] | None = None,
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
        self.on_state = on_state  # told after every turn that changed what pi has done
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
                prompt=STT_HINT,
            )
        except GatewayUnavailable:
            logger.warning("room_speech_stt_unavailable")
            return ""
        text = redacted(join_spoken_digits(result.text or ""), HEARD_CHARS)
        if re.sub(r"[^a-z]+", " ", text.lower()).strip() in STT_HINT_ECHOES:
            return ""  # the model repeated the hint on a near-silent turn: nobody said it
        return text

    async def on_turn(self, turn: Turn) -> str:
        """Handle a finished turn. Returns what happened: the reason pi stayed silent, or
        'disclosed' or 'spoke'."""
        text = await self.hear(turn)
        if not text or room_noise.is_invented(text):  # nobody said it: not heard, not kept
            return "unheard"
        if os.environ.get("ROOM_LOG_HEARD") == "1":  # off by default: only for a test room
            logger.info("room_heard %s", text[:160])
        if self.on_line:
            await self.on_line(turn.speaker_id, text)
        async with self._lock:
            state = self.session
            now = self.clock()
            held = state.carry.pop(turn.speaker_id, None)
            heard = text
            if held is not None:
                if now - held[1] <= CARRY_S:
                    heard = f"{held[0]} {text}"[-CARRY_CHARS:]
                else:
                    state.history.append(voice.Said(False, held[0]))  # too old to join
            if state.halted:
                state.history.append(voice.Said(False, heard))
                return "halted"
            emergency = safety.emergency(heard) if state.settings.mode == "speak" else None
            if emergency is not None:
                # an emergency is never left to the model, to the name trigger or to the cooldown;
                # only the host's mute (and the speech cap) still hold
                state.halted = True
                state.history.append(voice.Said(False, heard))
                numbers = safety.emergency_reply(emergency, None, state.settings.language or None)[
                    :SAFETY_CHARS
                ]
                if state.spoken >= room_turns.MAX_SPOKEN:
                    await self._persist()
                    return "cap"
                said_numbers = await self._say(numbers)
                await self._persist()
                return "emergency" if said_numbers == "complete" else "not_spoken"
            decision = room_turns.decide(
                Utterance(turn.speaker_id, heard, True, now),
                RoomState(
                    mode=state.settings.mode,
                    muted=await self._muted(),
                    disclosed=state.disclosed,
                    spoken=state.spoken,
                    last_spoke_at=state.last_spoke_at,
                    someone_speaking=self.someone_speaking() or self.speaking,
                    customers=self.customers(),
                    intake=state.settings.intake,
                    answering=voice.confirm_state(state.history) == "pending",
                    resumed=state.disclosed
                    and state.last_spoke_at is not None
                    and now - state.last_spoke_at > room_turns.ANSWER_S,
                    replying=bool(state.history)
                    and state.history[-1].pi
                    and state.last_spoke_at is not None
                    and now - state.last_spoke_at <= room_turns.ANSWER_S,
                ),
            )
            if decision.action == "silent":
                if decision.reason in CARRY_REASONS and not room_turns.is_filler(heard):
                    state.carry[turn.speaker_id] = (heard, now)  # may join this person's next piece
                else:
                    state.history.append(voice.Said(False, heard))
                return decision.reason
            block = self.what_i_know() if self.what_i_know else {}
            if decision.action == "disclose":
                # a first name is asked about only when one customer is alone in the room: the
                # question is who it is, and memory stays unused until a clear yes
                name = meeting_memory.first_name(block) if block and self.customers() == 1 else ""
                line = voice.opening(name=name, language=state.settings.language)
            else:
                before = voice.confirm_state(state.history)
                answered = voice.confirm_state([*state.history, voice.Said(False, heard)])
                if answered == "denied" and before == "pending":
                    line = voice.NOT_THEM  # not them: memory stays unused for the whole call
                else:
                    reply = await voice.reply_to(
                        self.manager,
                        self.scope,
                        state.history,
                        heard,
                        language=state.settings.language,
                        what_i_know=block if answered == "confirmed" else {},
                    )
                    line = reply.text
            state.history.append(voice.Said(False, heard))
            said = await self._say(line)
            if said == "none":
                return "not_spoken"
            if said == "cut":
                await self._persist()
                return "cut_off"  # a disclosure that was cut off was not made: it is made again
            state.disclosed = True
            await self._persist()
            return "disclosed" if decision.action == "disclose" else "spoke"

    async def _persist(self) -> None:
        """Tell the owner of this session what pi has done so far; a failure never stops pi."""
        if self.on_state is None:
            return
        try:
            await self.on_state(self.session)
        except Exception:  # noqa: BLE001
            logger.warning("room_state_not_saved")

    async def _say(self, line: str) -> str:
        """Speak one line. 'complete' when every piece went out, 'cut' when it was stopped part of
        the way (by a mute or a person talking), 'none' when nothing was said."""
        if not line or await self._muted():
            return "none"
        style = STYLE_UR if ARABIC_SCRIPT.search(line) else STYLE_EN
        key = (line, self.session.settings.voice, style)
        audio = _SPEECH_CACHE.get(key)
        if audio is None:
            try:
                speech = await self.manager.synthesize(
                    self.scope,
                    line,
                    voice=self.session.settings.voice,
                    audio_format="pcm",
                    instructions=style,
                )
            except (GatewayUnavailable, ValueError):
                logger.warning("room_speech_tts_unavailable")
                return "none"
            audio = speech.audio
            if len(line) <= 220:  # fixed lines repeat across calls; long replies do not
                if len(_SPEECH_CACHE) >= SPEECH_CACHE_MAX:
                    _SPEECH_CACHE.pop(next(iter(_SPEECH_CACHE)))
                _SPEECH_CACHE[key] = audio
        pcm = resample(audio, TTS_RATE, TTS_RATE * 2)
        piece = int(TTS_RATE * 2 * PIECE_S) * 2  # bytes
        self._cut.clear()
        waited = 0.0
        while self.someone_speaking() and waited < START_WAIT_S and not self._cut.is_set():
            await asyncio.sleep(0.1)
            waited += 0.1
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
