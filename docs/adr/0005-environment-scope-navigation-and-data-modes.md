# 0005 — Environment-scoped data, a single navigation registry, and UI data modes

Date: 2026-09-24

Status: Accepted and implemented.

## Environment scope

Business data (customers, catalog, stock, sales, quotes, orders, invoices, payments,
expenses, employees, notifications, all PI data) belongs to one tenant environment.
Each such table carries `tenant_id` and `environment_id` with a composite foreign key to
`environments(tenant_id, id)`, and child rows reference parents through
`(tenant_id, environment_id, id)`, so a reference cannot cross tenants or environments even
if service code is wrong. Organization data (users, memberships, roles, branches,
departments) stays tenant-wide. Reason: a staging PI number or test data must never touch
production stock, orders or customers.

The active tenant and environment are stored on the server-side session and revalidated
against active membership on every request. `WorkspaceRepository` rechecks tenant,
environment and active actor in every statement.

## Navigation registry

Routes, labels, icons, sections, default sort order, permissions, product/feature
dependencies and environment scope are defined once in the API
(`app/modules/navigation/definitions.py`). `GET /api/v1/navigation` resolves them for the
current user and merges the user's saved order; saving an order is validated so it can
only contain currently visible items. A newly registered module appears automatically
after its nearest default neighbour, even for users with a saved custom order.

The web app renders the sidebar, mobile drawer, module tabs, breadcrumbs and the command
menu from this one source. For sample-data mode the API exports a snapshot
(`registry.generated.json`, plus the permission catalog), and the browser mirrors the
resolver; a backend test fails if the snapshot is stale.

## Data modes

The web app has one data contract per feature and two adapters: `live` (the API through a
same-origin `/api/v1` proxy) and `demo` (fictional in-browser data partitioned by tenant and
environment). Demo mode is visibly marked, is the default only for local UI work, and is
never used by container builds (`NEXT_PUBLIC_DATA_MODE=live`). Where a backend does not exist
yet (PI), the live adapter fails with an explicit "not connected" error rather than
returning fabricated data.

## Optional pgvector

`CREATE EXTENSION vector` needs elevated privileges and is unavailable on the local
workstation. Migration 0002 adds embedding columns only when the extension can be created
(inside a savepoint). The columns are unmapped and excluded from autogenerate comparison.
Retrieval must fall back to full-text search (`tsvector`, `simple` configuration) when
they are absent.
