# Owner OS dashboard: capability map (FT-F1, read-only audit)

Scope: the 22 areas of the Owner OS workspace. Base: `pi/p-f1` = origin/main d88b0ee (2026-10-30). Nothing was changed
outside this file. Labels: **VERIFIED** = I read the exact code path or ran the test; **SUSPECTED** = inferred.
Paths are relative to the repo root; `api` = `apps/api/app`, `web` = `apps/web/src`.

## 0. Method, and what this is not

- Read: route modules, services, permission catalog, navigation registry, web page tree, isolation/RBAC tests.
- Ran: `pytest` on every non-pi unit test file (303 passed, 51 s) and a sample of 8 files (111 passed). Integration tests
  were NOT run (need the disposable database and a lock). The pi-prefixed unit tests were not run (the full unit
  suite does not finish inside 500 s here).
- Ran an import-time route census (`create_app` routers, dummy env, no connection made): 907 route handlers. Every handler
  without an auth dependency is a known public/token/signature route (section 3.1).
- No app launched, no database, no network, no model calls. The web app was not built or type-checked (the lane has no
  `node_modules`); no UI was rendered, so "UI works" is never claimed, only "page exists and calls the API".
- The task names "PIAI": I read it as the nav item **PI** (`/pi`, the WhatsApp agent workspace in `apps/web`), and
  "Platform Products" as Settings > Products (`/settings/products`). Inventory is in the nav but not in the 22; it is
  covered in a short extra row.

## 1. Cross-cutting design (read once, applies to all areas)

| Layer | How it works | Evidence |
|---|---|---|
| Identity | server session only; no header/dev bypass | `api/modules/tenants/dependencies.py:6-12` |
| Workspace scope | per request: active membership + active environment + role grants, 409 `WORKSPACE_CHANGED` if tab header differs | `api/modules/access/dependencies.py:21-110` |
| Permission check | `Depends(require("x.read"))` on the route and/or `scope.require(...)` in the service. 166 route-level `require`, the rest in services | route census; `shared/scope.py:33-41` |
| Row isolation | every business table has `tenant_id` (+`environment_id`); `WorkspaceRepository` filters both; foreign IDs 404 | `shared/workspace_repository.py`; matrix test below |
| Audit | `audit.service.record()` inside the caller's transaction, details redacted | `api/modules/audit/service.py:35-75` |
| Events | `emit()` to the integration outbox on customer/order/invoice/quote changes | e.g. `customers/service.py:114`, `orders/service.py:~455` |
| Roles | 9 system roles + custom; custom roles cannot exceed the creator's permissions; only owners grant owner; last owner protected | `access/service.py:149-159,226-232`; `access/members.py:199-241,279-301`; `access/permissions.py:84-150` |
| Nav | permission-filtered registry (`navigation/definitions.py`); page gating + 403 state in the web shell | `web/components/app/page.tsx:192`, `components/app/states.tsx:88` |

## 2. Critical-risk cases (confirmed tenant-isolation, privacy or security faults)

**None confirmed.** I looked specifically for them and did not find one:

- Every public (unauthenticated) route is a login/registration step, a signed webhook, or an unguessable-token page
  (section 3.1). Webhooks verify signatures before storing (`pi_saas/webhook_routes.py:30-34,63-69,85-101`; integration
  inbound `integrations/webhook_routes.py:76-110`).
- Path-tenant route `GET /tenants/{tenant_id}/branches` resolves membership first (`tenants/routes.py:25-30`,
  `tenants/context.py:34-42`); the matrix test attacks it (`tests/integration/test_isolation_matrix.py:422`).
- Role/API-key escalation is blocked (`access/service.py:149-159`; `integrations/api_keys.py:92-97`). API-key secret is
  stored as SHA-256 and compared constant-time (`api_keys.py:54-55,180-181`).
- Integration credentials never appear in response schemas (`integrations/schemas.py:3-4`).
- Customer file download is workspace-scoped and served `attachment`, `nosniff`, CSP sandbox
  (`customers/file_routes.py:59-74`).

