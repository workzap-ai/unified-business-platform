"""Background job dispatch. ARQ is the only queue framework (ADR 0003).

`inline` mode runs the *same* registered job functions in-process for development and
tests where Redis/ARQ is unavailable. Settings validation forbids it in production.
Jobs must be idempotent: ARQ may run a job again after an interrupted attempt, and the
stale-event sweeper re-enqueues receipts whose enqueue failed.
"""

import asyncio
import logging
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings

logger = logging.getLogger("platform")


class JobQueue(Protocol):
    async def enqueue(self, name: str, *args: str, job_id: str | None = None) -> bool: ...

    async def close(self) -> None: ...


class ArqQueue:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pool: Any = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            self._pool = await create_pool(
                RedisSettings.from_dsn(self.settings.redis_url.get_secret_value()),
                default_queue_name=self.settings.job_queue_name,
            )
        return self._pool

    async def enqueue(self, name: str, *args: str, job_id: str | None = None) -> bool:
        """Returns False when the queue is unreachable; callers keep durable state."""
        try:
            pool = await self._get_pool()
            await pool.enqueue_job(name, *args, _job_id=job_id)
            return True
        except Exception:
            logger.warning("job_enqueue_failed")
            return False

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()


class InlineQueue:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        http: httpx.AsyncClient,
    ) -> None:
        self.ctx: dict[str, Any] = {"settings": settings, "sessions": sessions, "http": http}
        self.tasks: set[asyncio.Task[Any]] = set()
        self.seen: set[str] = set()

    async def enqueue(self, name: str, *args: str, job_id: str | None = None) -> bool:
        from app.worker import JOB_FUNCTIONS

        if job_id is not None:
            if job_id in self.seen:
                return True
            self.seen.add(job_id)
        function = JOB_FUNCTIONS[name]

        async def run() -> None:
            try:
                await function(self.ctx, *args)
            except Exception:
                logger.error("inline_job_failed")

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return True

    async def drain(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def close(self) -> None:
        await self.drain()


def create_queue(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
) -> JobQueue:
    if settings.job_queue_mode == "inline":
        return InlineQueue(settings, sessions, http)
    return ArqQueue(settings)
