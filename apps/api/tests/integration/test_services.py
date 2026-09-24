import os

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from arq.constants import result_key_prefix
from arq.worker import Worker
from sqlalchemy import text

from app.core.config import Settings
from app.core.database import create_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with PostgreSQL and Redis available",
    ),
]


async def test_postgres_and_queue_job():
    from app.worker import health_probe

    settings = Settings()
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url.get_secret_value()))
    from uuid import uuid4

    queue = f"test:foundation:{uuid4()}"
    worker = Worker(
        [health_probe], redis_pool=redis, queue_name=queue, burst=True, handle_signals=False
    )
    try:
        job = await redis.enqueue_job("health_probe", _queue_name=queue)
        assert job is not None
        await worker.async_run()
        assert await job.result(timeout=5) == "ok"
        await redis.delete(result_key_prefix + job.job_id)
    finally:
        await worker.close()
