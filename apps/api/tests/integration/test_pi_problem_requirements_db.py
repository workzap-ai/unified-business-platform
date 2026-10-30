"""B2a on the disposable database: migration 0053 up, down, up; persistence of the new problem
fields; old rows; revisions; two workspaces; erase. The migration runs inside the test's
rolled-back transaction, so the shared disposable database is left as it was."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from test_pi_isolation_core import problem, two_chats

from app.modules.pi import brain_erase
from app.modules.pi.problem_models import PiProblemRevision
from app.modules.pi.problems import ProblemBook, ProblemNote

pytestmark = pytest.mark.integration

NEW = ("constraints", "tried", "cause", "expected_outcome")
PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0053_pi_problem_requirements.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location("m0053_db", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def present(db):
    rows = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'pi_problems' AND table_schema = current_schema()"
        )
    )
    return {r[0] for r in rows}


async def run(db, which):
    migration = load_migration()

    def go(sync_connection):
        with Operations.context(MigrationContext.configure(sync_connection)):
            getattr(migration, which)()

    await (await db.connection()).run_sync(go)


async def at_0053(db):
    if not set(NEW) <= await present(db):
        await run(db, "upgrade")


async def book(db, scope, customer_id):
    return ProblemBook(db, scope, customer_id, "en")


async def test_the_migration_goes_up_down_and_up_without_touching_old_rows(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0053(db)  # the ORM selects the new columns, so the schema is made current first
    w = await two_chats(api, db, monkeypatch)
    old = problem(w.scope_a, w.cust_a, 1, "Old row before 0053")
    old.summary = "kept across the round trip"
    db.add(old)
    await db.flush()
    await run(db, "downgrade")  # back to 0052 with the row in place
    assert not set(NEW) & await present(db)
    count = "SELECT count(*) FROM pi_problems WHERE title = 'Old row before 0053'"
    assert await db.scalar(text(count)) == 1  # the row and its other columns are kept
    await run(db, "upgrade")
    assert set(NEW) <= await present(db)
    row = (
        await db.execute(
            text(
                "SELECT constraints, tried, cause, expected_outcome, summary FROM pi_problems "
                "WHERE title = 'Old row before 0053'"
            )
        )
    ).one()
    # a row that predates the columns reads as empty: no backfill, nothing else touched
    assert tuple(row) == (None, None, None, None, "kept across the round trip")
    await w.a.close()
    await w.b.close()


async def test_fields_persist_old_value_goes_to_history_and_old_rows_still_update(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    old = problem(w.scope_a, w.cust_a, 1, "Old row")
    db.add(old)
    await db.flush()
    b = await book(db, w.scope_a, w.cust_a)
    # an old row (all four NULL) takes a note with none of the new fields: behaviour unchanged
    assert await b.update(old, ProblemNote(trigger="at closing"), "enrichment", None) is True
    await db.refresh(old)
    assert old.constraints is None and old.tried is None and old.cause is None
    note = ProblemNote(
        budget="ready, about 5 lakh",
        cannot_change=["keep the current POS"],
        tried=[{"what": "WhatsApp group", "outcome": "orders got lost"}],
        cause_text="no stock count at closing",
        cause_said=True,
        cause_words=["we never count at night"],
        expected_outcome="orders never lost",
    )
    assert await b.update(old, note, "enrichment", None) is True
    await db.refresh(old)
    assert old.constraints["budget"]["text"] == "ready, about 5 lakh"
    assert old.tried[0]["outcome"] == "orders got lost"
    assert old.cause["status"] == "owner_said" and old.expected_outcome == "orders never lost"
    assert old.person_believes_cause == "no stock count at closing"
    # a correction: the old value is kept in the revision diff before the overwrite
    fix = ProblemNote(budget="about 3 lakh", expected_outcome="one list for the team")
    assert await b.update(old, fix, "correction", None) is True
    await db.refresh(old)
    assert old.constraints["budget"]["text"] == "about 3 lakh"
    last = (
        await db.scalars(
            select(PiProblemRevision)
            .where(PiProblemRevision.problem_id == old.id)
            .order_by(PiProblemRevision.revision.desc())
        )
    ).first()
    before, after = last.diff["constraints"]
    assert before["budget"]["text"] == "ready, about 5 lakh"
    assert after["budget"]["text"] == "about 3 lakh"
    assert last.diff["expected_outcome"][0] == "orders never lost"
    # a guess does not touch the owner's cause; confirm_cause confirms only an owner_said cause
    await b.update(old, ProblemNote(cause_text="bad suppliers"), "enrichment", None)
    await db.refresh(old)
    assert old.cause["text"] == "no stock count at closing"
    assert await b.confirm_cause(old) is True and old.cause["status"] == "confirmed"
    assert await b.confirm_cause(old) is False
    created, is_new = await b.create(
        ProblemNote(
            title="Orders get lost",
            category="stock_inventory",
            cause_text="staff are careless",
            deadline="before Eid",
        ),
        None,
        None,
    )
    assert is_new and created.cause["status"] == "pi_inferred"
    assert await b.confirm_cause(created) is False  # a guess is never confirmed
    assert created.person_believes_cause == ""
    assert created.constraints["deadline"]["text"] == "before Eid"
    await w.a.close()
    await w.b.close()


async def test_two_workspaces_never_see_each_others_new_fields(api, business_db, monkeypatch):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    a_row = problem(w.scope_a, w.cust_a, 1, "A problem")
    a_row.constraints = {"budget": {"text": "SECRET-A-BUDGET"}}
    a_row.cause = {"text": "SECRET-A-CAUSE", "status": "owner_said", "evidence": {}}
    b_row = problem(w.scope_b, w.cust_b, 1, "B problem")
    db.add_all([a_row, b_row])
    await db.flush()
    own = await (await book(db, w.scope_a, w.cust_a)).active()  # control: A sees its own
    assert own[0].constraints["budget"]["text"] == "SECRET-A-BUDGET"
    for scope, customer in ((w.scope_b, w.cust_b), (w.scope_b, w.cust_a), (w.scope_a, w.cust_b)):
        rows = await (await book(db, scope, customer)).active()
        assert all(r.constraints is None and r.cause is None for r in rows)
        assert "SECRET-A" not in repr([(r.constraints, r.cause) for r in rows])
    await w.a.close()
    await w.b.close()


async def test_erasing_a_customer_removes_the_new_fields_and_only_theirs(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0053(db)
    w = await two_chats(api, db, monkeypatch)
    mine = problem(w.scope_a, w.cust_a, 1, "Mine")
    mine.constraints = {"budget": {"text": "ERASE-ME"}}
    mine.tried = [{"what": "ERASE-ME", "outcome": "x"}]
    mine.cause = {"text": "ERASE-ME", "status": "owner_said", "evidence": {"words": ["ERASE-ME"]}}
    mine.expected_outcome = "ERASE-ME"
    other = problem(w.scope_b, w.cust_b, 1, "Other workspace")
    other.expected_outcome = "KEEP-ME"
    db.add_all([mine, other])
    await db.flush()
    # a revision that carries the words, as a correction writes it
    await ProblemBook(db, w.scope_a, w.cust_a, "en")._revise(
        mine, {"expected_outcome": ["ERASE-ME", "x"]}, "correction", "person"
    )
    await brain_erase.erase_customer(db, w.scope_a, w.cust_a)
    db.expire_all()
    left = await db.scalar(
        text(
            "SELECT count(*) FROM pi_problems WHERE constraints::text LIKE '%ERASE-ME%' "
            "OR tried::text LIKE '%ERASE-ME%' OR cause::text LIKE '%ERASE-ME%' "
            "OR expected_outcome LIKE '%ERASE-ME%'"
        )
    )
    assert left == 0
    revisions = await db.scalar(
        text("SELECT count(*) FROM pi_problem_revisions WHERE diff::text LIKE '%ERASE-ME%'")
    )
    assert revisions == 0
    kept = "SELECT expected_outcome FROM pi_problems WHERE title = 'Other workspace'"
    assert await db.scalar(text(kept)) == "KEEP-ME"  # the other workspace is untouched
    await w.a.close()
    await w.b.close()
