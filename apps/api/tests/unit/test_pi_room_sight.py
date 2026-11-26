"""Screen sight and call memory: what pi may keep from a shared screen and from the call so far."""

from types import SimpleNamespace
from uuid import uuid4

import numpy as np
from test_pi_room_speech import Manager

from app.modules.pi_meetings import meeting_memory, room_sight, voice
from app.modules.pi_meetings.room_sight import Sight
from app.shared.scope import WorkspaceScope

W, H = 64, 36


def i420(level: int) -> np.ndarray:
    y = np.full(W * H, level, dtype=np.uint8)
    uv = np.full(W * H // 2, 128, dtype=np.uint8)
    return np.concatenate([y, uv])


class Vision:
    def __init__(self, text: str) -> None:
        self.text, self.calls = text, 0

    async def vision(self, scope, prompt, images, **kw):
        self.calls += 1
        assert images[0][1] == "image/jpeg" and kw["system"] == room_sight.SYSTEM
        return SimpleNamespace(text=self.text)


def sight(text: str):
    clock = SimpleNamespace(t=1000.0)
    notes: list[str] = []

    async def on_note(note: str) -> None:
        notes.append(note)

    vision = Vision(text)
    return Sight(vision, None, clock=lambda: clock.t, on_note=on_note), vision, clock, notes


def test_frames_become_pictures_in_every_layout() -> None:
    assert room_sight.to_image(i420(120), W, H).size == (W, H)
    assert room_sight.to_image(np.zeros(W * H * 3, np.uint8), W, H).size == (W, H)
    assert room_sight.to_image(np.zeros(W * H * 4, np.uint8), W, H).size == (W, H)
    assert room_sight.to_image(np.zeros(7, np.uint8), W, H) is None


def test_an_email_in_a_note_is_redacted_before_it_is_kept() -> None:
    kept = room_sight.clean("A mail from ali@example.com")
    assert "ali" not in kept and "@" not in kept


def test_the_note_is_one_clean_sentence_never_data() -> None:
    assert room_sight.clean("A spreadsheet of customer orders.")
    for bad in (
        "SENSITIVE",
        "A bank page showing balance 4500000",
        "A price list, 5000 rupees",
        "",
    ):
        assert room_sight.clean(bad) == "", bad


async def test_pi_looks_when_due_and_changed_and_keeps_a_note() -> None:
    s, vision, clock, notes = sight("A spreadsheet of customer orders.")
    assert await s.look(i420(100), W, H) == "A spreadsheet of customer orders."
    assert notes == ["A spreadsheet of customer orders."] and s.current()
    clock.t += 5  # not due yet
    assert await s.look(i420(200), W, H) == "" and vision.calls == 1
    clock.t += room_sight.EVERY_S  # due, but the same picture
    assert await s.look(i420(101), W, H) == "" and vision.calls == 1
    clock.t += room_sight.EVERY_S  # due and changed
    assert await s.look(i420(220), W, H) != "" and vision.calls == 2
    clock.t += room_sight.STALE_S + 1
    assert s.current() == ""  # an old note is no longer what is on the screen


async def test_a_private_screen_leaves_no_note_and_clears_the_old_one() -> None:
    s, vision, clock, notes = sight("A spreadsheet of customer orders.")
    await s.look(i420(100), W, H)
    vision.text = "SENSITIVE"
    clock.t += room_sight.EVERY_S
    assert await s.look(i420(230), W, H) == ""
    assert s.current() == "" and len(notes) == 1


async def test_looks_per_call_are_capped() -> None:
    s, vision, clock, _ = sight("A design tool.")
    for n in range(room_sight.CAP + 5):
        clock.t += room_sight.EVERY_S
        await s.look(i420((n * 50) % 250), W, H)
    assert vision.calls <= room_sight.CAP


class Recorder(Manager):
    def __init__(self, reply: str, learned: str = "") -> None:
        super().__init__(reply=reply)
        self.learned, self.bodies = learned, []

    async def complete_structured(self, scope, model, **kw):
        self.bodies.append(kw["messages"][-1].content)
        return SimpleNamespace(value=model(reply=self.reply, learned=self.learned))


async def test_call_facts_and_the_screen_reach_the_next_reply() -> None:
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    history = [voice.Said(True, "Hi."), voice.Said(False, "I run a clothing brand")]
    first = Recorder("Clothing, got it.", learned="runs a clothing brand, team of 5")
    out = await voice.reply_to(first, scope, history, "my team of five is slow on ads")
    assert out.learned == "runs a clothing brand, team of 5"
    second = Recorder("Ads take time, I see.")
    await voice.reply_to(
        second,
        scope,
        history,
        "yes it is slow on ads",
        learned=[out.learned],
        on_screen="A spreadsheet of customer orders.",
    )
    assert "team of 5" in second.bodies[0] and "spreadsheet of customer orders" in second.bodies[0]


async def test_a_learned_fact_with_a_price_is_not_kept() -> None:
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    out = await voice.reply_to(
        Recorder("Noted, I see.", learned="pays 5000 rupees a month"), scope, [], "ok that is it"
    )
    assert out.learned == ""


def test_earlier_calls_are_speakable_and_cannot_be_recited() -> None:
    block = {
        "records": [],
        "earlier_calls": [
            {"when": "2026-11-20", "points": ["problem: Karachi branch loses orders on Fridays"]}
        ],
    }
    spoken = meeting_memory.speakable(block)
    assert spoken["earlier_calls"] and meeting_memory.speakable({}) == {}
    # a name from the earlier call is not said unless the person said it in this call
    assert meeting_memory.leaks("Last time, Karachi came up.", "hello", spoken)
    assert not meeting_memory.leaks("Last time we spoke about lost orders.", "hello", spoken)
    assert not meeting_memory.leaks("Karachi again?", "my Karachi branch", spoken)
