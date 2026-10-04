"""Business-owned tool connections: the Pi app (/api/v1/pi-app/pi/connectors) and Owner
OS workspaces (/api/v1/pi/connectors) share one implementation; only where the OAuth
provider sends the browser back (and which page shows the result) differs.

Viewing needs `integrations.read`; connecting, testing and disconnecting need
`integrations.manage` (business owner/admin presets). OAuth callbacks are browser
redirects that arrive with the Pi session cookie; the single-use state is bound to the
same user, business and environment, and the result is shown on the Tools page.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.integrations.http import OutboundClient
from app.modules.access.dependencies import Scope, Session
from app.modules.integrations.service import Runtime
from app.modules.pi.service import require_pi
from app.modules.pi_saas import connectors
from app.shared.errors import BusinessRuleViolation

TOOLS_PAGE = "/my-pi/tools"
RESULT_PAGE = {"pi": TOOLS_PAGE, "web": "/pi/setup"}


def _runtime(request: Request) -> Runtime:
    state = request.app.state
    return Runtime(
        settings=state.settings,
        http=OutboundClient(
            state.settings, state.http, resolver=getattr(state, "integration_resolver", None)
        ),
        queue=getattr(state, "queue", None),
        redis=getattr(state, "redis", None),
    )


def _key(key: str) -> str:
    if key not in connectors.KEYS:
        raise BusinessRuleViolation("UNKNOWN_CONNECTOR", "This tool can't be connected", 404)
    return key


class ShopifyStart(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    shop: str = Field(min_length=3, max_length=200)


def build(app: Literal["pi", "web"]) -> APIRouter:
    router = APIRouter(prefix="/pi/connectors", tags=["pi-connectors"])
    page = RESULT_PAGE[app]

    @router.get("")
    async def list_connectors(
        request: Request, scope: Scope, session: Session
    ) -> list[dict[str, Any]]:
        await require_pi(session, scope, "integrations.read")
        return await connectors.status(session, request.app.state.settings, scope)

    @router.post("/google_calendar/start")
    async def start_google(request: Request, scope: Scope, session: Session) -> dict[str, str]:
        await require_pi(session, scope, "integrations.manage")
        url = await connectors.start_google(
            session, scope, _runtime(request), app, request.headers.get("origin")
        )
        await session.commit()
        return {"authorization_url": url}

    @router.post("/shopify/start")
    async def start_shopify(
        data: ShopifyStart, request: Request, scope: Scope, session: Session
    ) -> dict[str, str]:
        await require_pi(session, scope, "integrations.manage")
        url = await connectors.start_shopify(
            session, scope, _runtime(request), data.shop, app, request.headers.get("origin")
        )
        await session.commit()
        return {"authorization_url": url}

    @router.get("/google_calendar/callback", include_in_schema=False)
    async def google_callback(
        request: Request,
        scope: Scope,
        session: Session,
        state: Annotated[str, Query(max_length=200)] = "",
        code: Annotated[str | None, Query(max_length=2048)] = None,
        error: Annotated[str | None, Query(max_length=200)] = None,
    ) -> RedirectResponse:
        scope.require("integrations.manage")
        ok = await connectors.finish_google(
            session, scope, _runtime(request), state=state, code=code, error=error
        )
        await session.commit()  # Consumed states stay consumed even when the grant failed.
        outcome = "connected" if ok else "failed"
        return RedirectResponse(f"{page}?google_calendar={outcome}", status_code=302)

    @router.get("/shopify/callback", include_in_schema=False)
    async def shopify_callback(
        request: Request, scope: Scope, session: Session
    ) -> RedirectResponse:
        scope.require("integrations.manage")
        params = {k: v[:2048] for k, v in request.query_params.items()}
        ok = await connectors.finish_shopify(session, scope, _runtime(request), params)
        await session.commit()
        outcome = "connected" if ok else "failed"
        return RedirectResponse(f"{page}?shopify={outcome}", status_code=302)

    @router.post("/{key}/test")
    async def test_connector(key: str, request: Request, scope: Scope, session: Session) -> Any:
        await require_pi(session, scope, "integrations.manage")
        result = await connectors.test(session, scope, _runtime(request), _key(key))
        await session.commit()
        return result

    @router.delete("/{key}", status_code=204)
    async def disconnect_connector(
        key: str, request: Request, scope: Scope, session: Session
    ) -> None:
        await require_pi(session, scope, "integrations.manage")
        await connectors.disconnect(session, scope, _runtime(request), _key(key))
        await session.commit()

    return router


router = build("pi")
web_router = build("web")