I could not execute integration tests, so none of this is "reproduced at runtime"; it is VERIFIED from code and from the
test files' contents only. The isolation proof for several areas depends on tests I did not run (see gaps, B8).

### 2.1 Security-adjacent, not confirmed faults (SUSPECTED / design risks)

- **Customer merge is destructive and low-gated** (S-1, backlog B6).
- **Denied actions are never audited** (VERIFIED, backlog B1): a security-monitoring gap rather than a leak.

## 3. Evidence tables

### 3.1 Public routes found by the census (all expected)

`/auth/*` login, register, MFA, enroll, forgot/reset; `/pi-app/auth/*` and `/pi-app/plans`; `/public/onboarding/{token}`;
`/pay/{token}`, `/pay/request/{token}` (+proof, qr.png); `/docs/{token}`; `/brain-docs/{token}/{name}`;
`/brain-visuals/{token}/{name}`; `/customer-portal/*` (OTP/MFA/shared/card); `/health/live|ready`;
`/webhooks/kapso`, `/pi-billing/stripe`, `/nori-send`, `/whatsapp`, `/webhooks/{integration_key}/{endpoint_token}`.
Not individually tested for rate limiting or token entropy (not checked).

### 3.2 Test inventory used as evidence (file names)

Unit (no DB, ran): `test_tenant_boundary.py`, `test_foundation.py`, `test_navigation.py`, `test_money.py`,
`test_integrations_adapters.py`, `test_integrations_resilience.py`, `test_integrations_http.py`, `test_integrations_sigv4.py`,
`test_integration_scheduler.py`, `test_workspace_forecast.py`, `test_workspace_agent_documents.py`.
Integration (NOT run): `test_isolation_matrix.py`, `test_tenant_isolation.py`, `test_rbac.py`, `test_business_modules.py`,
`test_money_and_states.py`, `test_order_flows.py`, `test_reports.py`, `test_notifications.py`, `test_integrations_api.py`,
`test_integration_workflows.py`, `test_workflows.py`, `test_workspaces.py`, `test_workspace_agent*.py`,
`test_customer_files.py`, `test_customer_merge.py`, `test_employee_onboarding.py`, `test_domain_events.py`,
`test_operator_*.py`, `test_api_surface.py`, `test_concurrency.py`, `test_receipts.py`. Web (Playwright, NOT run):
`web/tests/{api-client,integrations,integration-workflows,hr-onboarding,navigation-resolve,live,auth.live,integrations.live}.spec.ts`.

## 4. The 22 areas

Status vocabulary: implemented, partial, broken, disconnected, duplicated, missing. "Broken" is not used for any area:
I reproduced no failure that deserves it (a failing existing test counts; none failed once the env was correct).

### 4.1 Overview
- Purpose: landing KPIs and activity. UI: `/` (`web/features/overview/overview-page.tsx`). API: `GET /overview` (`api/modules/reports/routes.py:23`).
- Permission: `overview.read` on route; each block gated by its own key inside `ReportService.overview` (`reports/service.py:343,374,394,409,414,429,442`) so a Sales/Billing role sees only what it can read. VERIFIED.
- Models: aggregates over billing/orders/customers/inventory/quotes/hr/audit. Events: none. States: nav/loading/403 via shared page shell.
- Tests: `test_reports.py` (figures from own workspace; bounded params), `test_rbac.py`. Status: **implemented**.
- Risks: none found. The overview links to `/workflows` (orphan page, B9).

### 4.2 Pi Agent Beta (workspace assistant)
- Purpose: permission-aware assistant with tools, plans, proposals, document import. UI: `/workspace-agent`
  (`web/features/workspace-agent/*`). API: `/workspace-agent/*` (`api/modules/workspace_agent/routes.py`, 214 lines;
  context, chat, chat/stream NDJSON, read, monitor, analytics, team, proposals, decision, documents).
