"""L1-3 and L1-1 on the disposable database: a model-written cause is stored as a hypothesis and
shown to the model as one; the owner's own words make owner_said; the offer gate reads only that."""

import pytest
from test_pi_isolation_core import two_chats
from test_pi_problem_requirements_db import at_0053

from app.modules.pi import box_signals, problems
from app.modules.pi.problems import ProblemNote, ProblemOp, apply_ops

pytestmark = pytest.mark.integration


def create(**note):
    base = {"title": "Sales are down", "category": "sales_leads"}
    return ProblemOp(op="create", note=ProblemNote(**base, **note))


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
