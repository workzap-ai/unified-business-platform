"""Real PostgreSQL tests; all per-test data rolls back. No SQLite substitute."""

import os
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import get_session
from app.core.pagination import Pagination
from app.main import create_app
from app.models import Branch, Department, Membership, PlatformUser, Tenant
from app.modules.tenants.context import TenantScope, resolve_scope
from app.modules.tenants.dependencies import authenticated_user_id
from app.modules.tenants.errors import OrganizationConflict, ResourceNotFound
from app.modules.tenants.schemas import BranchCreate, DepartmentCreate, Rename
from app.modules.tenants.service import OrganizationService, list_tenants
from app.shared.repositories import TenantRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a migrated disposable PostgreSQL database ending _test"
        )
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or not (parsed.database or "").endswith("_test"):
        pytest.fail("Tenant tests require a disposable PostgreSQL database ending _test")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                yield session
            await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def seeded(db):
    a, b = Tenant(name="Tenant A", slug="tenant-a"), Tenant(name="Tenant B", slug="tenant-b")
    alice = PlatformUser(email="alice@example.test", display_name="Alice")
    bob = PlatformUser(email="bob@example.test", display_name="Bob")
    db.add_all([a, b, alice, bob])
    await db.flush()
    ma, mb = (
        Membership(tenant_id=a.id, user_id=alice.id),
        Membership(tenant_id=b.id, user_id=bob.id),
    )
    ba, bb = (
        Branch(tenant_id=a.id, name="A branch", code="main"),
        Branch(tenant_id=b.id, name="B branch", code="main"),
    )
    db.add_all([ma, mb, ba, bb])
    await db.flush()
    da = Department(tenant_id=a.id, branch_id=ba.id, name="A department", code="office")
    dbb = Department(tenant_id=b.id, branch_id=bb.id, name="B department", code="office")
    db.add_all([da, dbb])
    await db.flush()
    scope = await resolve_scope(db, alice.id, a.id)
    return SimpleNamespace(
        a=a, b=b, alice=alice, bob=bob, ma=ma, mb=mb, ba=ba, bb=bb, da=da, dbb=dbb, scope=scope
    )


@pytest.mark.parametrize("model,own,foreign", [(Branch, "ba", "bb"), (Department, "da", "dbb")])
async def test_read_update_delete_and_guessed_ids_are_scoped(db, seeded, model, own, foreign):
    repo = TenantRepository(db, model, seeded.scope)
    own_row, foreign_row = getattr(seeded, own), getattr(seeded, foreign)
    assert (await repo.get(own_row.id)).id == own_row.id
    rows, count = await repo.list(Pagination())
    assert count == 1 and [r.id for r in rows] == [own_row.id]
    # Foreign objects already exist in this session's identity map.
    for record_id in (foreign_row.id, uuid4()):
        with pytest.raises(ResourceNotFound):
            await repo.get(record_id)
        with pytest.raises(ResourceNotFound):
            await repo.rename(record_id, "unauthorized")
        with pytest.raises(ResourceNotFound):
            await repo.delete(record_id)
    await db.refresh(foreign_row)
    assert foreign_row.name.startswith("B ")
    renamed = await repo.rename(own_row.id, "Allowed name")
    assert renamed.name == "Allowed name"


async def test_memberships_and_tenant_listing_do_not_leak(db, seeded):
    page = await list_tenants(db, seeded.alice.id, Pagination())
    assert [t.id for t in page.items] == [seeded.a.id] and page.total == 1
    repo = TenantRepository(db, Membership, seeded.scope)
    with pytest.raises(ResourceNotFound):
        await repo.get(seeded.mb.id)
    with pytest.raises(ResourceNotFound):
        await resolve_scope(db, seeded.alice.id, seeded.b.id)
    forged = TenantScope(seeded.alice.id, seeded.b.id, seeded.mb.id)
    with pytest.raises(ResourceNotFound):
        await TenantRepository(db, Branch, forged).get(seeded.bb.id)


async def test_multi_tenant_member_still_has_one_scope_per_operation(db, seeded):
    db.add(Membership(tenant_id=seeded.b.id, user_id=seeded.alice.id))
    await db.flush()
    page = await list_tenants(db, seeded.alice.id, Pagination())
    assert {tenant.id for tenant in page.items} == {seeded.a.id, seeded.b.id}
    scope_b = await resolve_scope(db, seeded.alice.id, seeded.b.id)
    assert (await TenantRepository(db, Branch, scope_b).get(seeded.bb.id)).id == seeded.bb.id
    with pytest.raises(ResourceNotFound):
        await TenantRepository(db, Branch, seeded.scope).get(seeded.bb.id)


