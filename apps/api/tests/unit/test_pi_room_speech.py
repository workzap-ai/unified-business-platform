"""One spoken turn in a room: heard, decided, spoken, cut off."""

from types import SimpleNamespace
from uuid import uuid4

from app.ai.errors import GatewayUnavailable
from app.modules.pi_meetings import room_speech, voice
from app.modules.pi_meetings.room_speech import RoomSpeech, Session, Settings
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope

RATE = 48000
PCM = b"\x10\x00" * RATE  # one second


def turn(who="g_1"):
    return Turn(who, PCM, RATE, 0.0, 1.0)


class Manager:
    def __init__(self, heard="pi what do you think about my shop", reply="Which part is slowest?"):
        self.heard, self.reply = heard, reply
        self.stt_calls, self.tts = [], []
        self.fail_stt = self.fail_tts = False

    async def transcribe(self, scope, audio, mime, **kw):
        self.stt_calls.append((mime, kw))
        if self.fail_stt:
            raise GatewayUnavailable("down")
        return SimpleNamespace(text=self.heard)

    async def synthesize(self, scope, text, **kw):
        self.tts.append((text, kw))
        if self.fail_tts:
            raise GatewayUnavailable("down")
        return SimpleNamespace(audio=b"\x01\x00" * 24000)  # one second at 24 kHz

    async def complete_structured(self, scope, model, **kw):
        return SimpleNamespace(value=model(reply=self.reply))


class Out:
    def __init__(self):
        self.written, self.flushes = [], 0

    async def write(self, pcm, rate):
        self.written.append((len(pcm), rate))

    async def flush(self):
        self.flushes += 1


def build(manager=None, *, mode="speak", customers=1, busy=False, intake=False, **kw):
    manager = manager or Manager()
    out = Out()
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")
    session = Session(Settings(mode=mode, intake=intake))
    clock = iter(range(1000, 100000, 10))
    speech = RoomSpeech(
        manager=manager,
        scope=scope,
        session=session,
        out=out,
        customers=lambda: customers,
        someone_speaking=lambda: busy,
        clock=lambda: float(next(clock)),
        **kw,
    )
    return speech, manager, out, session


async def test_the_first_thing_pi_says_is_the_ai_disclosure():
    speech, manager, out, session = build()
    assert await speech.on_turn(turn()) == "disclosed"
    assert manager.tts[0][0] == voice.opening()
    assert "AI" in manager.tts[0][0]
    assert session.disclosed and session.spoken == 1 and out.written


async def test_after_that_pi_answers_through_the_voice_gate():
    speech, manager, out, session = build()
    await speech.on_turn(turn())
    assert await speech.on_turn(turn()) == "spoke"
    assert manager.tts[1][0] == "Which part is slowest?"
    assert session.spoken == 2


async def test_a_reply_that_breaks_a_rule_becomes_the_safe_line():
    speech, manager, _, _ = build(Manager(reply="It costs 5000 rupees, so pay now?"))
    await speech.on_turn(turn())
    await speech.on_turn(turn())
    spoken = manager.tts[1][0]
    assert "5000" not in spoken and "pay" not in spoken.lower()


async def test_not_named_means_silence_and_no_speech_call():
    speech, manager, out, _ = build(Manager(heard="so about the invoice we sent"))
    assert await speech.on_turn(turn("s_1")) == "not_addressed"
    assert manager.tts == [] and out.written == []


async def test_off_and_muted_stay_silent():
    speech, manager, _, _ = build(mode="off")
    assert await speech.on_turn(turn()) == "mode"
    speech, manager, _, session = build()
    session.muted = True
    assert await speech.on_turn(turn()) == "muted"
    assert manager.tts == []


async def test_a_mute_set_by_the_server_stops_the_audio_before_it_starts():
    async def muted():
        return True

    speech, manager, out, _ = build(is_muted=muted)
    assert await speech.on_turn(turn()) == "muted"
    assert manager.tts == [] and out.written == []


async def test_nobody_is_talked_over():
    speech, manager, _, _ = build(busy=True)
    assert await speech.on_turn(turn()) == "someone_speaking"
    assert manager.tts == []


async def test_a_lone_customer_is_answered_in_intake_without_the_name():
    speech, manager, _, _ = build(Manager(heard="we sell clothes in a small shop"), intake=True)
    assert await speech.on_turn(turn("g_1")) == "disclosed"


async def test_barge_in_cuts_pi_off_at_the_next_piece():
    speech, manager, out, session = build()

    class CutOut(Out):
        async def write(self, pcm, rate):
            await super().write(pcm, rate)
            speech.barge_in()

    speech.out = cut = CutOut()
    await speech.on_turn(turn())
    assert len(cut.written) == 1 and cut.flushes == 1
    assert not speech.speaking


async def test_speech_to_text_down_is_silence_not_a_crash():
    manager = Manager()
    manager.fail_stt = True
    speech, _, out, _ = build(manager)
    assert await speech.on_turn(turn()) == "unheard"
    assert out.written == []


async def test_text_to_speech_down_means_nothing_is_said_and_nothing_is_counted():
    manager = Manager()
    manager.fail_tts = True
    speech, _, out, session = build(manager)
    assert await speech.on_turn(turn()) == "not_spoken"
    assert session.spoken == 0 and not session.disclosed and out.written == []


async def test_a_spoken_phone_number_never_reaches_the_transcript_or_the_model():
    lines = []

    async def on_line(who, text):
        lines.append((who, text))

    speech, _, _, _ = build(Manager(heard="pi call me on 0 3 0 0 1 2 3 4 5 6 7"), on_line=on_line)
    await speech.on_turn(turn())
    assert "1 2 3 4" not in lines[0][1]
    assert lines[0][1].startswith("pi call me")


async def test_both_sides_of_the_conversation_are_given_to_the_transcript():
    lines = []

    async def on_line(who, text):
        lines.append(who)

    speech, _, _, _ = build(on_line=on_line)
    await speech.on_turn(turn("g_1"))
    assert lines == ["g_1", voice.PI_LABEL]


def test_resampling_keeps_length_ratio_and_wav_is_valid():
    down = room_speech.resample(PCM, 48000, 16000)
    assert len(down) * 3 == len(PCM)
    up = room_speech.resample(down, 16000, 48000)
    assert len(up) == len(PCM)
    assert room_speech.wav(down, 16000)[:4] == b"RIFF"


async def test_the_speech_to_text_gets_the_spelling_hint_and_an_echo_of_it_is_dropped():
    from app.modules.pi_meetings import room_speech

    asked = {}
    manager = Manager(heard="Workzap, pi.")
    original = manager.transcribe

    async def spy(*a, **k):
        asked.update(k)
        return await original(*a, **k)

    manager.transcribe = spy
    speech = RoomSpeech(
        manager=manager,
        scope=WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t"),
        session=Session(Settings(mode="speak")),
        out=Out(),
        customers=lambda: 1,
        someone_speaking=lambda: False,
        clock=lambda: 100.0,
    )
    assert await speech.hear(Turn("g_1", b"\x10\x00" * 48000, 48000, 0.0, 1.0)) == ""
    assert asked["prompt"] == room_speech.STT_HINT
