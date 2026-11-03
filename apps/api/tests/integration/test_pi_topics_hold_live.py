# ruff: noqa: E501
"""Spec v1.4 17.3 (topic pointer, a second business), 11.1 S_HOLD (heavy disclosure) and 17.4 G10,
live through the conversation flow behind response_rules.brain.thinking. With thinking off the
chat behaves as before: no hold, no pointer."""

import json
from types import SimpleNamespace

import pytest
from test_pi_brain_problems import say, workspace

from app.ai.manager import LLMManager
from app.modules.pi.service_conversation import ServiceTurn, ThinkingServiceTurn
from app.modules.pi.think_plan import MovePlan

pytestmark = pytest.mark.integration

IDEAS = "I'm pi, an AI from Workzap. That sounds heavy.\n• Count the stock every week.\n• Call the late payers first."
KIND = "I'm pi, an AI from Workzap. That sounds really heavy, and I'm sorry you carry it."
ASK_WHICH = "I'm pi, an AI from Workzap. A farm with water trouble is a different problem. Dono karobar ke naqshe alag rakhte hain. Pehle kis se shuru karein?"
NOTED = "I'm pi, an AI from Workzap. Alag note kar li hai."


def script(monkeypatch, replies: list[str], *, thinking: bool = True):
    """Each model call takes the next reply (the last repeats); records the contexts sent."""
    seen: list[dict] = []
    queue = list(replies)

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if text.startswith("{"):
            seen.append(json.loads(text))
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if thinking:
            plan = MovePlan(
                move="M1_reflect",
                reason="say it back",
                asks_question=reply.rstrip().endswith("?"),
                addresses="b1",
            )
            value = ThinkingServiceTurn(reply=reply, language="en", move_plan=plan)
        else:
            value = ServiceTurn(reply=reply, language="en")
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return seen


async def start(api, db, *, thinking=True):
    pi = await workspace(api, db)
    rules = {"pi_mode": "brain", "brain": {"thinking": True} if thinking else {}}
    response = await api.patch("/api/v1/pi/settings/response_rules", json={"value": rules})
    assert response.status_code == 200, response.text
    return pi


async def last_reply(pi) -> str:
    return (await pi.outbound())[-1].body


async def test_a_heavy_disclosure_holds_the_chat_and_a_reply_with_ideas_is_rewritten(
    api, business_db, monkeypatch
):
    seen = script(monkeypatch, [IDEAS, KIND])
    pi = await start(api, business_db)
    await say(pi, "I run a small shop in Lahore and stock keeps running out", "hold-1")
    await say(pi, "I can't take it any more, the debts are crushing me and I give up", "hold-2")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S_HOLD"
    context = seen[-1] if seen else {}
    assert "hold_note" in json.dumps(seen) and context.get("solution_ideas") is None
    body = await last_reply(pi)
    assert "•" not in body and "sorry" in body
    await pi.close()


async def test_the_next_ordinary_message_takes_the_chat_off_hold(api, business_db, monkeypatch):
    script(monkeypatch, [KIND])
    pi = await start(api, business_db)
    await say(pi, "I can't take it any more, the debts are crushing me and I give up", "hold-3")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S_HOLD"
    await say(pi, "ok, let us talk about my stock now, it runs out on Fridays", "hold-4")
    await business_db.refresh(conversation)
    assert conversation.flow_state != "S_HOLD"
    await pi.close()


async def test_a_second_business_is_parked_and_pi_asks_which_first(api, business_db, monkeypatch):
    seen = script(monkeypatch, [NOTED, ASK_WHICH])
    pi = await start(api, business_db)
    await say(pi, "I am a locksmith in Lahore and missed calls cost me jobs", "topic-1")
    await say(pi, "Mera ek aur karobar hai, lettuce farm, wahan paani ka masla hai", "topic-2")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    topics = conversation.service_brief["topics"]
    assert [i["id"] for i in topics["items"]] == ["b1", "b2"] and topics["pending"] is True
    assert any(c.get("topic_event") == "second_business" for c in seen)
    body = await last_reply(pi)
    assert body.rstrip().endswith("?") and "alag note" not in body.lower()
    await pi.close()


async def test_an_infeasible_plan_is_rewritten_for_a_two_technician_business(
    api, business_db, monkeypatch
):
    plan = "I'm pi, an AI from Workzap. Keep a named on-call person always available at night."
    fixed = (
        "I'm pi, an AI from Workzap. Whoever finishes a job first can call the missed callers back."
    )
    script(monkeypatch, [plan, fixed])
    pi = await start(api, business_db)
    await say(pi, "We are two technicians and both are on jobs at night, calls get missed", "g10-1")
    assert "always available" not in await last_reply(pi)
    await pi.close()


async def test_with_thinking_off_nothing_is_held_and_no_pointer_is_kept(
    api, business_db, monkeypatch
):
    script(monkeypatch, [KIND], thinking=False)
    pi = await start(api, business_db, thinking=False)
    await say(pi, "I can't take it any more, the debts are crushing me and I give up", "off-1")
    await say(pi, "Mera ek aur karobar hai, lettuce farm, wahan paani ka masla hai", "off-2")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state != "S_HOLD"
    assert "topics" not in (conversation.service_brief or {})
    await pi.close()
