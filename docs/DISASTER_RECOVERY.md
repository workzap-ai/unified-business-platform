# Disaster recovery

Status: **UNVERIFIED.** No production infrastructure exists yet, so no backup has been
taken or restored. Values in angle brackets are placeholders to be replaced with measured
numbers; do not quote them as commitments.

A backup that has never been restored is not a verified backup.

## Objectives

| Objective | Target |
| --- | --- |
| RPO (maximum data loss) | `<to be set after infrastructure is chosen>` |
| RTO (maximum time to restore service) | `<to be set after a timed restore drill>` |

## What must be recoverable

| Asset | Source of truth | Backup mechanism (intended) |
| --- | --- | --- |
| Business, PI, integration and audit data | PostgreSQL on Neon | Neon history retention (point-in-time restore / branch from a past timestamp); retention window `<per Neon plan>`; plus periodic `pg_dump` exports to object storage for provider-independent recovery |
| Uploaded files / knowledge documents | object storage | bucket versioning + cross-region replication or scheduled copy |
| Queued jobs | Redis (ARQ) | not backed up; rebuilt from the database (see below) |
| Encryption keys, provider secrets | secret store | secret-store versioning; keys escrowed separately from database backups |
| Configuration | repository + environment | infrastructure-as-code and secret-store history |

Database backups are useless without `SECRETS_ENCRYPTION_KEY`: integration credentials
are encrypted with it. Keep key backups separate from, but restorable alongside, database
backups.

## Recovery procedures

**Database.** On Neon, create a branch from the target timestamp (or restore the branch
in place), verify it, then point `DATABASE_URL`/`MIGRATION_DATABASE_URL` at it. For
provider loss, restore the latest `pg_dump` into any PostgreSQL 17 with pgvector.
In either case run
`alembic current` to confirm the revision matches the deployed code, point the API/worker
at it, and check `/api/v1/health/ready`.

**Queue.** Redis contents are disposable. After a Redis loss, the database still holds
every durable record: inbound webhook events in `received`/`queued`/`failed` state,
pending outbox events and deliveries, and sync jobs. The worker's periodic dispatch
re-enqueues them; operators can also use Replay/Retry in Settings → Integrations. All
handlers are idempotent (unique provider event IDs, delivery idempotency keys), so
re-processing does not duplicate orders, payments or messages.

**Webhooks from providers.** Providers retry failed deliveries for a limited window
(provider-specific). Events missed beyond that window must be re-fetched through the
provider's API where available, or reconciled manually.

**Outbox.** Outbox rows are written in the same transaction as the business change, so a
restored database contains every event that was committed. Undelivered rows are
dispatched when the worker resumes.

**Files.** Restore the bucket version set matching the database restore point.

**Secrets.** Restore the secret-store version in use at the database restore point. If a
secret may have leaked, rotate it at the provider and in Settings → Integrations
(rotate credentials) instead of restoring it.

## Drills

Schedule a restore drill `<frequency>` into an isolated environment: restore database +
files + keys, run the application smoke test, and record the measured RTO/RPO in
PROJECT_STATUS.md. Until the first drill is recorded, backups remain UNVERIFIED.
