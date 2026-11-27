"""Transcripts and captions are written in Roman Urdu: no Hindi or Urdu letters are left."""

from types import SimpleNamespace
from uuid import uuid4

from app.modules.pi_meetings import roman_urdu
from app.shared.scope import WorkspaceScope

SCOPE = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "t")
HINDI = "हेलो मेरी बेकरी है कराची में"
URDU = "میرا کپڑوں کا کاروبار ہے"


def test_the_plain_rewrite_gives_latin_letters_only() -> None:
    for text in (
        HINDI,
        URDU,
        "अब सलूशन बताओ क्या सलूशन आना चाहिए कौन सा सिस्टम बनाना चाहिए",
        "آپ کی بیکری کا نام کیا ہے؟",
        "मेरा कारोबार ५० ऑर्डर",
    ):
        out = roman_urdu.rules(text)
        assert out and not roman_urdu.needs_roman(out), (text, out)
    assert roman_urdu.rules(HINDI) == "hello meri bakery hai karachi mein"
    assert roman_urdu.rules("हम चार लोग हैं") == "hum char log hain"
    assert "50" in roman_urdu.rules("मेरा कारोबार ५० ऑर्डर")  # digits stay digits


def test_english_and_roman_text_are_left_alone() -> None:
    for text in ("I run a small bakery in Karachi", "mera karobar hai", "25 orders a day"):
        assert not roman_urdu.needs_roman(text)
        assert roman_urdu.rules(text) == text


class Model:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.calls = answer, fail, 0

    async def complete_structured(self, scope, model, **kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return SimpleNamespace(value=model(lines=self.answer(kw)))


async def test_the_model_rewrite_is_used_and_latin_lines_cost_nothing() -> None:
    manager = Model(lambda kw: ["mera bakery Karachi mein hai"])
    out = await roman_urdu.to_roman(manager, SCOPE, ["I sell bread", HINDI, "ok"])
    assert out == ["I sell bread", "mera bakery Karachi mein hai", "ok"]
    assert manager.calls == 1
    quiet = Model(lambda kw: [])
    assert await roman_urdu.to_roman(quiet, SCOPE, ["only English here"]) == ["only English here"]
    assert quiet.calls == 0  # nothing to rewrite: no model call


async def test_a_model_that_fails_or_answers_badly_falls_back_to_the_plain_rewrite() -> None:
    expected = roman_urdu.rules(HINDI)
    for manager in (
        Model(fail=True),
        Model(lambda kw: ["wrong count", "of lines"]),
        Model(lambda kw: [HINDI]),  # it still left Hindi letters in
        object(),  # no model door at all (a test double)
    ):
        out = await roman_urdu.to_roman(manager, SCOPE, [HINDI])
        assert out == [expected], manager


async def test_many_lines_go_in_batches_and_keep_their_order() -> None:
    lines = [f"{HINDI} {n}" for n in range(roman_urdu.BATCH + 5)]
    manager = Model(
        lambda kw: [
            f"roman {i}"
            for i in range(len(__import__("json").loads(kw["messages"][1].content)["lines"]))
        ]
    )
    out = await roman_urdu.to_roman(manager, SCOPE, lines)
    assert manager.calls == 2 and len(out) == len(lines)
    assert out[0] == "roman 0" and out[roman_urdu.BATCH] == "roman 0"