@pytest.mark.parametrize(
    "target,status", [("ma", "revoked"), ("alice", "inactive"), ("a", "inactive")]
)
async def test_stale_context_is_rejected_after_revocation_or_deactivation(
    db, seeded, target, status
):
    getattr(seeded, target).status = status
    await db.flush()
    service = OrganizationService(db, seeded.scope)
    with pytest.raises(ResourceNotFound):
        await service.branches.get(seeded.ba.id)
    with pytest.raises(ResourceNotFound):
        await service.rename_branch(seeded.ba.id, Rename(name="Blocked"))
    with pytest.raises(ResourceNotFound):
        await service.delete_branch(seeded.ba.id)
    with pytest.raises(ResourceNotFound):
        await service.create_branch(BranchCreate(name="Blocked", code="blocked"))
    assert (await list_tenants(db, seeded.alice.id, Pagination())).items == []


async def test_cross_tenant_branch_reference_rejected_by_service_and_database(db, seeded):
    service = OrganizationService(db, seeded.scope)
    with pytest.raises(ResourceNotFound):
        await service.create_department(
            DepartmentCreate(name="Bad", code="bad", branch_id=seeded.bb.id)
        )
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(
                Department(tenant_id=seeded.a.id, branch_id=seeded.bb.id, name="Bad", code="bad")
            )
            await db.flush()


async def test_unique_membership_and_tenant_scoped_codes(db, seeded):
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Membership(tenant_id=seeded.a.id, user_id=seeded.alice.id))
            await db.flush()
    # Both seeded tenants already use code=main; uniqueness is per tenant.
    service = OrganizationService(db, seeded.scope)
    with pytest.raises(OrganizationConflict):
        await service.create_branch(BranchCreate(name="Duplicate", code="main"))
    created = await service.create_branch(BranchCreate(name="New", code="new"))
    assert created.tenant_id == seeded.a.id


async def test_valid_department_delete_and_restrict_branch_deletion(db, seeded):
    service = OrganizationService(db, seeded.scope)
    with pytest.raises(OrganizationConflict):
        await service.delete_branch(seeded.ba.id)
    await service.departments.delete(seeded.da.id)
    await service.delete_branch(seeded.ba.id)
    with pytest.raises(ResourceNotFound):
        await service.branches.get(seeded.ba.id)
    assert await db.scalar(select(Branch.id).where(Branch.id == seeded.bb.id)) == seeded.bb.id


async def test_department_can_be_tenant_wide_and_pages_are_bounded(db, seeded):
    service = OrganizationService(db, seeded.scope)
    result = await service.create_department(DepartmentCreate(name="Shared", code="shared"))
    assert result.branch_id is None and result.tenant_id == seeded.a.id
    await service.create_branch(BranchCreate(name="Second", code="second"))
    page = await service.list_branches(Pagination(page_size=1))
    assert len(page.items) == 1 and page.total == 2
    second = await service.list_branches(Pagination(page_size=1, page=2))
    assert second.items[0].id != page.items[0].id


async def test_http_scope_uses_verified_identity_not_client_headers(db, seeded, settings):
    app = create_app(settings)

    async def session_override():
        yield db

    async def identity_override():
        return seeded.alice.id

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[authenticated_user_id] = identity_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/tenants", headers={"x-user-id": str(seeded.bob.id)})
        assert response.status_code == 200
        assert [t["id"] for t in response.json()["items"]] == [str(seeded.a.id)]
        for tenant_id in (seeded.b.id, uuid4()):
            denied = await client.get(f"/api/v1/tenants/{tenant_id}/branches")
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        own = await client.get(f"/api/v1/tenants/{seeded.a.id}/branches?page_size=1")
        assert own.status_code == 200 and own.json()["total"] == 1


async def test_database_uuid_defaults_and_normalization_constraints(db):
    user_id = await db.scalar(
        text(
            "INSERT INTO platform_users (email, display_name) "
            "VALUES ('db@example.test', 'DB') RETURNING id"
        )
    )
    assert user_id is not None
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                text(
                    "INSERT INTO platform_users (email, display_name) "
                    "VALUES ('DB@example.test', 'Bad')"
                )
            )
