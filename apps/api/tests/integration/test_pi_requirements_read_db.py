"""L2-1 on the disposable database: read_requirements reads the four B2a columns explicitly, is
scoped by tenant AND environment, and on a database without the 0053 columns returns empty
requirements and leaves the transaction usable. The column drop runs inside a savepoint that is
rolled back, so the shared disposable database is left as it was."""

import pytest
from sqlalchemy import select, text
from test_pi_isolation_core import problem, two_chats
from test_pi_problem_requirements_db import NEW, at_0053, present, run

from app.modules.pi.problem_models import PiProblem
from app.modules.pi.requirements_read import read_requirements

pytestmark = pytest.mark.integration

CONSTRAINTS = {
    "budget": {"text": "Rs 20000", "msg": "m1"},
    "cannot_change": [{"text": "our POS system"}],
}
TRIED = [{"what": "reminder calls", "outcome": "didn't work"}]
CAUSE = {"text": "nobody owns follow-up", "status": "owner_said", "evidence": {"words": ["owns"]}}


async def seed(db, scope, customer_id):
    rich = problem(scope, customer_id, 1, "Orders get lost")
    rich.constraints, rich.tried, rich.cause = CONSTRAINTS, TRIED, CAUSE
    rich.expected_outcome = "no lost orders"
    bare = problem(scope, customer_id, 2, "Stock runs out")
    merged = problem(scope, customer_id, 3, "Merged away")
    merged.status = "merged"
    merged.constraints = {"budget": {"text": "Rs 1"}}
    db.add_all([merged, bare, rich])  # inserted out of number order on purpose
    await db.flush()
    return rich, bare


async def test_the_four_columns_are_read_back_for_a_customer_and_for_a_conversation(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    rich, bare = await seed(db, w.scope_a, w.cust_a)
    rich_id, bare_id, conv_a_id = rich.id, bare.id, w.conv_a.id  # read before the expiry below
    db.expire_all()  # nothing of the seeded values may come from the identity map
    result = await read_requirements(db, w.scope_a, customer_id=w.cust_a)
    assert result.columns_available
    assert [(p.number, p.title) for p in result.problems] == [
        (1, "Orders get lost"),
        (2, "Stock runs out"),
    ]  # the merged problem is not active
    first, second = result.problems
    assert first.problem_id == rich_id
    assert first.constraints.budget.text == "Rs 20000" and first.constraints.budget.msg == "m1"
    assert [c.text for c in first.constraints.cannot_change] == ["our POS system"]
    assert [(t.what, t.outcome) for t in first.tried] == [("reminder calls", "didn't work")]
    assert first.cause.owner_said and first.cause.evidence_words == ("owns",)
    assert first.expected_outcome == "no lost orders"
    assert second.empty and second.problem_id == bare_id  # an old row reads as "not said"
    by_conversation = await read_requirements(db, w.scope_a, conversation_id=conv_a_id)
    assert by_conversation == result
    # the deferred columns of the ORM objects were never loaded by the reader
    from sqlalchemy import inspect

    fresh = await db.scalar(select(PiProblem).where(PiProblem.id == rich_id))
    assert set(NEW) <= set(inspect(fresh).unloaded)
    await w.a.close()
    await w.b.close()


async def test_two_workspaces_never_read_each_others_requirements(api, business_db, monkeypatch):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)  # the same phone is a customer of both
    await seed(db, w.scope_a, w.cust_a)
    other = problem(w.scope_b, w.cust_b, 1, "B's own problem")
    other.constraints = {"budget": {"text": "Rs 99"}}
    db.add(other)
    await db.flush()
    conv_a_id, conv_b_id = w.conv_a.id, w.conv_b.id  # read before the expiry below
    db.expire_all()
    own = await read_requirements(db, w.scope_a, customer_id=w.cust_a)
    assert [p.title for p in own.problems] == ["Orders get lost", "Stock runs out"]
    # B asking for A's customer, or A's conversation, finds nothing at all
    assert (await read_requirements(db, w.scope_b, customer_id=w.cust_a)).problems == ()
    assert (await read_requirements(db, w.scope_b, conversation_id=conv_a_id)).problems == ()
    assert (
        await read_requirements(db, w.scope_b, customer_id=w.cust_a, conversation_id=conv_b_id)
    ).problems == ()
    # and B's own read holds only B's row
    theirs = await read_requirements(db, w.scope_b, customer_id=w.cust_b)
    assert [p.title for p in theirs.problems] == ["B's own problem"]
    assert theirs.budgets[0].text == "Rs 99"
    # a right customer under the right tenant but another environment is a different workspace
    from dataclasses import replace
    from uuid import uuid4

    elsewhere = replace(w.scope_a, environment_id=uuid4())
    assert (await read_requirements(db, elsewhere, customer_id=w.cust_a)).problems == ()
    await w.a.close()
    await w.b.close()


async def test_a_database_without_the_0053_columns_gives_empty_requirements_and_stays_usable(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    await seed(db, w.scope_a, w.cust_a)
    conv_a_id = w.conv_a.id
    savepoint = await db.begin_nested()
    try:
        await run(db, "downgrade")  # 0053 off, inside a savepoint that is rolled back below
        assert not set(NEW) & await present(db)
        result = await read_requirements(db, w.scope_a, customer_id=w.cust_a)
        assert result.problems == () and result.columns_available is False
        # the failed select did not poison the transaction: ordinary work still runs
        assert await db.scalar(text("SELECT count(*) FROM pi_problems")) == 3
        again = await read_requirements(db, w.scope_a, conversation_id=conv_a_id)
        assert again.columns_available is False
    finally:
        await savepoint.rollback()
    assert set(NEW) <= await present(db)  # the columns are back
    db.expire_all()
    restored = await read_requirements(db, w.scope_a, customer_id=w.cust_a)
    assert restored.columns_available and len(restored.problems) == 2
    assert restored.problems[0].constraints.budget.text == "Rs 20000"
    await w.a.close()
    await w.b.close()
