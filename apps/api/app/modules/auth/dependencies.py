from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audience import audience_for_path, cookie_names
from app.core.database import get_session
from app.modules.auth.crypto import digest, same
from app.modules.auth.service import AuthContext, AuthService
from app.shared.errors import CsrfFailed, Unauthenticated

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def auth_context(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AuthContext:
    """Resolve the verified session cookie. Headers or query IDs never select identity.

    The route prefix selects the application audience (Owner OS or the Pi app); each has
    its own cookie, and a session is only valid for the audience that issued it."""
    settings = request.app.state.settings
    audience = audience_for_path(request.url.path)
    token = request.cookies.get(cookie_names(settings, audience)[0], "")
    if not token or len(token) > 128:
        raise Unauthenticated
    context = await AuthService(session, settings).resolve(token, audience)
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
