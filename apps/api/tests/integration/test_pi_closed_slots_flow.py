"""R-ASK-07 end to end: the answered question is stored as a closed slot in the brief, shown to the
model next turn, and a reply that asks it again (in other words, in another language) is sent
back for a rewrite. Real database; the AI and WhatsApp are mocked."""

import json
from types import SimpleNamespace

import pytest
from test_pi_brain_problems import say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap. What is your business called, and what do you make?"
FIRST = "Which branch is it worse at?"
AGAIN = "Noted. Where does the taste change most, the same branch or different ones?"
FINE = "Noted. Anything else getting in the way?"


def script(monkeypatch):
    prompts: list[str] = []

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        prompts.append(text)
        if not text.startswith("{"):  # the rewrite request: a different reply
            value = turn(reply=FINE, language="en")
        else:
            said = json.loads(text)["latest_customer_message"]
            if said == "I need some help please":  # first reply to a new number: who are you (18.2)
                value = turn(reply=OPENING, language="en", asked_slot="business.what")
            elif "Tipu" in said:  # asked again, in other words, same slot
                value = turn(reply=AGAIN, language="en", asked_slot="branch.where")
            elif "since" in said:
                value = turn(reply="Noted. How many kitchens?", language="en")
            else:
                value = turn(reply=FIRST, language="en", asked_slot="branch.where")
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return prompts


async def test_an_answered_question_is_closed_and_asking_it_again_is_sent_back(
    api, business_db, monkeypatch
):
    prompts = script(monkeypatch)
    pi = await workspace(api, business_db)
    await say(pi, "I need some help please", "slot-0")
    await say(pi, "the menu taste changes every day", "slot-1")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.service_brief["last_question"]["slot"] == "branch.where"
    # the identity question is answered by now; the branch question is the open one
    assert [c["slot"] for c in conversation.service_brief["closed_slots"]] == ["business.what"]

    await say(pi, "Tipu sultan wali", "slot-2")  # the answer; pi tries to ask it again
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    closed = [c["slot"] for c in conversation.service_brief["closed_slots"]]
    assert closed == ["business.what", "branch.where"]
    reply = (await pi.reply_to("slot-2")).body
    assert "branch" not in reply.lower()  # the repeat was rewritten
    assert any("already asked" in p for p in prompts if not p.startswith("{"))

    await say(pi, "since March", "slot-3")
    last_context = json.loads([p for p in prompts if p.startswith("{")][-1])
    assert "branch.where" in [c["slot"] for c in last_context["closed_slots"]]  # the model is told
    await pi.close()
