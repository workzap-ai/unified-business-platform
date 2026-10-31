"""BL-04: a failed permission check leaves one throttled "denied" audit event.

Row scope is the workspace of the caller; details hold the route template and the missing
permission only. A failing audit write never changes the 403.
"""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.audit import denials
from app.modules.audit.models import AuditEvent
from tests.support.workspace import add_member, error_code

pytestmark = pytest.mark.integration

MARKER = "BODY-MARKER-7d2e91"


@pytest.fixture(autouse=True)
def _fresh_throttle():
    denials._seen.clear()
    denials._tenant_counts.clear()
    yield
    denials._seen.clear()
    denials._tenant_counts.clear()


@pytest.fixture
def audited(stack):
    """Route the handler's own session onto the test connection (savepoint, rolled back)."""
    stack.app.state.sessions = async_sessionmaker(
        bind=stack.app.state.test_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    return stack


async def denied_rows(stack, tenant_id: str) -> list[AuditEvent]:
    async with AsyncSession(
        bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
    ) as session:
        rows = await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == UUID(tenant_id), AuditEvent.outcome == "denied")
            .where(AuditEvent.action == "access.denied")
        )
        return list(rows)


async def member_of(stack, owner, browser, role: str = "viewer"):
    email = await add_member(owner, [role])
    return await stack.login(browser, email)


async def test_denied_write_is_audited_with_scope(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        response = await member.post("customers", {"name": MARKER})
        assert response.status_code == 403
        rows = await denied_rows(stack, owner.tenant_id)
    assert len(rows) == 1
    row = rows[0]
    assert str(row.tenant_id) == owner.tenant_id
    assert str(row.environment_id) == owner.environment_id
    assert str(row.actor_user_id) == member.session["user"]["id"]
    assert row.details["permission"] == "customers.write"
    assert row.details["method"] == "POST"
    assert row.details["route"].endswith("/customers")
    assert MARKER not in str(row.details)


async def test_repeats_are_throttled(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        for _ in range(10):
            assert (await member.post("customers", {"name": "x"})).status_code == 403
        rows = await denied_rows(stack, owner.tenant_id)
    assert len(rows) == 1


async def test_success_and_unauthenticated_write_nothing(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as anon:
        owner = await stack.register(ob)
        await owner.create("customers", {"name": "Fine"})
        response = await anon.post("/api/v1/customers", json={"name": "x"})
        assert response.status_code in (401, 403)
        rows = await denied_rows(stack, owner.tenant_id)
    assert rows == []


async def test_denials_are_isolated_per_tenant(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb, stack.browser() as b2:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        other = await stack.register(b2)
        assert (await member.post("customers", {"name": "x"})).status_code == 403
        mine = await denied_rows(stack, owner.tenant_id)
        theirs = await denied_rows(stack, other.tenant_id)
        listed = (await other.get("audit/events", params={"outcome": "denied"})).json()
    assert len(mine) == 1
    assert theirs == []
    assert all(e["action"] != "access.denied" for e in listed["items"])


async def test_failed_audit_write_keeps_the_403(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)

        def broken():
            raise RuntimeError("audit store down")

        stack.app.state.sessions = broken
        response = await member.post("customers", {"name": "x"})
        assert response.status_code == 403
        assert error_code(response) == "FORBIDDEN"


def test_tenant_cap_bounds_a_flood():
    tenant = UUID(int=1)
    allowed = sum(
        denials._allow(tenant, (tenant, None, f"p{i}", "POST", "/r"), 100.0) for i in range(500)
    )
    assert allowed == denials.PER_TENANT_PER_WINDOW
    assert denials._allow(tenant, (tenant, None, "late", "POST", "/r"), 161.0)
