"""Cutting live room audio into spoken turns."""

import math
from array import array

from app.modules.pi_meetings.room_vad import (
    END_SILENCE_S,
    MAX_TURN_S,
    MIN_TURN_S,
    TurnCutter,
)

RATE = 16000
FRAME_S = 0.02
FRAME_N = int(RATE * FRAME_S)


def frame(loud: bool) -> bytes:
    amp = 6000 if loud else 40
    samples = array("h", [int(amp * math.sin(i / 5)) for i in range(FRAME_N)])
    return samples.tobytes()


def run(cutter: TurnCutter, who: str, pattern: list[tuple[bool, float]]) -> list:
    """Feed (loud, seconds) blocks; returns every turn that ended, with the clock advancing."""
    turns = []
    clock = 0.0
    for loud, seconds in pattern:
        for _ in range(round(seconds / FRAME_S)):
            clock += FRAME_S
            turns += cutter.feed(who, frame(loud), clock)
    return turns


def test_a_spoken_sentence_followed_by_a_pause_is_one_turn() -> None:
    cutter = TurnCutter(RATE)
    turns = run(cutter, "g_1", [(False, 0.5), (True, 2.0), (False, END_SILENCE_S + 0.1)])
    assert len(turns) == 1
    turn = turns[0]
    assert turn.speaker_id == "g_1" and turn.sample_rate == RATE
    seconds = len(turn.pcm) / 2 / RATE
    assert 2.0 <= seconds <= 2.0 + END_SILENCE_S + 0.4  # voice, its silence tail, a little pre-roll
    assert not cutter.speaking()


def test_a_short_pause_inside_a_sentence_does_not_split_it() -> None:
    cutter = TurnCutter(RATE)
    turns = run(
        cutter,
        "g_1",
        [(True, 1.0), (False, 0.4), (True, 1.0), (False, END_SILENCE_S + 0.1)],
    )
    assert len(turns) == 1


def test_a_cough_is_not_a_turn() -> None:
    cutter = TurnCutter(RATE)
    assert run(cutter, "g_1", [(True, 0.2), (False, END_SILENCE_S + 0.1)]) == []
    assert run(cutter, "g_1", [(True, MIN_TURN_S - 0.2), (False, END_SILENCE_S + 0.1)]) == []


def test_a_long_speech_is_cut_at_the_maximum_and_continues() -> None:
    cutter = TurnCutter(RATE)
    turns = run(cutter, "g_1", [(True, MAX_TURN_S + 4.0), (False, END_SILENCE_S + 0.1)])
    assert len(turns) == 2
    assert len(turns[0].pcm) / 2 / RATE <= MAX_TURN_S + 0.1


def test_people_are_kept_apart() -> None:
    cutter = TurnCutter(RATE)
    clock = 0.0
    turns = []
    for _ in range(round(1.5 / FRAME_S)):  # two people talking at the same time
        clock += FRAME_S
        turns += cutter.feed("g_1", frame(True), clock)
        turns += cutter.feed("s_2", frame(True), clock)
    assert cutter.speaking()
    for _ in range(round((END_SILENCE_S + 0.1) / FRAME_S)):
        clock += FRAME_S
        turns += cutter.feed("g_1", frame(False), clock)
        turns += cutter.feed("s_2", frame(False), clock)
    assert sorted(t.speaker_id for t in turns) == ["g_1", "s_2"]


def test_silence_alone_makes_nothing() -> None:
    cutter = TurnCutter(RATE)
    assert run(cutter, "g_1", [(False, 5.0)]) == []
    assert not cutter.speaking()


def test_unknown_speaker_and_empty_frames_are_ignored() -> None:
    cutter = TurnCutter(RATE)
    assert cutter.feed("", frame(True), 1.0) == []
    assert cutter.feed("g_1", b"", 1.0) == []
    assert not cutter.speaking()


def test_a_person_who_leaves_mid_sentence_gives_their_turn() -> None:
    cutter = TurnCutter(RATE)
    run(cutter, "g_1", [(True, 1.5)])
    assert cutter.speaking()
    turn = cutter.flush("g_1", 2.0)
    assert turn is not None and turn.speaker_id == "g_1"
    assert not cutter.speaking()
    assert cutter.flush("g_1", 3.0) is None


def test_a_turn_ends_by_the_clock_when_the_frames_stop_coming():
    """Found live: after a person fell silent the browser sent no more frames, so no quiet frame
    ever ended the turn, pi believed the person was still talking and nothing was answered."""
    cutter = TurnCutter(sample_rate=16000)
    t = 0.0
    for _ in range(60):  # 1.2 s of a loud voice in 20 ms frames
        assert cutter.feed("g_1", frame(True), t) == []
        t += 0.02
    assert cutter.speaking()
    assert cutter.idle(t + END_SILENCE_S / 2) == []  # a short pause is still the same turn
    turns = cutter.idle(t + END_SILENCE_S + 0.1)
    assert len(turns) == 1 and turns[0].speaker_id == "g_1"
    assert not cutter.speaking()
    assert cutter.idle(t + 5) == []  # nothing is ended twice
