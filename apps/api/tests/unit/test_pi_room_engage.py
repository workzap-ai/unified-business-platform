"""Live test 17 (2026-11-27): pi did not stop when talked over (audio was queued at once, so pi was
'not speaking' while it was heard), a filler sound came before every answer ('double voice'), the
live speech model wrote English as Urdu, pi never carried the conversation, and a customer who
said hello waited 28 s for the introduction."""

import asyncio
import struct
from types import SimpleNamespace

import pytest
from test_pi_room_speech import Manager, Out, build, turn

from app.ai.registry import DEFAULT_MODELS
from app.modules.pi_meetings import room_speech, voice
from app.modules.pi_meetings.room_vad import LOUD_RMS, TurnCutter


def test_live_speech_uses_the_better_model_with_a_fallback() -> None:
    assert room_speech.STT_ALIAS == "stt_live"
    assert DEFAULT_MODELS["openai"]["stt_live"] == "gpt-4o-transcribe"
    assert DEFAULT_MODELS["groq"]["stt_live"] == "whisper-large-v3"


def test_pi_leads_the_conversation_and_only_a_tired_person_gets_no_question() -> None:
    assert "LEAD the conversation" in voice.SYSTEM
    assert voice.question_policy([voice.Said(True, "Hi?"), voice.Said(True, "Which city?")]) == (
        "optional"
    )
    assert voice.question_policy([], calm=True) == "none"


@pytest.mark.parametrize(
    "text",
    ["क्या तुम मुझे सुन सकती है?", "आप मुझे सुन रहे हैं", "کیا آپ مجھے سن سکتے ہیں", "تم مجھے سن رہی ہو"],
)
def test_can_you_hear_me_is_understood_in_hindi_and_urdu_script(text) -> None:
    found = voice.control(text, [], "en")
    assert found is not None and found.kind == "hear", text


class Watch(Out):
    def __init__(self, speech_ref):
        super().__init__()
        self.speech_ref = speech_ref
        self.speaking_at_write = []
        self.after_write = None

    async def write(self, pcm, rate):
        self.speaking_at_write.append(self.speech_ref[0].speaking)
        await super().write(pcm, rate)
        if self.after_write:
            self.after_write(len(self.written))


async def test_pi_is_speaking_for_as_long_as_it_is_heard(monkeypatch) -> None:
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    speech, manager, out, session = build()
    ref = [speech]
    watch = Watch(ref)
    speech.out = watch
    speech.pace = True
    monkeypatch.setattr(room_speech.asyncio, "sleep", fake_sleep)
    await speech.on_turn(turn())
    assert watch.written and all(watch.speaking_at_write)  # `speaking` was true at every write
    assert sleeps and speech.speaking is False  # paced in real time, and finished at the end


async def test_a_person_talking_over_pi_stops_it_within_a_piece(monkeypatch) -> None:
    async def fake_sleep(s):
        return None

    speech, manager, out, session = build()
    watch = Watch([speech])
    speech.out = watch
    speech.pace = True
    monkeypatch.setattr(room_speech.asyncio, "sleep", fake_sleep)
    watch.after_write = lambda n: speech.barge_in() if n == 2 else None
    assert await speech.on_turn(turn()) == "cut_off"
    assert len(watch.written) == 2 and watch.flushes >= 1  # stopped, and what was queued dropped


def test_pis_own_echo_is_not_a_person_and_a_sustained_voice_is() -> None:
    cutter = TurnCutter(sample_rate=16000)

    def frame(level):
        n = 1600
        return struct.pack(f"<{n}h", *[level if i % 2 else -level for i in range(n)])

    t = 0.0
    for _ in range(10):  # a second of quiet teaches the room's noise level
        cutter.feed("g_1", frame(20), t)
        t += 0.1
    soft = 300
    assert soft < LOUD_RMS
    cutter.guard = True  # pi is speaking: its echo at this level must not start a turn
    for _ in range(5):
        cutter.feed("g_1", frame(soft), t)
        t += 0.1
    assert not cutter.speaking()
    cutter.guard = False
    for _ in range(6):
        cutter.feed("g_1", frame(soft), t)
        t += 0.1
    assert cutter.speaking() and cutter.talking_s() >= room_speech.BARGE_S


async def test_a_sound_like_mm_hm_comes_only_before_a_slow_answer(monkeypatch) -> None:
    monkeypatch.setattr(room_speech, "FILLER_AFTER_S", 0.05)

    class Delay(Manager):
        def __init__(self, wait, reply):
            super().__init__(heard="pi what do you think about my whole shop and its orders")
            self.wait, self.reply = wait, reply

        async def complete_structured(self, scope, model, **kw):
            await asyncio.sleep(self.wait)
            return SimpleNamespace(value=model(reply=self.reply))

    for wait, sounds in ((0.0, 0), (0.2, 1)):
        reply = f"Ten a day adds up {wait}."  # a new line each time: spoken lines are cached
        speech, manager, out, session = build(Delay(wait, reply))
        await speech.on_turn(turn())  # the disclosure
        session.last_spoke_at = None
        before = len(manager.tts)
        await speech.on_turn(turn())
        spoken = [t for t, _ in manager.tts[before:]]
        assert spoken[-1] == reply and len(spoken) == 1 + sounds, (wait, spoken)


async def test_a_silent_customer_who_spoke_first_gets_the_introduction_on_its_own() -> None:
    speech, manager, out, session = build(intake=True)
    speech.clock = lambda: 1000.0  # a still clock: the test's own one jumps ten seconds a call
    session.first_unheard_at = 999.0
    assert await speech.nudge() is False  # not yet: they may be about to go on
    session.first_unheard_at = 1000.0 - room_speech.INTRO_AFTER_S - 1
    assert await speech.nudge() is True
    assert manager.tts[0][0] == voice.late_opening("") and session.disclosed
    assert await speech.nudge() is False  # once
