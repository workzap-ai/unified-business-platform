"""BL-04: a failed permission check leaves one throttled "denied" audit event.

Row scope is the workspace of the caller; details hold the route template and the missing
permission only. A failing, slow or saturated audit write never changes the 403.
"""

import asyncio
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.audit import denials
from app.modules.audit.models import AuditEvent
from app.modules.memberships.models import Membership
from app.shared.errors import PermissionDenied
from tests.support.workspace import add_member, error_code

pytestmark = pytest.mark.integration

MARKER = "BODY-MARKER-7d2e91"


@pytest.fixture(autouse=True)
def _fresh_throttle():
    denials._reset()
    yield
    denials._reset()


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


def whole_row(event: AuditEvent) -> str:
    columns = (
        "actor_label",
        "actor_type",
        "action",
        "entity_type",
        "request_id",
        "details",
    )
    return " ".join(str(getattr(event, c)) for c in columns)


async def test_denied_write_is_audited_with_scope_and_no_body(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        response = await member.post(f"customers?q={MARKER}", {"name": MARKER, "note": MARKER})
        assert response.status_code == 403
        rows = await denied_rows(stack, owner.tenant_id)
    assert len(rows) == 1
    row = rows[0]
    assert str(row.tenant_id) == owner.tenant_id
    assert str(row.environment_id) == owner.environment_id
    assert str(row.actor_user_id) == member.session["user"]["id"]
    assert row.actor_type == "user"
    assert row.details == {
        "permission": "customers.write",
        "method": "POST",
        "route": row.details["route"],
    }
    assert row.details["route"].endswith("/customers")
    assert MARKER not in whole_row(row)


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


async def test_spoofed_workspace_header_is_not_audited_anywhere(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb, stack.browser() as b2:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        other = await stack.register(b2)
        response = await member.client.post(
            "/api/v1/customers",
            json={"name": "x"},
            headers={"x-workspace-tenant": other.tenant_id},
        )
        assert response.status_code == 409
        assert await denied_rows(stack, other.tenant_id) == []
        assert await denied_rows(stack, owner.tenant_id) == []


async def test_lost_membership_is_audited(audited):
    """Membership revoked while the session still points at the workspace (a race)."""
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        async with AsyncSession(
            bind=stack.app.state.test_connection, join_transaction_mode="create_savepoint"
        ) as session:
            await session.execute(
                update(Membership)
                .where(
                    Membership.tenant_id == UUID(owner.tenant_id),
                    Membership.user_id == UUID(member.session["user"]["id"]),
                )
                .values(status="revoked")
            )
            await session.commit()
        response = await member.get("customers")
        assert response.status_code == 403, response.text
        rows = await denied_rows(stack, owner.tenant_id)
    assert [r.details["permission"] for r in rows] == ["workspace.membership"]


async def test_failed_audit_write_keeps_the_403_and_is_retried(audited):
    stack = audited
    good = stack.app.state.sessions
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)

        def broken():
            raise RuntimeError("audit store down")

        stack.app.state.sessions = broken
        response = await member.post("customers", {"name": "x"})
        assert response.status_code == 403
        assert error_code(response) == "FORBIDDEN"
        assert await denied_rows(stack, owner.tenant_id) == []
        stack.app.state.sessions = good
        assert (await member.post("customers", {"name": "x"})).status_code == 403
        assert len(await denied_rows(stack, owner.tenant_id)) == 1


async def test_slow_audit_write_is_bounded(audited):
    stack = audited

    class Slow:
        async def __aenter__(self):
            await asyncio.sleep(30)

        async def __aexit__(self, *exc):
            return False

    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        stack.app.state.sessions = Slow
        started = time.monotonic()
        response = await member.post("customers", {"name": "x"})
        elapsed = time.monotonic() - started
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"
    assert elapsed < denials.WRITE_TIMEOUT_SECONDS + 1.5
    assert not denials._in_flight


async def test_saturated_writers_skip_the_audit_not_the_403(audited):
    stack = audited
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        member = await member_of(stack, owner, mb)
        for _ in range(denials.MAX_CONCURRENT_WRITES):
            denials._in_flight.add((uuid4(), (None, "p", "POST", "/r")))
        response = await member.post("customers", {"name": "x"})
        assert response.status_code == 403
        assert await denied_rows(stack, owner.tenant_id) == []


async def test_system_actor_keeps_its_type(audited):
    stack = audited
    async with stack.browser() as ob:
        owner = await stack.register(ob)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(sessions=stack.app.state.sessions)),
            scope={},
            method="POST",
        )
        await denials.audit_denial(
            request,  # type: ignore[arg-type]
            PermissionDenied(
                tenant_id=UUID(owner.tenant_id),
                environment_id=UUID(owner.environment_id),
                actor_label="nightly job",
                actor_type="system",
                missing=("customers.write",),
            ),
        )
        rows = await denied_rows(stack, owner.tenant_id)
    assert [(r.actor_type, r.actor_label) for r in rows] == [("system", "nightly job")]


def key(i: int) -> denials.Key:
    return (None, f"p{i}", "POST", "/r")


def test_tenant_cap_bounds_a_flood():
    tenant = UUID(int=1)
    written = 0
    for i in range(500):
        if denials._allow(tenant, key(i), 100.0):
            denials._mark_written(tenant, key(i), 100.0)
            written += 1
    assert written == denials.PER_TENANT_PER_WINDOW
    assert denials._allow(tenant, key(999), 161.0)


def test_one_tenants_flood_does_not_starve_another():
    flooder, other = UUID(int=1), UUID(int=2)
    for i in range(5000):
        if denials._allow(flooder, key(i), 100.0):
            denials._mark_written(flooder, key(i), 100.0)
    assert not denials._allow(flooder, key(10_000), 101.0)
    assert denials._allow(other, key(0), 101.0)
    assert len(denials._tenants[flooder].keys) <= denials.KEYS_PER_TENANT


def test_key_table_and_tenant_table_stay_bounded():
    tenant = UUID(int=7)
    for i in range(denials.KEYS_PER_TENANT * 3):
        denials._mark_written(tenant, key(i), float(i))
    assert len(denials._tenants[tenant].keys) == denials.KEYS_PER_TENANT
    for n in range(denials.MAX_TENANTS + 50):
        denials._allow(UUID(int=1000 + n), key(0), 1.0)
    assert len(denials._tenants) == denials.MAX_TENANTS


def test_email_like_actor_label_is_redacted():
    from app.modules.audit.denials import _safe_label

    assert _safe_label("jo@example.com") == "user"
    assert _safe_label("Jo Smith") == "Jo Smith"
    assert _safe_label(None) is None
