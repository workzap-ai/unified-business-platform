"""The room agent's core: frames in, turns out, pi cut off by a mute or by a person talking."""

import asyncio
import math
from array import array
from uuid import uuid4

from test_pi_room_speech import Manager, Out

from app.modules.pi_meetings import voice
from app.modules.pi_meetings.room_agent import AGENT_USER, RoomRun, mono
from app.modules.pi_meetings.room_agent_claim import Orders
from app.modules.pi_meetings.room_speech import RoomSpeech, Session, Settings
from app.shared.scope import WorkspaceScope

RATE = 48000
FRAME = int(RATE * 0.02)


def frame(loud):
    amp = 6000 if loud else 40
    return array("h", [int(amp * math.sin(i / 5)) for i in range(FRAME)]).tobytes()


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def build(heard="pi what do you think about my shop"):
    clock = Clock()
    manager = Manager(heard=heard)
    out = Out()
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")
    speech = RoomSpeech(
        manager=manager,
        scope=scope,
        session=Session(Settings(mode="speak")),
        out=out,
        customers=lambda: 0,
        someone_speaking=lambda: False,
        clock=clock,
    )
    return RoomRun(speech, clock=clock), manager, out, clock


def talk(run, clock, who, seconds, loud=True):
    for _ in range(round(seconds / 0.02)):
        clock.t += 0.02
        run.on_audio(who, frame(loud), RATE)


def say(run, clock, who, seconds=1.5):
    talk(run, clock, who, seconds)
    talk(run, clock, who, 1.0, loud=False)


def orders(**kw):
    base = {
        "room_id": uuid4(),
        "meeting_id": uuid4(),
        "started_at": None,
        "call_id": "r1",
        "scope": WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t"),
        "speak": True,
        "muted": False,
        "intake": False,
        "language": "",
        "stay": True,
    }
    return Orders(**{**base, **kw})


async def test_a_spoken_sentence_is_heard_and_pi_answers():
    run, manager, out, clock = build()
    say(run, clock, "g_1")
    await run.drain()
    assert manager.tts and manager.tts[0][0] == voice.opening()
    assert out.written


async def test_pi_never_hears_itself():
    run, manager, out, clock = build()
    say(run, clock, AGENT_USER)
    await run.drain()
    assert manager.stt_calls == [] and run.people == set()


async def test_customers_are_counted_without_staff_or_pi():
    run, *_ = build()
    for who in ("s_1", "g_1", "g_2", AGENT_USER):
        run.joined(who)
    assert run.customers() == 2
    run.left("g_2")
    assert run.customers() == 1


async def test_a_mute_from_the_heartbeat_stops_pi_mid_sentence():
    run, manager, out, clock = build()
    original = out.write
    muted_after = []

    async def write(pcm, rate):
        await original(pcm, rate)
        run.apply(orders(muted=True))  # the host presses mute while pi is speaking
        muted_after.append(run.speech.session.muted)

    out.write = write
    say(run, clock, "g_1")
    await run.drain()
    assert len(out.written) == 1 and out.flushes == 1 and muted_after == [True]


async def test_orders_that_switch_speech_off_make_pi_silent():
    run, manager, out, clock = build()
    run.apply(orders(speak=False))
    assert run.speech.session.settings.mode == "off" and run.speech.session.muted
    say(run, clock, "g_1")
    await run.drain()
    assert manager.tts == []


async def test_a_person_talking_cuts_pi_off():
    run, manager, out, clock = build()
    original = out.write

    async def write(pcm, rate):
        await original(pcm, rate)
        talk(run, clock, "s_9", 0.3)  # a staff member starts talking over pi

    out.write = write
    say(run, clock, "g_1")
    await run.drain()
    assert out.flushes == 1 and len(out.written) == 1


async def test_a_flood_of_turns_is_dropped_not_queued_without_limit():
    run, manager, out, clock = build()
    gate = asyncio.Event()
    original = manager.transcribe

    async def slow(*a, **k):
        await gate.wait()
        return await original(*a, **k)

    manager.transcribe = slow
    for who in ("g_1", "g_2", "g_3", "g_4", "g_5"):
        say(run, clock, who, 1.0)
    assert run.dropped >= 1
    gate.set()
    await run.drain()


async def test_a_person_who_leaves_mid_sentence_still_gets_heard():
    run, manager, out, clock = build(heard="so about the invoice we sent")
    talk(run, clock, "g_1", 1.5)
    run.left("g_1")
    await run.drain()
    assert len(manager.stt_calls) == 1


def test_stereo_becomes_mono():
    stereo = array("h", [100, 300, -50, 50]).tobytes()
    assert array("h", mono(stereo, 2)).tolist() == [200, 0]
    assert mono(stereo, 1) == stereo


async def test_a_turn_whose_frames_stop_is_ended_and_answered_by_the_clock():
    """No frame arrives while a person is silent: the room's clock tick ends their turn."""
    run, manager, out, clock = build()
    talk(run, clock, "g_1", 1.5)  # loud, then nothing at all
    assert manager.stt_calls == []
    clock.t += 1.0
    run.tick()
    await run.drain()
    assert len(manager.stt_calls) == 1 and manager.tts  # heard, and pi answered
    assert run.report() == {"g_1": 75}  # frame counts only, never sound
    assert run.report() == {}


def test_a_guest_who_closed_the_page_does_not_make_one_customer_look_like_two():
    """Found live: after a refresh the old guest id stayed in the room for a while, so a lone
    customer counted as two and pi stayed silent."""
    run, manager, out, clock = build()
    run.joined("g_old")
    clock.t += 60  # the old guest has sent no sound for a minute
    run.joined("g_new")
    assert run.customers() == 1
    run.on_audio("g_old", frame(True), RATE)  # a sound brings them back
    assert run.customers() == 2
