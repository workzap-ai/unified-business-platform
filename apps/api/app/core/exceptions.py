from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.shared.errors import (
    BusinessRuleViolation,
    Conflict,
    CsrfFailed,
    OrganizationConflict,
    PermissionDenied,
    ResourceNotFound,
    Unauthenticated,
)


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": getattr(request.state, "request_id", "unavailable"),
            }
        },
    )


async def http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred")
    messages = {
        404: ("RESOURCE_NOT_FOUND", "Resource was not found"),
        405: ("METHOD_NOT_ALLOWED", "Method is not allowed"),
        403: ("FORBIDDEN", "Access denied"),
        401: ("UNAUTHORIZED", "Authentication required"),
        413: ("PAYLOAD_TOO_LARGE", "Request is too large"),
        429: ("RATE_LIMITED", "Too many requests. Please wait and try again."),
    }
    code, message = messages.get(exc.status_code, ("REQUEST_FAILED", "Request failed"))
    return error_response(request, exc.status_code, code, message)


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    # Field locations help forms; raw input and context may contain credentials, so omit them.
    fields: dict[str, str] = {}
    if isinstance(exc, RequestValidationError):
        for item in exc.errors()[:20]:
            loc = [str(p) for p in item.get("loc", ()) if p not in ("body", "query", "path")]
            if loc:
                fields.setdefault(".".join(loc)[:80], str(item.get("type", "invalid"))[:40])
    return error_response(
        request, 422, "VALIDATION_ERROR", "Request validation failed", {"fields": fields}
    )


async def resource_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(request, 404, "RESOURCE_NOT_FOUND", "Resource was not found")


async def conflict_error(request: Request, exc: Exception) -> JSONResponse:
    message = (
        exc.message if isinstance(exc, Conflict) else "The operation conflicts with existing data"
    )
    return error_response(request, 409, "RESOURCE_CONFLICT", message)


async def unauthenticated_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(request, 401, "UNAUTHORIZED", "Authentication required")


async def forbidden_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, CsrfFailed):
        return error_response(request, 403, "CSRF_FAILED", "Security check failed. Reload.")
    return error_response(request, 403, "FORBIDDEN", "Access denied")


async def business_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BusinessRuleViolation)
    return error_response(request, exc.status, exc.code, exc.message)


def install_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ResourceNotFound, resource_error)
    app.add_exception_handler(OrganizationConflict, conflict_error)
    app.add_exception_handler(Unauthenticated, unauthenticated_error)
    app.add_exception_handler(PermissionDenied, forbidden_error)
    app.add_exception_handler(BusinessRuleViolation, business_error)