- Permissions: router-level `bound_workspace` (tab/workspace match); per-area checks in the service/tools
  (`service.py:176,284,305,322-347,450,495`; `toolkit.py:103,462,575`; analytics/insights use `scope.can(...)` per block).
  Writes are two-step: a proposal row, then a decision; "even owners cannot approve another user's draft"
  (`service.py:462-470`); retry after lost response does not duplicate (`:480`). Rate limit 30/60 s per user (`routes.py:46-47`); timeouts 100/110 s with a clear error event (`:68-74,103-120`). VERIFIED.
- Models: `workspace_agent/models.py` (actions table). Integrations: LLM manager with provider failover; no live model call made.
- Tests: `test_workspace_agent*.py` (4 integration files, NOT run); unit `test_workspace_agent_documents.py`, `test_workspace_forecast.py` (ran, pass).
- Status: **implemented**. Risks: `POST /documents` with `purpose=summary` needs no permission beyond membership and
  sends extracted text to the model (`routes.py:194-214`); it is rate limited and size-limited; SUSPECTED low (B12).

### 4.3 Customers / CRM
- UI: `/customers`, `/customers/new`, `/customers/[id]`, `/customers/segments`. API: `/customers` CRUD, status, notes,
  activities (`customers/routes.py`), files (`file_routes.py`), `{id}/duplicates` and `{id}/merge` (`merge.py:177-190`).
- Permissions: `customers.read` / `customers.write` at route and service (`service.py:157-171`). Models: `customers/models.py` (customers, notes, activities, files).
- Events/audit: `customer.created|updated|archived|merged` audited and emitted. File upload/delete write an activity
  entry (`file_routes.py:52,84`) but not an audit event (VERIFIED by grep; B10).
- States: 404 on foreign id; unique phone -> 409 `Conflict` (`service.py:99-100`); merge conflict message `MERGE_CONFLICT` 409.
- Tests: isolation matrix (customer, note), `test_customer_files.py`, `test_customer_merge.py`, `test_customer_pi_overview.py`, `test_customer_solution.py`. Status: **implemented**. "Segments" page: calls the same customer API; no separate backend segment model (SUSPECTED a client-side filter only; not read in detail).
- Risk: **S-1 / B6** merge is irreversible and moves orders/invoices (`merge.py:96-135`, raw `UPDATE` over every table with `customer_id`), gated only by `customers.write`, which Sales, Support and Member roles hold (`access/permissions.py` roles). SUSPECTED (design risk, not a leak).

### 4.4 Catalog
- UI: `/catalog`, `/catalog/products[/new|/[id]]`, `/catalog/categories`, `/catalog/pricing`. API: `/catalog/categories|products|variants` (`catalog/routes.py`).
- Permissions: `catalog.read/write`. Models: `catalog/models.py`. Audit: create/update product, variant, category (5 `record` calls). Events: none observed.
- Tests: `test_business_modules.py`, isolation matrix (category, product, variant). Status: **implemented**. No delete endpoint for products/categories (archive via update only; not verified in schema). Risk: none found.

### 4.5 PI (PIAI): the WhatsApp agent workspace inside Owner OS
- UI: `/pi/*` (about 30 pages: inbox, handoffs, agents + tools + versions, knowledge sources/documents/ingestion, whatsapp status/webhook/events, analytics, brain, documents, meetings, requests, review, team, settings, setup, health). The separate `apps/pi` app (about 45 pages) is the owner-facing product; its API is `/pi-app/*` (`modules/pi_saas`, 53 handlers in `app_routes.py`).
- API: `modules/pi/*routes*.py` (`routes.py` 603 lines plus config/inbox/read/brain routes). Permissions: 25 `pi.*` keys (`access/permissions.py:44-70`), nav gates each page (`navigation/definitions.py:59-460`).
- Integrations: Kapso/WhatsApp, Stripe, Nori bridge, Google Calendar, email; learning/brain code (`CLAUDE.md` code map).
- Tests: about 150 `test_pi_*` files in unit and integration; **not run in this audit** (the pi brain has its own eval, `/pi-eval`).
- Status: **implemented** (large). This audit did not read the brain/learning internals; they have their own spec and rule-coverage docs. Risk: not assessed beyond route auth (all routes authenticated or signature-checked).

