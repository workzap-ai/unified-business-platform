"""Room noise is not sent to speech-to-text (it writes sentences out of silence), and a refused
reply gets a second chance before pi falls back to a generic line (live test 18)."""

import struct
from types import SimpleNamespace
from uuid import uuid4

from test_pi_room_speech import Manager, build
from test_pi_room_speech import turn as base_turn

from app.modules.pi_meetings import room_speech, voice
from app.modules.pi_meetings.room_vad import Turn, TurnCutter
from app.shared.scope import WorkspaceScope


def frame(level: int, n: int = 1600) -> bytes:
    return struct.pack(f"<{n}h", *[level if i % 2 else -level for i in range(n)])


def test_a_turn_knows_its_loudest_moment() -> None:
    cutter = TurnCutter(sample_rate=16000)
    t, turns = 0.0, []
    for level in [20] * 10 + [900] * 10 + [20] * 12:
        turns += cutter.feed("g_1", frame(level), t)
        t += 0.1
    (turn,) = turns
    assert 800 <= turn.peak <= 1000
    quiet = []
    for level in [20] * 10 + [480] * 10 + [20] * 12:  # above the threshold but a soft murmur
        quiet += cutter.feed("g_2", frame(level), t)
        t += 0.1
    assert [round(x.peak) for x in quiet] == [480]


async def test_noise_that_never_rose_above_room_level_is_not_transcribed() -> None:
    calls = []

    class Count(Manager):
        async def transcribe(self, scope, audio, mime, **kw):
            calls.append(1)
            return await super().transcribe(scope, audio, mime, **kw)

    speech, manager, out, session = build(Count(heard="I'm a fucking idiot"))
    soft = Turn("g_1", b"\x10\x00" * 48000, 48000, 0.0, 1.0, peak=room_speech.STT_MIN_PEAK - 1)
    assert await speech.hear(soft) == "" and calls == []
    loud = Turn("g_1", b"\x10\x00" * 48000, 48000, 0.0, 1.0, peak=room_speech.STT_MIN_PEAK + 1)
    assert await speech.hear(loud) != "" and calls == [1]
    unknown = base_turn()  # a turn with no level (peak 0) is always read
    assert await speech.hear(unknown) != ""


async def test_a_refused_reply_gets_two_corrections_before_the_generic_line() -> None:
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    history = [voice.Said(True, "Hi, I'm pi, an AI. What does your business do?")]

    class Slow(Manager):
        def __init__(self, replies):
            super().__init__()
            self.replies, self.calls = list(replies), 0

        async def complete_structured(self, scope, model, **kw):
            self.calls += 1
            return SimpleNamespace(value=model(reply=self.replies.pop(0)))

    manager = Slow(
        [
            "That is a great question, thank you for asking.",
            "Great question, I am an assistant from Workzap.",
            "I'm pi, an AI assistant from Workzap. What kind of business do you run?",
        ]
    )
    out = await voice.reply_to(manager, scope, history, "What is your work?")
    assert not out.fallback and manager.calls == 3
    assert out.text.startswith("I'm pi, an AI assistant")
