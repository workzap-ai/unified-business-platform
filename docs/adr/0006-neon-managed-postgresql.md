# 0006 — Neon as the managed PostgreSQL database

Date: 2026-09-25

Status: Accepted (owner decision). Implemented. Verified 2026-09-25 against the owner's
Neon project: TLS connections through the pooled and direct endpoints, migrations to
head over the direct endpoint, `alembic check` clean, `vector` and `pg_trgm` created.

## Context

The platform needs a managed PostgreSQL with pgvector for shared and production
environments. The owner chose Neon. Neon is PostgreSQL (the project runs 18.6), so the schema,
Alembic migrations, SQLAlchemy/asyncpg access, `pg_trgm` and `vector` extensions are
unchanged. Differences that matter to the application:

- Connections require TLS; console strings use libpq parameters (`sslmode`,
  `channel_binding`) that asyncpg does not accept.
- The pooled endpoint (`…-pooler…`) is PgBouncer in transaction mode. Generic PgBouncer
  breaks asyncpg's cached prepared statements; Neon's supports protocol-level prepared
  statements (verified against the project).
- Computes scale to zero; the first connection after idle can take seconds, and idle
  connections are closed server-side.

## Decision

- `DATABASE_URL` may be Neon's pooled string exactly as copied; `app/core/database.py`
  (`resolve_database`, `create_engine`) converts it to `postgresql+asyncpg`, strips libpq-
  only parameters, enables verified TLS (certificate chain and hostname) for Neon hosts or
  when `sslmode`/`DATABASE_SSL` requires it, and detects the pooler.
- On Neon's pooler, asyncpg prepared-statement caching and the `statement_timeout` startup
  setting stay on: Neon's PgBouncer supports protocol-level prepared statements, and
  measured against the project (us-east-2) a cached query costs one round trip (~200 ms
  from the development workstation) instead of two (~600 ms). For other PgBouncer
  deployments (`DATABASE_POOLED=true`, non-Neon host) or with
  `DATABASE_POOLER_PREPARED_STATEMENTS=false`, caches are disabled, statement names are
  unique and no startup parameters are sent; set the timeout on the role instead
  (`ALTER ROLE <role> SET statement_timeout = '10s'`, also applied to the Neon role).
- Deploy the API and worker in the same region as the Neon project (currently AWS
  us-east-2): every query is a network round trip.
- `MIGRATION_DATABASE_URL` (Neon direct endpoint) is used by Alembic; migrations never
  run through PgBouncer.
- `DB_CONNECT_TIMEOUT_SECONDS` (default 10) tolerates cold starts; `DB_POOL_RECYCLE_SECONDS`
  (default 300) recycles connections before Neon closes them; `pool_pre_ping` stays on.
- Production refuses remote databases without SSL.
- Environments map naturally to Neon branches (e.g. a `staging` branch and disposable CI
  branches whose database name ends in `_test`). Platform environments inside one tenant
  remain rows in the same database; Neon branches separate deployments, not tenants.
- The local portable PostgreSQL and the compose `postgres` service remain for offline
  development and tests.

## Consequences

- Backups/PITR use Neon's history retention and branching (see DISASTER_RECOVERY.md);
  restore drills are still required.
- `channel_binding=require` is dropped because asyncpg does not implement it; TLS with
  certificate and hostname verification is enforced instead.
- Verification pending: run migrations and the integration suite against a Neon branch.

## Latency findings (2026-09-25)

From the development workstation (Pakistan) to the project in AWS us-east-2 a round trip
is ~200–250 ms, so request time is dominated by the number of statements:

- Registration issued 199 statements (one INSERT per role permission) and took ~52 s;
  role seeding now uses two multi-row INSERTs (26 statements total).
- Every authenticated request resolved membership, environment, grants and business type
  with four queries; they are now one query (a customer list went from 7 to 4 statements).
- The API pool is enlarged for Neon (`DB_POOL_SIZE`/`DB_MAX_OVERFLOW` 15) and waits up to
  `DB_POOL_TIMEOUT_SECONDS` (10) for a connection, instead of failing after 3 s.

Remaining cost is distance. For interactive use either run the API in the Neon region
(production plan) or move the Neon project closer to the users (e.g. AWS ap-southeast-1 /
Singapore or eu-central-1 / Frankfurt) with a Neon branch restore.
