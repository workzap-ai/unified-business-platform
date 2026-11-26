"""Room behaviour fixes found live: language stickiness, tired owner, solution request."""

from app.modules.pi_meetings import voice

U = "آپ کا کاروبار کیا ہے؟"


def test_short_english_fragment_does_not_switch_language() -> None:
    history = [voice.Said(True, U)]
    assert voice.reply_language(history, "your company name", "") != "en"


def test_long_english_turn_switches_language() -> None:
    history = [voice.Said(True, U)]
    heard = "I run a clothing brand and my team of five handles design and ads"
    assert voice.reply_language(history, heard, "") == "en"


def test_annoyed_detected() -> None:
    assert voice.annoyed("Why are you asking again and again?")
    assert voice.annoyed("बार बार पूछ रहे हो")
    assert not voice.annoyed("I sell shoes")


def test_solution_request_detected_and_line_has_no_question() -> None:
    assert voice.asks_for_solution("Can you build a system like this?")
    assert voice.asks_for_solution("मुझे सलूशन बताओ")
    assert not voice.asks_for_solution("I sell shoes")
    for lang in ("en", "ur"):
        line = voice.solution_line(lang)
        assert "?" not in line and "؟" not in line


def test_question_policy_never_two_in_a_row_and_calm() -> None:
    assert voice.question_policy([voice.Said(True, "Ok?")]) == "none"
    assert voice.question_policy([voice.Said(True, "Ok.")]) == "optional"
    assert voice.question_policy([voice.Said(True, "Ok.")], calm=True) == "none"


async def test_a_request_for_help_gets_one_suggestion_then_the_fixed_line_after_the_cap():
    from uuid import uuid4

    from test_pi_room_speech import Manager

    from app.shared.scope import WorkspaceScope

    idea = "One thing worth thinking about is a single shared place for all the design requests."
    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    history = [voice.Said(True, "Got it."), voice.Said(False, "my design team of five is slow")]
    asked = "Can you build a system like this or find a solution?"
    out = await voice.reply_to(Manager(reply=idea), scope, history, asked)
    assert out.idea and out.text == idea and "?" not in out.text
    capped = await voice.reply_to(
        Manager(reply=idea), scope, history, asked, ideas_given=voice.IDEA_CAP
    )
    assert not capped.idea and capped.text == voice.solution_line("en")


async def test_a_suggestion_with_a_price_or_a_question_becomes_the_fixed_line():
    from uuid import uuid4

    from test_pi_room_speech import Manager

    from app.shared.scope import WorkspaceScope

    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
    for bad in ("We can build it for 5000 rupees.", "Would a shared board help you?"):
        out = await voice.reply_to(Manager(reply=bad), scope, [], "Can you build a system?")
        assert not out.idea and out.text == voice.solution_line("en")


def test_fillers_rotate_and_are_not_questions() -> None:
    seen = {voice.filler("en", n) for n in range(4)}
    assert len(seen) == 4
    for n in range(4):
        assert "?" not in voice.filler("en", n) and "؟" not in voice.filler("ur", n)


def test_echo_openers_and_empty_praise_are_caught() -> None:
    for tic in (
        "You said that your team is slow.",
        "آپ نے کہا کہ آپ کی ٹیم سست ہے۔",
        "یہ واقعی ایک اہم مسئلہ ہے۔",
        "That is a great question.",
    ):
        assert voice.has_tic(tic), tic
    for fine in ("Ten a day, that adds up.", "دس روز، یہ بہت ہوتے ہیں۔", "I see."):
        assert not voice.has_tic(fine), fine
