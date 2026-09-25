"""UsageTracker/SqlUsageStore against real PostgreSQL (per-test rollback)."""

import os
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.errors import UsageLimitExceeded
from app.ai.health import ProviderHealth
from app.ai.manager import LLMManager
from app.ai.models import AIUsageEvent
from app.ai.types import Message
from app.ai.usage import SqlUsageStore
from app.modules.environments.models import Environment
from app.modules.tenants.models import Tenant
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessions():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    parsed = make_url(url)
    assert parsed.drivername == "postgresql+asyncpg" and (parsed.database or "").endswith("_test")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            tx = await connection.begin()
            # Store commits become savepoint releases; the outer rollback cleans up.
            yield async_sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            await tx.rollback()
    finally:
        await engine.dispose()


async def workspace(sessions: async_sessionmaker[AsyncSession]) -> WorkspaceScope:
    async with sessions() as session:
        suffix = uuid4().hex[:8]
        tenant = Tenant(name=f"AI tenant {suffix}", slug=f"ai-tenant-{suffix}")
        session.add(tenant)
        await session.flush()
        environment = Environment(
            tenant_id=tenant.id, key="production", name="Production", kind="production"
        )
        session.add(environment)
        await session.commit()
        return WorkspaceScope.system(tenant.id, environment.id, frozenset(), "ai-test")


async def test_usage_rows_are_persisted_per_attempt_and_budget_reads_them(settings, sessions):
    settings.openai_api_key = SecretStr("sk-openai-test")
    settings.gemini_api_key = SecretStr("gemini-test")
    settings.openai_models = {"agent": "oa-model"}
    settings.gemini_models = {"agent": "gm-model"}
    settings.llm_max_retries = 0
    settings.ai_model_prices = {"gemini:gm-model": {"input": Decimal("1"), "output": Decimal("2")}}
    scope = await workspace(sessions)

    def handler(request):
        if request.url.host == "api.openai.com":
            return httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Hi"}]}}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
            },
        )

    manager = LLMManager(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        usage=SqlUsageStore(sessions),
        health=ProviderHealth(5, 30),
    )
    run_id = uuid4()
    await manager.complete(
        scope, alias="agent", purpose="routing", messages=[Message.user("Hi")], run_id=run_id
    )
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(AIUsageEvent)
                .where(AIUsageEvent.tenant_id == scope.tenant_id)
                .order_by(AIUsageEvent.attempt)
            )
        ).all()
    assert [(r.provider, r.model, r.status, r.fallback, r.attempt, r.error_kind) for r in rows] == [
        ("openai", "oa-model", "failed", False, 1, "quota"),
        ("gemini", "gm-model", "success", True, 2, None),
    ]
    assert all(r.environment_id == scope.environment_id for r in rows)
    assert all((r.alias, r.purpose, r.run_id) == ("agent", "routing", run_id) for r in rows)
    assert (rows[1].input_tokens, rows[1].output_tokens) == (100, 50)
    assert rows[1].estimated_cost == Decimal("0.000200")

    settings.ai_tenant_daily_token_limit = 150
    with pytest.raises(UsageLimitExceeded):
        await manager.complete(
            scope, alias="agent", purpose="routing", messages=[Message.user("x")]
        )
    totals = await SqlUsageStore(sessions).totals_since(
        scope.tenant_id, rows[0].created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    assert totals.tokens == 150 and totals.cost == Decimal("0.000200")
