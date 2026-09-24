# Project status

CURRENT STAGE: 2 — Database + Multi-Tenant Foundation

STATUS: Complete within Stage 2 scope. PostgreSQL isolation and migration checks pass. Authentication, RBAC, and production readiness are not implemented.

Updated: 2026-09-23.

## Completed

- Five UUID-based models/tables: platform_users, tenants, tenant_memberships, branches, departments.
- Revision 0001_tenant_foundation with timestamps, uniqueness, indexes, status/name/code checks, restrictive foreign keys, and a composite department-to-branch ownership constraint.
- Explicit model registry used by Alembic; no schema creation at application startup.
- Immutable internal TenantScope, active membership/user/tenant resolution, scoped repositories, and organization services. Tenant predicates and active membership checks cover reads, lists, updates, and deletes. Inserts derive ownership from scope.
- Read-only tenant/branch API contracts behind an unconditional 401 identity boundary until Stage 3. No browser identity override and no HTTP mutations.
- Tenant/branch context and selectors, tenant-specific query keys, switch-time cancellation/cache removal, scoped payload checks, and deny-by-default permission-display preparation.
- Real PostgreSQL isolation tests and migration round trip. CI now enables database tests with TEST_DATABASE_URL.

## In progress

None. Stage 2 stops here. Redis/worker, Docker builds, and remote CI are still unverified in this environment; no production-readiness claim is made.

## Next step

Stage 3 — Authentication + Secure Sessions, only after explicit authorization. Replace the fail-closed authenticated_user_id dependency with verified session identity. Purge frontend caches whenever identity changes or logs out. Add credentials/session migrations after 0001; do not edit the applied migration.

## Backend

Organization models reside in their respective modules; tenants contains scope resolution, schemas, service, and read routes. The shared TenantRepository requires scope and rechecks membership in SQL. Services participate in a caller-owned transaction and use savepoints for translated constraint conflicts. They do not grant business mutation permissions; public writes await RBAC.

Users and tenants are global roots; memberships/branches/departments have tenant ownership. Departments optionally reference a same-tenant branch. These definitions are shared across future environments. No passwords, sessions, roles, business modules, product registry, or AI functionality was added.

## Frontend

TenantProvider and selectors are installed in the existing shell. Selection is explicit and in memory only. Switching clears the branch, cancels/removes previous-tenant queries, and cannot display another tenant's returned branch payload. Lists support loading more pages. Empty, unauthorized, loading, and error states are handled.

Actual API requests return 401 until Stage 3, so selectors remain disabled without authenticated data. Browser tests use mocked authorized responses. PermissionGate grants nothing until Stage 4 supplies verified permissions. No login page or fabricated tenant records were introduced.

## Database and migrations

Revision: 0001_tenant_foundation; parent: base.

Verified against PostgreSQL 17.11 using an official portable EDB archive in ignored .cache/postgres-portable. A generated-password, loopback-only cluster in .cache/pg-stage2 served port 55432. Tests used a non-superuser owner and disposable stage2_test database. Per-test data rolled back. The temporary server was stopped after validation; binaries and test files remain ignored for reuse.

Upgrade from empty database, downgrade on confirmed-empty tables, re-upgrade, and Alembic metadata comparison passed. Downgrade destroys the five tables; never run it on working data without a deliberate recovery plan. pgvector is not enabled by this migration.

## API changes

- GET /api/v1/tenants?page=1&page_size=100.
- GET /api/v1/tenants/{tenant_id}/branches with the same pagination.
- Both deny normal requests with 401 until verified session authentication exists.
- With a verified actor in tests, memberships filter tenants, foreign/missing tenants produce equivalent 404 responses, and branches are scoped.
- Existing health endpoints are unchanged.

See [API conventions](API_CONVENTIONS.md).

## Security and tenant isolation

PostgreSQL tests prove cross-tenant reads, updates, deletes, guessed IDs, mismatched branch references, forged internal scope combinations, revoked memberships, inactive identities/tenants, and multiple-membership scope separation behave correctly. Ownership fields are rejected in input schemas. Same-tenant positive paths also pass.

RLS is not enabled. Raw/privileged SQL can bypass repository scope; no database-wide row-security claim is made. Reassess runtime/migration roles and RLS in Stages 4/17. Active membership is not action permission. See [ADR 0004](adr/0004-tenant-ownership-and-scope.md).

## Test status and last verified commands

| Command/check | Result |
| --- | --- |
| ruff format --check . | Passed; 39 Python files |
| ruff check . | Passed |
| mypy app | Passed; strict, 32 source files |
| pytest -q with TEST_DATABASE_URL | 25 passed: 12 unit/API checks and 13 PostgreSQL checks; 1 Redis/worker test skipped |
| alembic upgrade head | Passed on disposable PostgreSQL |
| alembic downgrade base, then upgrade head | Passed on confirmed-empty disposable database |
| alembic check | Passed before and after round trip; no drift |
| npm run format / lint / typecheck | Passed |
| npm run build | Passed |
| npm test | 7 Chromium tests passed |
| Docker / Redis worker / remote CI | Not run locally; tooling/services unavailable |
| Git status / diff | Unavailable; no Git on PATH or workspace .git |

Initial long-line and selector-label issues were fixed before final checks. PostgreSQL tests are real database tests, not SQLite approximations. Browser API responses are mocked and do not verify a real login.

## Performance

Tenant-first composite indexes support ownership and reference checks. Queries are paginated with bounded page sizes and deterministic ordering; no unbounded list endpoint or relationship N+1 access was added. Scope joins add authorization checks to statements. No load benchmark was run.

## Known issues

- Git and Docker remain unavailable. Portable PostgreSQL resolved the database-testing blocker for this stage, not Docker or Redis/worker verification.
- Runtime auth is intentionally denied pending Stage 3. RBAC and RLS remain unimplemented.
- Starlette TestClient emits the existing HTTPX deprecation warning; tests pass.
- The existing ESLint 9 deprecation and version-tagged container images remain Stage 1 maintenance notes.
- Remote CI definitions are updated but not executed here.
- Stage 18 quality gate remains unmet; PI must not begin.

## Environment variables

Existing API/Compose/frontend settings remain unchanged. New test setting: TEST_DATABASE_URL, pointing to a migrated disposable PostgreSQL database with a name ending _test. Missing value skips PostgreSQL tests; an incompatible URL/database name fails explicitly. RUN_INTEGRATION=1 independently enables the Linux Redis/worker test. Never point tests at production.

No dependency changes or production credentials were added. Local tools remain Python 3.12.10, Node 26.10.0, npm 11.19.1; CI targets Python 3.12 and Node 22.

## Documentation

[Setup](../README.md), [architecture](ARCHITECTURE.md), [security](SECURITY.md), [handoff](AI_HANDOFF.md), [API conventions](API_CONVENTIONS.md), and [decisions](adr/README.md).
