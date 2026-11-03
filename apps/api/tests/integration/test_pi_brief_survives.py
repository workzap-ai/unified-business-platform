"""A failing optional step while saving a turn (the customer's record, the idea feedback) must not
cost the turn its brief: the open question and the closed ones are still saved (live chat of
2026-10-27: the brief stopped being saved from the third reply and pi asked a question twice)."""

from types import SimpleNamespace

import pytest
from test_pi_brain_problems import say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import service_conversation

pytestmark = pytest.mark.integration

QUESTIONS = [
    "Aap ke business mein kya masla hai?",
    "Sab se zyada kahan hota hai: sale ya stock?",
    "Kya roz ka koi target hai?",
]


def script(monkeypatch):
    n = {"i": 0}

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if not text.startswith("{"):
            value = turn(reply="Theek hai. Aap ke paas kitne salesman hain?", language="roman_ur")
        else:
            value = turn(reply=QUESTIONS[min(n["i"], 2)], language="roman_ur")
            n["i"] += 1
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)


async def boom(*_a, **_k):
    raise RuntimeError("an optional step failed")


async def test_the_brief_is_saved_even_when_optional_steps_fail(api, business_db, monkeypatch):
    script(monkeypatch)
    monkeypatch.setattr(service_conversation, "remember_customer", boom)
    monkeypatch.setattr(service_conversation, "save_feedback", boom)
    pi = await workspace(api, business_db)
    for i, said in enumerate(["Hello", "Maslay bohat hain", "Sale mai hai"]):
        await say(pi, said, f"b-{i}")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    brief = conversation.service_brief
    last = (await pi.reply_to("b-2")).body
    assert last and brief["last_question"]["q"] in last  # the open question is the one just asked
    assert len(brief["closed_slots"]) >= 1
    assert brief["source_message_id"]  # and the turn was saved at all
    await pi.close()
