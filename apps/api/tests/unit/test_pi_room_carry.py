"""People pause inside a sentence and the voice detector ends a turn at a pause: pi must answer the
whole sentence, not its first breath. Found live: a customer who spoke in two or three pieces got no
answer, because every piece but the last was heard while they were still talking and the last was
too short to count."""

from uuid import uuid4

from test_pi_room_speech import Manager, Out

from app.modules.pi_meetings import room_speech, voice
from app.modules.pi_meetings.room_speech import RoomSpeech, Session, Settings
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def build(*, customers=1, talking=lambda: False):
    clock = Clock()
    manager = Manager()
    speech = RoomSpeech(
        manager=manager,
        scope=WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test"),
        session=Session(Settings(mode="speak", intake=True)),
        out=Out(),
        customers=lambda: customers,
        someone_speaking=talking,
        clock=clock,
    )
    return speech, manager, clock


async def say(speech, manager, words, who="g_1", *, keep_pause=False):
    manager.heard = words
    if not keep_pause:
        speech.session.last_spoke_at = None  # no pause between pi's turns unless a test asks
    return await speech.on_turn(Turn(who, b"\x10\x00" * 48000, 48000, 0.0, 1.0))


async def test_two_short_pieces_of_one_sentence_are_answered_together():
    speech, manager, clock = build()
    assert (
        await say(
            speech,
            manager,
            "hello",
        )
        == "not_addressed"
    )  # one word: too short alone
    clock.t += 2
    assert await say(speech, manager, "I run a small shop") == "disclosed"
    assert manager.tts and voice.opening() in manager.tts[0][0]


async def test_a_piece_heard_while_they_keep_talking_joins_their_next_piece():
    talking = {"now": True}
    speech, manager, clock = build(talking=lambda: talking["now"])
    assert await say(speech, manager, "hello, I run a small clothing shop") == "someone_speaking"
    assert manager.tts == []  # pi does not talk over them
    talking["now"] = False
    clock.t += 1.5
    assert await say(speech, manager, "and we sell online too") == "disclosed"


async def test_the_joined_words_reach_the_model_not_only_the_last_piece():
    speech, manager, clock = build()
    await say(speech, manager, "hello I run a small shop")  # disclosure
    sent = []
    original = manager.complete_structured

    async def spy(scope, model, **kw):
        sent.append(" ".join(m.content for m in kw["messages"]))
        return await original(scope, model, **kw)

    manager.complete_structured = spy
    clock.t += 20
    assert await say(speech, manager, "orders") == "not_addressed"
    clock.t += 2
    assert await say(speech, manager, "get missed when we are busy") == "spoke"
    assert "orders get missed when we are busy" in sent[0]


async def test_an_old_piece_is_not_joined_and_is_kept_in_the_history():
    speech, manager, clock = build()
    assert await say(speech, manager, "hello") == "not_addressed"
    clock.t += room_speech.CARRY_S + 1
    assert await say(speech, manager, "two words") == "not_addressed"  # only two words alone
    assert [h.text for h in speech.session.history] == ["hello"]


async def test_pieces_of_different_people_are_not_joined():
    speech, manager, clock = build(customers=2)
    assert await say(speech, manager, "hello", who="g_1") == "not_addressed"
    clock.t += 1
    # the second person's words stand alone: g_1's "hello" is not put in front of them
    assert await say(speech, manager, "I run a shop", who="g_2") == "disclosed"
    assert speech.session.carry["g_1"][0] == "hello"
    assert "g_2" not in speech.session.carry


async def test_a_long_run_of_pieces_never_grows_without_limit():
    speech, manager, clock = build(customers=2)  # nobody is named: every piece is held
    for _ in range(80):
        clock.t += 1
        await say(speech, manager, "blah blah blah blah blah blah")
    assert len(speech.session.carry["g_1"][0]) <= room_speech.CARRY_CHARS


async def test_with_two_customers_pi_introduces_itself_and_then_answers_whoever_answers_it():
    speech, manager, clock = build(customers=2)
    assert await say(speech, manager, "hello, we are two partners here", who="g_1") == "disclosed"
    clock.t += 4  # g_2 answers pi's question a few seconds later
    assert (
        await say(speech, manager, "we sell clothes online", who="g_2", keep_pause=True) == "spoke"
    )
    # talking among themselves, long after pi's last question, is left alone
    clock.t += 60
    said = await say(speech, manager, "did you pay the rent yet", who="g_1", keep_pause=True)
    assert said == "not_addressed"


async def test_staff_speaking_first_also_brings_the_introduction():
    speech, manager, clock = build(customers=1)
    assert await say(speech, manager, "welcome everyone to this call", who="s_1") == "disclosed"
    assert voice.opening() in manager.tts[0][0]


async def test_pi_does_not_answer_an_answer_in_the_same_breath():
    speech, manager, clock = build(customers=2)
    assert await say(speech, manager, "hello, we are two partners here", who="g_1") == "disclosed"
    speech.session.last_spoke_at = clock.t  # pi finished speaking just now
    manager.heard = "we sell clothes online"
    assert await speech.on_turn(Turn("g_2", b"\x10\x00" * 48000, 48000, 0.0, 1.0)) == "cooldown"
