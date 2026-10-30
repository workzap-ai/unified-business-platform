# Owner OS workspace: Product Capability Map (FT-F1 + FT-F2, read-only audit)

Base: `origin/main` 25c3922 (2026-10-31), worktree `.cache/lanes/f2map`, branch `pi/f-capability-map`. Docs only: this file and
`docs/pi-saas/pi-capability-backlog.md`. Nothing else was changed.

Paths are relative to the repo root. `api` = `apps/api/app`, `web` = `apps/web/src`, `pi` = `apps/pi/src`.

Evidence labels used everywhere:

- **VERIFIED**: I read the exact line(s) cited, or ran the census described in section 0.
- **SUSPECTED**: inferred from code I read; impact or exploitability not shown.
- **ASSUMPTION / UNVERIFIED IDEA**: kept only in section 8. Nothing in sections 1 to 7 depends on it.

Relation to the earlier `docs/pi-saas/capability-map.md` (FT-F1, 2026-10-30): that file is kept. This one re-checked its
backlog items B1 to B12 in code (all still true on 25c3922, section 7), found items it missed (SEC-1, no UI path to a
branch, the S3/DB duplicate attachment systems, no category or department edit/delete, audit filters), and adds the
F2 per-feature table. Where I did not re-read a claim from the older file, section 8 says so.

## 0. Method and what this is not

Ran (all read-only, no database, no network, no model call, no test run):

1. **Route census.** Imported `app.main.ROUTERS` with dummy `DATABASE_URL`/`REDIS_URL` (no connection opened) and walked each
   router's `dependant` tree: **508 Owner OS route handlers** (the older map's 907 also counted the `/pi-app` re-mounts of the
   same routers, `api/main.py:346-356`). Of the 247 handlers that take `workspace_scope` but no route-level `require(...)`, I
   scanned each handler body for an in-handler check and found **42 without one visible**; I read each of those (section 3.2).
2. **UI to API mismatch census.** Extracted every `apiRequest("METHOD", "/path")` call in `web/**` (**395 calls**, base
   constants resolved, path params wildcarded) and matched each to a mounted route: **0 calls without a matching route**.
   Reverse: every non-`/pi`, non-`/operator`, non-`/auth` route has a web caller except the ones in section 3.3.
   Limits: calls made through `fetch`, `EventSource` or anchors are not counted; wildcard matching can hide a method or
   segment mix-up; it proves "a route of that shape exists", not "the response schema matches".
3. **Navigation census.** `build_registry()` gives **81 nav definitions**; every `route` resolves to an existing
   `web/app/(app)/**/page.tsx` (0 orphan nav items). 124 `page.tsx` files exist in `web/app/(app)`, so some pages are
   reachable only by link (e.g. `/workflows`, `/account`, `/workspaces/new`).
4. Read the module code cited per row. I did **not** read the pi brain/learning internals (own spec and `/pi-eval`).

Not done: no UI rendered, no web build or type-check, no pytest/Playwright run (integration tests need the disposable
database and the lock; unit tests were not re-run because the older map already did and nothing in code changed since).
"Test coverage" below therefore means **tests that exist and what they assert**, not tests that pass today.

## 1. Critical findings (G3)

### SEC-1: unverified-email identity squatting lets an outsider inherit a later invitation (code-verified, NOT reproduced)

Severity: High to Critical for tenant isolation (a person with no relationship to a workspace ends up with a member's roles
in it). I did not fix it. Evidence chain, all VERIFIED by reading:

1. Anyone can register any email and is signed in at once: `api/modules/auth/service.py:105-136` (`register` creates the
   user, a credential with the chosen password, a tenant, and `_issue`s a session). Open registration is the default:
   `api/core/config.py:53` (`allow_registration: bool = True`). The only throttle is 5 per hour per IP
   (`api/modules/auth/routes.py:151`).
2. Email ownership is never required. `email_verified_at` is only ever **set** (`auth/service.py:403-425,462-464`); a grep of
   `api/**` finds no place that reads it as a gate, and the docstring says so: "nothing is gated on verification yet"
   (`auth/service.py:361-364`).
3. When a workspace admin later invites that email, `MemberService.add` finds the existing user and does **not** touch the
   credential, send a token or require verification: `api/modules/access/members.py:100-130` (existing user path),
   `:151-153,169-170` (existing person gets only a "sign in" link). This is intended and pinned by a test:
   `test_adding_an_existing_user_as_a_member_never_touches_their_password`
   (`api/tests/integration/test_auth_sessions.py:497-511`).
4. Sign-in is password only unless the person enrolled a face or fingerprint: `auth/routes.py:196-203`,
   `auth/mfa.py:142-170`. The squatter chooses whether to enrol.

Result: attacker registers `cfo@victim-corp.com` first, a victim-corp admin invites that address, the attacker signs in with
their own password and holds the roles the admin granted, in the admin's workspace (all environments the roles reach).
Preconditions: registration enabled (default), attacker guesses an address that will be invited, and registers before the
real owner of the mailbox ever does. The "set a password from the emailed link" flow (`accept_invite`, `auth/service.py:434-474`)
protects only **new** accounts, which is exactly the case the squatter avoids.

Not reproduced (no runtime). Smallest safe fix and tests are in the backlog (item 1). Related, lower: the inviter receives the
raw invite link in the API response (`members.py:139-141,167`, UI `web/features/admin/members-page.tsx:448-451`) so an admin
can set the first password of an account bound to someone else's address (accepted design as a fallback when email fails;
the same fix covers it).

