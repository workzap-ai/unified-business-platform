"""L1-3 and L1-1 on the disposable database: a model-written cause is stored as a hypothesis and
shown to the model as one; the owner's own words make owner_said; the offer gate reads only that."""

import pytest
import test_pi_brain_problems as bp
from sqlalchemy import select
from test_pi_industry_context import scripted
from test_pi_isolation_core import two_chats
from test_pi_problem_requirements_db import at_0053
from test_pi_service_conversations import turn

from app.modules.pi import box_signals, problems
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.problems import ProblemNote, ProblemOp, apply_ops

pytestmark = pytest.mark.integration


def create(**note):
    base = {"title": "Sales are down", "category": "sales_leads"}
    return ProblemOp(op="create", note=ProblemNote(**{**base, **note}))


async def run(db, w, ops, owner_text):
    await apply_ops(db, w.scope_a, w.cust_a, w.conv_a.id, None, ops, "en", owner_text=owner_text)
    return await problems.noted_context(db, w.scope_a, w.cust_a)


async def test_a_model_cause_the_owner_never_said_is_a_hypothesis(api, business_db, monkeypatch):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    noted = await run(db, w, [create(believes_cause="competitor")], "bikri kam hai")
    (row,) = noted
    assert row["cause"] == ""  # not the owner's
    assert row["cause_hypothesis"] == "competitor"
    assert row["cause_status"] == "pi_inferred"
    assert box_signals.main_cause_known({"noted_problems": noted}) is False
    await w.a.close()
    await w.b.close()


async def test_a_cause_in_the_owners_words_is_owner_said(api, business_db, monkeypatch):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    noted = await run(
        db, w, [create(believes_cause="competitor")], "mujhe lagta hai competitor ki wajah se"
    )
    (row,) = noted
    assert row["cause"] == "competitor"
    assert row["cause_status"] == "owner_said"
    assert "cause_hypothesis" not in row
    assert box_signals.main_cause_known({"noted_problems": noted}) is True
    await w.a.close()
    await w.b.close()


async def test_a_later_update_with_a_guess_does_not_replace_the_owners_cause(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    await run(db, w, [create(believes_cause="competitor")], "lagta hai competitor hai")
    ref = problems.short_ref(
        (await problems.ProblemBook(db, w.scope_a, w.cust_a, "en").active())[0].id
    )
    update = ProblemOp(op="update", ref=ref, note=ProblemNote(believes_cause="rent"))
    (row,) = await run(db, w, [update], "bikri kam hai")
    assert row["cause"] == "competitor"
    assert row["cause_status"] == "owner_said"
    await w.a.close()
    await w.b.close()


async def cause_after(api, db, monkeypatch, texts, believes):
    """L1-1 through the real turn: the model's note carries `believes`; the owner said `texts`
    (the last one is the message the note comes with, earlier ones are a burst or earlier chat)."""
    await at_0053(db)
    pi = await bp.workspace(api, db)
    ops = [bp.create("Sales are down", "sales", "sales_leads", believes_cause=believes)]
    scripted(
        monkeypatch,
        turn(
            reply="Hi, I'm pi, an AI from Workzap. Noted. Anything else?",
            language="en",
            problem_ops=ops,
        ),
    )
    for i, text in enumerate(texts):
        await bp.say(pi, text, f"l1-{i}")
    conv = await pi.conversation()
    await db.refresh(conv)
    causes = await db.scalars(
        select(PiProblem.cause).where(PiProblem.customer_id == conv.customer_id)
    )
    statuses = [(c or {}).get("status") for c in causes]
    await pi.close()
    return statuses


async def test_a_cause_the_owner_said_in_the_burst_is_owner_said_through_the_turn(
    api, business_db, monkeypatch
):
    statuses = await cause_after(
        api,
        business_db,
        monkeypatch,
        ["mera competitor sasta hai", "bikri kam ho gayi hai"],
        "competitor",
    )
    assert statuses == ["owner_said"]


async def test_a_cause_with_invented_words_stays_pi_inferred_through_the_turn(
    api, business_db, monkeypatch
):
    statuses = await cause_after(
        api, business_db, monkeypatch, ["bikri kam ho gayi hai"], "supplier delays"
    )
    assert statuses == ["pi_inferred"]


async def test_owner_text_is_the_owners_earlier_and_latest_words_only(
    api, business_db, monkeypatch
):
    from sqlalchemy import select

    from app.modules.pi import service_conversation as sc
    from app.modules.pi.models import PiMessage

    await at_0053(business_db)
    pi = await bp.workspace(api, business_db)
    scripted(
        monkeypatch, turn(reply="Hi, I'm pi, an AI from Workzap. Anything else?", language="en")
    )
    await bp.say(pi, "mera competitor sasta hai", "l1-o0")
    await bp.say(pi, "bikri kam ho gayi hai", "l1-o1")
    conv = await pi.conversation()
    last = (
        await business_db.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conv.id, PiMessage.direction == "inbound")
            .order_by(PiMessage.created_at.desc())
        )
    ).first()
    text = await sc.owner_text_for(business_db, pi.scope(), conv, last)
    assert sorted(text.splitlines()) == sorted(
        ["mera competitor sasta hai", "bikri kam ho gayi hai"]
    )
    await pi.close()


async def test_the_extractor_fields_are_saved_by_apply_ops(api, business_db, monkeypatch):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    note = ProblemNote(
        title="Sales are down",
        category="sales_leads",
        budget="50,000 rupees",
        cannot_change=["close the second shop"],
        tried=[{"what": "Facebook ads", "outcome": "brought nobody"}],
        cause_text="the competitor is cheaper",
        cause_said=True,
        cause_words=["competitor", "cheaper"],
        expected_outcome="back to last year",
    )
    await apply_ops(
        db,
        w.scope_a,
        w.cust_a,
        w.conv_a.id,
        None,
        [ProblemOp(op="create", note=note)],
        "en",
        owner_text="the competitor is cheaper and sales fell",
    )
    (row,) = await problems.noted_context(db, w.scope_a, w.cust_a)
    assert row["cause_status"] == "owner_said"
    stored = (await db.scalars(select(PiProblem).where(PiProblem.customer_id == w.cust_a))).one()
    await db.refresh(stored, ["constraints", "tried", "expected_outcome"])
    assert stored.constraints["budget"]["text"] == "50,000 rupees"
    assert stored.constraints["cannot_change"][0]["text"] == "close the second shop"
    assert stored.tried[0]["what"] == "Facebook ads"
    assert stored.expected_outcome == "back to last year"
    await w.a.close()
    await w.b.close()


async def test_understood_count_reads_the_real_noted_context(api, business_db, monkeypatch):
    from app.modules.pi import box

    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)

    async def understood(**note):
        ops = [create(**note)]
        await apply_ops(db, w.scope_a, w.cust_a, w.conv_a.id, None, ops, "en")
        noted = await problems.noted_context(db, w.scope_a, w.cust_a)
        return box.offer_facts({"noted_problems": noted}).understood_count

    assert await understood() == 0  # a title alone: nothing known
    assert await understood(title="Orders are late", since_text="since March") == 1
    await w.a.close()
    await w.b.close()
