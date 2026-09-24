"""Domain errors with fixed public codes. Messages are safe to show to operators."""

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
    """Authenticated but not authorized for the requested action."""


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
