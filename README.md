# Business platform

Multi-tenant business platform (FastAPI + PostgreSQL API, Next.js web app) with core modules
(Customers/CRM, Catalog, Inventory, Sales, Quotes, Orders, Billing, Finance, HR, Reports)
and PI, an installable AI WhatsApp assistant product. Live API mode is the default;
labelled sample data is available explicitly with `NEXT_PUBLIC_DATA_MODE=demo`.
Registration and workspace pages need the API and a migrated PostgreSQL database.

## Start the configured local workspace (Windows)

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

This starts the configured portable PostgreSQL cluster when present, applies pending
migrations, starts the API on `127.0.0.1:8000`, and starts or reuses the website on
`localhost:3000`. Open http://localhost:3000/register. The API reads `apps/api/.env`;
local logs are in `.cache/local`. Keep these local files private. The current workstation
uses a persistent `owner_os_development` database, separate from the disposable test
database. Local `JOB_QUEUE_MODE=inline` runs jobs without a worker; production requires
Redis and ARQ. Redis-backed rate limiting remains unavailable without Redis.

If registration reports a service error and `/` cannot reach the workspace, check
http://localhost:3000/api/v1/health/live. A failed proxy request usually means only the
website is running. Run the startup command above and retry. If using a custom API
address, set `API_PROXY_TARGET` in `apps/web/.env.local` and restart the website; Next
production builds need rebuilding when this value changes. Running only `npm run dev`
does not start the backend.

Read [project status](docs/PROJECT_STATUS.md), [architecture](docs/ARCHITECTURE.md),
[security](docs/SECURITY.md), [frontend guide](docs/FRONTEND_GUIDE.md) and
[handoff](docs/AI_HANDOFF.md) before making changes.

## Quick look at the UI (no API needed)

```powershell
Set-Location apps/web
npm.cmd ci
$env:NEXT_PUBLIC_DATA_MODE='demo'
npm.cmd run dev
```

Open http://localhost:3000 and sign in with any email/password.
`NEXT_PUBLIC_DATA_MODE=demo` explicitly enables fictional in-browser sample data (marked
"Sample data"); changes reset on reload. Try switching workspace (Northwind retail,
Brightline services), switching to the Staging environment (first-use empty states, PI
not enabled), and "View as role" in the account menu.

To use the real API instead, set `NEXT_PUBLIC_DATA_MODE=live` and
`API_PROXY_TARGET=http://localhost:8000` in `apps/web/.env.local` (the browser calls
same-origin `/api/v1`, proxied to the API). Live mode is already the default.

## Requirements

Python 3.12+, Node 22+ (Node 22 in CI/containers), npm, and Docker with Compose for local PostgreSQL/Redis and full-stack checks. The current development workstation has no Docker, so container and Redis checks have not run locally.

## Database: Neon

Shared and production environments use [Neon](https://neon.tech) (managed PostgreSQL;
see [ADR 0006](docs/adr/0006-neon-managed-postgresql.md)). In `apps/api/.env`:

```ini
# Pooled endpoint, pasted from the Neon console as-is (the API and worker use it)
DATABASE_URL=postgresql://<role>:<password>@<endpoint>-pooler.<region>.aws.neon.tech/<db>?sslmode=require&channel_binding=require
# Direct endpoint (Alembic migrations)
MIGRATION_DATABASE_URL=postgresql://<role>:<password>@<endpoint>.<region>.aws.neon.tech/<db>?sslmode=require
```

Then, from `apps/api`: `..\..\.venv\Scripts\alembic.exe upgrade head`. Once, as the
database owner, run `ALTER ROLE <role> SET statement_timeout = '10s';` (the pooler cannot
set it per connection). Neon provides `pg_trgm` and `vector`, so semantic retrieval
columns are created. For tests, create a Neon branch with a database whose name ends in
`_test` and point `TEST_DATABASE_URL` at it; never at the main branch.

A local PostgreSQL (compose `postgres` service or any PostgreSQL 17) still works for
offline development.

## Run with Docker

From the repository root, copy .env.example to .env, choose a local development password, then run:

```sh
docker compose config --quiet
docker compose up --build --wait
docker compose exec api alembic upgrade head
```

