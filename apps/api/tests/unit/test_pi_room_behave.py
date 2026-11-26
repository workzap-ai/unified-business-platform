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