### 4.6 Sales
- UI: `/sales`, `/sales/pipeline`, `/sales/leads[/[id]]`. API: `/sales/pipeline|leads` (`sales/routes.py`). Permissions `sales.read/write`. Audit: lead create/update/stage (4 calls). Events: stage moves also driven by pi deals (`orders/service.py _deal_moved`).
- Tests: `test_business_modules.py`, isolation matrix (lead). Status: **implemented**. Risk: none found.

### 4.7 Quotes
- UI: `/quotes`, `/quotes/new`, `/quotes/[id]`, `/quotes/[id]/edit`, `/quotes/approvals`. API: `/quotes` CRUD, `POST {id}/actions`, `POST {id}/order` (`quotes/routes.py`).
- Permissions: `quotes.read/write`; `actions` route takes Read but the service enforces `quotes.approve` for approve, else `quotes.write` (`quotes/service.py:268`). VERIFIED. State machine `QUOTE_STATES`; edit only in draft (`:231`); send/accept blocked after `valid_until` (`:271`). Conversion needs `orders.write` in the order service (`orders/service.py:314`).
- Audit/events: `quote.*` audited with from/to; `emit` on sent/approved. No notification to approvers when a quote reaches `pending_approval` (B5).
- Tests: `test_business_modules.py`, `test_money_and_states.py`, `test_order_flows.py`, isolation matrix. Status: **implemented**. Risk (SUSPECTED, B11): a user holding `quotes.approve` can approve their own quote; no separation-of-duties rule exists in `transition`.

### 4.8 Orders
- UI: `/orders`, `/orders/new`, `/orders/[id]`, `/orders/fulfillment`. API: `/orders` CRUD-ish, `PUT {id}/lines`, `POST {id}/actions`. Permissions: `orders.read/write`, cancel needs `orders.cancel` (`orders/service.py:408`). Confirm moves stock via idempotency-keyed inventory moves (`:~468`); cancel reverses and voids the invoice (`:479`).
- Tests: `test_order_flows.py`, `test_money_and_states.py`, `test_concurrency.py`. Status: **implemented**. Gap: an order whose invoice has any payment cannot be cancelled (invoice void raises `INVOICE_HAS_PAYMENTS`) and there is no refund path (B4).

### 4.9 Billing
- UI: `/billing`, `/billing/invoices[/new|/[id]]`, `/billing/payments`. API: `/billing/summary|invoices|payments`, `POST invoices/{id}/actions` (issue|void), `POST invoices/{id}/payments`; integration extras `POST /billing/invoices/{id}/checkout` and `/email` (`integrations/workflow_routes.py:126-143`, `business.py:148,305` require `billing.write`).
- Permissions `billing.read/write`. Money via `Decimal` with quantize, overpayment guard (`billing/service.py:336-338`), `INVOICE_STATES`. Receipts PDF (`billing/receipts.py`, `test_receipts.py`).
- Tests: `test_money_and_states.py`, `test_receipts.py`, `test_order_flows.py`; unit `test_money.py` (pass). Status: **implemented, partial on corrections**: no payment reversal, refund or credit note route exists (route census; B4). `record_payment` takes no idempotency key (`schemas.py:31-36`), so a double submit inside the balance records two payments (SUSPECTED, B7).

### 4.10 Finance
- UI: `/finance`, `/finance/expenses`, `/finance/receivables`. API: `/finance/summary|expenses`, `POST expenses/{id}/void`. Permissions `finance.read/write`. Audit: expense recorded/voided. Tests: `test_business_modules.py`, `test_reports.py`. Status: **implemented** but thin: only expenses and a summary; receivables is derived from invoices in the UI (SUSPECTED; page not read in depth). No budgets, categories API, or ledger (do not treat as a defect: not a stated requirement).

