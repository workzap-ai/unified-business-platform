"""Asked 'can you see my screen?', pi answers from what it really sees: the kind of thing shown,
that it is still looking, that nothing is shared, or (sight off) that it cannot see screens."""

import pytest
from test_pi_room_speech import Manager, build, turn

from app.modules.pi_meetings import room_sight, voice


@pytest.mark.parametrize(
    "text",
    [
        "can you see my screen",
        "what do you see",
        "what's on my screen",
        "kya aap meri screen dekh sakte hain",
        "screen par kya hai",
        "کیا آپ میری سکرین دیکھ رہے ہیں",
    ],
)
def test_screen_questions_are_found(text) -> None:
    found = voice.control(text, [], "en")
    assert found is not None and found.kind == "screen", text


def test_the_screen_line_says_what_is_seen_without_names_or_numbers() -> None:
    line = voice.screen_line("en", True, "a spreadsheet of customer orders with a status column")
    assert line.startswith("Yes, I can see your screen.") and "spreadsheet" in line
    assert "?" not in line and voice.spoken_rules.broken(line) == ""
    ur = voice.screen_line("ur", True, "an online clothing store")
    assert "clothing store" in ur and "۔" in ur
    assert voice.screen_line("en", True, "") == voice.SCREEN_LINES["looking"]["en"]
    assert voice.screen_line("en", False, "") == voice.SCREEN_LINES["none"]["en"]
    # a note that would break a spoken rule is never read out: pi only says it is looking
    priced = voice.screen_line("en", True, "a page showing a price of 500 rupees")
    assert priced == voice.SCREEN_LINES["looking"]["en"]
    for per_language in voice.SCREEN_LINES.values():
        for text in per_language.values():
            assert "{note}" in text or voice.spoken_rules.broken(text) == ""


async def ask_screen(sees, state):
    speech, manager, out, session = build(Manager(heard="pi can you see my screen"))
    speech.can_see_screen = sees
    speech.screen = lambda: state
    await speech.on_turn(turn())  # the disclosure
    session.last_spoke_at = None
    await speech.on_turn(turn())
    return manager.tts[-1][0]


async def test_pi_answers_a_screen_question_from_what_it_sees() -> None:
    cannot = await ask_screen(False, (False, ""))  # sight is off in this deployment
    assert cannot == voice.CONTROL_LINES["screen"]["en"]
    assert await ask_screen(True, (False, "")) == voice.SCREEN_LINES["none"]["en"]
    assert await ask_screen(True, (True, "")) == voice.SCREEN_LINES["looking"]["en"]
    seen = await ask_screen(True, (True, "a social media post designer"))
    assert seen.startswith("Yes, I can see your screen.") and "post designer" in seen


def test_the_sight_knows_whether_a_screen_is_being_watched() -> None:
    sight = room_sight.Sight(object(), None, clock=lambda: 0.0)
    assert sight.sharing is False
    sight.sharing = True
    assert sight.sharing is True and sight.current() == ""
