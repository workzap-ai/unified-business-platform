# API conventions

Stage 2 adds tenant read contracts behind a fail-closed identity boundary. Authentication remains Stage 3 and action permissions Stage 4. No tenant mutation endpoint is exposed.

## Tenant contracts

- GET /api/v1/tenants?page=1&page_size=100 returns only active memberships of the verified active user in active tenants. Response: items (id, name, slug), total, page, page_size.
- GET /api/v1/tenants/{tenant_id}/branches uses the same pagination and validates membership before querying. Branch items include id, tenant_id, name, and code.
- Both currently return 401 for every normal request. Stage 3 must replace authenticated_user_id with verified session resolution. Headers, query IDs, arbitrary cookies, and environment variables cannot provide an identity. Tests override the dependency only within the test application.
- Once identity is verified, missing/foreign tenants share a safe 404. List pagination is capped at 100; total counts use the same scope predicates as items. Client tenant selection is a request, not authority.
- Internal services validate creation/rename inputs, reject ownership fields, and translate relationship/uniqueness conflicts to safe domain errors. Public mutations await RBAC; clients cannot create users, tenants, memberships, branches, or departments through this stage's HTTP API.

- Prefix: /api/v1.
- GET /api/v1/health/live: 200 with {"status":"ok"}; process availability only.
- GET /api/v1/health/ready: 200 with {"status":"ok"} after PostgreSQL SELECT 1 and Redis PING, otherwise 503 with a sanitized error.
- Non-production /docs and /openapi.json expose API documentation; production disables them.
- Errors use {"error":{"code":"...","message":"...","details":{},"request_id":"..."}} for route, validation, readiness, and unexpected failures. The host middleware rejects invalid Host headers with its own 400 response before routing.
- Each application request receives a new UUID X-Request-ID. X-Correlation-ID is accepted only as 1–64 ASCII alphanumeric, underscore, or hyphen characters; otherwise a generated ID is used. These IDs convey no authority.
- CORS origins and hosts are explicit configuration. Correlation and request headers are exposed to allowed browser origins. Responses set no-store and nosniff.
- Pagination input defaults to page=1, page_size=25; page_size is capped at 100 and page at 10000. Future large lists should use cursor pagination.
- Services will own transaction commits; session dependency closure rolls back uncommitted work. No tenant data should be exposed using an unscoped repository.
- The browser GET client validates JSON through Zod, uses a 10-second timeout, supports cancellation, and emits safe ApiError objects. Mutation helpers and CSRF handling must be added together with authentication before authenticated mutations are introduced.
