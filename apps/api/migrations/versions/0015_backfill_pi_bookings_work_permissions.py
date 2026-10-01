"""backfill pi bookings work permissions

Revision ID: 0015_backfill_pi_bookings_work
Revises: 0014_pi_platform_verification

0007_pi_saas added pi.bookings.* and pi.work.* to role_permissions for existing
tenants, but that backfill never ran against the shared dev database (the file
was edited after 0007 had already been stamped there), leaving owner/admin and
every other system role unable to grant these permissions. Re-running the same
backfill here is idempotent and a no-op anywhere 0007 already applied it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_backfill_pi_bookings_work"
down_revision = "0014_pi_platform_verification"
branch_labels = None
depends_on = None

_FULL = ("pi.bookings.read", "pi.bookings.manage", "pi.work.read", "pi.work.manage")
_READ_ONLY = ("pi.bookings.read", "pi.work.read")

_GRANTS: dict[str, tuple[str, ...]] = {
    "owner": _FULL,
    "admin": _FULL,
    "manager": _FULL,
    "support": _FULL,
    "member": _FULL,
    "viewer": _READ_ONLY,
}


def upgrade() -> None:
    for key, permissions in _GRANTS.items():
        for permission in permissions:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, tenant_id, role_id, permission) "
                    "SELECT gen_random_uuid(), r.tenant_id, r.id, :permission FROM roles r "
                    "WHERE r.is_system AND r.key = :key ON CONFLICT DO NOTHING"
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
