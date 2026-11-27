"""pi's small listening sounds ("mm-hm") while a person talks, and the more human voice."""

from test_pi_room_speech import build, turn

from app.modules.pi_meetings import room_speech
from app.modules.pi_meetings.room_vad import NOD_AFTER_S, TurnCutter

RATE = 16000
LOUD = b"\xe8\x03" * (RATE // 10)  # 0.1 s of a loud voice
QUIET = b"\x00\x00" * (RATE // 10)


def talk(cutter, seconds, who="g_1", t=0.0):
    for _ in range(int(seconds * 10)):
        cutter.feed(who, LOUD, t)
        t += 0.1
    return t


def test_a_nod_fits_in_a_small_pause_after_long_speech_and_only_once() -> None:
    cutter = TurnCutter(sample_rate=RATE)
    t = talk(cutter, NOD_AFTER_S + 1)
    assert not cutter.nod_ready("g_1")  # still talking: no breath yet
    for _ in range(4):  # a 0.4 s breath
        cutter.feed("g_1", QUIET, t)
        t += 0.1
    assert cutter.nod_ready("g_1")
    assert not cutter.nod_ready("g_1")  # once per stretch
    t = talk(cutter, 1.0, t=t)
    for _ in range(4):
        cutter.feed("g_1", QUIET, t)
        t += 0.1
    assert not cutter.nod_ready("g_1")  # not again until they have talked a while longer


def test_a_short_turn_never_gets_a_nod() -> None:
    cutter = TurnCutter(sample_rate=RATE)
    t = talk(cutter, 2.0)
    for _ in range(4):
        cutter.feed("g_1", QUIET, t)
        t += 0.1
    assert not cutter.nod_ready("g_1")


async def spoken_ready(**kw):
    speech, manager, out, session = build(**kw)
    await speech.on_turn(turn())  # the disclosure
    return speech, manager, out, session


async def test_pi_nods_softly_and_it_is_not_a_turn() -> None:
    speech, manager, out, session = await spoken_ready()
    spoken, written = session.spoken, len(out.written)
    assert await speech.nod() is True
    text, kw = manager.tts[-1]
    assert text in room_speech.NODS["en"] and kw["instructions"] == room_speech.STYLE_SOFT
    assert len(out.written) > written
    assert session.spoken == spoken and all(h.text != text for h in session.history)


async def test_pi_does_not_nod_before_the_ai_disclosure_or_when_muted_or_too_often() -> None:
    speech, manager, out, session = build()
    assert await speech.nod() is False  # nothing said yet: not disclosed
    speech, manager, out, session = await spoken_ready()
    assert await speech.nod() is True
    session.last_nod_at = 10**9  # a nod just now (the test clock jumps ten seconds per call)
    assert await speech.nod() is False  # NOD_GAP_S has not passed
    session.last_nod_at = None
    session.muted = True
    assert await speech.nod() is False
    session.muted = False
    session.nods = room_speech.NOD_CAP
    assert await speech.nod() is False
    session.nods = 0
    session.last_spoke_at = -1000.0  # pi has not spoken for a long time: not in the conversation
    assert await speech.nod() is False


async def test_pi_nods_in_urdu_when_the_person_asked_for_urdu() -> None:
    speech, manager, out, session = await spoken_ready()
    session.language_pref = "ur"
    assert await speech.nod() is True
    assert manager.tts[-1][0] in room_speech.NODS["ur"]


def test_the_voice_is_a_more_human_one_with_a_natural_style() -> None:
    assert room_speech.Settings().voice == "marin"
    assert "real person" in room_speech.STYLE_EN and "real" not in room_speech.STYLE_SOFT.lower()
