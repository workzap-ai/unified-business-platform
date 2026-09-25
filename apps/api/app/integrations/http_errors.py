"""Render integration errors with the standard envelope (installed by app.main).

Messages on IntegrationError are safe by construction (no provider bodies or secrets).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import error_response
from app.integrations.errors import IntegrationError, OutboundUrlRejected

STATUS_BY_KIND = {
    "configuration": 503,
    "rate_limited": 429,
    "retryable": 503,
    "ambiguous": 504,
    "auth": 502,
    "invalid_response": 502,
    "permanent": 422,
}


async def integration_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IntegrationError)
    if isinstance(exc, OutboundUrlRejected):
        return error_response(request, 422, exc.code, exc.message)
    return error_response(request, STATUS_BY_KIND.get(exc.kind, 502), exc.code, exc.message)


def install_integration_handlers(app: FastAPI) -> None:
    app.add_exception_handler(IntegrationError, integration_error)
