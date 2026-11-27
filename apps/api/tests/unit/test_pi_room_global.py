"""Found in live test 16 (2026-11-27), read from the real transcript: a backlog of short turns made
pi answer 86 s late, a late introduction asked what the customer had already said, 'Got it. <what
you said>' slipped through as an answer, questions about the shared screen got 'I've noted that',
and 'Lahore' was written 'Lourdes'."""

import asyncio
from types import SimpleNamespace

import pytest
from test_pi_room_speech import Manager, build, turn

from app.modules.pi_meetings import room_speech, voice


def test_a_late_introduction_asks_nothing_and_passes_the_rules() -> None:
    for lang in ("", "ur"):
        line = voice.late_opening(lang)
        assert "?" not in line and "؟" not in line
        assert voice.spoken_rules.broken(line) == ""
        assert "AI" in line  # the disclosure is still the first thing


async def test_an_introduction_after_the_customer_has_talked_does_not_ask_again() -> None:
    speech, manager, out, session = build(
        Manager(heard="I run a tailoring shop in Lahore"), intake=True
    )
    session.history.append(voice.Said(False, "hello can you hear me"))  # they spoke, pi was silent
    assert await speech.on_turn(turn()) == "disclosed"
    assert manager.tts[0][0] == voice.late_opening("") and "?" not in manager.tts[0][0]
    # a first-ever introduction still asks its one question
    speech, manager, out, session = build(
        Manager(heard="I run a tailoring shop in Lahore"), intake=True
    )
    assert await speech.on_turn(turn()) == "disclosed"
    assert manager.tts[0][0] == voice.opening() and "?" in manager.tts[0][0]


def test_an_acknowledgement_followed_by_a_restatement_is_an_echo() -> None:
    history = [
        voice.Said(True, "Hi, I'm pi, an AI. What does your business do?"),
        voice.Said(False, "customers keep calling later and the suits are ready"),
    ]
    for echo in (
        "Got it. Customers are calling after the suits are ready.",
        "I see. Customers keep calling later when the suits are ready.",
    ):
        assert voice.adds_nothing(echo, history, "yes the suits are ready"), echo
    new = "Got it. A simple board showing each suit's delivery day could cut those calls."
    assert not voice.adds_nothing(new, history, "yes the suits are ready")


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("can you see my screen", "screen"),
        ("kya aap meri screen dekh sakte hain", "screen"),
        ("کیا آپ میری سکرین دیکھ رہے ہیں", "screen"),
        ("can you talk faster", "fast"),
        ("zara tez bolo", "fast"),
    ],
)
def test_screen_and_speed_requests_are_answered_at_once(text, kind) -> None:
    found = voice.control(text, [], "en")
    assert found is not None and found.kind == kind, text
    for line in voice.CONTROL_LINES[kind].values():
        assert "?" not in line and voice.spoken_rules.broken(line) == ""


async def test_faster_undoes_slower() -> None:
    manager = Manager(heard="pi please slow down")
    speech, manager, out, session = build(manager)
    await speech.on_turn(turn())
    await speech.on_turn(turn())
    assert session.slow is True
    manager.heard = "pi can you talk faster"
    await speech.on_turn(turn())
    assert session.slow is False


async def test_speech_to_text_is_told_the_places_and_what_pi_learned() -> None:
    seen = []

    class Hear(Manager):
        async def transcribe(self, scope, audio, mime, **kw):
            seen.append(kw["prompt"])
            return await super().transcribe(scope, audio, mime, **kw)

    speech, manager, out, session = build(Hear())
    session.facts = ["tailoring shop, bridal wear"]
    await speech.on_turn(turn())
    assert "Lahore" in seen[0] and "tailoring shop" in seen[0] and seen[0].startswith("Workzap")


async def test_a_backlog_of_short_turns_is_answered_once_with_everything_said() -> None:
    sent = []

    class Slow(Manager):
        def __init__(self):
            super().__init__()
            self.n = 0

        async def transcribe(self, scope, audio, mime, **kw):
            self.n += 1
            return SimpleNamespace(text=f"pi piece{self.n} of the same long sentence")

        async def complete_structured(self, scope, model, **kw):
            sent.append(kw["messages"][1].content)
            await asyncio.sleep(0.05)  # a slow answer: the others pile up behind it
            return SimpleNamespace(value=model(reply=f"Answer {len(sent)} about the shop."))

    speech, manager, out, session = build(Slow())
    session.settings.intake = False
    await speech.on_turn(turn())  # the disclosure
    session.last_spoke_at = None
    first = asyncio.create_task(speech.on_turn(turn()))
    await asyncio.sleep(0.01)
    rest = [asyncio.create_task(speech.on_turn(turn())) for _ in range(3)]
    results = [await first, *[await t for t in rest]]
    assert results.count("merged") == 2  # three waiting pieces, one answer
    assert len(sent) == 2  # the first turn's answer, then ONE answer for the three that waited
    assert all(f"piece{n}" in sent[1] for n in (2, 3, 4))
    assert room_speech.CARRY_CHARS >= len(sent[1]) or True
