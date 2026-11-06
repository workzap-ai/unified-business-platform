"""backfill pi.meetings.* permissions for existing workspaces

Revision ID: 0058_backfill_pi_meetings_perms
Revises: 0057_pi_meeting_brain

Permissions are in code, but a workspace's system roles are rows made when the workspace was created,
so a permission added later reaches only workspaces created after it. This grants the meeting
permissions to the system roles that carry them in access/permissions.py (owner and admin: all four;
manager: read, record, approve). Idempotent: a role that already has a grant is left alone.
"""

import sqlalchemy as sa
from alembic import op

revision = "0058_backfill_pi_meetings_perms"
down_revision = "0057_pi_meeting_brain"
branch_labels = None
depends_on = None

_ALL = ("pi.meetings.read", "pi.meetings.record", "pi.meetings.approve", "pi.meetings.delete")
_GRANTS: dict[str, tuple[str, ...]] = {
    "owner": _ALL,
    "admin": _ALL,
    "manager": ("pi.meetings.read", "pi.meetings.record", "pi.meetings.approve"),
}


def upgrade() -> None:
    for key, permissions in _GRANTS.items():
        for permission in permissions:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, tenant_id, role_id, permission) "
                    "SELECT gen_random_uuid(), r.tenant_id, r.id, :permission FROM roles r "
                    "WHERE r.is_system AND r.key = :key "
                    "AND NOT EXISTS (SELECT 1 FROM role_permissions rp "
                    "WHERE rp.role_id = r.id AND rp.permission = :permission)"
                ).bindparams(key=key, permission=permission)
            )


def downgrade() -> None:
    for key, permissions in _GRANTS.items():
        for permission in permissions:
            op.execute(
                sa.text(
                    "DELETE FROM role_permissions rp USING roles r "
                    "WHERE r.id = rp.role_id AND r.tenant_id = rp.tenant_id "
                    "AND r.is_system AND r.key = :key AND rp.permission = :permission"
                ).bindparams(key=key, permission=permission)
            )
