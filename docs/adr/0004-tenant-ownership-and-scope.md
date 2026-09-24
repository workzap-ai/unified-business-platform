# 0004 — Tenant ownership, scope, and the authentication boundary

Date: 2026-09-23

Status: Accepted and implemented at Stage 2. PostgreSQL migration and isolation tests executed locally.

## Context

Stage 2 introduces identity/organization persistence before Stage 3 authentication and Stage 4 RBAC. Client-supplied identities cannot safely unlock tenant data during that interval. The foundation also needs database constraints that reject cross-tenant references even when service validation is bypassed.

## Decision

Create platform_users, tenants, tenant_memberships, branches, and departments using UUID primary keys and timezone-aware timestamps. Users are global identities. A membership uniquely links a user to a tenant; its active/revoked status is independent of future roles. Tenant and user active/inactive status also gate access. There are no passwords, sessions, roles, or onboarding endpoints in Stage 2.

Branches and departments are tenant-owned. A department can be tenant-wide (null branch_id) or attached to a branch in that same tenant. Memberships are tenant-wide, not branch-specific. These organizational definitions are shared across future environments; environment-scoped business entities will be decided in their own stages. No environment_id is added prematurely to these five tables.

Use unique (tenant_id, id) keys and a composite department (tenant_id, branch_id) foreign key. This pairs ownership with the referenced ID rather than checking two unrelated foreign keys. Tenant-scoped branch/department codes are unique; tenants have unique slugs and users have unique normalized emails. Deletes use RESTRICT to prevent accidental cascades. See [SQLAlchemy composite constraints](https://docs.sqlalchemy.org/en/20/core/constraints.html).

TenantScope is an immutable internal value constructed after resolving an active membership from a verified actor ID. It is never accepted as a request payload. TenantRepository requires scope and checks both tenant_id and an active membership/user/tenant predicate on every read, list, update, and delete. It uses SQL statements rather than identity-map-only lookups. Updates cannot assign tenant_id or arbitrary fields. Inserts obtain scope from the service, reject ownership fields in input, and hold shared membership/user/tenant locks until the caller's transaction completes. These checks establish ownership, not business permissions.

Internal services participate in a caller-owned transaction and do not commit. Savepoints translate constraint conflicts without invalidating the outer transaction. Future registration/onboarding/RBAC services must wrap their multi-step operations in explicit transactions and add the appropriate action permission before exposing mutations.

Expose only paginated tenant and branch read contracts. The authenticated_user_id dependency unconditionally rejects requests with 401 until Stage 3 supplies verified sessions. There are no developer headers, environment overrides, hardcoded users, or public mutation routes. Test-only FastAPI dependency overrides exercise verified-identity paths. Stage 4 will add permission enforcement to the existing scope foundation.

## RLS decision and limits

Use explicit scoped SQL and relational constraints now. PostgreSQL RLS is not enabled in this revision. Choosing policies without the future runtime-role/session trust boundary would create a misleading guarantee: PostgreSQL table owners normally bypass RLS, and privileged roles require special handling. See [PostgreSQL row-security documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

Revisit RLS and separate migration/runtime roles alongside Stage 4 and the Stage 17 security review. Until then, privileged/raw SQL can read across tenants; callers must use reviewed scoped services/repositories. Do not claim database-wide row isolation or treat the Stage 2 API boundary as implemented authentication. No production deployment is authorized by this decision.

## Frontend

TenantProvider loads only the membership-filtered API list and requires explicit selection. Branch query keys include tenant identity. Switching tenants clears branch selection and cancels/removes old tenant queries; stale responses cannot populate another tenant's choices. Payload tenant IDs are checked as a defensive UI measure. A failed membership refresh yields no active tenant. No selection or credentials are persisted in browser storage. Selectors support paginated loading, empty, denied, loading, and error states. PermissionGate denies all permissions until Stage 4 provides verified permission data; it is display logic only.

## Verification

Tests use PostgreSQL 17.11 from an official EDB portable archive in the ignored workspace cache, on loopback port 55432 with a generated password and a non-superuser database owner. Test rows are rolled back. Migration upgrade, clean downgrade/re-upgrade, and Alembic drift checks pass. Integration tests prove scoped reads/updates/deletes, guessed-ID rejection, membership revocation/deactivation, multiple memberships with separate scopes, composite-FK enforcement, uniqueness, restricted deletes, pagination, UUID defaults, and HTTP identity spoof rejection. Browser tests use mocked API responses; they do not claim authentication works.
