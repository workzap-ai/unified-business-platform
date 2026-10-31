"""L2-1: read_requirements with a fake session (no database). The real database is covered by
tests/integration/test_pi_requirements_read_db.py."""

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.modules.pi import requirements_read as rr
from app.shared.scope import WorkspaceScope

SCOPE = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "test")
CUSTOMER = uuid4()
SECRET_WORDS = "Ahmed Raza owns the Gulberg shop"


def row(**kw):
    base = dict(
        id=uuid4(), number=1, title="Orders get lost", constraints=None, tried=None, cause=None,
        expected_outcome=None,
    )  # fmt: skip
    base.update(kw)
    return SimpleNamespace(**base)


class Nested:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.entered += 1
        return self

    async def __aexit__(self, *exc):
        self.session.exited += 1
        return False


class FakeSession:
    def __init__(self, rows=(), error=None, owner=None):
        self.rows, self.error, self.owner = list(rows), error, owner
        self.entered = self.exited = 0
        self.statements = []

    def begin_nested(self):
        return Nested(self)

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.owner

    async def execute(self, statement):
        self.statements.append(statement)
        if self.error:
            raise self.error
        return SimpleNamespace(all=lambda: self.rows)


def pg_error(code, cls=ProgrammingError, name="UndefinedColumnError"):
    orig = type(name, (Exception,), {})("column pi_problems.constraints does not exist")
    orig.sqlstate = code
    return cls("SELECT ...", {}, orig)


async def test_the_columns_are_parsed_into_plain_dataclasses():
    stored = row(
        constraints={
            "budget": {"text": "Rs 20000", "msg": "m1"},
            "deadline": {"text": "within 2 weeks"},
            "cannot_change": [{"text": "our POS system"}, {"text": ""}, "junk"],
        },
        tried=[
            {"what": "reminder calls", "outcome": "didn't work", "msg": "m2"},
            {"what": "", "outcome": "x"},
            "junk",
        ],
        cause={"text": "no one owns follow-up", "status": "owner_said",
               "evidence": {"msgs": ["m3"], "words": ["follow", "owns"]}},
        expected_outcome="  fewer   missed orders ",
    )  # fmt: skip
    result = await rr.read_requirements(FakeSession([stored]), SCOPE, customer_id=CUSTOMER)
    assert result.columns_available and len(result.problems) == 1
    p = result.problems[0]
    assert p.problem_id == stored.id and p.number == 1 and p.title == "Orders get lost"
    assert p.constraints.budget.text == "Rs 20000" and p.constraints.budget.msg == "m1"
    assert p.constraints.deadline.text == "within 2 weeks" and p.constraints.staff is None
    assert [c.text for c in p.constraints.cannot_change] == ["our POS system"]
    assert [(t.what, t.outcome, t.msg) for t in p.tried] == [
        ("reminder calls", "didn't work", "m2")
    ]
    assert p.cause.text == "no one owns follow-up" and p.cause.owner_said
    assert p.cause.evidence_words == ("follow", "owns") and p.cause.evidence_msgs == ("m3",)
    assert p.expected_outcome == "fewer missed orders"
    assert result.cannot_change == p.constraints.cannot_change and result.tried == p.tried
    assert result.budgets == (p.constraints.budget,)


async def test_null_and_malformed_columns_read_as_not_said():
    stored = row(constraints="oops", tried={"a": 1}, cause=["x"], expected_outcome=5)
    result = await rr.read_requirements(FakeSession([stored]), SCOPE, customer_id=CUSTOMER)
    assert result.problems[0].empty and result.empty
    assert (await rr.read_requirements(FakeSession([]), SCOPE, customer_id=CUSTOMER)).problems == ()


async def test_an_inferred_cause_is_not_an_owner_statement():
    stored = row(cause={"text": "a guess", "status": "pi_inferred"})
    p = (await rr.read_requirements(FakeSession([stored]), SCOPE, customer_id=CUSTOMER)).problems[0]
    assert p.cause is not None and not p.cause.owner_said


async def test_the_select_names_the_columns_and_the_workspace_and_runs_in_a_savepoint():
    session = FakeSession([row()])
    await rr.read_requirements(session, SCOPE, customer_id=CUSTOMER)
    assert (session.entered, session.exited) == (1, 1)
    statement = session.statements[-1]
    sql = str(statement)
    for column in ("constraints", "tried", "cause", "expected_outcome"):
        assert f"pi_problems.{column}" in sql.split("FROM")[0]
    assert "pi_problems.tenant_id" in sql and "pi_problems.environment_id" in sql
    params = statement.compile().params.values()
    assert SCOPE.tenant_id in params and SCOPE.environment_id in params and CUSTOMER in params


async def test_a_conversation_is_resolved_inside_the_workspace_and_must_agree_with_the_customer():
    session = FakeSession([row()], owner=CUSTOMER)
    result = await rr.read_requirements(session, SCOPE, conversation_id=uuid4())
    assert len(result.problems) == 1
    assert "pi_conversations.tenant_id" in str(session.statements[0])
    assert "pi_conversations.environment_id" in str(session.statements[0])
    other = FakeSession([row()], owner=uuid4())
    assert (
        await rr.read_requirements(other, SCOPE, customer_id=CUSTOMER, conversation_id=uuid4())
    ).problems == ()
    missing = FakeSession([row()], owner=None)
    assert (await rr.read_requirements(missing, SCOPE, conversation_id=uuid4())).problems == ()
    assert len(missing.statements) == 1  # no problem query ran for a conversation not found


async def test_a_customer_or_a_conversation_is_required():
    with pytest.raises(ValueError):
        await rr.read_requirements(FakeSession(), SCOPE)


async def test_a_database_without_the_columns_gives_empty_requirements():
    session = FakeSession(error=pg_error("42703"))
    result = await rr.read_requirements(session, SCOPE, customer_id=CUSTOMER)
    assert result.problems == () and result.columns_available is False
    assert (session.entered, session.exited) == (1, 1)


async def test_the_asyncpg_error_class_alone_is_enough_to_recognise_the_missing_column():
    error = pg_error(None)  # no sqlstate, only the class name
    result = await rr.read_requirements(FakeSession(error=error), SCOPE, customer_id=CUSTOMER)
    assert result.columns_available is False


@pytest.mark.parametrize(
    "error",
    [pg_error("42P01", name="UndefinedTableError"),  # a missing table is not a missing column
     pg_error("42501", name="InsufficientPrivilegeError"),
     pg_error("40001", cls=OperationalError, name="SerializationError"),
     RuntimeError("boom")],
)  # fmt: skip
async def test_every_other_error_propagates(error):
    with pytest.raises(type(error)):
        await rr.read_requirements(FakeSession(error=error), SCOPE, customer_id=CUSTOMER)


async def test_logs_carry_counts_only_never_the_owners_words(caplog):
    stored = row(
        title=SECRET_WORDS,
        constraints={"budget": {"text": SECRET_WORDS}},
        tried=[{"what": SECRET_WORDS, "outcome": SECRET_WORDS}],
        cause={"text": SECRET_WORDS},
        expected_outcome=SECRET_WORDS,
    )
    with caplog.at_level(logging.DEBUG):
        await rr.read_requirements(FakeSession([stored]), SCOPE, customer_id=CUSTOMER)
        await rr.read_requirements(
            FakeSession(error=pg_error("42703")), SCOPE, customer_id=CUSTOMER
        )
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert caplog.records and "Ahmed" not in text and "Gulberg" not in text
