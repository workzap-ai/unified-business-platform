# Architecture baseline and target

Updated at Stage 2, 2026-09-23. The technical and organization-data foundations are implemented. Authentication, RBAC, business modules, product registry, and AI remain future stages. No pre-existing application required migration or replacement.

## Implemented foundation

apps/api contains the FastAPI factory, validated settings, async SQLAlchemy session/engine lifecycle, bounded Redis and HTTPX clients, request/correlation middleware, JSON application logs, safe errors, health routes, pagination schemas, Alembic, ARQ worker, and tests. Stage 2 adds five organization models, revision 0001_tenant_foundation, immutable internal tenant scope, scope-enforcing repositories, organization services, and paginated tenant/branch read contracts behind a fail-closed identity dependency.

apps/web contains a Next.js App Router shell, strict TypeScript, Tailwind, owned shadcn-style button primitive, feedback/error pages, TanStack Query, schema-validated GET client, React Hook Form/Zod hook, and notifications. Stage 2 adds tenant/branch selectors and context, tenant-specific query keys, and a deny-by-default permission-display helper. Only Home exists as an application page. Selectors cannot access data until verified authentication is implemented.

Root Compose defines api, web, postgres, redis, and worker. Dockerfiles use non-root application users. CI definitions cover both applications and real service/container checks but have not run remotely. See PROJECT_STATUS.md for local verification and remaining limitations.

## Product boundaries

Use a generic parent platform; do not invent a public parent product name. The local folder name does not establish a public brand.

The platform owns identity, users, tenants, memberships, branches, departments, environments, roles, permissions, security, product installations, feature flags, audit, usage, jobs, events, notifications, observability, and a shared AI gateway.

Core business modules are Overview, Customers/CRM, Catalog, Inventory, Sales, Quotes, Orders, Billing, Finance, HR, and Reports. They remain platform modules independently of any product installation.

PI means AI WhatsApp Multi-Agent Product. It is one future installable product; its agents are not sub-products. PI must consume core business services through controlled tools and must not duplicate their data models. No PI registration, code, directories, or functionality is created at Stage 0. Future products are an extension requirement, not current deliverables.

Business catalog entities use catalog_products, catalog_categories, and catalog_variants. Installable software uses platform_products, tenant_product_installations, and environment_product_installations. These are separate concepts and tables.

## Planned repository and stack

Use a modular monolith with apps/api, apps/web, packages/shared, packages/config, infrastructure, and docs. Create directories when their implementation stage needs them.

Backend: Python 3.12+, FastAPI, Pydantic v2 and Pydantic Settings, SQLAlchemy 2 async, Alembic, PostgreSQL, asyncpg, pgvector, Redis, HTTPX, pytest, Docker, and Compose. LangChain and LangGraph are required at their AI stages, not justification to build PI early.

Frontend: Next.js, React, strict TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Hook Form, Zod, and Playwright. Avoid redundant state libraries.

ARQ is the single selected queue framework; see ADR 0003. Runtime and development Python locks and the frontend npm lock specify resolved versions. No LangChain/LangGraph or product code is introduced ahead of its stage.

## Module boundaries

Backend modules separate request/response schemas, routes, services, repositories, models, permissions, and tests. Routes validate requests and delegate business logic. Services enforce business rules and own transaction boundaries. Repositories require trusted scope for tenant-owned data. Return explicit response schemas, never raw ORM models.

Cross-module operations use explicit service interfaces and lightweight events. Avoid circular imports and direct writes into another module's tables. Use a transactional outbox when a committed change must reliably produce an asynchronous event. Events and jobs carry scope, correlation identifiers, and idempotency information; workers revalidate authority as appropriate.

Frontend features follow module boundaries and share a shell, forms, tables, feedback states, and API client. The backend is the authorization authority. Pages need loading, error, empty, success, denied, and not-found states as appropriate, with accessible responsive navigation.

## Identity and data isolation

Platform users are global identities; tenant memberships link users to tenants. Roles apply through memberships. Branches and departments belong to tenants. Environments belong to tenants and support custom names. Exact environment scope for each business entity must be recorded before its migration; do not add or omit environment scope blindly.

Stage 2 uses UUIDs and tenant_id on memberships, branches, and departments. Departments may reference a same-tenant branch through a composite foreign key. These organizational definitions are tenant-wide across future environments. Validate requested tenant selection against active membership before constructing internal scope; recheck active user/tenant/membership on scoped operations. Database constraints reject cross-tenant relationships. RLS is not enabled: ADR 0004 records the scoped-SQL design and requires reassessment with runtime roles at Stage 4 and Stage 17. Privileged raw SQL is not isolated by this design.

