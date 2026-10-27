"""A turn that fails the schema never ends in the tech-down notice (Dalal&Co., 2026-10-27)."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.ai.errors import AllProvidersFailed, PermanentProviderFailure
from app.ai.manager import StructuredResult
from app.ai.types import Attempt, LLMResponse, Message
from app.modules.pi.service_conversation import ReplyOnlyTurn, ServiceTurn, structured_turn

LONG = "Sales team tracking: " + "who visits which shop, when, and where the day goes. " * 20


def test_long_understanding_and_slot_no_longer_fail() -> None:
    turn = ServiceTurn.model_validate(
        {
            "reply": "Ji, samajh gaya.",
            "understanding": LONG,
            "asked_slot": "sales_tracking.team_location_and_daily_activity_visibility_now",
        }
    )
    assert len(turn.understanding) == 600 and len(turn.asked_slot) <= 60
    # a list or a number in a text field is text, not a schema error
    turn = ServiceTurn.model_validate({"reply": "ok", "understanding": ["a", "b"], "asked_slot": 3})
    assert turn.understanding == "a, b" and turn.asked_slot == "3"


def _attempt(provider: str, kind: str | None) -> Attempt:
    return Attempt(
        provider=provider,
        model="m",
        status="failed" if kind else "success",
        error_kind=kind,
        latency_ms=1,
        attempt=1,
        fallback=False,
    )


class Fake:
    def __init__(self, first: Exception, second: Any) -> None:
        self.first, self.second, self.calls = first, second, []

    async def complete_structured(self, scope: Any, output: Any, **kwargs: Any) -> Any:
        self.calls.append((output, kwargs))
        if len(self.calls) == 1:
            raise self.first
        if isinstance(self.second, Exception):
            raise self.second
        return self.second


def _ok(reply: str) -> StructuredResult[ReplyOnlyTurn]:
    response = LLMResponse(text="{}", provider="gemini", model="m")
    return StructuredResult(ReplyOnlyTurn(reply=reply, language="roman_ur"), response)


async def _run(fake: Fake) -> StructuredResult[ServiceTurn]:
    return await structured_turn(
        fake,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        ServiceTurn,
        alias="pi_service",
        messages=[Message.system("s"), Message.user("{}")],
        temperature=0.2,
        conversation_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_all_providers_invalid_output_falls_back_to_reply_only() -> None:
    failed = AllProvidersFailed(
        [],
        [
            _attempt("gemini", "rate_limit"),
            _attempt("anthropic", "invalid_output"),
            _attempt("openai", "invalid_request"),
        ],
    )
    fake = Fake(failed, _ok("Ji, sales team ka track rakhna hai."))
    result = await _run(fake)
    assert result.value.reply.startswith("Ji, sales team")
    assert result.value.language == "roman_ur" and result.value.problem_ops == []
    assert fake.calls[1][0] is ReplyOnlyTurn
    assert len(result.response.attempts) == 3  # the failed ones stay in the record


@pytest.mark.asyncio
async def test_a_rejected_schema_that_stopped_the_chain_also_falls_back() -> None:
    from app.ai.errors import ErrorKind, ProviderError

    stopped = PermanentProviderFailure(
        ProviderError("openai", ErrorKind.INVALID_REQUEST, code="schema"),
        [],
        [_attempt("anthropic", "invalid_output"), _attempt("openai", "invalid_request")],
    )
    result = await _run(Fake(stopped, _ok("Ji.")))
    assert result.value.reply == "Ji."


@pytest.mark.asyncio
async def test_real_unavailability_still_raises() -> None:
    down = AllProvidersFailed([], [_attempt("gemini", "rate_limit"), _attempt("openai", "timeout")])
    fake = Fake(down, _ok("never used"))
    with pytest.raises(AllProvidersFailed):
        await _run(fake)
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_lenient_call_failing_or_empty_still_raises() -> None:
    bad = AllProvidersFailed([], [_attempt("anthropic", "invalid_output")])
    with pytest.raises(AllProvidersFailed):
        await _run(Fake(bad, AllProvidersFailed([], [_attempt("gemini", "timeout")])))
    with pytest.raises(AllProvidersFailed):
        await _run(Fake(bad, _ok("   ")))