Open http://localhost:3000. API documentation is at http://localhost:8000/docs. Health endpoints are /api/v1/health/live and /api/v1/health/ready. The example credentials are local placeholders, not production secrets. If your password contains URL-reserved characters, supply a correctly URL-encoded DATABASE_URL and adjust the Compose database URL accordingly.

Compose binds published ports to loopback. It uses persistent named database/Redis volumes; ordinary `docker compose down` retains data. The supplied Compose configuration is development-only. Revision 0002 creates the auth, RBAC, business, product-registry, navigation and PI tables, enables pg_trgm, and adds pgvector embedding columns when the extension can be created (it can in the Compose image). Back up any existing database before applying migrations; downgrade removes those tables and their data.

## Run applications locally (PowerShell)

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r apps/api/requirements-dev.lock
Copy-Item .env.example apps/api/.env
docker compose --env-file .env.example up -d postgres redis
Set-Location apps/api
..\..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --no-access-log
```

Settings read .env from the process working directory. For local API and worker commands, use apps/api and its .env. Root .env is for Compose. Edit the local database URL when using different credentials. The application intentionally requires explicit DATABASE_URL and REDIS_URL.

In a second terminal from the repository root:

```powershell
Set-Location apps/web
npm.cmd ci
npm.cmd run dev
```

For live data set NEXT_PUBLIC_DATA_MODE=live and API_PROXY_TARGET=http://localhost:8000 in apps/web/.env.local; both are read at build/start time. The browser calls same-origin /api/v1, which Next proxies to the API, so the HttpOnly session cookie stays first-party.

Run the worker in its Linux container (ARQ's process signal handling is not supported by this foundation on native Windows):

```powershell
docker compose up --build worker
```

## Verify

From apps/api:

```powershell
..\..\.venv\Scripts\ruff.exe format --check .
..\..\.venv\Scripts\ruff.exe check .
..\..\.venv\Scripts\mypy.exe app
..\..\.venv\Scripts\pytest.exe -q
..\..\.venv\Scripts\alembic.exe heads
..\..\.venv\Scripts\alembic.exe upgrade head --sql
```

With PostgreSQL and Redis running against a disposable test database, set DATABASE_URL and REDIS_URL for those services, then:

```powershell
$env:RUN_INTEGRATION='1'
..\..\.venv\Scripts\alembic.exe upgrade head
..\..\.venv\Scripts\alembic.exe check
..\..\.venv\Scripts\pytest.exe -q -m integration
```

Run the full queue integration test on Linux (as CI does). Do not point integration tests at production. Queue tests create a uniquely named test queue and short-lived result data.

Stage 2 isolation tests need PostgreSQL only and also run on Windows. Create an isolated database whose name ends in _test. Set DATABASE_URL to that database, run `alembic upgrade head`, then set TEST_DATABASE_URL to the same URL. From apps/api run:

```powershell
$env:TEST_DATABASE_URL=$env:DATABASE_URL
..\..\.venv\Scripts\pytest.exe -q tests/integration/test_tenant_isolation.py
```

These tests roll back their rows and refuse non-PostgreSQL URLs or database names without the _test suffix. Missing TEST_DATABASE_URL causes an explicit skip. CI sets it and applies migrations. A clean downgrade/re-upgrade is tested only on disposable empty databases; do not run that check on your working data.

From apps/web:

```powershell
npm.cmd run format:check
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
$env:PLAYWRIGHT_BROWSERS_PATH='../../.cache/ms-playwright'
npx.cmd playwright install chromium
npm.cmd test
```

Browser tests start an isolated production web server on port 3100 in sample-data mode (no API); they do not replace integration tests against the real API. `npm run start` assembles static assets into the standalone build before starting it. CI configuration is in .github/workflows/checks.yml and has not been run remotely during this stage.

## Dependency maintenance

Install backend packages using the hashed lock files. To intentionally update them, install pip-tools in your tooling environment and run pip-compile --generate-hashes --strip-extras against apps/api/pyproject.toml, once for requirements.lock and once with --extra dev for requirements-dev.lock. Review changes and run checks on Python 3.12/Linux as well as the local environment. npm ci consumes apps/web/package-lock.json; use npm install only when intentionally changing dependencies.

LangGraph is installed for the PI agent phase but not used yet. packages/shared and packages/config will be created when concrete shared code requires them.
