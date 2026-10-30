"""B2a on the disposable database: migration 0053 up, down, up; persistence of the new problem
fields; old rows; revisions; two workspaces; erase. The migration runs inside the test's
rolled-back transaction, so the shared disposable database is left as it was."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from test_pi_isolation_core import problem, two_chats

from app.modules.customers.models import Customer
from app.modules.pi import brain_erase, business, map_builder, problems
from app.modules.pi.problem_models import PiProblem, PiProblemRevision
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


async def load(db, row):
    """The deferred columns of a row, freshly read."""
    await db.refresh(row, list(NEW))


async def at_0052(db):
    if set(NEW) <= await present(db):
        await run(db, "downgrade")
    assert not set(NEW) & await present(db)


async def test_ordinary_reads_and_writes_work_on_a_database_without_the_0053_columns(
    api, business_db, monkeypatch
):
    """Code deployed before 0053 must not break: the new columns are deferred, so nothing selects
    them unless a note carries one of the new fields."""
    db = business_db
    await at_0052(db)
    w = await two_chats(api, db, monkeypatch)
    b = await book(db, w.scope_a, w.cust_a)
    first, new = await b.create(
        ProblemNote(title="Orders get lost", category="stock_inventory", trigger="at night"),
        None,
        None,
    )  # also _next_number
    assert new
    assert [p.id for p in await b.active()] == [first.id]
    assert list(await b.by_ref()) == [problems.short_ref(first.id)]
    assert await b.update(first, ProblemNote(workaround="a notebook"), "enrichment", None)
    assert [c["title"] for c in await problems.noted_context(db, w.scope_a, w.cust_a)] == [
        "Orders get lost"
    ]
    assert (await db.get(PiProblem, first.id)).title == "Orders get lost"
    assert map_builder.facts_of(first) is not None
    await business.link_duplicates_for_problem(db, w.scope_a, first)
    await db.refresh(first)  # a plain refresh does not select the deferred columns
    await brain_erase.erase_customer(db, w.scope_a, w.cust_a)
    assert await db.scalar(text("SELECT count(*) FROM pi_problems")) == 0
    await w.a.close()
    await w.b.close()


async def test_a_note_with_the_new_fields_needs_the_columns_and_nothing_else_does(
    api, business_db, monkeypatch
):
    db = business_db
    await at_0052(db)
    w = await two_chats(api, db, monkeypatch)
    b = await book(db, w.scope_a, w.cust_a)
    row, _ = await b.create(
        ProblemNote(title="Stock runs out", category="stock_inventory"), None, None
    )
    with pytest.raises(ProgrammingError):  # only the new-field path needs the columns
        async with db.begin_nested():
            await b.update(row, ProblemNote(budget="ready"), "enrichment", None)
    assert await b.update(row, ProblemNote(workaround="a list"), "enrichment", None)  # still fine
    await w.a.close()
    await w.b.close()


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
    await load(db, old)
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
    assert await b.update(old, note, "enrichment", None, "we never count at night") is True
    await load(db, old)
    assert old.constraints["budget"]["text"] == "ready, about 5 lakh"
    assert old.tried[0]["outcome"] == "orders got lost"
    assert old.cause["status"] == "owner_said" and old.expected_outcome == "orders never lost"
    assert old.person_believes_cause == "no stock count at closing"
    # a correction: the old value is kept in the revision diff before the overwrite
    fix = ProblemNote(budget="about 3 lakh", expected_outcome="one list for the team")
    assert await b.update(old, fix, "correction", None) is True
    await load(db, old)
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
    # the same constraint again is not a change (no revision churn)
    revision = old.revision
    assert await b.update(old, ProblemNote(budget="About 3 lakh"), "enrichment", None) is False
    assert old.revision == revision
    # the owner removes a cannot-change entry: the old list stays in the revision diff
    assert await b.update(
        old, ProblemNote(cannot_change_remove=["keep the current pos"]), "correction", None
    )
    await load(db, old)
    assert "cannot_change" not in old.constraints
    last = (
        await db.scalars(
            select(PiProblemRevision)
            .where(PiProblemRevision.problem_id == old.id)
            .order_by(PiProblemRevision.revision.desc())
        )
    ).first()
    assert last.diff["constraints"][0]["cannot_change"][0]["text"] == "keep the current POS"
    # a fabricated evidence word: the cause stays a guess
    fake = ProblemNote(cause_text="bad staff", cause_said=True, cause_words=["never said this"])
    made, _ = await b.create(
        ProblemNote(title="Staff late", category="stock_inventory"), None, None
    )
    assert await b.update(made, fake, "enrichment", None, "staff are late")
    await load(db, made)
    assert made.cause["status"] == "pi_inferred" and made.person_believes_cause == ""
    # a guess does not touch the owner's cause; confirm_cause confirms only an owner_said cause
    await b.update(old, ProblemNote(cause_text="bad suppliers"), "enrichment", None)
    await load(db, old)
    assert old.cause["text"] == "no stock count at closing"
    assert await b.confirm_cause(old) is True and old.cause["status"] == "confirmed"
    assert await b.confirm_cause(old) is False
    await load(db, old)
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
    for r in own:
        await load(db, r)
    assert own[0].constraints["budget"]["text"] == "SECRET-A-BUDGET"
    for scope, customer in ((w.scope_b, w.cust_b), (w.scope_b, w.cust_a), (w.scope_a, w.cust_b)):
        rows = await (await book(db, scope, customer)).active()
        for r in rows:
            await load(db, r)
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
    second = Customer(
        tenant_id=w.scope_a.tenant_id,
        environment_id=w.scope_a.environment_id,
        name="Second customer",
        source="manual",
    )
    db.add(second)
    await db.flush()
    mine = problem(w.scope_a, w.cust_a, 1, "Mine")
    mine.constraints = {"budget": {"text": "ERASE-ME"}}
    mine.tried = [{"what": "ERASE-ME", "outcome": "x"}]
    mine.cause = {"text": "ERASE-ME", "status": "owner_said", "evidence": {"words": ["ERASE-ME"]}}
    mine.expected_outcome = "ERASE-ME"
    same_workspace = problem(w.scope_a, second.id, 1, "Same workspace, other customer")
    same_workspace.expected_outcome = "KEEP-SAME"
    same_workspace.cause = {"text": "KEEP-SAME", "status": "pi_inferred", "evidence": {}}
    other = problem(w.scope_b, w.cust_b, 1, "Other workspace")
    other.expected_outcome = "KEEP-OTHER"
    db.add_all([mine, same_workspace, other])
    await db.flush()
    # revisions that carry the words, as a correction writes them
    await ProblemBook(db, w.scope_a, w.cust_a, "en")._revise(
        mine, {"expected_outcome": ["ERASE-ME", "x"]}, "correction", "person"
    )
    await ProblemBook(db, w.scope_a, second.id, "en")._revise(
        same_workspace, {"expected_outcome": ["KEEP-SAME", "y"]}, "correction", "person"
    )
    holds = (
        "SELECT count(*) FROM pi_problems WHERE customer_id = :c AND (constraints::text LIKE "
        "'%ERASE-ME%' OR tried::text LIKE '%ERASE-ME%' OR cause::text LIKE '%ERASE-ME%' "
        "OR expected_outcome LIKE '%ERASE-ME%')"
    )
    assert await db.scalar(text(holds), {"c": w.cust_a}) == 1  # control: the words are there
    rev = "SELECT count(*) FROM pi_problem_revisions WHERE diff::text LIKE :w"
    assert await db.scalar(text(rev), {"w": "%ERASE-ME%"}) == 1
    await brain_erase.erase_customer(db, w.scope_a, w.cust_a)
    db.expire_all()
    assert await db.scalar(text(holds), {"c": w.cust_a}) == 0  # fails if not erased
    assert (
        await db.scalar(
            text("SELECT count(*) FROM pi_problems WHERE customer_id = :c"), {"c": w.cust_a}
        )
        == 0
    )
    assert await db.scalar(text(rev), {"w": "%ERASE-ME%"}) == 0
    # the other customer of the same workspace and the other workspace keep everything
    kept = "SELECT expected_outcome FROM pi_problems WHERE title = :t"
    assert await db.scalar(text(kept), {"t": "Same workspace, other customer"}) == "KEEP-SAME"
    assert await db.scalar(text(kept), {"t": "Other workspace"}) == "KEEP-OTHER"
    assert await db.scalar(text(rev), {"w": "%KEEP-SAME%"}) == 1
    await w.a.close()
    await w.b.close()