No other critical tenant-isolation, privacy or security fault was found. Items looked for and not found are in section 3.

## 2. Cross-cutting design (read once, applies to every area)

| Layer | How it works | Evidence |
|---|---|---|
| Identity | server-side session; workspace headers `x-workspace-tenant/environment` are optional extra staleness checks (mismatch gives 409 `WORKSPACE_CHANGED`), the server-held selection is authoritative | `api/modules/access/dependencies.py:20-32` |
| Workspace scope | every request re-reads membership, active environment, role grants and business type in one query; revoked membership gives 403 | `access/dependencies.py:37-96` |
| Permission check | declarative `Depends(require(...))` (132 routes) or in-handler/service `scope.require` (the rest); pi routes use `PiService.require` which also checks the product install | `access/dependencies.py:117-125`; `pi/service.py:56-63,111-112` |
| Row isolation | `WorkspaceRepository` filters tenant and environment; foreign ids are 404 | `shared/workspace_repository.py`; `tests/integration/test_isolation_matrix.py:1-6` |
| Audit | `record()` in the caller's transaction, details redacted | `api/modules/audit/service.py:35-75` |
| Rate limits | Redis fixed window, **fails open** when Redis is down (documented) | `api/core/rate_limit.py:29-31,56-60` |
| Demo data | `NEXT_PUBLIC_DATA_MODE=demo` swaps services for in-browser fixtures with a visible marker | `web/lib/data-mode.ts:1-18` |
| Roles | 9 system roles + custom; custom roles cannot exceed the creator; only owners grant owner; last owner protected | `access/service.py:145-159,184-190`; `access/members.py:199-201,236-244,275-301` |

## 3. Search for critical classes, with results

### 3.1 Public (unauthenticated) routes

All are login/registration steps, signed webhooks or unguessable-token pages. Token pages are rate limited: HR onboarding
(`hr/onboarding_routes.py:100-105`, token `secrets.token_urlsafe(32)` stored as SHA-256 with expiry,
`hr/onboarding.py:272-273,337-341`), `/pay/{token}` (`pi_saas/payment_routes.py:591-592,618-619,643-644`),
`/pay/request/{token}` (`customer_payment_routes.py:290-291`), brain documents and visuals
(`pi/brain_doc_routes.py:348-349`, `pi/brain_visual_routes.py:60-61`), invite acceptance (`auth/routes.py:167`).
Brain-document links are a signed token derived from the doc id (`pi/brain_docs.py:189-213`); I did not check revocation.

### 3.2 Handlers with no visible route-level permission (42 found, all read)

- `/organization`, `/organization/branches`, `/organization/departments`, `/environments`, `/products`, `/settings/business` (GET),
  `/navigation*`: membership only. Reads of the workspace's own structure; see backlog item 7. Navigation preferences are own-user data.
- `/workflows*` (6): list and detail filter on `requested_by == scope.user_id` and `t.available(scope)`
  (`api/workflows/routes.py:53-66`); start and approve require the tool's permission in the service (`workflows/service.py:28,161`).
- `/integrations/capabilities`, `PUT .../workflow`, `activate-pi`, `/billing/invoices/{id}/checkout|email`, `/files/*`: the handler
  body or `business.entity` requires the entity's own read/write key or `integrations.manage|operate`
  (`integrations/business.py:63-70,148,305`; `integrations/whatsapp_bridge.py:25-26`; `integrations/workflows.py:59`;
  `modules/integrations/workflow_routes.py:59,78,94`).
- `/pi/conversations*`, `/pi/conversations/.../messages`, `actions/{action}`, `/pi/requests/{id}/answer|meeting`,
  `/pi/conversations/.../approve|reject`: checks live in `PiService.require("pi.inbox.reply")` (`pi/service.py:312,363`),
  `meetings.arrange` (`pi_saas/meetings.py:167`), `requests.answer` (`pi_saas/requests.py:480`). `auto_arrange` reaches `arrange` and
  so the check (`meetings.py:321-362`). The approve/reject handlers (`pi/inbox_routes.py:238,280`) call `_pending_reply`; I did not
  read it to the end (section 8).
- `/workspace-agent/*` (10): router-level `bound_workspace` plus per-block checks in the service and tools (`workspace_agent/service.py:176,284,305,322-347`).
  `POST /documents purpose=summary` needs only membership (`workspace_agent/routes.py:185-214`), rate limited 30/min (`:56`).

### 3.3 Backend routes with no web caller (non-pi, non-operator)

Downloads and PDFs reached by anchors (`/customer-files/{id}/download`, `/customers/{id}/pi-overview.pdf`, `/files/{id}/download`),
external API-key routes (`/external/customers`, `/external/invoices/{id}`), OAuth callback, webhooks, health, and
**`PATCH /organization/departments/{id}` (rename a department): no UI calls it** (`web/features/admin/service.ts:187-198` has list and create only).
`POST /workspace-agent/chat/stream` is called by `fetch` streaming (not counted by the census).

### 3.4 Looked for and not found

Cross-tenant reads through ids (all repositories scope tenant+environment; the matrix test attacks 22 entities); role or API-key
escalation (`access/service.py:149-159`; `integrations/api_keys.py:92-100`, keys also die with the creator's membership,
`api_keys.py:178-198`, so the "revoked member keeps an API key" idea is **false**); customer-file XSS (served `attachment`,
`nosniff`, CSP sandbox, `customers/file_routes.py:59-74`; type from magic bytes, `customers/files.py`); merge writing across tenants
(every raw `UPDATE` carries tenant+environment when the table has both, and `drop_id` was loaded through the scoped repository first,
`customers/merge.py:93-135`).

