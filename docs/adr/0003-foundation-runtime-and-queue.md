# 0003 — Foundation runtime and queue

Date: 2026-09-23

Status: Accepted; Stage 1 implementation. Container and real-service validation pending an equipped environment.

## Context

There was no existing application or queue. The foundation needs asynchronous database and HTTP clients, a Redis worker, a browser shell, and reproducible dependencies without business features.

## Decision

Use Python 3.12, async FastAPI/SQLAlchemy/asyncpg, Redis, HTTPX, Pydantic Settings, and Alembic. Select ARQ as the only queue framework: its async functions and Redis transport fit this foundation without adapters for synchronous task workers. The initial compatibility range is ARQ 0.26.x with Redis client 5.x, concretely resolved in requirements.lock. Revisit upgrades deliberately with worker tests rather than silently changing queue semantics.

ARQ jobs may execute again following interrupted work; future side-effecting jobs must be idempotent. Only a side-effect-free health probe is registered now. Set bounded worker concurrency, timeout, tries, result retention, and a worker health key. Redis must stay on a trusted network: queue contents are trusted serialized application data, not a public input protocol. Business retry policies and dead-letter handling belong with the first business jobs.

Worker process execution and queue integration target Linux containers/CI. Native Windows development is supported for the API and web shell; use the container for ARQ's process signal handling.

Use Next.js App Router, React, strict TypeScript, Tailwind v4, locally owned shadcn-style UI primitives, TanStack Query, React Hook Form with Zod, Sonner notifications, and Playwright. A shared schema-form hook configures validation without inventing a business form. Node 22 is the container/CI runtime; local validation used Node 26.10.0. Next.js requires Node 20.9 or newer according to its [installation documentation](https://nextjs.org/docs/app/getting-started/installation).

Use hashed pip-tools runtime/dev locks and npm package-lock.json. Development dependencies do not enter the API runtime image. Docker Compose is local development infrastructure with loopback-only published ports; it is not a production deployment configuration.

## Consequences

No auth, tenant context, domain tables, or PI behavior exists yet. Dependency health is checked on readiness; liveness remains independent of PostgreSQL/Redis. Runtime resources are created and closed through FastAPI lifespan. Domain table migrations begin at Stage 2; Stage 1 only prepares Alembic.

Frontend API origin is public build-time configuration and requires a rebuild when changed. Business authorization will be server-side in future stages. HTTPX remains the application HTTP client; a dependency deprecation notice from the current Starlette TestClient does not introduce a second application client.

## Verification

See PROJECT_STATUS.md for executed checks and limitations. CI includes PostgreSQL, Redis, a real queue probe, Alembic checks, production frontend build, browser tests, and Compose startup; adding the workflow does not mean it has run.

Reference: [ARQ documentation](https://arq-docs.helpmanual.io/) for worker behavior and Redis-backed asynchronous jobs. The dependency lock, not the documentation's latest version, is authoritative for this repository.
