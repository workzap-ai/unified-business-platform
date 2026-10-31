"""PS-flow: the turn's one language decision (PS-9) feeds the fixed lines and keeps the script."""

from app.modules.pi import fixed_lines, language_script


def decision(text, pin=None, history=()):
    d = language_script.detect_message_language(text, history=list(history), pinned=pin)
    code, script = language_script.reply_language_for(d, pin, list(history))
    return {
        "code": code,
        "script": script,
        "key": language_script.fixed_line_key(code, script),
        "uncertain": d.uncertain,
    }


def test_an_urdu_script_owner_keeps_urdu_script_lines():
    d = decision("مجھے اپنے کاروبار میں بکنگ کا مسئلہ ہے")
    ctx = {
        "language_decision": d,
        "latest_customer_message": "مجھے اپنے کاروبار میں بکنگ کا مسئلہ ہے",
    }
    assert fixed_lines.code(ctx, script=False) == "ur" == d["key"]


def test_a_roman_urdu_owner_never_gets_urdu_script():
    text = "Hamare school mein fees dair se aati hai har mahine"
    d = decision(text)
    assert fixed_lines.code({"language_decision": d, "latest_customer_message": text}) == "roman_ur"


def test_a_short_message_never_moves_the_pin():
    d = decision("ok", pin=("ur", "arabic"))
    assert d["key"] == "ur"
    assert fixed_lines.code({"language_decision": d, "latest_customer_message": "ok"}) in (
        "ur",
        "en",
    )


def test_an_explicit_request_for_another_language_still_wins():
    ctx = {
        "reply_language_other": "French",
        "language_decision": {"key": "ur", "uncertain": False},
    }
    assert fixed_lines.code(ctx) == "fr"
