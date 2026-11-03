# ruff: noqa: E501  (long Roman Urdu and comment lines)
"""B6 root cause 2: a problem noted by the separate extractor is not lost when the reply is sent back
for a rewrite. Before the fix the rewrite replaced the whole turn, extractor notes included, so the
owner's facts never became a problem record and pi asked for them again."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import OPENING, say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import problems
from app.modules.pi.problem_extract import Extracted, SimpleNote
from app.modules.pi.problem_models import PiProblem

pytestmark = pytest.mark.integration

HELLO = "hello"
FACTS = "Cash does not match at day end, every day, in 2 of our 4 shops."
NOTE = SimpleNote(
    title="Cash does not match at day end",
    title_local="Cash does not match at day end",
    user_words=[FACTS],
    summary="Cash does not match at day end",
    category="cash_collections",
    where=["2 of our 4 shops"],
    frequency="daily",
)
ENGLISH = "Cash not matching at day end is costly. Which shops does it happen in?"
ROMAN = "Cash ka masla samajh aaya. Kaun si shop mein hota hai?"  # wrong language for this owner


def models(monkeypatch, first_reply, first_language):
    seen = {"extract": 0, "rewrites": 0}

    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            seen["extract"] += 1
            return SimpleNamespace(
                value=Extracted(found=[NOTE]), response=SimpleNamespace(attempts=[])
            )
        text = kwargs["messages"][-1].text()
        if text.startswith("{"):
            if json.loads(text).get("latest_customer_message") == HELLO:
                value = turn(reply=f"{OPENING} What is your business called?", language="en")
            else:
                value = turn(reply=first_reply, language=first_language)
        else:  # the rewrite request: a good reply, but no problem_ops of its own
            seen["rewrites"] += 1
            value = turn(reply=ENGLISH, language="en")
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    return seen


async def rows(db):
    return list(await db.scalars(select(PiProblem)))


async def test_the_problem_is_saved_when_the_first_reply_passes(api, business_db, monkeypatch):
    seen = models(monkeypatch, ENGLISH, "en")
    pi = await workspace(api, business_db)
    await say(pi, HELLO, "x-0")
    await say(pi, FACTS, "x-1")
    assert seen["rewrites"] == 0 and seen["extract"] == 1
    assert len(await rows(business_db)) == 1  # control: this always worked
    await pi.close()


async def test_the_problem_is_saved_even_when_the_reply_is_rewritten(api, business_db, monkeypatch):
    seen = models(monkeypatch, ROMAN, "roman_ur")
    pi = await workspace(api, business_db)
    await say(pi, HELLO, "y-0")
    await say(pi, FACTS, "y-1")
    assert seen["rewrites"] == 1 and seen["extract"] == 1
    saved = await rows(business_db)
    assert len(saved) == 1, "the extractor's note was lost in the rewrite"
    conversation = await pi.conversation()
    noted = await problems.noted_context(business_db, pi.scope(), conversation.customer_id)
    assert [p["where"] for p in noted] == [["2 of our 4 shops"]]
    await pi.close()
