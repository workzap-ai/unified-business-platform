"""pi's durable memory (spec 3.10, R-MEM-01/02/04, R-PRIV-06): facts kept at customer level,
corrections with history, the block in every brain turn, a new conversation that still knows the
person, and erasure that removes all of it. Real database; the AI and WhatsApp are mocked.

NOT YET RUN when written: the shared test database was busy with a long sweep (see the
SWEEP_DONE rule). Run `pytest tests/integration/test_pi_brain_memory.py` on the disposable DB."""

import json

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.customers.models import Customer
from app.modules.pi.brain_erase import erase_customer
from app.modules.pi.models import PiConversation, PiMemory

pytestmark = pytest.mark.integration


def contexts_of(prompts):
    return [json.loads(p) for p in prompts if p.startswith("{")]


async def memories(db, customer_id, status=None):
    query = select(PiMemory).where(PiMemory.customer_id == customer_id)
    if status:
        query = query.where(PiMemory.status == status)
    return {m.content for m in await db.scalars(query)}


def said_turn(context, n):
    facts = {
        1: {"name": "Ayesha", "business_type": "bakery", "location": "Lahore"},
        2: {"location": "Karachi"},
    }.get(n, {})
    return turn(
        reply="Thanks. What else is getting in the way?", language="en", customer_profile=facts
    )


async def test_facts_are_kept_per_customer_and_a_correction_keeps_the_old_value_as_history(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, said_turn)
    pi = await workspace(api, business_db)
    await say(pi, "I run a bakery in Lahore, my name is Ayesha", "mem-1")
    customer_id = (await pi.conversation()).customer_id
    assert {"name: Ayesha", "business_type: bakery", "location: Lahore"} <= await memories(
        business_db, customer_id, "active"
    )
    await say(pi, "Actually we moved to Karachi", "mem-2")
    await say(pi, "stock runs out", "mem-3")
    active = await memories(business_db, customer_id, "active")
    assert "location: Karachi" in active and "location: Lahore" not in active
    assert "location: Lahore" in await memories(business_db, customer_id, "archived")
    last = contexts_of(prompts)[-1]
    assert last["what_i_know"]["location"] == "Karachi"
    assert len(json.dumps(last["what_i_know"], ensure_ascii=False)) <= 700
    assert next(iter(last)) == "what_i_know"  # a stable place in the prompt
    await pi.close()


async def test_a_new_conversation_after_a_closed_one_still_knows_the_person(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, said_turn)
    pi = await workspace(api, business_db)
    await say(pi, "I run a bakery in Lahore, my name is Ayesha", "mem-4")
    first = await pi.conversation()
    first.status = "closed"
    await business_db.commit()
    # a real message, not a bare greeting (a greeting gets the fixed welcome-back and no model call)
    await say(pi, "stock runs out in two shops again", "mem-5")
    conversations = list(await business_db.scalars(select(PiConversation)))
    assert len(conversations) == 2
    block = contexts_of(prompts)[-1].get("what_i_know") or {}
    assert block.get("name") == "Ayesha" and block.get("business_type") == "bakery"
    await pi.close()


async def test_erasing_a_customer_removes_every_memory_row_the_summary_and_the_industry(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, said_turn)
    pi = await workspace(api, business_db)
    await say(pi, "I run a bakery in Lahore, my name is Ayesha", "mem-6")
    await say(pi, "Actually we moved to Karachi", "mem-7")  # leaves an archived row too
    conversation = await pi.conversation()
    customer_id = conversation.customer_id
    customer = await business_db.get(Customer, customer_id)
    customer.industry_primary = "bakery"
    await business_db.commit()
    assert await memories(business_db, customer_id)
    await erase_customer(business_db, pi.scope(), customer_id)
    await business_db.commit()
    await business_db.refresh(conversation)
    await business_db.refresh(customer)
    assert not await memories(business_db, customer_id)
    assert conversation.summary == "" and conversation.service_brief == {"erased": True}
    assert customer.industry_primary is None
    await pi.close()