## 4. Area traces and classification (the 22 areas, plus Inventory)

Class: implemented, partial, broken, disconnected, duplicated, missing. "broken" needs a reproduced failure; I reproduced
none (no runtime), so no area is classed broken. A code path that cannot do what its screen promises is classed partial or
disconnected, with the proof cited.

| # | Area | UI | API | DB | Permissions | Integrations | Errors / states | Workflow | Class |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Overview | `web/features/overview/overview-page.tsx`, `/` | `GET /overview` `reports/routes.py:23` | aggregates | `overview.read`; each block by its own key `reports/service.py:343,374,394,409,414,429,442` | none | shared 403/empty/skeleton shell | landing; links to `/workflows` (`overview-page.tsx:250`, not in nav) | implemented |
| 2 | Pi Agent Beta | `web/features/workspace-agent/*`, `/workspace-agent` | `/workspace-agent/*` (`routes.py`, 214 lines) | `workspace_agent_actions`, `workspace_tasks` | per block, two-step proposal/decision, own drafts only | LLM manager with failover | rate limit 30/min `routes.py:56`; 409 on workspace change `:30-34`; NDJSON stream | ask, read, propose, decide, import employees from a file | implemented |
| 3 | Customers / CRM | `/customers`, `/new`, `/[id]`, `/segments` | `/customers*`, `/customer-files*`, `{id}/duplicates|merge` | `customers`, `customer_notes`, `customer_activities`, `customer_files` | `customers.read|write` route and service | emits events; pi writes here | 409 on duplicate phone `service.py:99-101`; `MERGE_CONFLICT`; 10 MB file cap `files.py` | create, tag, note, file, merge, archive | implemented (Segments is partial, row F-CRM-5) |
| 4 | Catalog | `/catalog`, `/products*`, `/categories`, `/pricing` | `/catalog/categories|products|variants` | `catalog_categories|products|variants` | `catalog.read|write` | none | variant/product status archive via PATCH | create product, variants, price | partial: categories cannot be edited or archived (row F-CAT-3) |
| 5 | PIAI (the `PI` nav item, WhatsApp agent) | `web/app/(app)/pi/**` (30 pages); owner product is `apps/pi` (59 pages) | 203 workspace-scope handlers under `/pi*` (`modules/pi`, `modules/pi_saas`) | many `pi_*` tables | `pi.*` keys, `PiService.require` also checks install | Kapso/WhatsApp, Stripe, Google Calendar, Shopify, email, LLM | per-route; see the pi docs | inbox, handoffs, knowledge, agents, brain, deals, meetings, payments | implemented (internals not audited, section 8) |
| 6 | Sales | `/sales`, `/pipeline`, `/leads*` | `/sales/pipeline|leads`, stage PUT | `sales_leads` | `sales.read|write` | pi deals move stages (`orders/service.py:_deal_moved`) | stage machine `sales/service.py:26-28`; won/lost are terminal | lead, stage, win | implemented |
| 7 | Quotes | `/quotes`, `/new`, `/[id]`, `/edit`, `/approvals` | `/quotes*`, `{id}/actions`, `{id}/order` | `quotes`, `quote_lines` | read/write; approve needs `quotes.approve` `service.py:268`; convert needs `orders.write` | event on sent/approved | `QUOTE_EXPIRED` on send/accept `:271`; edit in draft only | draft, submit, approve, send, accept, convert | implemented (friction rows F-QUO-2/3) |
| 8 | Orders | `/orders`, `/new`, `/[id]`, `/fulfillment` | `/orders*`, `PUT lines`, `actions` | `orders`, `order_lines` | `orders.read|write`, cancel `orders.cancel` `service.py:408` | stock moves, invoice creation, pi deal sync | idempotent stock keys `:468-475`; cancel blocked by payments | confirm, fulfil, cancel | partial (no way to cancel a paid order, F-ORD-2) |
| 9 | Billing | `/billing`, `/invoices*`, `/payments` | `/billing/*`; integration extras `checkout`, `email`, `payment-link/send` | `invoices`, `invoice_lines`, `payments` | `billing.read|write` | Stripe checkout, email, receipts PDF | `OVERPAYMENT` `service.py:338`; `INVOICE_HAS_PAYMENTS` `:301` | issue, pay, void | partial (no refund, reversal, credit note; no payment idempotency) |
| 10 | Finance | `/finance`, `/expenses`, `/receivables` | `/finance/summary|expenses`, `expenses/{id}/void` | `expenses` | `finance.read|write` | none | receivables truncation notice `receivables-page.tsx:144-146` | record and void expenses, read figures | partial (thin: no categories, budgets, ledger; none were requirements I could find) |
| 11 | HR | `/hr`, `/employees*`, `/departments`, `/onboarding*`, public `/onboarding/[token]` | `/hr/*`, `/public/onboarding/{token}` | `employees`, `employee_onboardings` | `hr.read|write`, `hr.sensitive` for pay and personal data | notify on onboarding events `onboarding.py:608` | token expiry, 20-128 chars `:272-293,528-533` | employee records, link-based onboarding with approve/reject | implemented (departments page is duplicated, F-HR-5) |
| 12 | Reports | `/reports/*` (9 pages) | `/reports/revenue|orders|customers|quotes|inventory|employees` | none (queries) | `reports.read` AND the source module's read key `routes.py:30-72` | none | CSV export `web/features/reports/csv.ts` | read, export | implemented. `/reports/billing` and `/reports/pi` have no same-named API by design: they compose `billing summary`, `finance summary`, `reports/revenue` (`billing-report.tsx:49-57`) and the pi analytics API (`pi-report.tsx`) |
| 13 | Settings | `/settings` and children | `GET|PATCH /settings/business`, `/organization` | `business_settings`, `tenants` | `settings.manage` (GET is membership only) | none | `capabilities.py` removes inventory for service businesses even for owners (`test_rbac.py:175`) | business type, currency, due days, thresholds | implemented |
| 14 | Members | `/settings/members` | `/members` list/add/roles/revoke `access/routes.py:96-135` | `memberships`, `membership_roles`, `member_invite_tokens` | `admin.members.read|manage` | invite email | guards for owner, last owner, self `members.py:199-201,236-244,275-301` | add, change roles, revoke (clears active session) | implemented, with SEC-1 |
| 15 | Roles and Permissions | `/settings/roles`, `/new`, `/[id]` | `/permissions`, `/roles*` `access/routes.py` | `roles`, `role_permissions` | read `admin.members.read`; write `admin.roles.manage` | none | system roles immutable `service.py:187-188`; escalation blocked `:149-159` | create, edit, delete custom role | implemented |
| 16 | Branches | `/settings/branches` | `/organization/branches` CRUD `organization_routes.py:66-95`, `PUT /auth/session/workspace` accepts `branch_id` | `branches` (composite FKs, RESTRICT) | writes `admin.organization.manage`; list has none | none | delete blocked by dependants (`tenants/service.py:92-97`) | create/rename/delete only | **disconnected** (F-BRA-2) |
| 17 | Departments | `/settings/departments` and `/hr/departments` | `/organization/departments` (list, create, PATCH rename; **no DELETE**) | `departments` | writes `admin.organization.manage`; list has none | none | RESTRICT FK to branch | create; rename has no UI | **duplicated** UI, partial CRUD |
| 18 | Environments | `/settings/environments` | `/environments` list/create/patch | `environments` | writes `admin.environments.manage`; list membership only | none | refuse archive of default/current (`routes.py` ~92-95, carried) | create staging, archive | implemented |
| 19 | Integrations | `/settings/integrations/*` (10 pages) | 40+ routes + public webhook + `/external/*` | 12 `integration_*` tables, `api_keys` | `integrations.read|manage|operate`, `api_keys.manage` | S3, Stripe, email, OAuth, webhooks, WhatsApp bridge | audited, retries, circuit breaker, signed deliveries (`integrations/service.py:217+`) | connect, test, sync, replay, rotate | implemented |
| 20 | Audit Logs | `/settings/audit` (`web/features/admin/audit-page.tsx`) | `GET /audit/events` `audit/routes.py:34-65` | `audit_events` | `audit.read` | none | filters action prefix, entity, outcome | read | partial (F-AUD-1/2) |
| 21 | Platform Products | `/settings/products*` | `/products`, `{key}/install`, `{key}/environment` | `platform_products`, 2 install tables | writes `admin.products.manage` | pi product hooks | idempotent install | install and enable PI | implemented |
| 22 | Notifications | bell `web/components/shell/notification-center.tsx`, `/notifications` | `GET /notifications`, `unread-count`, `POST /read` | `notifications`, `notification_reads` | `notifications.read`; audience by permission or user | none | mark-all handles more than 500 (`test_notifications.py:37`) | read, mark read | partial (few producers, F-NOT-2) |
| 23 | Inventory (not in the 22) | `/inventory/*` | `/inventory/*` | `inventory_locations`, `stock_levels`, `stock_movements` | `inventory.read|adjust` | low-stock notify `service.py:280-300` | idempotent moves | stock, locations, adjustments | implemented |

