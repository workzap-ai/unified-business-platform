import os

import httpx
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import get_session
from app.main import create_app


@pytest.fixture
async def business_db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL business tests")
    parsed = make_url(url)
    assert parsed.drivername == "postgresql+asyncpg" and (parsed.database or "").endswith("_test")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            tx = await connection.begin()
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                yield session
            await tx.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def api(business_db, settings):
    settings.job_queue_mode = "inline"
    app = create_app(settings)

    async def session():
        yield business_db

    app.dependency_overrides[get_session] = session
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"origin": "http://localhost:3000"},
        ) as client:
            yield client


@pytest.fixture
async def stack(settings):
    """App whose every request gets its own session on one rolled-back connection.

    Unlike `api` (one shared session), per-request sessions keep identity maps separate,
    so stale in-memory state cannot mask a scoping bug. Nothing is committed for real.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    from tests.support.workspace import Stack, disposable_database_url

    url = disposable_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    settings.job_queue_mode = "inline"
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            app = create_app(settings)

            async def per_request_session():
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_session] = per_request_session
            app.state.test_connection = connection
            async with app.router.lifespan_context(app):
                yield Stack(app)
            await outer.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def live_stack(settings):
    """App on a real connection pool with real commits, for concurrency tests.

    Data is committed to the disposable *_test database under unique tenant names.
    """
    from pydantic import SecretStr

    from tests.support.workspace import Stack, disposable_database_url

    url = disposable_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    settings.job_queue_mode = "inline"
    settings.database_url = SecretStr(url)
    settings.db_pool_size = 25
    settings.db_max_overflow = 5
    settings.dependency_timeout_seconds = 10
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        yield Stack(app)
