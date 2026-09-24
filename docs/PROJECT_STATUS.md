# Project status

Updated: 2026-09-24.

CURRENT PHASE: UI-first milestone complete (verified in a browser on sample data). Next:
real API connection and backend completion, starting with automated tests for the new
backend modules, then the PI backend.

Nothing here is production-ready. No deployment, penetration test, or load test has been
performed.

## Summary

| Area | State |
| --- | --- |
| Web app: shell, navigation, all modules, PI workspace, admin | Built; runs on sample data; 88 routes; verified in Chromium |
| Web app: live API mode | Business-module services target the implemented API contracts; not yet exercised against a running API |
| Backend: auth, RBAC, environments, audit, product registry, navigation | Implemented; lint + strict mypy clean; navigation has unit tests; others lack dedicated tests |
| Backend: customers, catalog, inventory, sales, quotes, orders, billing, finance, HR, reports | Implemented services + routes; migrated; **no dedicated tests yet** |
| Backend: PI | Schema only (migration 0002). No PI services, routes, AI gateway, WhatsApp, or agents yet |
| Redis/ARQ worker, Docker, remote CI | Not run in this environment (tooling unavailable) |

## Web app (apps/web)

- Design system: tokens (light/dark), primitives on Radix, business primitives (page shell,
  data table with sorting/selection/column visibility/pagination, URL-synced filters,
  saved views, metric cards, charts with table views, record header, timelines, forms,
  confirm dialogs, stepper). Chart palette validated for contrast and colour-vision
  separation in both themes.
- Shell: sidebar rendered from the navigation registry (default order Overview, Customers /
  CRM, Catalog, PI, Inventory, Sales, Quotes, Orders, Billing, Finance, HR, Reports; admin
  section separate); drag-and-drop and keyboard reordering, per-user persistence, reset;
  collapsed rail on tablet, drawer on mobile; tenant and environment switchers;
  notifications; command menu (pages from the registry, module actions, record search,
  recent items); breadcrumbs from the registry; theme toggle.
- Modules: Overview; Customers/CRM (list, create, detail with tabs, segments); Sales
  (overview, pipeline board, leads, lead detail); Catalog (overview, products, create,
  detail, categories, pricing); Inventory (overview, stock with adjustment drawer,
  locations, movement ledger); Quotes (list, approvals, guided builder, detail, edit);
  Orders (list, fulfillment board, builder, detail); Billing (overview, invoices, create,
  detail with payments, payments); Finance (overview, receivables, expenses); HR (overview,
  directory, create, profile, departments); Reports (catalog + 8 reports with CSV export).
- PI workspace: overview, 3-panel inbox (thread, takeover, composer, context panel),
  handoff queue by status, agents (list, configuration wizard, detail, versions with diff
  and rollback, tools), WhatsApp (connection, status, webhook events with replay),
  knowledge (overview, sources, documents, ingestion), analytics (6 sections), settings
  (10 sections).
- Admin: settings, members, roles and permission matrix, role editor, branches,
  departments, environments, audit log, platform products, notifications, account.

### Data modes

`NEXT_PUBLIC_DATA_MODE=live` calls the API through the same-origin `/api/v1` proxy.
Otherwise the app runs on fictional in-browser sample data, marked "Sample data" in the
header. Sample data covers a retail workspace (Northwind), a services workspace
(Brightline) and an empty staging environment for first-use states. Container builds
default to live mode.

- Business modules: live adapters call the implemented endpoints; demo adapters mirror the
  same contracts and key business rules.
- PI: there is no PI API yet. The live adapter reports "PI isn't connected in this
  environment yet" instead of returning data. PI screens are demonstrable only in sample
  mode.

## Backend (apps/api)

Implemented since Stage 2 (single migration `0002_business_platform_pi`):
- Password auth (Argon2id), opaque server-side sessions, session-bound CSRF, origin check,
  lockout, Redis rate limiting (fails open), server-held workspace/environment selection.
- RBAC: permission catalog, system roles per tenant, custom roles (no escalation), member
  management with last-owner protection.
- Environments; environment-scoped business data via composite foreign keys.
- Audit log (redacted), notifications, product registry (PI seeded), navigation registry
  with per-user order preferences.
- Business modules listed in the summary, with Decimal/NUMERIC money, state machines, row
  locking for stock and numbering, idempotent order stock effects, auto-invoicing.
- PI tables (conversations, messages, runs, tool calls, handoffs, memory, knowledge,
  WhatsApp connections and webhook receipts); optional pgvector columns added only where
  the extension can be created.

## Verification (2026-09-24)

| Check | Result |
| --- | --- |
| Web: prettier, eslint, typecheck | Pass |
| Web: production build | Pass (88 app routes) |
| Web: Playwright (16 tests: resolver unit tests, sidebar order/persist/reset/drag, role gating, product gating per environment, mobile drawer, command menu, workspace isolation, every registered route renders) | 16 passed |
| Visual QA | 14 routes at 1440px and 8 at 390px screenshotted and reviewed; no console errors or horizontal overflow; one truncation defect fixed |
| API: ruff format/check, mypy strict (121 files) | Pass |
| API: pytest with PostgreSQL 17 | 36 passed, 1 skipped (Redis worker, Linux only) |
| Alembic: upgrade, downgrade to 0001, re-upgrade, check | Pass; no drift |
| Docker / Redis worker / remote CI | Not run (unavailable locally) |
| Live web ↔ API end to end | Not run yet |

## Known gaps and limitations

- No automated tests yet for auth, RBAC, business modules, or cross-tenant isolation of the
  new tables. These are the first backend task.
- The web app has not been run against the live API; contract mismatches may exist.
- PI backend (AI gateway with OpenAI → Gemini → Groq fallback, WhatsApp webhook and worker
  pipeline, LangGraph agents, controlled tools, memory/RAG, voice/vision) is not built.
- pgvector is unavailable locally, so semantic retrieval is untested; full-text search is
  the fallback.
- Password reset and email verification are not implemented (no email delivery).
- RLS is not enabled (see ADR 0004).
- Sample-data mutations are in memory and reset on reload.
- Some list views are capped at 100 rows client-side because the API has no filter for that
  view (noted in the UI where it applies).

## Next steps

1. Backend tests: auth/session/CSRF, RBAC, tenant and environment isolation of every new
   table, money and state-machine rules, order/stock/invoice flows.
2. Run the web app in live mode against the API; fix contract mismatches; Playwright E2E
   against a real database.
3. PI backend: AI gateway and fallback, WhatsApp webhook → queue → pipeline, agents and
   controlled tools, memory/RAG, handoff/takeover enforcement, then connect the PI UI.