## 5. F2 feature table (one row per feature)

Columns: **Purpose / implementation and dependencies**; **Roles** (who can do it, from `access/permissions.py:84-150`; "o/a" = owner and admin hold every key); **APIs, tables, integrations**; **Known bugs and friction**;
**Security, privacy, tenant risk**; **Tests that exist**; **Recommendation** as priority (P0 to P3) / effort (S, M, L) / outcome.
Class tokens: IMPL, PART, DISC (disconnected), DUP, MISS, BROKEN (none).

| ID | Feature | Class | Purpose and implementation | Roles | APIs, tables, integrations | Bugs and friction | Security, privacy, tenant risk | Tests | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| F-OVR-1 | Overview KPIs | IMPL | blocks per module, each gated by `s.can(...)` (`reports/service.py:343-442`) | any with `overview.read`; sees only blocks they may read | `GET /overview`; reads billing, orders, customers, inventory, quotes, hr, audit | link to `/workflows` has no nav entry (`overview-page.tsx:250`) | none found | `test_reports.py::test_report_figures_come_from_own_workspace_data`, `::test_report_and_list_parameters_are_bounded`, `test_rbac.py::test_system_role_route_matrix` | P3 / S / decide whether `/workflows` joins the nav |
| F-AGT-1 | Chat, read, analytics, monitor | IMPL | LLM assistant with per-block permission checks | all members (no nav permission) | `/workspace-agent/chat|read|analytics|monitor`; `workspace_agent_actions` | none observed | summary mode needs only membership (`routes.py:185-214`), bounded by rate limit and size | integration `test_workspace_agent.py`, `_analytics.py`, `_insights.py`, `_toolkit.py`; unit `test_workspace_agent_documents.py`, `test_workspace_forecast.py` | P3 / S / require a read key per summary source or document the intent |
| F-AGT-2 | Proposals (writes) | IMPL | two-step proposal then decision, own drafts only, idempotent retry (`service.py:462-480`, carried) | per target permission | `/workspace-agent/proposals`, `team`, `documents` | none observed | design is sound | `test_workspace_agent_toolkit.py` | none |
| F-CRM-1 | Customer CRUD, tags, status | IMPL | list/search/create/patch/status | read: all with `customers.read`; write: sales, support, member, manager, o/a | `/customers*`; `customers` | phone uniqueness is the only dedupe at write time (`service.py:99-101,136`) | none found | isolation matrix (customer, note); `test_money_and_states.py::test_expense_lead_and_customer_state_rules` | none |
| F-CRM-2 | Notes, activity timeline | IMPL | notes and activity log entries from every module (`customers/service.py:29`) | `customers.write` | `/customers/{id}/notes`; `customer_notes`, `customer_activities` | none | notes may hold personal data; isolated by matrix | matrix `note` | none |
| F-CRM-3 | Customer files | IMPL | upload (10 MB, magic-byte type), list, download, delete; stored in the database (`files.py`) | read `customers.read`, write `customers.write` | `/customers/{id}/files`, `/customer-files/{id}`; `customer_files` | upload/delete write an activity entry but **no audit event** (`file_routes.py:52,84`); no per-customer quota | safe serving (`:59-74`) | `test_customer_files.py` | P2 / S / record audit events; consider object storage later |
| F-CRM-4 | Duplicates and merge | IMPL | likeness list and irreversible merge, moves every table with `customer_id` (`merge.py:93-135`) | any holder of `customers.write` (sales, support, member, manager, o/a) | `/customers/{id}/duplicates|merge` | no undo, no preview of moved rows in the response (only audit `moved`) | **low gate for an irreversible, money-moving action** (SUSPECTED, backlog 9) | `test_customer_merge.py` | P2 / S / separate permission or manager-only |
| F-CRM-5 | Segments | PART | page shows built-in segments (all active, tags whatsapp and vip, archived) as client filters that call the same list API for counts (`customer-segments-page.tsx:29-60,119-147`) | `customers.read` | `GET /customers?status|tag`; no segment table | segments are not definable by the user; list sample limited | none | none specific (web `service-first.spec.ts` does not target it; not verified) | P3 / M / saved segments only if a customer asks |
| F-CAT-1 | Products and variants | IMPL | create, edit, status, SKU variants, price | read `catalog.read`; write sales/manager/o/a hold `catalog.write` via `_pick` | `/catalog/products|variants`; 3 tables | no delete (archive by status only) | none | matrix (product, variant); `test_order_flows.py` | none |
| F-CAT-2 | Pricing page | IMPL | read-only price view over variants | `catalog.read` | same API | none observed | none | none specific | none |
| F-CAT-3 | Categories | PART | create and list only: API has POST and GET, no PATCH or DELETE (route census); UI service has the same two calls (`web/features/catalog/service.ts:56-58`) | `catalog.write` | `/catalog/categories` | a typo or obsolete category can never be fixed or removed | none | matrix (category) | P2 / S / add PATCH (name, status) and UI dialog |
| F-PI-1 | WhatsApp inbox and handoffs | IMPL | conversations, takeover, return to AI, assign, notes, tags, approve drafts | `pi.inbox.*`, `pi.handoffs.manage` | `/pi/conversations*`, `/pi/handoffs*` | not audited by me beyond routes | checks inside `PiService.require` (`pi/service.py:312,363`) | about 150 `test_pi_*` files | see pi docs |
| F-PI-2 | Agents, knowledge, brain, settings | IMPL | agent versions, tools, knowledge sources/documents, brain review and learning | `pi.agents.manage`, `pi.knowledge.manage`, `pi.settings.manage` | `/pi/agents*`, `/pi/knowledge*`, `/pi/brain-*` | not assessed | none found; the parent `pi` nav item carries the product gate (nav census) | `test_pi_*`; web `pi-services.spec.ts`, `pi-solutions.spec.ts`, `pi-pagination.spec.ts` | none |
| F-PI-3 | Deals, payments, meetings, requests | IMPL | pi deals board, proposals, pay links, meeting board, staff requests | `pi.work.*`, `pi.bookings.*`, `billing.write` | `/pi/deals*`, `/pi/payment-requests*`, `/pi/meetings*`, `/pi/requests*` | `answer` and `meeting` have no route-level `require`; the check is in `answer`/`arrange` (`requests.py:480`, `meetings.py:167`) | verified chain; fragile pattern | `test_pi_team_board.py`, `test_pi_*` | P3 / S / add route-level `Depends(require(...))` to make it declarative |
| F-SAL-1 | Leads, pipeline stages | IMPL | stage machine new, qualified, proposal, won, lost | `sales.read|write` (sales, manager, o/a) | `/sales/*`; `sales_leads` | winning a lead does not create a customer, quote or order by itself (`sales/service.py:95-103`: customer link is optional); manual hand-off | none | matrix (lead); `test_money_and_states.py::test_pipeline_totals_never_mix_currencies` | P3 / M / ask the owner whether win should offer "create quote" |
| F-QUO-1 | Quote lifecycle | IMPL | draft, pending approval, approved, sent, accepted/rejected/expired/cancelled | write: sales, manager, o/a; approve: manager, o/a | `/quotes*`; 2 tables; event on sent/approved | none observed | creator with `quotes.approve` can approve own quote (SUSPECTED, `quotes/service.py:268-281`) | `test_money_and_states.py::test_quote_state_machine_rejects_illegal_moves`, `::test_expired_quote_cannot_be_sent_or_accepted`, `::test_accepted_quote_prices_carry_over_even_if_catalog_changes`, `::test_quote_totals_round_half_up_at_every_step` | P2 / S / optional separation-of-duties setting |
| F-QUO-2 | Approval inbox | PART | `/quotes/approvals` page lists pending; **no notification** when a quote reaches `pending_approval` (grep: no `notify` outside HR, inventory, pi) | `quotes.approve` | `GET /quotes?status` | approver finds out only by opening the page | none | none for notification | P1 / S / `notify(..., permission="quotes.approve")` on submit |
| F-QUO-3 | Expiry | PART | `valid_until` blocks send and accept (`:271`) but status never changes to `expired` on its own: no job (`worker.py:104-122`); manual `expire` action only | write | `POST /quotes/{id}/actions` | stale "sent" quotes stay open in pipeline numbers | none | `test_expired_quote_cannot_be_sent_or_accepted` | P3 / S / daily sweep |
| F-QUO-4 | Convert quote to order | IMPL | `POST /quotes/{id}/order`, prices carry over | `quotes.write` + `orders.write` | order service `:314` carried | none | none | `test_order_flows.py::test_quote_to_order_to_stock_invoice_and_payments` | none |
| F-ORD-1 | Order lifecycle and stock | IMPL | confirm deducts stock with idempotency keys; cancel returns stock and voids the invoice | write sales, manager, o/a; cancel manager, o/a (`orders.cancel`) | `/orders*`; stock moves; auto-invoice | price change blocks confirming a draft (`PRICE_CHANGED`) | none | `test_order_flows.py` (4 tests: restore, rollback, untracked, idempotent), `test_concurrency.py`, `test_money_and_states.py::test_order_state_machine_and_locked_fields` | none |
| F-ORD-2 | Cancel after payment | MISS | `_cancel_effects` voids the invoice first and `act("void")` refuses when `amount_paid > 0` (`orders/service.py:477-480`, `billing/service.py:299-302`) | `orders.cancel` | no refund route (route census) | the user gets `INVOICE_HAS_PAYMENTS` with no next step | none | `test_money_and_states.py::test_invoice_and_payment_rules` (asserts the refusal) | P1 / M-L / decide credit-note vs refund, then add (backlog 2) |
| F-BIL-1 | Invoices | IMPL | draft, issue, void; due date from settings (`billing/service.py:288-320`) | `billing.write` (accountant, manager, o/a) | `/billing/invoices*` | none | none | `test_money_and_states.py::test_invoice_and_payment_rules`, `test_order_flows.py` | none |
| F-BIL-2 | Payments | PART | record payment with overpayment guard; **no idempotency key** (`billing/schemas.py:31-37`, route `routes.py:70-78`) so a double click of the same amount inside the balance records two | `billing.write` | `POST /billing/invoices/{id}/payments`; `payments` | duplicate entry; no reversal | none | `::test_invoice_and_payment_rules` (overpayment, partial) | P1 / S / client request id with unique constraint (backlog 5) |
| F-BIL-3 | Receipts PDF | IMPL | receipt rendered and kept as a protected customer file (`RECEIPT_KEPT`, `file_routes.py:79-80`) | `billing.read` | `billing/receipts.py` | none | none | `test_receipts.py` | none |
| F-BIL-4 | Online payment (checkout, email, payment link) | IMPL | Stripe checkout and mailing via the integration platform | `billing.write` + integration permissions | `/billing/invoices/{id}/checkout|email|payment-link/send` | handler-level checks only (`integrations/business.py:148,305`; `payment_link.py:126`) | verified | `test_integration_workflows.py`; unit `test_integrations_*` | none |
| F-FIN-1 | Expenses | IMPL | record and void | `finance.write` (accountant, o/a) | `/finance/expenses*`; `expenses` | free-text category (not checked further) | none | `test_money_and_states.py::test_expense_lead_and_customer_state_rules`, `test_business_modules.py` | none |
| F-FIN-2 | Finance summary and receivables | PART | summary figures plus an open-invoice view built from two invoice list calls capped at 100 each, with a truncation notice (`receivables-page.tsx:27,118-146`) | `finance.read` | `/finance/summary`, `/billing/invoices` | beyond 100 open invoices the page is incomplete (disclosed) | none | `test_business_modules.py`, `test_reports.py` | P3 / S / server-side aging endpoint |
| F-HR-1 | Employees | IMPL | create, edit, status; sensitive pay and personal fields only with `hr.sensitive` | `hr.read|write`; sensitive only if granted | `/hr/employees*`; `employees` | none observed | privacy gate verified by test | `test_rbac.py::test_sensitive_hr_fields_and_balances_follow_permissions`, `::test_hr_writer_without_sensitive_access_cannot_set_salary` | none |
| F-HR-2 | Link-based onboarding | IMPL | tokenised public form, approve, reject, revoke, expiry | `hr.write` to issue; public form by token | `/hr/onboarding*`, `/public/onboarding/{token}`; `employee_onboardings` | none | token hashed, expiring, rate limited (`:272-293,337-341`; `onboarding_routes.py:100-105`) | `test_employee_onboarding.py`; web `hr-onboarding.spec.ts` | none |
| F-HR-3 | Headcount and reports | IMPL | headcount and employee report | `hr.read` | `/hr/headcount`, `/reports/employees` | none | none | `test_business_modules.py` | none |
| F-HR-5 | Departments page (HR copy) | DUP | `web/features/hr/departments-page.tsx` (367 lines) and `web/features/admin/departments-page.tsx` (242 lines) both render and create over `/organization/departments` | HR copy needs `hr.read`, admin copy `admin.organization.manage`; the API write needs the latter | same API | two UIs drift; the HR copy lets an HR user open a create dialog that the API will 403 (not reproduced, SUSPECTED) | none | `test_tenant_isolation.py:146,170` (service level: create, delete, RESTRICT) | P3 / S / one component, two entry points |
| F-REP-1 | Module reports and CSV | IMPL | six report APIs, each requiring `reports.read` and the source key (`reports/routes.py:30-72`) | accountant, manager, viewer, o/a | `/reports/*` | none | verified gate | `test_reports.py` | none |
| F-REP-2 | Billing and Pi report pages | IMPL | compose existing APIs (no dedicated endpoint) | `reports.read` + `billing.read`/`pi.analytics.read` | see row 12 | none | none | none specific | none |
| F-SET-1 | Business settings | IMPL | type, currency, due days, low-stock threshold, auto-invoice | `settings.manage`; GET membership only | `/settings/business`; `business_settings` | none | GET leaks only the workspace's own settings | `test_rbac.py::test_service_business_removes_inventory_permissions_even_for_owners`, `test_workspaces.py` | none |
| F-SET-2 | Navigation preferences | IMPL | per-user ordering | any member | `/navigation/preferences/{section}`; `navigation_preferences` | none | own data only | unit `test_navigation.py`; web `navigation-resolve.spec.ts` | none |
| F-MEM-1 | Add, change roles, revoke member | IMPL | owner/last-owner/self guards; revoke clears session selection (`members.py:275-315`) | `admin.members.manage` | `/members*`; `memberships`, `membership_roles`, `member_invite_tokens` | none | **SEC-1** (existing unverified account takes a new membership) | `test_rbac.py::test_owner_protection_last_owner_and_admin_limits`, `test_auth_sessions.py:461-511`, `test_workspaces.py::test_member_permissions_revocation_and_foreign_roles` | P0 / S-M / see backlog 1 |
| F-ROL-1 | Custom roles | IMPL | create, edit, delete; no escalation beyond creator | `admin.roles.manage` | `/roles*`; `roles`, `role_permissions` | none | verified | `test_rbac.py::test_custom_roles_cannot_escalate_beyond_their_creator`, `::test_system_role_route_matrix` | none |
| F-BRA-1 | Branch records | IMPL | create, rename, delete with FK RESTRICT | `admin.organization.manage` | `/organization/branches`; `branches` | any member can list (`organization_routes.py:66-69`) | low (same tenant) | `test_tenant_isolation.py:133,177,186-213`, matrix | P2 / S / add `require` to the list routes (backlog 7) |
| F-BRA-2 | Active branch | DISC | `PUT /auth/session/workspace` accepts `branch_id` (`auth/schemas.py:100-104`), stores `active_branch_id` (`auth/service.py:481-517`), copies to `scope.branch_id` (`access/dependencies.py:104`). **No module reads `scope.branch_id`** (grep over `api/**` outside tenants/pi: no hits) and **the web never sends it** (`web/features/auth/service.ts:116-119`) | n/a | none | selecting a branch is impossible in the UI and would change nothing | none | none | P2 / S now, M-L later / decide what a branch scopes (backlog 6) |
| F-DEP-1 | Department records | PART | create and list; PATCH rename exists with no UI (`web/features/admin/service.ts:187-198`); **no delete route** | `admin.organization.manage` | `/organization/departments` | cannot rename (UI) or remove | none | `test_tenant_isolation.py:146,170` (a service-level department delete exists and is tested, but no route exposes it) | P3 / S / add UI rename, API delete with RESTRICT |
| F-ENV-1 | Environments | IMPL | production, staging, development; archive | `admin.environments.manage`; list any member | `/environments`; `environments` | no delete or key rename (by design) | list open to members (low) | `test_workspaces.py::test_create_switch_environments_and_isolation`, matrix | P3 / S / add `require` to the list or accept |
| F-INT-1 | Connections, OAuth, credentials | IMPL | write-only credentials, test, enable/disable | `integrations.manage` | `/integrations/connections*`; `integration_connections` | none | credentials never returned (`integrations/schemas.py`, carried) | `test_integrations_api.py`; unit `test_integrations_adapters.py`, `_http.py`, `_resilience.py`, `_sigv4.py`; web `integrations.spec.ts` | none |
| F-INT-2 | Webhooks, events, jobs, failures, health | IMPL | signed deliveries, replay, retry, circuit breaker | `integrations.read|operate` | `/integrations/webhooks|events|jobs|failures|health` | failures page exists but **no notification** when a delivery or sync fails (grep `notify(`) | none | `test_integration_workflows.py`; unit `test_integration_scheduler.py` | P2 / S / notify on failed or degraded (backlog 3) |
| F-INT-3 | API keys and external API | IMPL | keys hashed, scoped to creator's live permissions; 2 read routes | `api_keys.manage` | `/integrations/api-keys`, `/external/customers|invoices/{id}` | external API is read-only and tiny | verified (`api_keys.py:92-100,178-198`) | `test_integrations_api.py` | none |
| F-INT-4 | Record file attachments (S3) | DUP | `/files/records/{type}/{id}` stores to S3 via a connection, separate from customer files in the database | entity read/write key | `integration_operations` | two attachment systems with different limits (25 MB vs 10 MB) and audit behaviour | S3 key is tenant-scoped (`scoped_key`) | `test_integration_workflows.py` | P3 / M / document or unify |
| F-AUD-1 | Audit read and filters | PART | filters action prefix, entity type, entity id, outcome (`audit/routes.py:34-45`); UI search, two selects | `audit.read` (o/a only: `READ_ONLY` excludes it, `permissions.py:84`) | `GET /audit/events`; `audit_events` | no actor filter, no date range, no export | environment-scoped plus tenant-wide events (`:46-55`) | matrix asserts no leak (`:320-328`, carried) | P2 / S / add actor and date filters |
| F-AUD-2 | Denied outcome | PART | `outcome` can be `denied` and the UI filters on it, but only `auth/service.py:199,254` and `pi_saas/connections.py:381` write it; the 403 handler writes nothing (`core/exceptions.py:82-85`) | n/a | `audit_events` | the "denied" filter shows sign-in problems only; forbidden-action probing leaves no trace | monitoring gap | none | P1 / M / audit denied business actions with throttling (backlog 4) |
| F-PRD-1 | Product install and enable | IMPL | PI product install and per-environment enable | `admin.products.manage`; list membership | `/products*`; 3 tables | none | none | `test_workspaces.py`, unit `test_navigation.py`; `test_api_surface.py` | none |
| F-NOT-1 | Bell and inbox | IMPL | per-user, per-environment, audience by permission, read state | `notifications.read` (all system roles) | `/notifications*`; 2 tables | none | audience isolation tested | `test_notifications.py` (5 tests); web `notifications.live.spec.ts` | none |
| F-NOT-2 | Notification producers | PART | `notify(` is called only from HR onboarding, inventory low stock and pi modules (grep). Not from quotes, orders, billing, finance, integrations | n/a | `notify` `notifications/service.py:27-60` | quote approvals, payments received, overdue invoices, integration failures are silent | none | none for missing producers | P1 / M / start with approvals, payment received, integration failure (backlog 3) |
| F-INV-1 | Stock, locations, movements | IMPL | idempotent moves, availability, low-stock alert | `inventory.read|adjust` | `/inventory/*`; 3 tables | location edit is not exposed (POST only) | none | matrix, `test_notifications.py::test_low_stock_delivery_links_to_filtered_stock_and_deduplicates`, `test_order_flows.py::test_stock_effects_are_idempotent_at_the_service_layer` | none |