### 4.11 HR
- UI: `/hr`, `/hr/employees[/new|/[id]]`, `/hr/departments`, `/hr/onboarding[/[id]]`; public `/onboarding/[token]`. API: `/hr/headcount|employees`, onboarding link create/list/detail/approve/reject/revoke, `employees/{id}/personal` (`hr/routes.py`, `hr/onboarding_routes.py`).
- Permissions `hr.read/write`; `hr.sensitive` for compensation and personal data (`onboarding_routes.py:27,91`); the agent also asks `hr.sensitive` for salary fields (`workspace_agent/service.py:305-347`). VERIFIED. Tests: `test_rbac.py:190,221` (sensitive fields, writer cannot set salary), `test_employee_onboarding.py`, `web/tests/hr-onboarding.spec.ts`. Notifications on onboarding events (`hr/onboarding.py:608`).
- Status: **implemented**. `/hr/departments` and `/settings/departments` are two separate page components for the same `/organization/departments` data (**duplicated**, B8). Risk: public onboarding by token collects personal data; token strength and expiry not checked.

### 4.12 Reports
- UI: `/reports` plus revenue, orders, customers, quotes, inventory, employees, billing, pi pages. API: `/reports/revenue|orders|customers|quotes|inventory|employees` (`reports/routes.py`); each requires `reports.read` AND the source module's read key (`:30-72`). VERIFIED. Tests: `test_reports.py`. Status: **partial**: web routes `/reports/billing` and `/reports/pi` have no matching `/reports/billing|pi` API (the billing page likely reuses `/reports/revenue`, the pi page the pi analytics API); SUSPECTED naming only, not traced.

### 4.13 Settings
- UI: `/settings` (+ account, pi-billing, products, integrations, audit...). API: `GET/PATCH /settings/business` (`business_settings/routes.py`, `settings.manage`); business type drives capabilities (`business_settings/capabilities.py`; service business removes inventory permissions even for owners, `test_rbac.py:175`). Navigation preferences per user (`navigation/routes.py`, no extra permission, own-user data). Audit via service. Tests: `test_rbac.py`, `test_workspaces.py`. Status: **implemented**.

### 4.14 Members
- UI `/settings/members`. API `/access/members` list/add/replace roles/revoke (`access/routes.py:96-130`). Permissions `admin.members.read|manage`. Invites via email through `OutboundClient` (`routes.py:106-114`). Guards: only owners grant owner (`members.py:199-201`), owners cannot be changed by non-owners (`:240-241`), last-owner protection (`:279-301`), session `active_*` cleared on revoke (`:310`). VERIFIED. Tests: `test_rbac.py:360`, `test_auth_sessions.py`, `test_concurrency.py`. Status: **implemented**.

### 4.15 Roles and Permissions
- UI `/settings/roles[/new|/[id]]`. API `/access/permissions|roles` (`access/routes.py:30-93`). Read needs `admin.members.read`, write `admin.roles.manage`. System roles immutable (`service.py:187-188,225-226`); custom roles limited to the actor's permissions (`:149-159`); delete conflicts when still assigned. Audit `role.created|updated|deleted`. Tests: `test_rbac.py:145,259`. Status: **implemented**. Note: effective permissions are also filtered by business type (`business_permissions`), so a role editor can show a key that a workspace cannot use; this is intended (`test_rbac.py:175`).

