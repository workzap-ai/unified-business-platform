"""Which lines of a meeting the question model sees, and when its answer is kept."""

from types import SimpleNamespace

import pytest

from app.modules.pi_meetings import qa
from app.modules.pi_meetings.qa import Line


def lines(n, size=100):
    return [Line(i * 1000, f"line {i} " + "x" * size) for i in range(n)]


def test_a_short_meeting_goes_in_whole():
    part, partial = qa.pick(lines(10), [3])
    assert len(part) == 10 and partial is False


def test_a_long_meeting_sends_the_hits_with_their_neighbours_in_order():
    everything = lines(400)
    part, partial = qa.pick(everything, [200, 50], limit=2_000)
    assert partial is True
    got = [x.ordinal // 1000 for x in part]
    assert got == sorted(got)
    assert {48, 49, 50, 51, 52, 198, 199, 200, 201, 202} <= set(got)
    assert sum(len(x.text) + 24 for x in part) <= 2_000


def test_with_no_hit_a_long_meeting_sends_its_start_and_end():
    part, partial = qa.pick(lines(400), [], limit=2_000)
    got = [x.ordinal // 1000 for x in part]
    assert partial and 0 in got and 399 in got and 200 not in got


def test_search_words_are_plain_and_bounded():
    terms = qa.search_terms("What's the BUDGET? budget; drop table x -- 'or' 1=1 stock stock")
    assert terms == ["what", "the", "budget", "drop", "table", "stock"]
    assert all(t.isalnum() for t in terms)
    assert len(qa.search_terms(" ".join(f"word{i}" for i in range(30)))) == 8


class Model:
    def __init__(self, found=True, answer="They need stock alerts", refs=(2,)):
        self.value = qa.ModelAnswer(found=found, answer=answer, refs=list(refs))
        self.calls = 0

    async def complete_structured(self, scope, output, **kw):
        self.calls += 1
        return SimpleNamespace(value=self.value)


PART = [Line(1, "a"), Line(2, "stock alerts please", "Speaker 1", "customer")]


async def test_an_answer_that_cites_a_shown_line_is_kept_with_its_sources():
    out = await qa.ask(Model(), None, "what do they need", PART, partial=False)
    assert out.found and out.text == "They need stock alerts"
    assert [s.ordinal for s in out.sources] == [2]


@pytest.mark.parametrize("refs", [(), (99,)])
async def test_an_answer_with_no_line_of_the_meeting_behind_it_is_not_shown(refs):
    out = await qa.ask(Model(refs=refs), None, "q?", PART, partial=False)
    assert out.found is False and out.text == "" and out.sources == []


async def test_the_model_saying_not_found_is_not_found():
    out = await qa.ask(Model(found=False, answer="", refs=()), None, "q?", PART, partial=True)
    assert out.found is False and out.partial is True


async def test_a_phone_number_in_the_answer_is_removed():
    out = await qa.ask(
        Model(answer="Call him on 03001234567 for stock"), None, "q?", PART, partial=False
    )
    assert "03001234567" not in out.text


async def test_a_provider_that_always_refuses_raises(monkeypatch):
    from app.ai.errors import GatewayUnavailable

    monkeypatch.setattr(qa, "RETRY_PAUSES", (0.0, 0.0))

    class Down:
        calls = 0

        async def complete_structured(self, *a, **k):
            Down.calls += 1
            raise GatewayUnavailable()

    with pytest.raises(qa.AskFailed):
        await qa.ask(Down(), None, "q?", PART, partial=False)
    assert Down.calls == 3
