# Platform foundation

Stage 2 foundation for a modular business platform. Includes FastAPI, a Next.js shell, PostgreSQL organization models/migration, tenant-scoped services, selectors, Redis/ARQ configuration, and tests. No business modules, authentication, RBAC, or PI functionality exists yet. Tenant read endpoints intentionally return 401 until Stage 3 supplies verified sessions.

Read [project status](docs/PROJECT_STATUS.md), [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md), and [handoff](docs/AI_HANDOFF.md) before making changes. Stage 3 requires separate authorization.

## Requirements

Python 3.12+, Node 22+ (Node 22 in CI/containers), npm, and Docker with Compose for local PostgreSQL/Redis and full-stack checks. Git is needed for version control. The Stage 1 workstation has Python/Node/npm but no available Git or Docker.

## Run with Docker

From the repository root, copy .env.example to .env, choose a local development password, then run:

```sh
docker compose config --quiet
docker compose up --build --wait
docker compose exec api alembic upgrade head
```

Open http://localhost:3000. API documentation is at http://localhost:8000/docs. Health endpoints are /api/v1/health/live and /api/v1/health/ready. The example credentials are local placeholders, not production secrets. If your password contains URL-reserved characters, supply a correctly URL-encoded DATABASE_URL and adjust the Compose database URL accordingly.

Compose binds published ports to loopback. It uses persistent named database/Redis volumes; ordinary `docker compose down` retains data. The supplied Compose configuration is development-only. pgvector is available in the database image but not enabled. Alembic revision 0001_tenant_foundation creates five identity/organization tables. Back up any existing database before applying migrations; downgrade removes those tables and their data.

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

The browser API defaults to http://localhost:8000/api/v1. Override NEXT_PUBLIC_API_BASE_URL in apps/web/.env.local if needed; production builds embed this value. It must contain no credentials. Use localhost in the browser to match the default CORS origin.

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

Browser tests start an isolated production web server on port 3100 and mock API responses; they do not replace real service integration tests. `npm run start` assembles static assets into the standalone build before starting it. CI configuration is in .github/workflows/checks.yml and has not been run remotely during this stage.

## Dependency maintenance

Install backend packages using the hashed lock files. To intentionally update them, install pip-tools in your tooling environment and run pip-compile --generate-hashes --strip-extras against apps/api/pyproject.toml, once for requirements.lock and once with --extra dev for requirements-dev.lock. Review changes and run checks on Python 3.12/Linux as well as the local environment. npm ci consumes apps/web/package-lock.json; use npm install only when intentionally changing dependencies.

LangChain and LangGraph are deferred until the AI stages. packages/shared, packages/config, and business feature directories will be created when concrete shared code or approved modules require them.
