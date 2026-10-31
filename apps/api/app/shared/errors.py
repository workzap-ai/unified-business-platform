"""Domain errors with fixed public codes. Messages are safe to show to operators."""

from uuid import UUID

from app.modules.tenants.errors import OrganizationConflict, ResourceNotFound

__all__ = [
    "BusinessRuleViolation",
    "Conflict",
    "CsrfFailed",
    "InvalidTransition",
    "OrganizationConflict",
    "PermissionDenied",
    "ResourceNotFound",
    "Unauthenticated",
]


class Unauthenticated(Exception):
    """No verified session; always rendered as a generic 401."""


class PermissionDenied(Exception):
    """Authenticated but not authorized for the requested action.

    A failed workspace permission check also carries who and where (ids and the missing
    permission keys only), so the 403 handler can audit it. Other raises carry nothing.
    """

    def __init__(
        self,
        *,
        tenant_id: UUID | None = None,
        environment_id: UUID | None = None,
        user_id: UUID | None = None,
        actor_label: str | None = None,
        request_id: str | None = None,
        missing: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.tenant_id = tenant_id
        self.environment_id = environment_id
        self.user_id = user_id
        self.actor_label = actor_label
        self.request_id = request_id
        self.missing = missing


class Conflict(OrganizationConflict):
    def __init__(self, message: str = "The operation conflicts with existing data") -> None:
        super().__init__(message)
        self.message = message


class CsrfFailed(PermissionDenied):
    """Unsafe request without a valid session-bound CSRF token."""


class BusinessRuleViolation(Exception):
    """A request that is well-formed but not allowed by business rules."""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class InvalidTransition(BusinessRuleViolation):
    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__("INVALID_TRANSITION", f"A {entity} cannot move from {current} to {target}")