No production request can currently provide authenticated identity. The Stage 2 dependency returns 401; Stage 3 replaces it with verified sessions, and Stage 4 adds action permissions. Internal mutation services have no HTTP routes and participate in caller-owned transactions. They do not grant mutation permission merely because a membership exists. All future cache keys, jobs, and retrieval operations must preserve trusted scope too.

Installation checks combine tenant entitlement, environment enablement, and user permission. Product extension must reuse identity, tenancy, billing foundation, audit, gateway, shell, and observability without redesign.

## API and runtime behavior

Use /api/v1/ and a consistent error envelope containing error.code, error.message, error.details, and error.request_id. Never return raw provider or database errors. Establish request IDs, correlation IDs, structured redacted logs, bounded pagination, health checks, and explicit configuration validation in Stage 1.

Use async database and HTTP clients, bounded pools and timeouts, short transactions, explicit loading, suitable indexes, and query limits. Avoid N+1 queries, unbounded reads, and blocking I/O in async handlers. Keep LLM network calls outside database transactions where consistency permits.

Slow work goes through Redis-backed workers: imports, notifications, ingestion, and later WhatsApp processing. Specify retry limits, backoff, deduplication, failure handling, and idempotency before enabling side effects. Compose will include api, web, postgres, redis, and worker. No microservices, Kafka, or Kubernetes are justified at this baseline.

Use Decimal and PostgreSQL NUMERIC for money with explicit currency. Orders, quotes, inventory movements, invoices, and payments require deterministic calculations, controlled transitions, transactional concurrency handling, and auditability in their respective stages.

## Shared AI gateway and deferred PI

Stage 16 introduces a provider-independent gateway for generation, streaming, structured responses, health, and normalized usage. Provider order and model aliases are configuration. The specified default order is OpenAI, Gemini, then Groq. Bound retries and fallback to eligible transient failures; invalid permissions, inputs, tenant context, or credentials must not trigger blind fallback. Sanitize customer-visible errors.

PI begins only after Stage 18 passes. Later tools receive trusted tenant, environment, actor, customer, permissions, and request context and validate model arguments. LLMs never receive unrestricted database, SQL, or HTTP access or determine authoritative prices. Retrieval must isolate tenant and environment before ranking. Human takeover stops automatic replies.

## Delivery order and gates

| Stage | Scope |
| --- | --- |
| 0 | Repository and architecture audit |
| 1 | Backend and frontend technical foundation |
| 2 | Database and multi-tenant foundation |
| 3 | Authentication and secure sessions |
| 4 | RBAC, tenant context, permissions |
| 5 | Environments and tenant onboarding |
| 6 | Core business module architecture |
| 7 | Customers / CRM |
| 8 | Catalog and inventory |
| 9 | Sales and quotes |
| 10 | Orders |
| 11 | Billing |
| 12 | Finance |
| 13 | HR / employees |
| 14 | Overview dashboard and reports |
| 15 | Generic platform product registry |
| 16 | AI gateway and provider fallback |
| 17 | Security hardening |
| 18 | Foundation quality gate |
| 19 | Register PI product |
| 20 | PI domain foundation |
| 21 | PI WhatsApp integration |
| 22 | PI message pipeline |
| 23 | PI LangGraph multi-agent system |
| 24 | PI controlled business tools |
| 25 | PI memory and RAG |
| 26 | PI human handoff |
| 27 | PI voice and vision |
| 28 | PI frontend |
| 29 | PI end-to-end, security, load tests |
| 30 | Production readiness |

Stage 18 must prove backend/frontend startup, PostgreSQL/Redis connectivity, clean migrations, session lifecycle, tenant creation/switching/isolation, RBAC, environments, all core business modules, product installations, gateway fallback, workers, audit logging, backend tests, frontend build/typecheck, and critical E2E tests. Some technical checks pass at Stage 1, but this gate is not met. Ready for PI: NO.

Each stage requires inspection, stage understanding, explicit start authorization, implementation only within scope, relevant checks, documentation updates, and a stop. Security is built into each stage; Stage 17 is a review and hardening milestone.

## Open design decisions

Dependency locking and queue selection are implemented in Stage 1. Stage 2 decides organizational scope and defers RLS activation explicitly. GitHub Actions definitions now include PostgreSQL isolation tests and migration round trips but have not run remotely. Session storage, business-entity environment scope, runtime database roles/RLS review, deployment target, recovery objectives, retention, and CI hosting remain pending. Resolve them at the earliest dependent stage with an ADR when architectural.