## 6. Counts

Areas (section 4, 23 rows including Inventory): **implemented 15** (Overview, Pi Agent Beta, Customers/CRM, PIAI, Sales, Quotes, HR,
Reports, Settings, Members, Roles and Permissions, Environments, Integrations, Platform Products, Inventory), **partial 6**
(Catalog, Orders, Billing, Finance, Audit Logs, Notifications), **disconnected 1** (Branches), **duplicated 1** (Departments),
**missing 0**, **broken 0** (no failure reproduced; no runtime was available).

Features (section 5, 51 rows, counted by script over the Class column): **IMPL 37, PART 10, DISC 1, DUP 2, MISS 1, BROKEN 0**.
Missing capabilities that are not their own row: payment refund or reversal and credit notes (F-ORD-2, F-BIL-2), department delete route
(F-DEP-1), category edit and archive (F-CAT-3), audit actor/date filters (F-AUD-1).

## 7. Backlog items of the older map re-verified here

B1 (denied not audited): still true, `core/exceptions.py:82-85`. B2 (membership-only list routes): still true,
`organization_routes.py:66-69,97-100`, `environments/routes.py:48-49`, `products/routes.py:19-20`. B3 (branch): still true and
worse (the web never sends `branch_id`). B4 (no refund): still true. B5 (few notifications): still true. B6 (merge gate),
B11 (quote self-approval): code confirmed; harm still SUSPECTED. B7 (payment idempotency): still true. B8 (duplicate
departments pages, orphan `/workflows`): still true. B10 (customer file audit): still true. B12 (agent summary): still true.
B9 (matrix gaps) and B13 (unit-test environment fragility): carried, **not re-run**.

