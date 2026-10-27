"""The thinking step end to end (Book 5, spec 3.2 and 11.2), behind response_rules.brain.thinking:
a bad plan goes back through the rewrite path, one pi_move_log row per pi message, the hypothesis
ledger, the moves fed back into the next turn's history, and nothing at all when the flag is off."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import OPENING, say, workspace

from app.ai.manager import LLMManager
from app.modules.pi.service_conversation import ServiceTurn, ThinkingServiceTurn
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.modules.pi.think_plan import HypothesisUpdate, MovePlan

pytestmark = pytest.mark.integration

GIVING = (
    f"{OPENING} Purana maal paisa roke rakhta hai, "
    "aur wahi paisa naye maal ke liye chahiye hota hai."
)


def script(monkeypatch, make):
    """make(call_number, user_text) -> a turn; the calls (system, last message) are kept."""
    calls: list[dict] = []

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        calls.append({"output": output, "text": text})
        return SimpleNamespace(value=make(len(calls), text), response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return calls


async def enable(api, thinking):
    brain = {"thinking": True} if thinking else {}
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"pi_mode": "brain", "brain": brain}},
    )
    assert response.status_code == 200, response.text


async def moves_of(db):
    rows = await db.scalars(select(PiMoveLog).order_by(PiMoveLog.created_at))
    return list(rows)


async def test_a_bad_plan_is_rewritten_and_never_stored_and_the_move_is_logged(
    api, business_db, monkeypatch
):
    def make(n, text):
        bad = n == 1
        plan = MovePlan(
            move="M99_magic" if bad else "M1_reflect",
            reason="" if bad else "they opened up about stock",
            asks_question=False,
            hypothesis=HypothesisUpdate(
                action="add",
                text="the stuck stock is what ties up their cash",
                confidence="low",
                evidence="purana maal ruka hai",
                test="ask what share of cash is in stock",
            ),
        )
        return ThinkingServiceTurn(reply=GIVING, language="en", move_plan=plan)

    calls = script(monkeypatch, make)
    pi = await workspace(api, business_db)
    await enable(api, True)
    await say(pi, "Purana maal ruka hai aur paisa phansa hai", "tk-1")
    assert calls[0]["output"] is ThinkingServiceTurn
    assert len(calls) == 2  # the first plan was refused, the rewrite fixed it
    assert "your move_plan is not valid" in calls[1]["text"]
    assert "unknown move" in calls[1]["text"]
    rows = await moves_of(business_db)
    assert [r.move for r in rows] == ["M1_reflect"]
    assert rows[0].reason == "they opened up about stock" and rows[0].had_question is False
    assert rows[0].message_id is not None
    ledger = list(await business_db.scalars(select(PiHypothesis)))
    assert len(ledger) == 1 and ledger[0].status == "open" and ledger[0].confidence == "low"
    await pi.close()


async def test_the_stored_move_comes_back_in_the_next_turns_history(api, business_db, monkeypatch):
    def make(n, text):
        return ThinkingServiceTurn(
            reply=GIVING,
            language="en",
            move_plan=MovePlan(move="M16_hold_space", reason="heavy opening"),
        )

    calls = script(monkeypatch, make)
    pi = await workspace(api, business_db)
    await enable(api, True)
    await say(pi, "Purana maal ruka hai aur paisa phansa hai", "tk-2")
    await say(pi, "Haan bilkul, aur gahak bhi kam hain", "tk-3")
    context = json.loads(next(c["text"] for c in reversed(calls) if c["text"].startswith("{")))
    assert context["thinking"] is True and "plan" not in context
    ai = [h for h in context["history"] if h["role"] == "ai"]
    assert ai and ai[-1]["move"] == "M16_hold_space"
    await pi.close()


async def test_with_thinking_off_nothing_changes_and_nothing_is_stored(
    api, business_db, monkeypatch
):
    def make(n, text):
        return ServiceTurn(reply=GIVING, language="en")

    calls = script(monkeypatch, make)
    pi = await workspace(api, business_db)
    await enable(api, False)
    await say(pi, "Purana maal ruka hai aur paisa phansa hai", "tk-4")
    assert calls[0]["output"] is ServiceTurn
    assert "move_plan" not in calls[0]["text"]
    assert await moves_of(business_db) == []
    assert list(await business_db.scalars(select(PiHypothesis))) == []
    await pi.close()
