"""Setup Center routes: /setup (Pi app and Owner OS) and the operator's platform checklist.

Viewing needs ``integrations.read`` and "Test all" needs ``integrations.operate``. Both
are owner/admin presets, because setup is their job.
"""

from typing import Any, Literal

from fastapi import APIRouter, Request

from app.modules.access.dependencies import Scope, Session
from app.modules.pi_saas import setup_center
from app.modules.pi_saas.connector_routes import _runtime
from app.modules.pi_saas.operator import Operator


def build(app: Literal["pi", "web"]) -> APIRouter:
    router = APIRouter(prefix="/setup", tags=["setup-center"])

    @router.get("/status")
    async def setup_status(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
        scope.require("integrations.read")
        items = await setup_center.status(session, request.app.state.settings, scope, app)
        required = [i for i in items if i["required"]]
        return {
            "items": items,
            "ready": all(i["state"] in {"connected", "platform"} for i in required),
            "connected": sum(i["state"] in {"connected", "platform"} for i in items),
            "total": len(items),
        }

    @router.post("/test-all")
    async def setup_test_all(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
        scope.require("integrations.operate")
        results = await setup_center.test_all(
            session, request.app.state.settings, request.app.state.http, scope, _runtime(request)
        )
        await session.commit()
        return {"results": results, "ok": all(r["ok"] for r in results)}

    return router


router = build("pi")
web_router = build("web")
operator_router = APIRouter(prefix="/operator/pi", tags=["pi-operator"])


@operator_router.get("/setup")
async def platform_setup(request: Request, operator: Operator) -> dict[str, Any]:
    operator.require("operator.health.read")
    checks = setup_center.platform_checklist(request.app.state.settings)
    return {"checks": checks, "ready": all(c["ok"] for c in checks[:6])}
