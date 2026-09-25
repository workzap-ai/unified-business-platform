from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.database import create_engine
from app.integrations.jobs import JOBS as INTEGRATION_JOBS
from app.integrations.jobs import integrations_sweep
from app.modules.pi.runtime import process_pi_event, send_pi_message, sweep_pi
from app.modules.pi.semantic import embed_document


async def health_probe(ctx: dict[str, Any]) -> str:
    """Side-effect-free job for deployment smoke checks; never tenant business work."""
    return "ok"


JOB_FUNCTIONS: dict[str, Callable[..., Awaitable[Any]]] = {
    "health_probe": health_probe,
    "process_pi_event": process_pi_event,
    "send_pi_message": send_pi_message,
    "sweep_pi": sweep_pi,
    "embed_document": embed_document,
    # Integration platform: inbound events, outbox dispatch, deliveries, sync, sweep.
    **INTEGRATION_JOBS,
}


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["engine"] = create_engine(settings)
    ctx["sessions"] = async_sessionmaker(ctx["engine"], expire_on_commit=False)
    ctx["http"] = httpx.AsyncClient(timeout=15, follow_redirects=False)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = list(JOB_FUNCTIONS.values())
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = [
        cron(sweep_pi, second={0, 30}, unique=True),
        cron(integrations_sweep, second={15}, unique=True),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url.get_secret_value())
    queue_name = get_settings().job_queue_name
    max_jobs = 10
    job_timeout = 180
    max_tries = 3
    keep_result = 60
    health_check_interval = 15
