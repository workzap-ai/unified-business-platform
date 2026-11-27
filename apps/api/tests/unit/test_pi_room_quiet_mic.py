"""A quiet microphone is still heard, and a silent customer gets one gentle word (found live: pi did
not answer a soft-spoken customer, and a silent room feels broken)."""

import struct

from test_pi_room_speech import Manager, build

from app.modules.pi_meetings import room_speech, voice
from app.modules.pi_meetings.room_vad import LOUD_RMS, MIN_LOUD_RMS, TurnCutter

RATE = 16000


def frame(level: int, seconds: float = 0.1) -> bytes:
    n = int(RATE * seconds)
    return struct.pack(f"<{n}h", *[level if i % 2 else -level for i in range(n)])


def feed(cutter, level, seconds, who="g_1", t=0.0):
    out = []
    for _ in range(int(seconds * 10)):
        out += cutter.feed(who, frame(level), t)
        t += 0.1
    return out, t


def test_a_soft_voice_is_not_heard_until_the_room_noise_is_known_then_it_is() -> None:
    cutter = TurnCutter(sample_rate=RATE)
    soft = 300  # a quiet microphone: under the default threshold
    assert soft < LOUD_RMS
    # no quiet yet: the default threshold holds, as before
    _, t = feed(cutter, soft, 1.0)
    assert not cutter.speaking()
    # one second of silence teaches the room's noise level; a soft voice now starts a turn
    _, t = feed(cutter, 20, 1.0, t=t)
    _, t = feed(cutter, soft, 0.6, t=t)
    assert cutter.speaking()
    turns, t = feed(cutter, 20, 1.0, t=t)
    assert len(turns) == 1 and turns[0].speaker_id == "g_1"


def test_a_noisy_room_is_no_worse_off_than_before() -> None:
    cutter = TurnCutter(sample_rate=RATE)
    noise = 200  # above LEARN_CEIL: loud room noise is never learned as silence
    _, t = feed(cutter, noise, 3.0)
    assert not cutter.speaking()  # still under the default threshold: no turn, no change
    _, t = feed(cutter, 700, 0.5, t=t)
    assert cutter.speaking()  # a real voice is still heard


def test_the_threshold_never_goes_below_the_floor_or_above_the_default() -> None:
    cutter = TurnCutter(sample_rate=RATE)
    _, t = feed(cutter, 0, 1.0)  # dead silence
    person = cutter._people["g_1"]
    assert MIN_LOUD_RMS <= cutter._threshold(person) <= LOUD_RMS
    _, t = feed(cutter, 100, 2.0, t=t)  # a soft hiss
    assert MIN_LOUD_RMS <= cutter._threshold(person) <= LOUD_RMS


async def ready():
    speech, manager, out, session = build(Manager(heard="pi what do you think about my shop"))
    await speech.on_turn(__import__("test_pi_room_speech").turn())  # the disclosure + a question
    return speech, manager, out, session


async def test_a_silent_customer_gets_one_gentle_word_after_a_question() -> None:
    speech, manager, out, session = await ready()
    assert session.history[-1].pi and session.history[-1].text.endswith("?")
    session.last_spoke_at = speech.clock() - room_speech.NUDGE_AFTER_S - 1
    written = len(out.written)
    assert await speech.nudge() is True
    assert manager.tts[-1][0] == room_speech.NUDGE_LINES["en"] and len(out.written) > written
    assert await speech.nudge() is False  # once per question
    assert all(h.text != room_speech.NUDGE_LINES["en"] for h in session.history)  # not a turn


async def test_no_nudge_when_it_is_too_soon_muted_or_somebody_is_talking() -> None:
    speech, manager, out, session = await ready()
    session.last_spoke_at = speech.clock()  # pi just spoke
    assert await speech.nudge() is False
    session.last_spoke_at = speech.clock() - room_speech.NUDGE_AFTER_S - 1
    session.muted = True
    assert await speech.nudge() is False
    session.muted = False
    speech.someone_speaking = lambda: True
    assert await speech.nudge() is False
    speech.someone_speaking = lambda: False
    session.history.append(voice.Said(False, "we sell shoes"))  # they answered: nothing to nudge
    assert await speech.nudge() is False


def test_the_fixed_nudge_lines_pass_the_spoken_rules() -> None:
    for line in room_speech.NUDGE_LINES.values():
        assert "?" not in line and "؟" not in line
        assert voice.spoken_rules.broken(line) == "" and not voice.has_tic(line)
