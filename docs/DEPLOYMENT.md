# Deployment

Status: **UNVERIFIED.** Nothing has been deployed. This describes the intended production
topology and the checks that must pass before a first deployment. The supplied
`docker-compose.yml` is for local development only.

## Components

| Component | Image / command | Scaling | State |
| --- | --- | --- | --- |
| web | `apps/web/Dockerfile` (Next.js standalone, `node server.js`, non-root) | stateless, horizontal | none |
| api | `apps/api/Dockerfile` (`uvicorn app.main:create_app --factory`) | stateless, horizontal | none |
| worker | same image, `arq app.worker.WorkerSettings` | horizontal (jobs are idempotent) | none |
| PostgreSQL 17 + pgvector | managed service recommended | primary + replica | **source of truth** |
| Redis 7 | managed service recommended, AOF on, `noeviction` | single primary | queue, rate limits, short-lived locks (not business truth) |
| Object storage | S3-compatible (S3, R2, MinIO) via the storage integration | — | uploaded files |

The browser talks only to the web origin; web proxies `/api/v1/*` to the API
(`API_PROXY_TARGET`), so session cookies stay first-party. Public webhook URLs
(`/api/v1/webhooks/...`) must be reachable from providers; route them to the API directly
or through the same proxy.

## Configuration

All settings are environment variables documented in `.env.example` and validated by
`apps/api/app/core/config.py` at startup. Production (`APP_ENV=production`) fails closed on:
non-HTTPS CORS origins, non-ARQ job queue, insecure cookies, missing explicit hosts.
Secrets (database/Redis URLs, `SECRETS_ENCRYPTION_KEY`, provider keys, WhatsApp app
secret) must come from the platform's secret store, never from images or the repository.

`SECRETS_ENCRYPTION_KEY` accepts comma-separated Fernet keys: the first encrypts, all
decrypt. Rotate by prepending a new key, deploying, running the re-encryption job, then
removing the old key.

## Release procedure

1. CI green on the release commit (`.github/workflows/checks.yml`: format, lint, types,
   migrations up/down/up + drift check, backend tests with PostgreSQL + Redis, web build,
   Playwright, dependency audit, container build).
2. Back up the database (see [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)).
3. Run `alembic upgrade head` once, from a single release job, before new API/worker pods
   receive traffic. Migrations are written to be additive where possible; review any
   destructive downgrade before use.
4. Roll out api and worker, then web. Readiness: `GET /api/v1/health/ready` (PostgreSQL +
   Redis). Liveness: `GET /api/v1/health/live`.
5. Smoke test: sign in, open Overview, list customers, `arq --check` on a worker.

## Production readiness gate

Every item below is currently **UNVERIFIED** unless PROJECT_STATUS.md records evidence:
TLS termination and HSTS; managed database backups with a tested restore; Redis
persistence; secret store wiring; separate migration and runtime database roles; log
shipping with redaction; tracing/error monitoring backend; alerting on queue depth,
webhook failures, provider fallback rate and 5xx rate; WhatsApp/AI/email/storage provider
credentials verified in a sandbox; load test; penetration test.
