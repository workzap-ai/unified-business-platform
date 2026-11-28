"""Everyone in the room can see whether pi has the shared screen: the agent puts a state ('none',
'looking' or 'seeing', never what was seen) on the call, only when it changes, and a failure to send
it never stops pi."""

import json
from types import SimpleNamespace
from uuid import uuid4

import httpx

from app.modules.pi_meetings import room_sight
from app.modules.pi_meetings.room_provider import CALL_TYPE, StreamProvider
from app.modules.pi_meetings.room_sight import Beacon, Sight
from app.shared.scope import WorkspaceScope

SCOPE = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_the_sight_tells_none_looking_and_seeing() -> None:
    clock = Clock()
    sight = Sight(object(), SCOPE, clock=clock)
    assert sight.state() == "none"  # nothing shared, or not received
    sight.begin()
    assert sight.state() == "looking"  # a screen arrived, pi has not understood it yet
    sight._note, sight._note_at = "a spreadsheet of orders", clock()
    assert sight.state() == "seeing"
    clock.t += room_sight.STALE_S + 1
    assert sight.state() == "looking"  # an old note no longer says what is on screen now
    sight.looks_done = 1  # but pi has looked (a private page keeps nothing): it is seeing it
    assert sight.state() == "seeing"
    sight.end()
    assert sight.state() == "none" and sight.current() == ""
    sight.begin()
    assert sight.looks_done == 0 and sight.state() == "looking"  # a new share starts fresh


async def test_a_private_screen_counts_as_seen_but_keeps_nothing() -> None:
    class Vision:
        async def vision(self, *a, **k):
            return SimpleNamespace(text="SENSITIVE")

    clock = Clock()
    sight = Sight(Vision(), SCOPE, clock=clock)
    sight.begin()
    frame = [120, 130, 140] * (64 * 36)
    assert await sight.look(frame, 64, 36) == ""
    assert sight.state() == "seeing" and sight.current() == ""  # seen, and nothing was kept


async def test_the_beacon_sends_a_state_only_when_it_changes_and_now_and_then() -> None:
    clock = Clock()
    sight = Sight(object(), SCOPE, clock=clock)
    sent: list[str] = []
    agents: list[str] = []
    current = {"agent": "pi"}

    async def send(state: str, agent: str) -> None:
        sent.append(state)
        agents.append(agent)

    beacon = Beacon(sight, send, clock=clock, agent=lambda: current["agent"])
    await beacon.tick()
    assert sent == ["none"]  # the first tick clears any state left on the call
    await beacon.tick()
    assert sent == ["none"]  # nothing changed
    sight.begin()
    await beacon.tick()
    sight._note, sight._note_at = "a design tool", clock()
    await beacon.tick()
    assert sent == ["none", "looking", "seeing"]
    clock.t += Beacon.REPEAT_S + 1  # a browser that joined late is told again
    await beacon.tick()
    assert sent[-1] == "seeing" and len(sent) == 4
    sight.end()
    await beacon.tick()
    assert sent[-1] == "none"
    # a change of the meeting's agent is sent at once, with the state, and nothing else changed
    before = len(sent)
    current["agent"] = "sales_coach"
    await beacon.tick()
    assert len(sent) == before + 1 and agents[-1] == "sales_coach" and sent[-1] == "none"
    await beacon.tick()
    assert len(sent) == before + 1


async def test_a_state_that_cannot_be_sent_never_stops_pi() -> None:
    clock = Clock()
    sight = Sight(object(), SCOPE, clock=clock)

    async def broken(state: str, agent: str) -> None:
        raise RuntimeError("provider down")

    await Beacon(sight, broken, clock=clock).tick()  # no exception


async def test_the_state_goes_to_the_call_as_a_small_custom_value() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await StreamProvider(http, "key", "secret").set_state("pm_abc", {"pi_screen": "seeing"})
    (request,) = seen
    assert request.method == "PATCH"
    assert request.url.path.endswith(f"/video/call/{CALL_TYPE}/pm_abc")
    assert json.loads(request.content) == {"custom": {"pi_screen": "seeing"}}


async def test_the_beacon_sends_what_pi_is_doing_the_moment_it_changes() -> None:
    clock = Clock()
    sight = Sight(object(), SCOPE, clock=clock)
    sent: list[tuple[str, str, str]] = []
    now = {"phase": "listening"}

    async def send(state: str, agent: str, phase: str) -> None:
        sent.append((state, agent, phase))

    beacon = Beacon(sight, send, clock=clock, phase=lambda: now["phase"])
    await beacon.tick()
    await beacon.tick()
    assert sent == [("none", "pi", "listening")]
    now["phase"] = "thinking"
    await beacon.tick()
    now["phase"] = "speaking"
    await beacon.tick()
    await beacon.tick()  # nothing changed
    assert [s[2] for s in sent] == ["listening", "thinking", "speaking"]
