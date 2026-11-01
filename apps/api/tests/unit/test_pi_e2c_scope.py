"""E2c: queries that were protected only by reachability now carry the workspace when asked to.

`learning_situation.category_of` and `industry_of` take an optional scope (anything with a
tenant_id and an environment_id: a WorkspaceScope or a row), and `brain_visual_queue.attach_board`
looks its summary message up through the workspace repository. The statements are checked, not
run: a spy session records what would be sent to the database. No database."""

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.modules.pi import brain_visual_queue, learning_situation
from app.shared.scope import WorkspaceScope

TENANT, ENVIRONMENT = uuid4(), uuid4()
OTHER_TENANT = uuid4()
PI = Path(__file__).resolve().parents[2] / "app" / "modules" / "pi"


class Spy:
    """A session that records the statements it is asked to run and answers `result`."""

    def __init__(self, result=None):
        self.statements = []
        self.result = result

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.result


def compiled(statement):
    return statement.compile(dialect=postgresql.dialect())


def scope_of(tenant=TENANT, environment=ENVIRONMENT):
    return WorkspaceScope.system(tenant, environment, frozenset(), "PI")


async def test_category_of_filters_by_workspace_when_given_one():
    spy = Spy("billing")
    got = await learning_situation.category_of(spy, uuid4(), scope=scope_of())
    assert got == "billing"
    text, params = str(compiled(spy.statements[0])), compiled(spy.statements[0]).params
    assert "pi_problems.tenant_id" in text and "pi_problems.environment_id" in text
    assert TENANT in params.values() and ENVIRONMENT in params.values()


async def test_category_of_without_a_scope_is_unchanged():
    spy = Spy(None)
    assert await learning_situation.category_of(spy, uuid4()) == ""
    text = str(compiled(spy.statements[0]))
    assert "tenant_id" not in text and "environment_id" not in text
    assert "pi_problems.conversation_id" in text


async def test_category_of_keeps_its_time_limit_with_a_scope():
    from datetime import UTC, datetime

    spy = Spy("x")
    await learning_situation.category_of(spy, uuid4(), datetime.now(UTC), scope=scope_of())
    text = str(compiled(spy.statements[0]))
    assert "pi_problems.created_at <=" in text and "pi_problems.tenant_id" in text


async def test_a_row_with_tenant_and_environment_works_as_the_scope():
    row = SimpleNamespace(tenant_id=OTHER_TENANT, environment_id=ENVIRONMENT)
    spy = Spy("x")
    await learning_situation.category_of(spy, uuid4(), scope=row)
    assert OTHER_TENANT in compiled(spy.statements[0]).params.values()


def conversation_with_customer():
    return SimpleNamespace(customer_id=uuid4(), tenant_id=TENANT, environment_id=ENVIRONMENT)


async def test_industry_of_filters_by_workspace_when_given_one():
    spy = Spy("retail")
    await learning_situation.industry_of(spy, conversation_with_customer(), scope=scope_of())
    text, params = str(compiled(spy.statements[0])), compiled(spy.statements[0]).params
    assert "customers.tenant_id" in text and "customers.environment_id" in text
    assert TENANT in params.values() and ENVIRONMENT in params.values()


async def test_industry_of_without_a_scope_is_unchanged():
    spy = Spy("retail")
    await learning_situation.industry_of(spy, conversation_with_customer())
    text = str(compiled(spy.statements[0]))
    assert "tenant_id" not in text and "environment_id" not in text


async def test_industry_of_with_no_customer_asks_nothing():
    spy = Spy("retail")
    nobody = SimpleNamespace(customer_id=None, tenant_id=TENANT, environment_id=ENVIRONMENT)
    assert await learning_situation.industry_of(spy, nobody, scope=scope_of()) == ""
    assert spy.statements == []


def calls_to(filename, names):
    tree = ast.parse((PI / filename).read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in names:
                found.append(node)
    return found


def test_both_callers_pass_the_workspace():
    for filename in ("learning_context.py", "experience_scorer.py"):
        calls = calls_to(filename, {"category_of", "industry_of"})
        assert len(calls) == 2, filename
        for call in calls:
            assert "scope" in {k.arg for k in call.keywords}, (filename, call.func.attr)


async def test_attach_board_looks_its_summary_up_inside_the_workspace():
    spy = Spy(None)
    conversation = SimpleNamespace(customer_id=uuid4(), id=uuid4())
    outbound = [str(uuid4())]
    got = await brain_visual_queue.attach_board(
        spy, scope_of(), SimpleNamespace(), conversation, outbound, "en"
    )
    assert got == outbound  # nothing found, nothing added
    statement = compiled(spy.statements[0])
    assert "pi_messages.tenant_id" in str(statement)
    assert "pi_messages.environment_id" in str(statement)
    assert TENANT in statement.params.values() and ENVIRONMENT in statement.params.values()
