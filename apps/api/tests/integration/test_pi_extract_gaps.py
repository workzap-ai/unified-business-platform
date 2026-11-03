"""B6 root cause 3 in a real turn: what the owner said about when, how much, how many and how often
reaches the problem record, so the noted problem is not listed as missing it."""

import json
from types import SimpleNamespace

import pytest
from test_pi_brain_problems import OPENING, say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import problems
from app.modules.pi.problem_extract import Extracted, SimpleNote

pytestmark = pytest.mark.integration

HELLO = "hello"
SAID = (
    "Cash does not match at day end since March, it costs us 4,000 rupees a day, every day, "
    "in 2 of our 4 shops."
)
NOTE = SimpleNote(
    title="Cash does not match at day end",
    title_local="Cash does not match at day end",
    user_words=[SAID],
    summary="Cash does not match at day end",
    category="cash_collections",
    where=["2 of our 4 shops"],
    frequency="daily",
    since_text="since March",
    money_text="4,000 rupees a day",
    of_total="2 of 4 shops",
    frequency_text="every day",
    impact_types=["lost_money"],
)


async def test_the_noted_problem_is_not_missing_what_the_owner_said(api, business_db, monkeypatch):
    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(
                value=Extracted(found=[NOTE]), response=SimpleNamespace(attempts=[])
            )
        text = kwargs["messages"][-1].text()
        if json.loads(text).get("latest_customer_message") == HELLO:
            value = turn(reply=f"{OPENING} What is your business called?", language="en")
        else:
            value = turn(
                reply="Cash not matching at day end is costly. Which shops does it happen in?",
                language="en",
            )
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    pi = await workspace(api, business_db)
    await say(pi, HELLO, "g-0")
    await say(pi, SAID, "g-1")
    conversation = await pi.conversation()
    noted = await problems.noted_context(business_db, pi.scope(), conversation.customer_id)
    assert [p["missing"] for p in noted] == [[]]
    await pi.close()