### 4.16 Branches
- UI `/settings/branches`. API `/organization/branches` CRUD (`tenants/organization_routes.py:67-95`), plus `GET /tenants/{id}/branches`. Writes need `admin.organization.manage` and are audited. Models `branches/models.py` (no routes of their own).
- Status: **partial / disconnected**: VERIFIED that the active-branch selection (`auth/service.py:481-517`, `auth/models.py:120`) is stored on the session but no business module reads `scope.branch_id` (grep over `api/app` excluding pi: no hits); only `inventory_locations.branch_id` and `departments` reference a branch. So switching branch changes nothing in the data (B3).
- Risk: `GET /organization/branches` has no permission (`scope: Scope` only, `:67-69`) although the nav item needs `admin.organization.manage`; any workspace member can list branches (B2, VERIFIED, low, same tenant only). Tests: isolation matrix, `test_tenant_isolation.py:143,170`.

### 4.17 Departments
- UI `/settings/departments` and `/hr/departments` (duplicated). API `/organization/departments` (`organization_routes.py:98-140`). Same permission gap on the list route (B2). Department may be tenant-wide or under a branch (`test_tenant_isolation.py:181`); employees reference `department_id` (`hr/models.py:17,41`). Status: **implemented, duplicated UI**.

### 4.18 Environments
- UI `/settings/environments`. API `/environments` list/create/patch (`environments/routes.py`), `admin.environments.manage` for writes (list: Scope, any member; low). Archive of the default or current environment refused (`:92-95`). Audit on create/update. Isolation by `environment_id` on business tables is tested (`test_isolation_matrix.py` header: tenant AND environment). Status: **implemented**. No delete or rename-key; by design (archive only).

### 4.19 Integrations
- UI `/settings/integrations` (+ `[key]`, `connections/[id]`, `webhooks`, `events`, `jobs`, `failures`, `health`, `api-keys`). API: 40+ routes (`integrations/routes.py`), workflow rules/operations (`workflow_routes.py`), public inbound webhook (`webhook_routes.py`), API-key external API (`/external/customers|invoices`).
- Permissions: `integrations.read|manage|operate`, `api_keys.manage` at route level; workflow routes call `scope.require` in the handler (`workflow_routes.py:59,78,94`) or in services (`workflows.py:59`, `whatsapp_bridge.py:25-26`); file routes require the entity's own read/write key (`business.py:63-70`). Credentials write-only; OAuth callback route; HMAC-signed webhooks with secret rotation; retries, circuit breaker, rate limit, outbox (`app/integrations/*`).
- Tests: unit (adapters, resilience, http, sigv4, scheduler: all pass); integration `test_integrations_api.py`, `test_integration_workflows.py` (NOT run); web `integrations*.spec.ts` (NOT run). Status: **implemented** (the most tested area). Gap: not in the isolation matrix (B8). Failure surfaces (Failures page, Health) exist but do not raise a notification (B5).

### 4.20 Audit Logs
- UI `/settings/audit` (`web/features/admin/audit-page.tsx`). API `GET /audit/events` (`audit/routes.py:34`), `audit.read`; filters action, entity, outcome; tenant events for the current environment plus tenant-wide ones. Redaction on write. Test: isolation matrix asserts no leak (`:320-328`).
- Status: **partial**: VERIFIED that only auth records `outcome="denied"` (`auth/service.py:199,254`); the 403 handler (`core/exceptions.py:82-85`) writes nothing, so the "denied" filter shows login events only and a user probing forbidden actions leaves no trace (B1). Customer file upload/delete and pi-side config changes: pi has its own audit calls (many `record` imports); customer files do not (B10). No export/retention control (not a stated requirement).

### 4.21 Platform Products
- UI `/settings/products[/[key]]`. API `GET /products`, `POST {key}/install`, `PUT {key}/environment` (`products/routes.py`, `admin.products.manage`). Registry in code (`products/registry.py`; currently PI). Install hooks idempotent. Audit: 2 calls. Navigation items are gated by `required_product` (`navigation/definitions.py:393`). Tests: `test_workspaces.py`, `test_navigation.py` (unit, pass). Status: **implemented**. `GET /products` has no permission beyond membership (read-only list, low).

