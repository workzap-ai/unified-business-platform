import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import error_response

logger = logging.getLogger("platform")
SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class OriginCheckMiddleware:
    """Reject browser-originated unsafe requests from origins other than the web app.

    Defense in depth next to session-bound CSRF tokens. Requests without an Origin
    header (server-to-server webhooks, CLI clients) are not affected here; cookie
    authenticated mutations still require the CSRF token.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = {o.rstrip("/") for o in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            origin = Headers(scope=scope).get("origin")
            if origin and origin.rstrip("/") not in self.allowed:
                response = error_response(Request(scope), 403, "FORBIDDEN", "Access denied")
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = str(uuid4())
        candidate = headers.get("x-correlation-id", "")
        correlation_id = candidate if SAFE_ID.fullmatch(candidate) else request_id
        scope.setdefault("state", {}).update(request_id=request_id, correlation_id=correlation_id)
        started = perf_counter()
        sent = False
        status = 500

        async def send_response(message: Message) -> None:
            nonlocal sent, status
            if message["type"] == "http.response.start":
                sent = True
                status = message["status"]
                outgoing = MutableHeaders(scope=message)
                outgoing["x-request-id"] = request_id
                outgoing["x-correlation-id"] = correlation_id
                outgoing["x-content-type-options"] = "nosniff"
                outgoing["cache-control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception as exc:
            # Class name only: exception text can carry SQL, payloads or secrets.
            logger.error(
                "request_failed",
                extra={"request_id": request_id, "error_kind": type(exc).__name__},
            )
            if sent:
                raise
            response = error_response(
                Request(scope), 500, "INTERNAL_ERROR", "An unexpected error occurred"
            )
            await response(scope, receive, send_response)
        finally:
            logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "status_code": status,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
