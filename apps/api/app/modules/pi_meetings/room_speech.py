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
from app.modules.pi_meetings import meeting_memory, room_noise, room_recall, room_turns, voice
from app.modules.pi_meetings.recording_routes import join_spoken_digits
from app.modules.pi_meetings.room_turns import Mode, RoomState, Utterance
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

STT_ALIAS = "stt_live"
# speech-to-text writes "pi" as "hi", "pie" or "bye"; a spelling hint fixes most of it
STT_HINT = "Workzap, pi."
# places and common words people in these calls say: speech-to-text writes them right
# more often when it has seen them (found live: Lahore was written 'Lourdes')
STT_PLACES = "Lahore, Karachi, Islamabad, Rawalpindi, Faisalabad, Multan, Peshawar, Quetta."
STT_FACT_CHARS = 200
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
FILLER_WORDS = 5  # a turn of at least this many words gets a short "mm-hm" while pi thinks
FALLBACK_QUIET_S = 15.0  # a safe-line reply within this long of pi speaking is not said
CARRY_REASONS = frozenset({"someone_speaking", "not_addressed"})
CARRY_CHARS = 600
# how pi sounds: a text-to-speech model that takes instructions is told the tone, the pace and,
# for Urdu, the accent; the line's script picks which (Urdu or Arabic letters mean Urdu)
STYLE_EN = (
    "Speak like a warm, real person on a call, not an announcer: natural rhythm, small breaths "
    "and pauses between thoughts, a gentle smile in the voice and slight changes in pitch. "
    "Calm, attentive, never robotic and never rushed."
)
STYLE_UR = (
    "Speak natural, warm Pakistani Urdu with a native accent, like a kind and attentive person "
    "on a call: calm conversational pace, small breaths and pauses, a gentle tone and slight "
    "changes in pitch. Never robotic."
)
# a listener's small sounds ("mm-hm"): very short, low and quiet, never louder than speech
STYLE_SOFT = (
    "A very quiet, low, warm listening sound of a person paying close attention, like a soft "
    "hum of agreement. Under one second, gentle, never louder than normal speech."
)
NODS = {
    "en": ("Mm-hm.", "Uh-huh.", "Mm.", "Mm-hm.", "Right."),
    "ur": ("ہوں۔", "جی۔", "ہمم۔", "جی جی۔", "اچھا۔"),
}
NUDGE_AFTER_S = 20.0  # pi asked and nobody answered for this long: one gentle 'take your time'
NUDGE_CAP = 4  # per call
NUDGE_LINES = {"en": "Take your time.", "ur": "آپ آرام سے بتائیں۔"}
PACE_LEAD_S = 0.4  # how much audio pi keeps queued ahead of the clock
BARGE_S = 0.35  # a person must talk this long, without a break, to stop pi
FILLER_AFTER_S = 1.0  # a sound like 'mm-hm' only when the answer takes longer than this
INTRO_AFTER_S = 4.0  # a silent customer who spoke first gets the introduction on its own
NOD_GAP_S = 9.0  # at least this long between two nods
NOD_CAP = 12  # nods in one call
NOD_ACTIVE_S = 60.0  # pi nods only while it is in the conversation (it spoke this recently)
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
    voice: str = "marin"