### 4.22 Notifications
- UI: bell (`components/shell/notification-center.tsx`) and `/notifications`. API `GET /notifications`, `unread-count`, `POST read` (`notifications/routes.py`), `notifications.read`; per-user audience and environment isolation (`notifications/service.py:77-97`); tests `test_notifications.py`, matrix. Mark-read of a foreign id is a silent no-op (matrix `:373`).
- Status: **partial (sparse producers)**. VERIFIED by grep: `notify(` is called only from HR onboarding, inventory low stock, and pi flows (follow-ups, problems, learning drift, check-in, lifecycle). Not from quotes (pending approval), orders, billing (payment received, overdue invoice), finance, integrations (failed delivery/sync, connection degraded) (B5). The nav hint "Receive notifications" suggests a general inbox; today it is mostly pi and stock alerts.

### 4.23 Extra: Inventory (in nav, not in the 22)
`/inventory/*`, `/inventory/locations|levels|adjustments|movements`, `inventory.read|adjust`. Idempotency-keyed movements; low-stock notification (`inventory/service.py:284-299`). Tests: matrix, `test_notifications.py`. **implemented**.

## 5. Backlog (deduplicated)

Severity: S1 security/privacy, S2 broken core workflow, S3 high-impact improvement, S4 cosmetic/hygiene. Effort S/M/L.

| ID | Symptom | Root cause | Workflow | Evidence | Sev | Effort | Regression risk | Label |
|---|---|---|---|---|---|---|---|---|
| B1 | Denied actions leave no audit trail; `outcome=denied` filter shows only login events | 403 handler does not call `audit.record`; only `auth/service.py` and `pi_saas/connections.py:381` (number conflict) use `denied` | member -> role -> permission; audit | `core/exceptions.py:82-85`; `auth/service.py:199,254`; web audit filter `features/admin/audit-page.tsx:55-66` | S1-adjacent (monitoring gap) | M (needs scope/tenant in the handler; throttle to avoid flooding) | Low-medium | VERIFIED |
| B2 | Any member can list branches, departments, environments, products | list routes use bare `Scope`, no `require` | admin | `tenants/organization_routes.py:67-69,98-100`; `environments/routes.py:49`; `products/routes.py:20` vs nav needing `admin.organization.manage` (`navigation/definitions.py:199,209`) | S3 (info exposure inside own tenant; not a cross-tenant leak) | S | Low (UI already hides) | VERIFIED |
| B3 | Choosing an active branch changes nothing in data | `active_branch_id` stored on session, never read by business modules; only inventory locations/departments carry `branch_id` | org structure | `auth/service.py:481-517`; grep: no `scope.branch_id` use outside tenants/pi | S3 | M-L (decision needed first: scope what by branch) | Medium | VERIFIED (behavior); intent SUSPECTED |
| B4 | Cannot refund or correct a recorded payment, nor cancel an order after payment | no payment reversal / credit note / refund route; void blocked when `amount_paid > 0` | customer -> quote -> order -> billing -> finance | `billing/service.py:294-297`; `orders/service.py:479`; `billing/routes.py` (only create payment) | S2 (money workflow dead end) | M-L | Medium-high (touches money, finance summary) | VERIFIED (absence) |
| B5 | Few business events notify people (quote awaiting approval, payment received, overdue invoice, integration failure) | `notify()` has producers only in HR, inventory, pi | integration -> event -> notification -> audit | grep `notify(`; `quotes/service.py:300+` emits events, no notify | S3 | M | Low | VERIFIED |
| B6 | Customer merge deletes a record and re-attributes orders/invoices with `customers.write` only | no approval/higher permission; no undo | CRM | `customers/merge.py:96-135,186-190`; roles in `access/permissions.py` | S3 (risk) | S (e.g. require a manager permission) | Low | SUSPECTED |
| B7 | Double submit of a payment records two payments | no idempotency key on `POST invoices/{id}/payments` (other integration ops do have `request_id`) | billing | `billing/schemas.py:31-36`, `billing/routes.py:70-78` | S3 | S | Low | SUSPECTED |
| B8 | Two separate departments pages; `/workflows` page not in nav | duplicated components; workflows only linked from Overview | HR / admin | `web/app/(app)/hr/departments/page.tsx` vs `settings/departments`; `features/overview/overview-page.tsx:250`, no nav entry | S4 | S | Low | VERIFIED |
| B9 | Test coverage gap: tenant-isolation matrix omits integrations, API keys, customer files, HR onboarding, agent actions | matrix built before these modules | all | ids list in `test_isolation_matrix.py` (22 entities, none of those) | S3 | M | None (tests only) | VERIFIED (gap); exploitability not shown |
| B10 | Customer file upload/delete not in audit log | only `log_activity`, no `record` | CRM | `customers/file_routes.py:52,84` | S4 | S | Low | VERIFIED |
| B11 | Quote creator can approve own quote | no separation-of-duties check | quotes | `quotes/service.py:254-277` | S3 | S | Low | SUSPECTED |
| B12 | Agent document summary has no permission beyond membership | `purpose=summary` skips `require` | Pi Agent Beta | `workspace_agent/routes.py:194-214` | S4 | S | Low | SUSPECTED |
| B13 | Some unit tests fail with a bare environment | `settings` fixture needs `DATABASE_URL` and `REDIS_URL`; with them empty, `test_integration_scheduler.py` fails (2 failed), with dummies it passes (303/303) | CI hygiene | observed runs | S4 | S | None | VERIFIED |