## 8. Assumptions, unverified ideas and what was not checked

Assumptions and ideas (none used as evidence above):

- A1. Registration is enabled in production; `.env` was never opened. If `ALLOW_REGISTRATION=false` in production, SEC-1 needs an
  existing account for the target address (still possible by an earlier self-signup or an admin invite elsewhere).
- A2. A reset of the victim's password after SEC-1 does not clear an attacker's enrolled face or fingerprint
  (`auth/service.py:324-359` has no factor handling). Whether that locks the victim out depends on the `email` fallback
  (`mfa.py:184-185`); not traced.
- A3. Idea: a "won" lead could offer one click to create a quote (F-SAL-1). A product choice, not a defect.
- A4. Idea: an aging endpoint for receivables (F-FIN-2) and saved customer segments (F-CRM-5) are optional.
- A5. Idea: unifying the two attachment systems (F-INT-4) may not be wanted if S3 is only for enterprise tenants.
- A6. The HR departments dialog may be hidden from users who lack the write key (F-HR-5 says SUSPECTED).

Not checked: the pi brain and learning internals; `apps/pi` pages beyond route auth; `_pending_reply` in `pi/inbox_routes.py`;
page rendering, accessibility, mobile layout, web build and types; pytest and Playwright results (none run here); database
constraints and migrations beyond the models I cite; email and WhatsApp delivery; Brain-document link revocation; pagination
and performance under load; `.env` and secrets; whether production runs the demo data mode.
