from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from app.modules.tenants.context import TenantScope
from app.shared.errors import PermissionDenied


@dataclass(frozen=True, slots=True)
class WorkspaceScope:
    """Trusted tenant + environment context with verified permissions.

    Built only by the request dependency (from a verified session and active
    membership) or by trusted workers (system actor). Never deserialized from input,
    never produced from model output.
    """

    tenant_id: UUID
    environment_id: UUID
    permissions: frozenset[str]
    user_id: UUID | None = None
    membership_id: UUID | None = None
    branch_id: UUID | None = None
    actor_type: Literal["user", "system"] = "user"
    actor_label: str = field(default="user")
    request_id: str | None = None

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, *permissions: str) -> None:
        missing = tuple(p for p in permissions if p not in self.permissions)
        if missing:
            raise PermissionDenied(
                tenant_id=self.tenant_id,
                environment_id=self.environment_id,
                user_id=self.user_id,
                actor_label=self.actor_label,
                actor_type=self.actor_type,
                request_id=self.request_id,
                missing=missing,
            )

    @property
    def is_system(self) -> bool:
        return self.actor_type == "system"

    def tenant_scope(self) -> TenantScope:
        if self.user_id is None or self.membership_id is None:
            raise PermissionDenied
        return TenantScope(self.user_id, self.tenant_id, self.membership_id)

    @classmethod
    def system(
        cls,
        tenant_id: UUID,
        environment_id: UUID,
        permissions: frozenset[str],
        label: str,
        request_id: str | None = None,
    ) -> "WorkspaceScope":
        return cls(
            tenant_id=tenant_id,
            environment_id=environment_id,
            permissions=permissions,
            actor_type="system",
            actor_label=label,
            request_id=request_id,
        )
