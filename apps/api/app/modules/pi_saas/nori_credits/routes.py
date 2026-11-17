"""POST /api/pi/nori-send: the HTTP face of send_door.handle (mounted without the /v1 prefix).

nori's WORKZAP_PI_SEND_URL is set to https://<pi api host>/api/pi/nori-send. The route exists in
every deployment but answers 503 until the server has NORI_BASE_URL and WORKZAP_BRIDGE_SECRET and a
workspace has the flag on, and 503 again the moment NORI_BRIDGE_KILL is true.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.modules.access.dependencies import Session
from app.modules.pi_saas.nori_credits import send_door

router = APIRouter(tags=["pi-nori-bridge"])


@router.post("/nori-send", include_in_schema=False)
async def nori_send(request: Request, session: Session) -> JSONResponse:
    declared = request.headers.get("content-length")
    length = int(declared) if declared and declared.isdigit() else None
    body = bytearray()
    if length is None or length <= send_door.MAX_BODY_BYTES:
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > send_door.MAX_BODY_BYTES:
                break
    result = await send_door.handle(
        session,
        request.app.state.settings,
        request.app.state.http,
        bytes(body),
        request.headers.get("x-workzap-signature"),
        declared_length=length,
    )
    return JSONResponse(result.body, status_code=result.status)