No item above is a confirmed tenant-isolation, privacy or security fault, so there is no "critical" section 1 entry.

## 6. Cross-workflow journeys to test (candidates only)

1. **Customer -> quote -> order -> invoice -> payment -> finance**: create customer, quote with approval, approve (check B11),
   convert, confirm (stock moves), issue invoice, pay in two parts (check B7), void/cancel after payment (B4), then compare
   Overview, Billing summary, Finance summary and Reports revenue for the same figures.
2. **Member -> role -> permission**: invite, assign a custom role, confirm nav, API 403, and an audit entry; try to
   escalate (custom role above creator, grant owner as admin); revoke and confirm the session loses the workspace.
   Include a denied attempt and check what the audit log shows (B1).
3. **Integration -> event -> notification -> audit**: connect (test connection), trigger an invoice/quote event, watch
   webhook delivery, force a failure, expect a Failures row, a notification (B5) and an audit trail.
4. **WhatsApp lead -> CRM -> deal -> quote/document -> order**: pi creates the customer, merge with a typed duplicate (B6), deal stage follows order status.
5. **Environment/branch**: create staging, switch tab, check that production rows are invisible; select a branch and note what changes (B3).
6. **Pi Agent Beta write**: propose an employee import as a low-permission user, then as HR; confirm only the proposer decides.

## 7. Prioritisation note

1. Confirmed leaks/security: none found. Do first anyway: run the integration isolation matrix and `test_rbac.py` on the
   disposable database and extend the matrix to the modules in B9 (cheapest way to turn "no leak seen" into proof).
2. Broken core workflows: B4 (no refund/reversal) is the only money dead end; it is a missing requirement, needs a product decision.
3. High-impact, low-risk: B1 (audit denied), B2 (add `require`), B5 (notifications for approvals/payments/failures), B7 (idempotency), B6/B11 (gates).
4. Cosmetic/hygiene: B8, B10, B12, B13. B3 needs an owner decision before any code.

Do not rebuild anything: each item is a targeted change in one module.

## 8. What I did not check

Integration and Playwright tests (not run); the pi brain/learning internals and the `apps/pi` customer portal beyond route
auth; web build, types, lint, accessibility, mobile layout; real rate limiting and token entropy on public routes;
database constraints and migrations (RLS or composite FKs) beyond what the tests name; performance and pagination limits;
email/WhatsApp delivery; Customer Segments and Receivables page internals; secrets handling (I never opened `.env`).
