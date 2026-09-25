import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.exceptions import error_response

router = APIRouter(prefix="/health", tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/live", response_model=Health)
async def live() -> Health:
    return Health(status="ok")


@router.get(
    "/ready", response_model=Health, responses={503: {"description": "Dependencies unavailable"}}
)
async def ready(request: Request) -> Health | JSONResponse:
    try:
        async with asyncio.timeout(request.app.state.settings.dependency_timeout_seconds):
            async with request.app.state.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            # Inline mode is explicitly for local development without Redis.
            # Production validation requires ARQ, whose readiness requires Redis.
            if request.app.state.settings.job_queue_mode == "arq":
                await request.app.state.redis.ping()
    except Exception:
        return error_response(request, 503, "DEPENDENCY_UNAVAILABLE", "Service is not ready")
    return Health(status="ok")
