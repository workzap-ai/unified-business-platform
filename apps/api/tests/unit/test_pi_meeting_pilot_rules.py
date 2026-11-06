"""What pi may suggest to the person running a meeting, and when a checklist item counts as done."""

from types import SimpleNamespace

import pytest

from app.modules.pi_meetings import pilot
from app.modules.pi_meetings.qa import Line


@pytest.mark.parametrize(
    "text",
    [
        "How often does the stock run out?",
        "Kitni baar stock khatam ho jata hai?",
        "That sounds hard. How often does it happen?",  # a short lead-in, the question last
    ],
)
def test_one_short_question_is_kept(text):
    assert pilot.acceptable_question(text, []) == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "How often does it happen? And since when?",  # two questions
        "Tell me about the stock?? ",  # two marks
        "How often does it happen",  # no question mark
        "Would Rs 5000 a month suit you?",  # a price
        "Would 20 lakh work for you?",  # a price in another form
        "Can you send the card number?",  # asks for a card
        "What is your CNIC number?",  # an identity number
        "Can you pay now?",  # a payment
        "x" * 230 + "?",  # too long
    ],
)
def test_anything_else_is_dropped(text):
    assert pilot.acceptable_question(text, []) == ""


def test_a_question_the_team_just_asked_is_not_suggested_again():
    said = ["How often does the stock run out?"]
    assert pilot.acceptable_question("how often does the stock run out?", said) == ""


def test_the_checklist_is_cleaned_and_bounded():
    raw = ["Budget", "budget", "  ", *[f"item {i}" for i in range(20)]]
    items = pilot.clean_items(raw)
    assert items[0] == "Budget" and len(items) == pilot.MAX_ITEMS and "" not in items
    assert pilot.clean_items(["call 03001234567 today"]) != ["call 03001234567 today"]


def test_only_the_newest_lines_that_fit_are_read():
    lines = [Line(i, "word " * 40) for i in range(500)]
    got = pilot.recent(lines)
    assert len(got) <= pilot.RECENT_LINES and got[-1].ordinal == 499
    assert [x.ordinal for x in got] == sorted(x.ordinal for x in got)


class Model:
    def __init__(self, **value):
        self.value = pilot.ModelSuggestion(**value)

    async def complete_structured(self, scope, output, **kw):
        return SimpleNamespace(value=self.value)


LINES = [Line(10, "our stock runs out", "Speaker 1", "customer"), Line(11, "ok", "Staff", "staff")]


async def test_a_tick_needs_a_line_the_model_was_shown():
    model = Model(
        question="How often is that?",
        covered=[
            pilot.Cover(item=0, refs=[10]),  # real line: done
            pilot.Cover(item=1, refs=[99]),  # a line that is not in the meeting: ignored
            pilot.Cover(item=2, refs=[]),  # no line at all: ignored
            pilot.Cover(item=9, refs=[10]),  # not an item: ignored
        ],
    )
    out = await pilot.suggest(model, None, LINES, ["problem", "budget", "timeline"])
    assert [i.done for i in out.checklist] == [True, False, False]
    assert out.checklist[0].refs == [10] and out.question == "How often is that?"


async def test_a_bad_question_is_dropped_but_the_ticks_stay():
    model = Model(question="Would Rs 5000 do?", covered=[pilot.Cover(item=0, refs=[10])])
    out = await pilot.suggest(model, None, LINES, ["problem"])
    assert out.question == "" and out.checklist[0].done is True


async def test_a_provider_that_refuses_raises(monkeypatch):
    from app.ai.errors import GatewayUnavailable

    monkeypatch.setattr(pilot, "RETRY_PAUSES", (0.0,))

    class Down:
        async def complete_structured(self, *a, **k):
            raise GatewayUnavailable()

    with pytest.raises(pilot.PilotFailed):
        await pilot.suggest(Down(), None, LINES, [])
