from uuid import UUID

from app.modules.auth.dependencies import Auth


async def authenticated_user_id(auth: Auth) -> UUID:
    """Identity comes only from a verified server-side session (see auth.dependencies).

    No header, query parameter, arbitrary cookie, environment flag or development bypass
    can select an identity. Tests may override this dependency.
    """
    return auth.user.id
