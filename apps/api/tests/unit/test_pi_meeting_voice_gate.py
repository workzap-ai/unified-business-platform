"""What pi may say out loud on a meeting link: one short question, last, nothing that sells or asks
for money, and the safe line whenever the model's reply is not allowed."""

from types import SimpleNamespace

import pytest

from app.ai.errors import GatewayUnavailable
from app.modules.pi_meetings import voice
from app.modules.pi_meetings.voice import Said

HEARD = "we sell tiles and the stock runs out every week"
HISTORY = [
    Said(True, "Hi, I'm pi, an AI from Workzap. What does your business do?"),
    Said(False, "we sell tiles"),
]


def ctx():
    return voice.context(HISTORY, HEARD)


@pytest.mark.parametrize(
    "reply",
    [
        "How often does the stock run out?",
        "That sounds hard. How often does the stock run out?",
    ],
)
def test_one_short_question_at_the_end_is_allowed(reply):
    assert voice.allowed(reply, ctx()) == reply


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "How often? And since when?",  # two questions
        "How often does it run out",  # no question
        "I can fix that for Rs 5000. Want it?",  # a price and a sale
        "You should buy our software. How often does it run out?",  # selling
        "Please send your card number. Is that fine?",  # asks for a card
        "What is your CNIC number?",  # an ID number
        "x" * 400 + "?",  # too long to say
    ],
)
def test_anything_else_is_not_said(reply):
    assert voice.allowed(reply, ctx()) == ""


def test_the_opening_is_the_ai_disclosure_then_one_question():
    words = voice.opening()
    assert "AI" in words and words.count("?") == 1 and words.endswith("?")
    assert voice.allowed(words, voice.context([], "")) in {
        "",
        words,
    }  # the fixed line is its own check


class Model:
    def __init__(self, reply="How often does it run out?", done=False):
        self.value = voice.ModelReply(reply=reply, done=done)

    async def complete_structured(self, scope, output, **kw):
        return SimpleNamespace(value=self.value)


async def test_a_reply_that_passes_is_spoken_as_written():
    out = await voice.reply_to(Model(), None, HISTORY, HEARD)
    assert out.text == "How often does it run out?" and out.fallback is False


async def test_a_reply_that_breaks_a_rule_becomes_the_safe_line():
    out = await voice.reply_to(Model("I can fix that for Rs 5000. Want it?"), None, HISTORY, HEARD)
    assert out.fallback is True and "5000" not in out.text and out.text.endswith("?")


async def test_asking_what_was_already_asked_becomes_the_safe_line():
    again = HISTORY + [Said(True, "How often does it run out?"), Said(False, "weekly")]
    out = await voice.reply_to(Model("How often does it run out?"), None, again, "weekly")
    assert out.fallback is True


async def test_a_closing_thanks_with_no_question_is_allowed_when_the_person_is_done():
    out = await voice.reply_to(
        Model("Thank you, that is all I needed.", done=True), None, HISTORY, "bas"
    )
    assert out.done is True and out.fallback is False and "?" not in out.text


async def test_a_closing_that_sells_is_not_said():
    out = await voice.reply_to(Model("Great, buy for Rs 5000.", done=True), None, HISTORY, "bas")
    assert out.done is False and out.fallback is True


async def test_a_model_that_is_down_gives_the_safe_line_not_an_error(monkeypatch):
    monkeypatch.setattr(voice, "RETRY_PAUSES", (0.0,))

    class Down:
        async def complete_structured(self, *a, **k):
            raise GatewayUnavailable()

    out = await voice.reply_to(Down(), None, HISTORY, HEARD)
    assert out.fallback is True and out.text.endswith("?")
