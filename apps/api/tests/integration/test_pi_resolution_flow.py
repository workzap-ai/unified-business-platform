"""PS-5 in a real chat: the owner answers the one question about what could not be checked; the
answer is stored as their own limit through the ordinary problem ops (no model is asked)."""

import dataclasses

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import unknown_resolution as ur
from app.modules.pi.models import PiConversation

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."


def pending():
    q = ur.Question(
        key="budget_ceiling",
        fact="budget ceiling",
        field="budget",
        text="What is the most you can spend on this, in one figure?",
        language="en",
        why=("x",),
        options=(0,),
        option_texts=("Buy a new tracking system for orders.",),
        problems=(),
        codes=(),
    )
    return dataclasses.asdict(q)


async def test_the_answer_is_stored_as_the_owners_budget(api, business_db, monkeypatch):
    def make(context, n):
        if n == 1:
            return turn(
                reply=f"{OPENING} Noted: late orders. What else is going wrong?",
                language="en",
                problem_ops=[
                    create(
                        "Late orders upset customers",
                        "our orders are late and customers are upset",
                        category="orders_fulfilment",
                        confidence=0.9,
                    )
                ],
            )
        return turn(reply="Thanks. Anything else getting in the way?", language="en")

    adaptive(monkeypatch, make)
    pi = await workspace(api, business_db)
    await say(pi, "our orders are late and customers are upset", "r-1")
    conversation, _rows = await problems_of(business_db, pi)
    row = await business_db.get(PiConversation, conversation.id)
    row.service_brief = {**(row.service_brief or {}), "pending_question": pending()}
    await business_db.flush()
    await say(pi, "my budget is 50,000 rupees a month", "r-2")
    conversation, rows = await problems_of(business_db, pi)
    await business_db.refresh(rows[0], ["constraints"])
    assert "budget" in (rows[0].constraints or {})
    assert "50" in str((rows[0].constraints or {})["budget"]["text"])
    row = await business_db.get(PiConversation, conversation.id)
    await business_db.refresh(row)
    assert "pending_question" not in (row.service_brief or {})  # one question at a time
    assert select  # imported for parity with the other integration tests
