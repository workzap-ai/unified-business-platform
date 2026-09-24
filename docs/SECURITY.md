# Security baseline and requirements

Updated Stage 2, 2026-09-23. The scoped data-access foundation has PostgreSQL isolation-test evidence. This is not implemented authentication, RBAC, database-wide row security, or a production security certification.

## Stage 2 isolation controls

- UUID identities, required tenant ownership, tenant-scoped uniqueness, and composite department/branch foreign keys enforce referential ownership.
- Internal scope resolves an active user, active tenant, and active membership. Every scoped repository SQL statement rechecks these conditions and the tenant predicate; cached ORM objects cannot bypass the query.
- Browser input cannot supply identity, scope, tenant_id in create payloads, or arbitrary update fields. Read endpoints deny all real requests until session identity is implemented. No HTTP mutation routes exist.
- Insert services hold shared membership/user/tenant locks in the caller's transaction. Constraint failures are converted to safe conflicts through savepoints. Privileged bootstrap operations are not exposed through HTTP.
- Real PostgreSQL tests exercise foreign reads/updates/deletes, guessed IDs, cross-tenant relationships, revoked/inactive context, multiple memberships, and HTTP spoof attempts.
- Frontend switching clears branch selection and cancels/removes old tenant queries. It validates returned branch ownership, shows no active tenant on membership-fetch errors, and never treats UI permissions as authorization.
- RLS is not enabled. Raw/privileged SQL can bypass repository filters. Revisit separate runtime/migration roles and RLS in Stages 4/17; see ADR 0004. Membership checks are not action permissions.

## Implemented and checked at Stage 1

- Required secret-wrapped PostgreSQL/Redis settings, hidden validation inputs, explicit CORS origins/hosts, and HTTPS browser origins in production configuration.
- Request-generated IDs and bounded correlation IDs; application request logs contain allowlisted metadata and fixed events without payloads, headers, or exception messages.
- Safe route, validation, unexpected-error, and dependency-readiness responses. Raw SQL/provider details are not returned.
- Bounded database pools, statement/network timeouts, bounded Redis connections, HTTP timeouts, and resource cleanup. SQL parameter logging is hidden.
- Production API documentation is disabled; browser/API responses include basic security headers. Browser API responses are validated with Zod and server error messages are not rendered directly.
- Docker application users are non-root and Compose service ports bind to loopback. Compose Redis has no external authentication and is suitable only for trusted local development. ARQ serialization assumes a trusted Redis boundary.
- Example credentials are development placeholders. .env files, caches, and local artifacts are ignored; no production secrets are provided.

Stage 1 tests cover hosts/CORS, safe errors, configuration, pagination, request IDs, readiness, and log allowlisting. Stage 2 adds the isolation controls above. Sessions, rate limiting, CSRF for authenticated mutations, RBAC, RLS, upload security, and production infrastructure controls remain future work. Stage 3 must purge frontend membership/tenant caches whenever the authenticated identity changes or logs out.

## Trust boundaries and required controls

| Boundary | Required behavior | Verification stage |
| --- | --- | --- |
| Browser to API | Validate input, enforce limits, safe errors, configured origins/hosts, server authorization | 1, 3, 4, 17 |
| Identity to tenant | Resolve active membership from authenticated identity; client tenant selection is untrusted | 2–5 |
| Tenant/environment to data | Scope queries, relationships, caches, jobs, exports, and object IDs; reject mismatched scope | 2 onward |
| API to database | Least privilege, constraints, safe transactions, bounded queries; no raw errors | 1 onward |
| API to workers | Trusted scope, bounded retries, idempotency, revocation handling, safe failed-job records | 1 onward |
| Platform to AI provider | Server-held secrets, timeouts, validated outputs, redaction, controlled fallback | 16–18 |
| Product to business service | Installation and permissions checked independently of navigation visibility | 15 onward |
| Webhook/media/LLM to PI | Signature, replay/deduplication, media validation, constrained tools and isolated retrieval | 21–29 |

## Authentication and authorization

Use strong password hashing and secure server-validated sessions. Prefer HttpOnly browser cookies, Secure in production, appropriate SameSite, and CSRF protection where required. Do not store raw refresh tokens or sensitive long-lived credentials in localStorage. Implement rotation, revocation, logout, account status enforcement, brute-force protection, and rate limits. Define verification and password-reset flows with expiring single-use credentials.

Use deny-by-default backend permissions through authenticated memberships. Reject inactive or revoked memberships and mismatched tenants/environments. Frontend hiding is usability only. Tenant-scoped foreign keys or equivalent constraints must prevent references crossing tenant boundaries. Determine database defense in depth during Stage 2.

## Secrets, logging, and audit

Never commit real secrets, expose provider keys to browsers, or record passwords, tokens, cookies, or raw sensitive payloads in logs. Use validated settings with non-secret examples. Audit important mutations with actor, tenant, applicable environment, action, resource, request ID, and timestamp. Redact metadata and define retention/access policies before production. Track operational IDs and latency without unrestricted customer data collection.

## Data and asynchronous safety

Use deterministic money calculations, controlled business state transitions, safe concurrent inventory updates, and transactional writes. Reliable events need an outbox where loss is unacceptable. Workers must not accept model-supplied tenant authority, repeat side effects on retries, or retain stale privileges without a defined policy.

Uploads require size, type, extension, and content validation where practical plus private storage and controlled retrieval. AI and media integrations must constrain outbound destinations and resource usage. LLMs cannot query databases directly or invent prices, stock, discounts, or totals.

## Required negative tests

- Tenant A cannot read, update, delete, search, export, or reference Tenant B records, including guessed IDs.
- Environment/branch restrictions hold wherever applicable, including queues and caches.
- Expired/revoked sessions and memberships fail; unauthorized state changes are rejected.
- Cookie and CSRF protections, rate limits, validation failures, and errors do not leak secrets.
- Product access fails when installation, environment enablement, or permission is absent.
- Later PI tests cover invalid signatures, replay, duplicate events, unauthorized tools, prompt injection, malformed model output, provider/worker failures, cross-tenant retrieval, and takeover stopping automated replies.

Stage 18 gates foundation security before PI. Stage 29 verifies PI failure paths. Production readiness also requires backup/restore evidence, recovery objectives, secrets rotation, dependency review, monitoring, and operational ownership in Stage 30.

## Audit limitations

Local API, PostgreSQL isolation/migration, and browser tests are recorded in PROJECT_STATUS.md. Tests use a disposable local PostgreSQL database and test-only identity dependency overrides; live session authentication is not tested because it does not exist. Redis/worker and Docker checks remain unavailable locally. No production credentials or resources were accessed, and no penetration test or production infrastructure audit was performed. Production readiness is not established.
