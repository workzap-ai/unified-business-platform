"""Pi's context memory in a long call: it never repeats a suggestion, it remembers what the person
turned down, and the older part of the call is kept as a short summary (found live: 'I want a
modern solution, not an old one' was answered with the same kind of idea again)."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_pi_room_speech import Manager, build, turn

from app.modules.pi_meetings import room_recall, room_speech, voice
from app.modules.pi_meetings.room_speech import Session, Settings
from app.shared.scope import WorkspaceScope

HISTORY = [voice.Said(True, "Hi, I'm pi, an AI. What does your business do?")]


@pytest.mark.parametrize(
    "text",
    [
        "no",
        "that is old, I want something modern",
        "we already tried that",
        "nahi, ye purana hai",
        "نہیں یہ پرانا ہے",
        "नहीं, ये बेकार है",
        "not really helpful",
    ],
)
def test_turning_down_a_suggestion_is_found(text) -> None:
    assert voice.rejects(text), text


def test_ordinary_replies_and_long_turns_are_not_a_rejection() -> None:
    for text in (
        "yes that makes sense, tell me more",
        "ok and how would that help with late orders",
        "we have six tailors and the shop is in the old city market near the mosque and the school",
    ):
        assert not voice.rejects(text), text


class Seen(Manager):
    def __init__(self, replies):
        super().__init__()
        self.replies, self.bodies = list(replies), []

    async def complete_structured(self, scope, model, **kw):
        self.bodies.append(json.loads(kw["messages"][1].content))
        reply = (
            self.replies.pop(0) if self.replies else "One more thing worth a look is a day board."
        )
        return SimpleNamespace(value=model(reply=reply))


async def test_the_idea_writer_is_told_what_was_given_and_what_was_turned_down() -> None:
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    manager = Seen(["One thing worth thinking about is a single board showing each order's day."])
    out = await voice.reply_to(
        manager,
        scope,
        HISTORY,
        "can you suggest a solution",
        ideas_log=["a tracking sheet for deliveries"],
        rejected=["a tracking sheet for deliveries"],
        summary="Tailoring shop, six tailors, late deliveries.",
    )
    assert out.idea
    body = manager.bodies[0]
    assert body["already_suggested"] == ["a tracking sheet for deliveries"]
    assert body["they_did_not_like"] == ["a tracking sheet for deliveries"]
    assert body["call_so_far"].startswith("Tailoring shop")


async def test_a_suggestion_that_is_turned_down_is_remembered_and_not_offered_again() -> None:
    idea = "One thing worth thinking about is a shared board with each order's delivery day."
    manager = Seen(
        [idea, "Noted.", "A different direction is a daily ready list for the front desk."]
    )
    speech, manager, out, session = build(manager)
    session.settings.intake = False
    await speech.on_turn(turn())  # the disclosure
    manager.heard = "pi can you suggest a solution"
    await speech.on_turn(turn())
    assert session.idea_pending and session.idea_log == [idea]
    manager.heard = "pi no that is old, I want something modern"
    await speech.on_turn(turn())
    assert session.rejected == [idea] and not session.idea_pending
    manager.heard = "pi can you suggest another solution"
    await speech.on_turn(turn())
    last = manager.bodies[-1]
    assert last["they_did_not_like"] == [idea] and last["already_suggested"] == [idea]


async def test_a_polite_answer_to_a_suggestion_is_not_a_rejection() -> None:
    idea = "One thing worth thinking about is a shared board with each order's delivery day."
    manager = Seen([idea, "Glad it fits."])
    speech, manager, out, session = build(manager)
    await speech.on_turn(turn())
    manager.heard = "pi can you suggest a solution"
    await speech.on_turn(turn())
    manager.heard = "pi yes that sounds good for us"
    await speech.on_turn(turn())
    assert session.rejected == [] and session.idea_log == [idea]


async def test_a_long_call_gets_a_summary_of_its_older_part(monkeypatch) -> None:
    monkeypatch.setattr(room_speech, "SUMMARY_EVERY", 2)

    class Memory(Manager):
        def __init__(self):
            super().__init__(heard="pi the oven is the problem for us in the morning rush")
            self.n = 0
            self.summaries = 0

        async def complete_structured(self, scope, model, **kw):
            self.n += 1
            if model is voice.CallSummary:
                self.summaries += 1
                return SimpleNamespace(
                    value=model(summary="Bakery with one oven and late morning orders.")
                )
            return SimpleNamespace(
                value=model(
                    reply=f"Answer {self.n} about the morning rush.", learned=f"fact{self.n} oven"
                )
            )

    speech, manager, out, session = build(Memory())
    session.settings.intake = False
    session.history += [voice.Said(i % 2 == 0, f"earlier line {i}") for i in range(14)]
    await speech.on_turn(turn())  # the disclosure
    for _ in range(3):
        session.last_spoke_at = None
        await speech.on_turn(turn())
    await asyncio.gather(*speech._side)  # the summary is written after the turn, in the background
    assert manager.summaries >= 1
    assert session.summary == "Bakery with one oven and late morning orders."
    notes = room_recall.pack(session)
    assert notes["summary"] == session.summary


async def test_the_summary_keeps_out_prices_and_survives_a_model_that_is_down() -> None:
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")

    class Price(Manager):
        async def complete_structured(self, scope, model, **kw):
            return SimpleNamespace(value=model(summary="They will pay 5000 rupees a month."))

    assert await voice.summarise(Price(), scope, HISTORY, ["a"], "old") == ""

    class Down(Manager):
        async def complete_structured(self, scope, model, **kw):
            from app.ai.errors import GatewayUnavailable

            raise GatewayUnavailable("down")

    assert await voice.summarise(Down(), scope, HISTORY, ["a"], "old") == ""


def test_the_memory_of_suggestions_and_the_summary_survive_a_restart() -> None:
    old = Session(Settings(mode="speak"))
    old.idea_log, old.rejected = ["a board", "a ready list"], ["a board"]
    old.summary = "Bakery, one oven."
    notes = room_recall.pack(old)
    new = Session(Settings(mode="speak"))
    room_recall.restore(new, notes)
    assert new.idea_log == ["a board", "a ready list"] and new.rejected == ["a board"]
    assert new.summary == "Bakery, one oven."
    room_recall.restore(new, {"ideas_given": "x", "rejected": 5, "summary": 3})  # bad notes
    assert new.idea_log == ["a board", "a ready list"]
