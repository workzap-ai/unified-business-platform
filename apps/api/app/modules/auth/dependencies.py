from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.auth.crypto import digest, same
from app.modules.auth.service import AuthContext, AuthService
from app.shared.errors import CsrfFailed, Unauthenticated

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def auth_context(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AuthContext:
    """Resolve the verified session cookie. Headers or query IDs never select identity."""
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name, "")
    if not token or len(token) > 128:
        raise Unauthenticated
    context = await AuthService(session, settings).resolve(token)
    if request.method not in SAFE_METHODS:
        supplied = request.headers.get("x-csrf-token", "")
        if (
            not supplied
            or len(supplied) > 128
            or not same(digest(supplied), context.session.csrf_hash)
        ):
            raise CsrfFailed
    return context


Auth = Annotated[AuthContext, Depends(auth_context)]
