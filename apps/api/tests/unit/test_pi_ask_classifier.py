"""The model check for "is this a request for a solution or an idea?" (any language or wording)."""

from types import SimpleNamespace

import pytest

from app.modules.pi import ask_classifier, solution_ask


class FakeManager:
    def __init__(self, text: str = '{"asks": true}', fail: bool = False) -> None:
        self.text, self.fail, self.calls = text, fail, 0

    async def complete(self, scope, **kwargs):  # noqa: ANN001, ANN201
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return SimpleNamespace(text=self.text)


@pytest.fixture(autouse=True)
def _clear() -> None:
    solution_ask._LEARNED_ASKS.clear()


def test_the_verdict_is_read_from_json_or_loose_text() -> None:
    assert ask_classifier.parse('{"asks": true}') is True
    assert ask_classifier.parse('{"asks": false}') is False
    assert ask_classifier.parse('Sure: {"asks":true}') is True
    assert ask_classifier.parse("maybe") is None
    assert ask_classifier.parse("") is None


def test_the_model_is_asked_only_when_the_phrase_banks_cannot_decide() -> None:
    state = "S3_NOTED"
    assert ask_classifier.needed(
        "Boleh tolong carikan jalan supaya pesanan tidak keliru lagi?", state
    )
    assert not ask_classifier.needed("Solution dain", state)  # the phrase bank already says yes
    assert not ask_classifier.needed("ok", state)  # too short
    assert not ask_classifier.needed(
        "Haan, har hafte hota hai aur nuksan ka andaza nahi hota.", state
    )
    assert not ask_classifier.needed(
        "Boleh tolong carikan jalan supaya pesanan tidak keliru?", "S6_PREPARING"
    )


async def test_a_yes_from_the_model_makes_the_message_an_ask() -> None:
    said = "Boleh tolong carikan jalan supaya pesanan tidak keliru lagi?"
    assert not solution_ask.asked_for_ideas(said)
    manager = FakeManager('{"asks": true}')
    verdict = await ask_classifier.prefetch(
        manager, None, said=said, flow_state="S3_NOTED", conversation_id=None
    )
    assert verdict is True and manager.calls == 1
    assert solution_ask.asked_for_ideas(said)
    again = await ask_classifier.prefetch(
        manager, None, said=said, flow_state="S3_NOTED", conversation_id=None
    )
    assert again is None and manager.calls == 1  # remembered: no second call


async def test_a_no_from_the_model_changes_nothing() -> None:
    said = "Pesanan kami sering keliru dan stok tidak cocok, bagaimana menurutmu?"
    verdict = await ask_classifier.prefetch(
        FakeManager('{"asks": false}'), None, said=said, flow_state="S3_NOTED", conversation_id=None
    )
    assert verdict is False and not solution_ask.asked_for_ideas(said)


async def test_a_failing_or_unsure_model_leaves_the_phrase_banks_as_the_answer() -> None:
    said = "Boleh tolong carikan jalan supaya pesanan tidak keliru lagi?"
    down = await ask_classifier.prefetch(
        FakeManager(fail=True), None, said=said, flow_state="S3_NOTED", conversation_id=None
    )
    unsure = await ask_classifier.prefetch(
        FakeManager("hmm"), None, said=said, flow_state="S3_NOTED", conversation_id=None
    )
    assert down is None and unsure is None and not solution_ask.asked_for_ideas(said)


def test_the_remembered_verdicts_are_bounded() -> None:
    for n in range(solution_ask.LEARNED_LIMIT + 50):
        solution_ask.remember_ask(f"message {n}", True)
    assert len(solution_ask._LEARNED_ASKS) <= solution_ask.LEARNED_LIMIT
