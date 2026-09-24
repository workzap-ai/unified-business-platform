from typing import Any

from arq.connections import RedisSettings

from app.core.config import get_settings


async def health_probe(ctx: dict[str, Any]) -> str:
    """Side-effect-free job for deployment smoke checks; never tenant business work."""
    return "ok"


JOB_FUNCTIONS = {"health_probe": health_probe}


class WorkerSettings:
    functions = [health_probe]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url.get_secret_value())
    max_jobs = 10
    job_timeout = 30
    max_tries = 3
    keep_result = 60
    health_check_interval = 15
