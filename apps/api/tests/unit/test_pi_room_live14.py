"""Fixes from live test 15 (2026-11-27): a named language holds, no echo openers, no line that
only repeats the owner, a solution asked in a held piece of speech is still answered."""

import pytest
from test_pi_room_speech import Manager, build, turn

from app.modules.pi_meetings import voice


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Please speak in Urdu", "ur"),
        ("اب اردو میں بولو", "ur"),
        ("اب انگلش میں بولو", "en"),
        ("Urdu mein baat karo", "ur"),
        ("english please", "en"),
        ("can you speak English now", "en"),
        ("Urdu mein bolo ... no, English please", "en"),
        ("मुझे उर्दू में बोलो", "ur"),
        ("I run a small bakery and we speak English at work", ""),
        ("I sell shoes", ""),
    ],
)
def test_a_named_language_is_found(text, code) -> None:
    assert voice.asked_language(text) == code


def test_acknowledgement_that_repeats_the_owner_is_an_echo() -> None:
    for tic in (
        "I see, so you specialize in breads.",
        "I understand, you have a team of 4 and only one oven.",
        "Got it, your bakery is called Fast Baker.",
        "It sounds like managing the schedule could help.",
        "That sounds frustrating.",
        "میں سمجھ گیا، آپ کے پاس ایک اوون ہے۔",
    ):
        assert voice.has_tic(tic), tic
    for fine in ("I see.", "Got it.", "Ten a day, that adds up.", "اچھا۔", "Understood."):
        assert not voice.has_tic(fine), fine


def test_a_reply_made_of_known_words_adds_nothing() -> None:
    history = [
        voice.Said(True, "Hi, I'm pi, an AI. What does your business do?"),
        voice.Said(False, "bakery, four people, only one oven, morning orders go out late"),
    ]
    echo = "Your bakery has four people and only one oven so morning orders go out late."
    assert voice.adds_nothing(echo, history, "we need a modern solution")
    assert not voice.adds_nothing(
        "One thing worth thinking about is a shared board for the day's orders.",
        history,
        "we need a modern solution",
    )
    assert not voice.adds_nothing("Ten a day.", history, "")  # too short to judge


async def test_an_echo_gets_one_correction_and_then_silence() -> None:
    from uuid import uuid4

    from app.shared.scope import WorkspaceScope

    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    history = [
        voice.Said(True, "Hi, I'm pi, an AI. What does your business do?"),
        voice.Said(False, "bakery four people one oven morning orders go out late"),
    ]
    echo = "Your bakery four people one oven morning orders go out late."
    out = await voice.reply_to(Manager(reply=echo), scope, history, "yes exactly")
    assert out.text == "" and not out.fallback


async def test_a_solution_asked_in_a_held_piece_is_answered_later() -> None:
    from uuid import uuid4

    from app.shared.scope import WorkspaceScope

    idea = "One thing worth thinking about is a single board that shows which order is next."
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    history = [voice.Said(True, "Hi, I'm pi, an AI. What does your business do?")]
    out = await voice.reply_to(
        Manager(reply=idea), scope, history, "yes the oven is the problem", wants_solution=True
    )
    assert out.idea and out.text == idea
    assert voice.asks_for_solution("अब सलूशन बताओ क्या सलूशन आना चाहिए")
    assert voice.asks_for_solution("modern solution")


class Capture(Manager):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.bodies = []

    async def complete_structured(self, scope, model, **kw):
        self.bodies.append(kw["messages"][-1].content)
        return await super().complete_structured(scope, model, **kw)


async def test_the_language_asked_for_holds_for_the_next_replies() -> None:
    manager = Capture(heard="pi please speak in Urdu, how are you")
    speech, manager, _, session = build(manager)
    await speech.on_turn(turn())  # the disclosure
    await speech.on_turn(turn())
    assert session.language_pref == "ur"
    assert "Urdu" in manager.bodies[-1]
    manager.heard = "pi tell me more about the oven and the morning rush"  # English words
    await speech.on_turn(turn())
    assert "Urdu" in manager.bodies[-1]  # still Urdu: the person asked for it


async def test_a_solution_request_is_remembered_until_it_is_answered() -> None:
    manager = Capture(heard="pi can you suggest a solution for the late orders")
    speech, manager, _, session = build(manager, mode="speak")
    await speech.on_turn(turn())
    assert session.wants_solution is True
