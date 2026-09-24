# AI and developer handoff

## Read first

1. [PROJECT_STATUS.md](PROJECT_STATUS.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [SECURITY.md](SECURITY.md)
4. [API_CONVENTIONS.md](API_CONVENTIONS.md)
5. [ADR 0004](adr/0004-tenant-ownership-and-scope.md)
6. [Setup](../README.md)

## Current stopping point

Stage 2 is complete. The user explicitly authorized “start stage 2”; Stage 3 is not authorized. Preserve Stage 1 and Stage 2 work. No business module or PI was built.

Five models and revision 0001_tenant_foundation exist. Internal tenant context, scoped repositories/services, paginated read routes, and frontend tenant/branch selectors are implemented. authenticated_user_id intentionally returns 401 for all normal requests. There is no development bypass or session authentication.

## Verification

25 backend tests pass, including 13 real PostgreSQL checks; one Redis/worker integration test remains skipped. Strict mypy, Ruff lint/format, real migration upgrade/downgrade/re-upgrade and drift comparison pass. Frontend formatting/lint/typecheck/build and seven browser tests pass. Browser responses are mocked; actual login is not tested or implemented.

PostgreSQL 17.11 portable binaries are in ignored .cache/postgres-portable. Generated credentials and the disposable cluster/database are under ignored .cache/pg-stage2, never committed. The loopback server on port 55432 was stopped after validation. Do not print credential files. Reusing it requires starting its existing cluster, not initializing over it. Tests require TEST_DATABASE_URL pointing to a migrated PostgreSQL database ending _test; all per-test rows roll back. Run migration round trips only on disposable databases whose data you may remove.

Git/Docker are unavailable locally, and Redis/worker/container/remote CI verification remains pending. Do not claim these passed. Node/Python dependencies did not change in Stage 2. Some Windows sandbox writes and local database access required escalation.

## Stage 3 preparation

Inspect source, docs, ADRs, migration, tests, .env.example, manifests/locks, and Git state when available. Present STAGE UNDERSTANDING before implementation and obtain explicit START STAGE 3 or an unmistakable stage-start instruction.

Implement secure authentication and sessions in Stage 3: strong password hashing; registration policy; login/logout/current user; refresh/rotation/revocation/all-session revocation; verification/reset architecture; account status; brute-force and rate-limit controls; secure HttpOnly browser cookies and appropriate CSRF protection. No raw refresh-token storage or sensitive long-lived localStorage credentials.

Replace app/modules/tenants/dependencies.py authenticated_user_id with verified server identity. Never accept user IDs from headers or browser state. Reuse membership resolution and tenant-scoped repositories; do not duplicate tenant models. Add new migrations after 0001 rather than rewriting it. Global users currently have normalized email, display name, status, UUID, and timestamps, but no credential fields.

Wire login/forgot-password/reset-password/verify-email pages and auth state. On logout, revocation, or identity replacement, cancel and clear membership and tenant query caches and clear selection. Current selections are memory-only. PermissionGate must continue to deny until Stage 4 supplies verified permissions. Public organization mutations await action permissions.

## Scope and ownership rules

- Users are global; tenant_memberships link active identities to active tenants.
- Internal TenantScope includes verified user, tenant, and membership IDs. It is not a request model.
- Repositories recheck tenant and active context in SQL for every read/update/delete. Inserts receive ownership from the service and lock membership/user/tenant rows through the caller's transaction.
- Internal services do not commit or grant mutation permissions. Future orchestration owns transaction and authorization boundaries.
- Departments may be tenant-wide or reference a same-tenant branch through a composite FK.
- The five identity/organization tables are shared across future environments; business entity scope remains stage-specific.
- RLS is not enabled. Privileged raw SQL bypasses scoped repositories. Revisit runtime roles/RLS at Stages 4/17; relational constraints do not filter reads.
- Avoid mass assignment, unscoped object lookup, arbitrary product IDs, secrets in source/logs, and fake authentication.

## Stage workflow and product boundaries

After each authorized stage run applicable checks, fix introduced failures, update docs, give STAGE RESULT, and stop. Report skipped/blocked checks honestly. Do not automatically start the next stage. No repository instruction requests sub-agent delegation.

Keep the generic parent platform, modular monolith, and ARQ-only queue. Business catalog and installable platform products are distinct. PI is one future AI WhatsApp product; agents are not products. PI registration begins at Stage 19 only after the Stage 18 quality gate. Shared AI gateway is Stage 16. Authentication is Stage 3, RBAC Stage 4, and environments/onboarding Stage 5.
