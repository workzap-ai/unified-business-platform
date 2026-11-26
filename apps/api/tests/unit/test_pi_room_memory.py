"""pi in a room and what it knows about the customer: the link page's identity rule, in a room.

The first name is asked about only when one customer is alone in the room; memory is used only
after a clear yes, never after a no or an unclear answer, and a room with no customer behaves as
before."""

from uuid import uuid4

from test_pi_room_speech import Manager, Out

from app.modules.pi_meetings import voice
from app.modules.pi_meetings.room_speech import RoomSpeech, Session, Settings
from app.modules.pi_meetings.room_vad import Turn
from app.shared.scope import WorkspaceScope

FIRST = "hello, I run a small shop"
BLOCK = {
    "records": [
        {"kind": "name", "source": "facts", "status": "owner_said", "text": "name: Ayesha"},
        {
            "kind": "problem",
            "source": "facts",
            "status": "owner_said",
            "text": "late deliveries each week",
        },
    ]
}


class Spy(Manager):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.prompts = []

    async def complete_structured(self, scope, model, **kw):
        self.prompts.append(" ".join(m.content for m in kw["messages"]))
        return await super().complete_structured(scope, model, **kw)


def room(manager, *, block=BLOCK, customers=1):
    speech = RoomSpeech(
        manager=manager,
        scope=WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test"),
        session=Session(Settings(mode="speak", intake=True)),
        out=Out(),
        customers=lambda: customers,
        someone_speaking=lambda: False,
        clock=lambda: 100.0,
        what_i_know=lambda: block,
    )
    return speech


def turn():
    return Turn("g_1", b"\x10\x00" * 48000, 48000, 0.0, 1.0)


async def say(speech, manager, words):
    manager.heard = words
    speech.session.last_spoke_at = None  # no cooldown between the turns of this test
    return await speech.on_turn(turn())


async def test_the_first_words_ask_who_it_is_when_one_customer_is_alone():
    manager = Spy()
    speech = room(manager)
    assert await say(speech, manager, FIRST) == "disclosed"
    assert manager.tts[0][0] == voice.opening(name="Ayesha")
    assert voice.IDENTITY_MARK in manager.tts[0][0]


async def test_with_two_customers_in_the_room_no_name_is_asked():
    manager = Spy()
    speech = room(manager, customers=2)
    await say(speech, manager, "pi hello there")
    assert manager.tts[0][0] == voice.opening()
    assert "Ayesha" not in manager.tts[0][0]


async def test_a_room_with_no_customer_behaves_as_before():
    manager = Spy()
    speech = room(manager, block={})
    await say(speech, manager, FIRST)
    assert manager.tts[0][0] == voice.opening()


async def test_after_a_clear_yes_memory_may_shape_the_reply():
    manager = Spy()
    speech = room(manager)
    await say(speech, manager, FIRST)
    assert await say(speech, manager, "yes") == "spoke"
    assert "late deliveries" in manager.prompts[-1]


async def test_after_a_no_pi_asks_who_it_is_and_never_uses_memory():
    manager = Spy()
    speech = room(manager)
    await say(speech, manager, FIRST)
    assert await say(speech, manager, "no, I am her husband") == "spoke"
    assert manager.tts[-1][0] == voice.NOT_THEM
    assert manager.prompts == []  # the model was not asked
    await say(speech, manager, "pi we sell clothes")
    assert all("late deliveries" not in p for p in manager.prompts)


async def test_an_unclear_answer_leaves_memory_unused():
    manager = Spy()
    speech = room(manager)
    await say(speech, manager, FIRST)
    await say(speech, manager, "who is speaking please")
    assert all("late deliveries" not in p for p in manager.prompts)


async def test_loading_memory_never_raises_and_gives_nothing_for_a_missing_meeting():
    from types import SimpleNamespace

    from app.modules.pi_meetings.room_agent_memory import load_block

    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")
    orders = SimpleNamespace(meeting_id=uuid4(), scope=scope)

    class Gone:
        async def scalar(self, *_):
            return None

    class Broken:
        async def scalar(self, *_):
            raise RuntimeError("database down")

    assert await load_block(Gone(), orders) == {}
    assert await load_block(Broken(), orders) == {}
