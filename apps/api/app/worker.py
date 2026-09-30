import logging
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
from app.modules.pi.followups import sweep_followups
from app.modules.pi.knowledge_jobs import index_document, sweep_knowledge
from app.modules.pi.runtime import process_pi_event, send_pi_message, sweep_pi
from app.modules.pi.semantic import embed_document
from app.modules.pi_saas.calendar_sync import JOBS as PI_CALENDAR_JOBS
from app.modules.pi_saas.calendar_sync import sweep_pi_calendar
from app.modules.pi_saas.campaigns import sweep_campaigns
from app.modules.pi_saas.digests import sweep_digests
from app.modules.pi_saas.jobs import JOBS as PI_SAAS_JOBS
from app.modules.pi_saas.jobs import sweep_pi_saas


async def health_probe(ctx: dict[str, Any]) -> str:
    """Side-effect-free job for deployment smoke checks; never tenant business work."""
    return "ok"


JOB_FUNCTIONS: dict[str, Callable[..., Awaitable[Any]]] = {
    "health_probe": health_probe,
    "process_pi_event": process_pi_event,
    "sweep_pi_campaigns": sweep_campaigns,
    "sweep_pi_digests": sweep_digests,
    "send_pi_message": send_pi_message,
    "sweep_pi": sweep_pi,
    "sweep_followups": sweep_followups,
    "embed_document": embed_document,
    "index_document": index_document,
    "sweep_knowledge": sweep_knowledge,
    # Integration platform: inbound events, outbox dispatch, deliveries, sync, sweep.
    **INTEGRATION_JOBS,
    # Pi SaaS: provider/billing webhooks and lifecycle sweep.
    **PI_SAAS_JOBS,
    # Booking -> Google Calendar event sync (after commit, idempotent).
    **PI_CALENDAR_JOBS,
}


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["engine"] = create_engine(settings)
    ctx["sessions"] = async_sessionmaker(ctx["engine"], expire_on_commit=False)
    ctx["http"] = httpx.AsyncClient(timeout=15, follow_redirects=False)
    await on_job_start(ctx, force=True)


async def on_job_start(ctx: dict[str, Any], *, force: bool = False) -> None:
    """Keep operator-saved platform keys current (checked at most every 15 seconds)."""
    from app.modules.pi_saas import platform_config

    try:
        async with ctx["sessions"]() as session:
            if force:
                await platform_config.apply(session, ctx["settings"])
            else:
                await platform_config.refresh(session, ctx["settings"])
    except Exception:  # noqa: BLE001 - .env values keep working
        logging.getLogger("platform").warning("platform_config_load_failed")


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["http"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = list(JOB_FUNCTIONS.values())
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    cron_jobs = [
        cron(sweep_pi, second={0, 30}, unique=True),
        cron(sweep_followups, minute=set(range(0, 60, 5)), second=10, unique=True),
        cron(sweep_knowledge, second={20, 50}, unique=True),
        cron(integrations_sweep, second={15}, unique=True),
        cron(sweep_pi_saas, second={40}, unique=True),
        cron(sweep_pi_calendar, second={5, 35}, unique=True),
        cron(sweep_campaigns, second={25, 55}, unique=True),
        cron(sweep_digests, minute={7, 37}, second=45, unique=True),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url.get_secret_value())
    queue_name = get_settings().job_queue_name
    max_jobs = 10
    job_timeout = 180
    max_tries = 3
    keep_result = 60
    health_check_interval = 15
