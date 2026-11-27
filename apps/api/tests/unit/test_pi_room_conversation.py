"""Conversation skills in a room: say that again, can you hear me, slow down (no model), and a
spoken recap every few answers (through the same gate as every other line)."""

import pytest
from test_pi_room_speech import Manager, build, turn

from app.modules.pi_meetings import voice

WORDS = ["bread", "staff", "oven", "orders", "morning", "delivery", "queue", "stock"]
TOPICS = ["sells bread daily", "four staff members", "single large oven", "orders by whatsapp"]
HISTORY = [
    voice.Said(True, "Hi, I'm pi, an AI from Workzap. What does your business do?"),
    voice.Said(False, "I run a small bakery"),
    voice.Said(True, "Ten a day, that adds up."),
]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("sorry, can you repeat that", "repeat"),
        ("say that again please", "repeat"),
        ("dobara bolo", "repeat"),
        ("پھر سے بولو", "repeat"),
        ("दोबारा बोलो", "repeat"),
        ("can you hear me?", "hear"),
        ("hello? hello?", "hear"),
        ("aap sun rahe hain", "hear"),
        ("کیا آپ سن رہے ہیں", "hear"),
        ("please slow down", "slow"),
        ("bohat tez bol rahe ho", "slow"),
        ("آہستہ بولو", "slow"),
    ],
)
def test_a_control_request_is_found(text, kind) -> None:
    found = voice.control(text, HISTORY, "en")
    assert found is not None and found.kind == kind, text


def test_ordinary_talk_and_long_questions_are_not_controls() -> None:
    for text in (
        "I run a bakery in Karachi",
        "hello, my name is Hassan",
        "can you repeat that, I did not catch what you said about the price of the new oven please",
        "we are slow in the morning because of the oven",
    ):
        assert voice.control(text, HISTORY, "en") is None, text


def test_repeat_gives_back_pis_last_line_and_the_fixed_lines_are_clean() -> None:
    assert voice.control("say that again", HISTORY, "en").line == "Ten a day, that adds up."
    assert voice.control("say that again", [], "en").line == voice.CONTROL_LINES["nothing"]["en"]
    for kind in ("hear", "slow", "nothing"):
        for line in voice.CONTROL_LINES[kind].values():
            assert not voice.has_tic(line) and "?" not in line and "؟" not in line
            assert voice.spoken_rules.broken(line) == ""


async def test_a_control_is_answered_at_once_without_the_model() -> None:
    manager = Manager(heard="pi can you hear me?")
    speech, manager, out, session = build(manager)
    calls = []
    original = manager.complete_structured

    async def spy(*a, **k):
        calls.append(1)
        return await original(*a, **k)

    manager.complete_structured = spy
    await speech.on_turn(turn())  # the disclosure
    assert await speech.on_turn(turn()) == "spoke"
    assert manager.tts[-1][0] == voice.CONTROL_LINES["hear"]["en"] and calls == []


async def test_slow_down_makes_the_voice_slower_from_then_on() -> None:
    manager = Manager(heard="pi please slow down")
    speech, manager, out, session = build(manager)
    await speech.on_turn(turn())
    await speech.on_turn(turn())
    assert session.slow is True
    manager.heard = "pi tell me what you understood about the shop"
    await speech.on_turn(turn())
    assert "slower" in manager.tts[-1][1]["instructions"]


async def test_pi_sums_up_after_a_few_answers_and_asks_if_it_is_right() -> None:
    from types import SimpleNamespace

    seen = []

    class Recap(Manager):
        async def complete_structured(self, scope, model, **kw):
            import json

            body = json.loads(kw["messages"][1].content)
            seen.append(body)
            if "recap" in body:
                return SimpleNamespace(
                    value=model(
                        reply="So far: a small bakery, four people, one oven. Did I get that right?"
                    )
                )
            return SimpleNamespace(
                value=model(
                    reply=f"The {WORDS[len(seen) % len(WORDS)]} matters here.",
                    learned=TOPICS[len(seen) % len(TOPICS)],
                )
            )

    speech, manager, out, session = build(Recap(heard="pi the oven is the problem for us"))
    session.settings.intake = False
    await speech.on_turn(turn())  # the disclosure
    for _ in range(voice.RECAP_EVERY):
        await speech.on_turn(turn())
        session.last_spoke_at = 0.0
    assert not any("recap" in b for b in seen)  # not before it has answered enough times
    await speech.on_turn(turn())
    assert "recap" in seen[-1] and "learned_this_call" in seen[-1]
    assert manager.tts[-1][0].endswith("Did I get that right?")
    assert session.since_recap == 0
    await speech.on_turn(turn())
    assert "recap" not in seen[-1]  # not again straight away


async def test_a_recap_still_goes_through_the_gate() -> None:
    from types import SimpleNamespace
    from uuid import uuid4

    from app.shared.scope import WorkspaceScope

    class Bad(Manager):
        async def complete_structured(self, scope, model, **kw):
            return SimpleNamespace(
                value=model(reply="So far it will cost 5000 rupees. Did I get that right?")
            )

    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    out = await voice.reply_to(
        Bad(), scope, HISTORY, "yes the oven", learned=["a", "b", "c"], recap=True
    )
    assert out.fallback and "5000" not in out.text
    # a recap is never asked for right after a question or of a tired person
    asked = [*HISTORY, voice.Said(False, "ok"), voice.Said(True, "Which city?")]
    again = await voice.reply_to(
        Manager(reply="Noted."), scope, asked, "Lahore", learned=["a", "b", "c"], recap=True
    )
    assert again.text == "Noted."
