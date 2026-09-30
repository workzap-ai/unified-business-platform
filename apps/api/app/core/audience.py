"""Application audiences. The Owner OS web app and the standalone Pi app share the API
but never share sessions: each has its own cookies, allowed origins and route prefix."""

from typing import Literal

from app.core.config import Settings

Audience = Literal["owner_os", "pi"]
PI_PREFIX = "/api/v1/pi-app"


def audience_for_path(path: str) -> Audience:
    return "pi" if path == PI_PREFIX or path.startswith(PI_PREFIX + "/") else "owner_os"


def cookie_names(settings: Settings, audience: Audience) -> tuple[str, str]:
    if audience == "pi":
        return settings.pi_session_cookie_name, settings.pi_csrf_cookie_name
    return settings.session_cookie_name, settings.csrf_cookie_name


def allowed_origins(settings: Settings, audience: Audience) -> list[str]:
    return settings.pi_app_origins if audience == "pi" else settings.cors_origins