@dataclass
class Session:
    """What pi remembers of this one call."""

    settings: Settings
    muted: bool = False
    disclosed: bool = False
    halted: bool = False  # an emergency was voiced: pi says the numbers once and then stops
    spoken: int = 0
    ideas: int = 0  # free suggestions given in this call (capped by voice.IDEA_CAP)
    # the language the person asked pi to speak ("Urdu mein bolo"): it holds until they ask again
    language_pref: str = ""
    # a solution was asked for in a piece of speech that was held and joined to a later one, where
    # the words may no longer show it: it is answered at the next reply
    wants_solution: bool = False
    facts: list[str] = field(default_factory=list)  # what they told pi in this call, in few words
    last_spoke_at: float | None = None
    nods: int = 0
    waiting: dict[str, list[str]] = field(default_factory=dict)  # heard, not yet answered
    nudges: int = 0
    nudged_for: float | None = None  # the pi line a nudge was already made for
    first_unheard_at: float | None = (
        None  # first short customer turn pi let pass, before its introduction
    )
    slow: bool = False  # the person asked pi to slow down: the voice is told so
    since_recap: int = 0  # pi's answers since it last summed up what it understood
    persona: str = ""  # the meeting's agent: focus and tone, below the rules (agents.py)
    last_nod_at: float | None = None
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
        on_screen: Callable[[], str] | None = None,
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
        self.on_screen = on_screen  # one sentence on what a shared screen shows, or ''
        self.on_line = (
            on_line  # (speaker_id, text) for every line heard and said, for the transcript
        )
        self.on_state = on_state  # told after every turn that changed what pi has done
        # is THIS person talking again? (set by the room; by default: anyone talking)
        self.speaker_active: Callable[[str], bool] = lambda _speaker: self.someone_speaking()
        self._lock = asyncio.Lock()
        self._out_lock = asyncio.Lock()  # one voice at a time: nothing is written over another
        # True in the real agent: audio is written in real time, so `speaking` stays true
        # for as long as pi is heard and a person talking can stop it (tests write at once)
        self.pace = False
        # can pi look at shared screens in this deployment, and what does it see right now:
        # (a screen is shared, one sentence about it). Set by the room agent.
        self.can_see_screen = False
        self.screen: Callable[[], tuple[bool, str]] = lambda: (False, "")
        self._cut = asyncio.Event()
        self.speaking = False

    def barge_in(self) -> None:
        """Someone started talking: pi stops at the next piece."""
        if self.speaking:
            self._cut.set()

    async def nod(self) -> bool:
        """A small "mm-hm" while a person is still talking, so they feel listened to. Only after
        pi has told them it is an AI, only while pi is in the conversation, never while pi is
        speaking, muted or halted, and not more often than NOD_GAP_S. It is not a turn: not kept
        in the history or the transcript, and a person talking does not cut it."""
        state = self.session
        now = self.clock()
        if (
            state.settings.mode != "speak"
            or not state.disclosed
            or state.halted
            or self.speaking
            or state.nods >= NOD_CAP
            or state.last_spoke_at is None
            or now - state.last_spoke_at > NOD_ACTIVE_S
            or (state.last_nod_at is not None and now - state.last_nod_at < NOD_GAP_S)
            or await self._muted()
        ):
            return False
        lang = state.language_pref or voice.reply_language(
            state.history, "", state.settings.language
        )
        options = NODS["en" if lang == "en" else "ur"]
        line = options[state.nods % len(options)]
        state.nods += 1
        state.last_nod_at = now
        audio = await self._speech(line, STYLE_SOFT)
        if audio is None or await self._muted() or self._out_lock.locked():
            return False
        pcm = resample(audio, TTS_RATE, TTS_RATE * 2)
        piece = int(TTS_RATE * 2 * PIECE_S) * 2
        async with self._out_lock:
            for i in range(0, len(pcm), piece):
                await self.out.write(pcm[i : i + piece], TTS_RATE * 2)
        return True

    async def _intro_alone(self, now: float) -> bool:
        """A customer spoke first, pi let short pieces pass, and then nobody said anything more:
        after INTRO_AFTER_S pi introduces itself on its own instead of waiting for the next piece
        of speech (live test 17: pi came in 28 s after the first 'hello')."""
        state = self.session
        if (
            state.settings.mode != "speak"
            or not state.settings.intake
            or state.disclosed
            or state.halted
            or state.first_unheard_at is None
            or now - state.first_unheard_at < INTRO_AFTER_S
            or self.speaking
            or self.someone_speaking()
            or self.customers() < 1
            or self._lock.locked()
            or await self._muted()
        ):
            return False
        async with self._lock:
            if state.disclosed or self.someone_speaking():
                return False
            language = voice.opening_language("", state.settings.language)
            said = await self._say(voice.late_opening(language))
            if said in ("none", "cut"):
                return False
            state.disclosed = True
            await self._persist()
            return True

    async def nudge(self) -> bool:
        """One gentle "Take your time." when pi's last line was a question and nobody has said a
        word for NUDGE_AFTER_S: a silent customer is thinking, not gone, and a silent room feels
        broken. Once per question, a few times a call, never while anyone is speaking, never when
        muted. Not a turn: not kept in the history or the transcript."""
        state = self.session
        now = self.clock()
        if await self._intro_alone(now):
            return True
        if (
            state.settings.mode != "speak"
            or not state.disclosed
            or state.halted
            or self.speaking
            or self.someone_speaking()
            or self.customers() < 1
            or state.nudges >= NUDGE_CAP
            or state.last_spoke_at is None
            or state.nudged_for == state.last_spoke_at
            or now - state.last_spoke_at < NUDGE_AFTER_S
            or not state.history
            or not state.history[-1].pi
            or not state.history[-1].text.rstrip().endswith(("?", "؟"))
            or await self._muted()
        ):
            return False
        state.nudged_for = state.last_spoke_at
        state.nudges += 1
        lang = state.language_pref or voice.reply_language(
            state.history, "", state.settings.language
        )
        line = NUDGE_LINES["en" if lang == "en" else "ur"]
        audio = await self._speech(line, STYLE_UR if lang != "en" else STYLE_EN)
        if audio is None or await self._muted() or self.someone_speaking():
            return False
        pcm = resample(audio, TTS_RATE, TTS_RATE * 2)
        piece = int(TTS_RATE * 2 * PIECE_S) * 2
        for i in range(0, len(pcm), piece):
            if self.someone_speaking():
                await self.out.flush()
                break
            await self.out.write(pcm[i : i + piece], TTS_RATE * 2)
        return True

    async def _speech(self, line: str, style: str) -> bytes | None:
        """The audio of one short fixed line (kept, so a nod costs one call per line, once)."""
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
                return None
            audio = speech.audio
            if len(_SPEECH_CACHE) >= SPEECH_CACHE_MAX:
                _SPEECH_CACHE.pop(next(iter(_SPEECH_CACHE)))
            _SPEECH_CACHE[key] = audio
        return audio

    async def _muted(self) -> bool:
        if self.session.muted:
            return True
        return bool(self.is_muted and await self.is_muted())

    def stt_prompt(self) -> str:
        """What speech-to-text is told before each turn: pi's names, common places, and the
        few words pi already learned in this call (the customer's trade and place come back)."""
        facts = " ".join(self.session.facts)[-STT_FACT_CHARS:]
        return " ".join(part for part in (STT_HINT, STT_PLACES, facts) if part)

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
                prompt=self.stt_prompt(),
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
        # every piece waits here with its words; whoever gets the lock first answers ALL the
        # pieces of this person that are waiting, the rest find nothing left (found live: 59
        # short turns queued behind each other and the answer to a question came 86 s late)
        self.session.waiting.setdefault(turn.speaker_id, []).append(text)
        async with self._lock:
            state = self.session
            now = self.clock()
            pieces = state.waiting.pop(turn.speaker_id, [])
            if not pieces:
                return "merged"
            text = " ".join(pieces)[-CARRY_CHARS:]
            if state.settings.mode == "speak":
                state.language_pref = voice.asked_language(text) or state.language_pref
                state.wants_solution = state.wants_solution or voice.asks_for_solution(text)
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
                    waited_s=0.0
                    if state.disclosed or state.first_unheard_at is None
                    else now - state.first_unheard_at,
                    resumed=state.disclosed
                    and state.last_spoke_at is not None
                    and now - state.last_spoke_at > room_turns.ANSWER_S,
                    replying=bool(state.history)
                    and state.history[-1].pi
                    and state.last_spoke_at is not None
                    and now - state.last_spoke_at <= room_turns.ANSWER_S,
                ),
            )
            if (
                decision.action == "silent"
                and not state.disclosed
                and state.first_unheard_at is None
                and decision.reason == "not_addressed"
                and state.settings.intake
                and not turn.speaker_id.startswith("s_")
            ):
                state.first_unheard_at = now
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
                opening_language = voice.opening_language(heard, state.settings.language)
                already_talking = any(not h.pi for h in state.history) or bool(state.carry)
                if already_talking and not name:
                    line = voice.late_opening(opening_language)  # no question: they have spoken
                else:
                    line = voice.opening(name=name, language=opening_language)
            else:
                before = voice.confirm_state(state.history)
                answered = voice.confirm_state([*state.history, voice.Said(False, heard)])
                if answered == "denied" and before == "pending":
                    line = voice.NOT_THEM  # not them: memory stays unused for the whole call
                elif (
                    ctrl := voice.control(
                        heard,
                        state.history,
                        state.language_pref
                        or voice.reply_language(state.history, heard, state.settings.language),
                    )
                ) is not None:
                    line = ctrl.line  # asked to repeat, to confirm it is heard, to slow down
                    if ctrl.kind == "screen" and self.can_see_screen:
                        sharing, note = self.screen()
                        line = voice.screen_line(
                            state.language_pref
                            or voice.reply_language(state.history, heard, state.settings.language),
                            sharing,
                            note,
                        )
                    if ctrl.kind in ("slow", "fast"):
                        state.slow = ctrl.kind == "slow"
                else:
                    lang = state.language_pref or voice.reply_language(
                        state.history, heard, state.settings.language
                    )
                    recap = (
                        state.since_recap >= voice.RECAP_EVERY
                        and len(state.facts) >= voice.RECAP_MIN_FACTS
                        and not state.wants_solution
                    )
                    quick = len(heard.split()) >= FILLER_WORDS and not self.speaker_active(
                        turn.speaker_id
                    )
                    thinking = asyncio.create_task(
                        voice.reply_to(
                            self.manager,
                            self.scope,
                            state.history,
                            heard,
                            language=state.settings.language,
                            what_i_know=block if answered == "confirmed" else {},
                            ideas_given=state.ideas,
                            acknowledged=quick,
                            prefer=state.language_pref,
                            persona=state.persona,
                            recap=recap,
                            wants_solution=state.wants_solution,
                            learned=state.facts,
                            on_screen=self.on_screen() if self.on_screen else "",
                        )
                    )
                    if quick:
                        # a human sound only when the answer is slow: with a fast one the
                        # sound and the answer would be two voices in a row
                        done, _ = await asyncio.wait({thinking}, timeout=FILLER_AFTER_S)
                        if not done:
                            await self._say(voice.filler(lang, state.spoken), filler=True)
                    reply = await thinking
                    logger.info(
                        "room_reply lang=%s fallback=%s why=%s idea=%s recap=%s chars=%d",
                        lang,
                        reply.fallback,
                        reply.why or "-",
                        reply.idea,
                        recap,
                        len(reply.text),
                    )
                    line = reply.text
                    if state.wants_solution and (reply.idea or line == voice.solution_line(lang)):
                        state.wants_solution = False  # answered
                    if reply.idea:
                        state.ideas += 1
                    room_recall.merge_fact(state.facts, reply.learned, reply.replaces)
                    state.since_recap += 1
                    if recap and not reply.fallback and reply.text.rstrip().endswith(("?", "؟")):
                        state.since_recap = 0  # it summed up and asked: the count starts again
                    if (
                        reply.fallback
                        and state.last_spoke_at is not None
                        and now - state.last_spoke_at <= FALLBACK_QUIET_S
                    ):
                        # the canned "let me think" line right after pi spoke only adds noise
                        state.history.append(voice.Said(False, heard))
                        return "not_spoken"
            if self.speaker_active(turn.speaker_id):
                # they began talking again while pi was thinking: what was heard is only the first
                # half of what they are saying. Hold it, throw this answer away and answer the whole
                # once they stop (found live: pi answered one long sentence twice in a row).
                state.carry[turn.speaker_id] = (heard, now)
                return "someone_speaking"
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

    async def _say(self, line: str, *, filler: bool = False) -> str:
        """Speak one line. 'complete' when every piece went out, 'cut' when it was stopped part of
        the way (by a mute or a person talking), 'none' when nothing was said. A filler (a short
        human sound) is not a turn: it is not counted, not kept in the history or the transcript."""
        if not line or await self._muted():
            return "none"
        style = STYLE_SOFT if filler else STYLE_UR if ARABIC_SCRIPT.search(line) else STYLE_EN
        if self.session.slow and not filler:
            style += " Speak noticeably slower and clearer than usual, with longer pauses."
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
        await self._out_lock.acquire()
        self.speaking = True
        spoke = False
        finished = False
        try:
            loop = asyncio.get_running_loop()
            began = loop.time()
            for n, i in enumerate(range(0, len(pcm), piece)):
                # re-checked before every piece, the first included: synthesis takes seconds, and
                # someone may have started talking meanwhile
                if self._cut.is_set() or self.someone_speaking() or await self._muted():
                    await self.out.flush()
                    break
                await self.out.write(pcm[i : i + piece], TTS_RATE * 2)
                spoke = True
                if self.pace:  # stay only PACE_LEAD_S ahead of what is being heard
                    ahead = began + (n + 1) * PIECE_S - PACE_LEAD_S - loop.time()
                    if ahead > 0:
                        await asyncio.sleep(ahead)
            else:
                finished = True
                if self.pace:
                    await asyncio.sleep(PACE_LEAD_S)  # the last of it is still playing
        finally:
            self.speaking = False
            self._out_lock.release()
        if spoke and filler:
            return "none"
        if spoke:
            self.session.spoken += 1
            self.session.last_spoke_at = self.clock()
            self.session.history.append(voice.Said(True, line))
            if self.on_line:
                await self.on_line(voice.PI_LABEL, line)
        if not spoke:
            return "none"
        return "complete" if finished else "cut"
