# Owner OS workspace: prioritised capability backlog (FT-F2, G4)

Base `origin/main` 25c3922, 2026-10-31. Source of every item: `docs/pi-saas/pi-capability-map.md` (row ids F-xxx and the
section numbers below refer to it). One deduplicated list. Nothing here was implemented; each fix is a targeted change in one
module, none is a rebuild.

Evidence labels: **VERIFIED** (I read the cited lines), **SUSPECTED** (code read, impact not shown). Paths: `api` = `apps/api/app`,
`web` = `apps/web/src`.

## 1. How the list is ranked

Order is by, in this sequence: customer harm, security/privacy, workflow criticality, frequency, business impact, then
confidence (higher first), effort (smaller first) and regression risk (lower first). Scores are 1 (low) to 5 (high) except
confidence (H/M/L), effort (S under half a day, M 1-3 days, L more) and regression risk (L/M/H). They are my judgement from
code reading; no production data was available, so "frequency" is a guess about normal use, not a measurement.

## 2. The list

Categories: **CD** confirmed defect (behaviour contradicts what the code or UI promises, proven by reading), **SV** spec violation,
**UF** usability friction, **MR** missing requirement, **OO** optional opportunity.

**Spec violations (SV): none found.** The pi non-negotiables in `CLAUDE.md` concern pi's replies; I did not audit pi internals
(map section 8), so "none found" means none seen in the Owner OS areas I read, not that pi is clean.

| Rank | ID | Cat | Title | Harm | Sec | Crit | Freq | Biz | Conf | Effort | Regr | Label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | BL-01 | CD | Unverified email lets an outsider inherit a later workspace invitation (SEC-1) | 5 | 5 | 4 | 2 | 5 | H (code) / M (exploit) | M | M | VERIFIED code path |
| 2 | BL-02 | MR | A paid order or invoice cannot be cancelled, refunded or credited | 4 | 1 | 5 | 3 | 4 | H | L | H | VERIFIED |
| 3 | BL-03 | MR | Business events never notify (quote awaiting approval, payment received, integration failure) | 3 | 1 | 4 | 5 | 4 | H | M | L | VERIFIED |
| 4 | BL-04 | CD | The audit "denied" filter exists but denied business actions are never recorded | 2 | 4 | 3 | 3 | 3 | H | M | M | VERIFIED |
| 5 | BL-05 | CD | A double-submitted payment is recorded twice | 4 | 1 | 4 | 3 | 3 | H (code) / M (impact) | S | L | VERIFIED code |
| 6 | BL-06 | MR | The branch feature is disconnected at both ends | 3 | 1 | 2 | 2 | 3 | H | S then L | M | VERIFIED |
| 7 | BL-07 | CD | Any member can list branches, departments, environments, products, workspace settings | 1 | 3 | 2 | 4 | 2 | H | S | L | VERIFIED |
| 8 | BL-08 | MR | A user holding `quotes.approve` can approve their own quote | 3 | 2 | 3 | 2 | 3 | M | S | L | SUSPECTED (design) |
| 9 | BL-09 | MR | Customer merge is irreversible and needs only `customers.write` | 4 | 2 | 3 | 1 | 3 | M | S | L | SUSPECTED (design) |
| 10 | BL-10 | MR | The isolation matrix omits integrations, API keys, customer files, HR onboarding, agent actions | 2 | 4 | 3 | 1 | 3 | H | M | L | VERIFIED gap |
| 11 | BL-11 | UF | Quotes never expire on their own | 2 | 1 | 2 | 4 | 2 | H | S | L | VERIFIED |
| 12 | BL-12 | MR | Catalog categories cannot be edited or archived; departments cannot be renamed in the UI or deleted | 2 | 1 | 2 | 3 | 2 | H | S | L | VERIFIED |
| 13 | BL-13 | UF | Audit log has no actor or date filter and no export | 2 | 2 | 2 | 3 | 2 | H | S | L | VERIFIED |
| 14 | BL-14 | UF | Two departments pages for one dataset | 1 | 1 | 1 | 2 | 1 | H | S | L | VERIFIED |
| 15 | BL-15 | CD | Customer file upload and delete leave no audit event | 2 | 3 | 2 | 3 | 2 | H | S | L | VERIFIED |
| 16 | BL-16 | UF | Receivables page shows at most 100 issued + 100 partly paid invoices (disclosed) | 2 | 1 | 2 | 2 | 2 | H | S | L | VERIFIED |
| 17 | BL-17 | UF | HR departments page may offer a create dialog the API refuses | 1 | 1 | 1 | 2 | 1 | L | S | L | SUSPECTED |
| 18 | BL-18 | - | WITHDRAWN: I first suspected `pi-analytics` lacked a product gate; the pi children are inconsistent and the parent `pi` item carries `required_product="pi"` (nav census), so no defect is claimed | - | - | - | - | - | - | - | - | withdrawn |
| 19 | BL-19 | UF | pi handlers `requests/answer` and `requests/meeting` check permission only inside services, not declaratively | 1 | 2 | 2 | 1 | 1 | H | S | L | VERIFIED |
| 20 | BL-20 | UF | `/workflows` page is reachable only from an Overview link | 1 | 1 | 1 | 2 | 1 | H | S | L | VERIFIED |
| 21 | BL-21 | UF | Won lead does not start a quote | 2 | 1 | 2 | 3 | 2 | M | M | L | SUSPECTED (product choice) |
| 22 | BL-22 | OO | Two attachment systems (customer files in the database, record files in S3) | 1 | 1 | 1 | 2 | 2 | H | M | M | VERIFIED duplicate |
| 23 | BL-23 | OO | Saved customer segments, server-side aging for receivables | 1 | 1 | 1 | 2 | 2 | M | M | L | optional |
| 24 | BL-24 | OO | Rate limiter fails open if Redis is down (documented) | 1 | 2 | 1 | 1 | 1 | H | S | L | VERIFIED, accepted design |
| 25 | BL-25 | UF | Agent `summary` documents need membership only | 1 | 2 | 1 | 2 | 1 | H | S | L | VERIFIED |
| 26 | BL-26 | MR | Carried from the older map, not re-run: unit tests fail with an empty bare environment (`settings` fixture needs `DATABASE_URL`, `REDIS_URL`) | 1 | 1 | 1 | 3 | 1 | L | S | L | NOT re-verified |

## 3. Top 15 in F3 format

### BL-01 (CD, security): unverified email lets an outsider inherit a later invitation

- **What is wrong.** Anyone can register any email and be signed in at once; the email is never proven to belong to them; when a
  workspace admin later invites that address, the invite attaches the roles to the existing, squatter-controlled account and
  sends only a "sign in" link.
- **Who and evidence.** Every workspace that invites a person who has no account yet. Chain: `api/modules/auth/service.py:105-136`
  (register signs in, no verification), `api/core/config.py:53` (open by default), `auth/service.py:361-364,403-425,462-464`
  (`email_verified_at` is only set, never checked), `api/modules/access/members.py:100-130,151-153,169-170` (existing user path),
  pinned as intended by `tests/integration/test_auth_sessions.py:497-511`. Login is password only unless factors are enrolled
  (`auth/routes.py:196-203`, `auth/mfa.py:142-170`). **Not reproduced.**
- **Root cause.** Account identity and mailbox ownership are decoupled; the invite flow trusts an existing account whatever its
  verification state.
- **Smallest safe fix.** In `MemberService._invite` and `add`, treat an existing user whose `email_verified_at is None` as a new
  account: create the `MemberInviteToken`, send the set-password link, and make `accept_invite` (which already overwrites the
  credential and verifies the email, `auth/service.py:457-464`) also revoke that user's existing sessions. Add the revoke in
  `accept_invite`.
- **Better long-term fix.** Require a verified email before any membership becomes usable (gate `workspace_scope` or session
  selection on `email_verified_at` for memberships created after the change), and send the verification link at sign-up with a
  grace limit. Stop returning the raw invite link to the inviter once email delivery is reliable.
- **Dependencies, risk, effort, success.** Touches `access/members.py`, `auth/service.py`, the invitation email template and the
  web members page text. Risk: users who signed up unverified and are invited later will get an invitation that resets their
  password; the existing test at `test_auth_sessions.py:497` must be rewritten for the verified case and kept for the verified-user case.
  Effort M. Success: an unverified existing account that is invited cannot sign in with its old password and gets the membership
  only after the emailed link is used; a verified account behaves as today.
- **Test and rollback.** Integration tests: (a) register A unverified, invite same email, old password rejected, link accepted,
  membership active; (b) verified account unchanged (the existing test); (c) invite link used twice is rejected. Rollback: revert
  the commit; no migration is needed (if the fix adds a column, ship it separately and keep it nullable).
  **Product decision needed first:** whether to enforce verification everywhere (long-term fix).

### BL-02 (MR): a paid order or invoice cannot be cancelled, refunded or credited

- **What is wrong.** Cancelling an order voids its invoice first; voiding is refused when anything was paid; there is no refund,
  payment reversal or credit note route, so the user gets `INVOICE_HAS_PAYMENTS` and a dead end.
- **Who and evidence.** Any workspace that takes a deposit then loses the deal. `orders/service.py:477-480`,
  `billing/service.py:299-302`, `billing/routes.py` (only `POST invoices`, `actions` issue/void, `payments`), and
  `tests/integration/test_money_and_states.py::test_invoice_and_payment_rules` asserts the refusal.
- **Root cause.** The money model has issue, pay and void, but not "correct after payment".
- **Smallest safe fix.** Add a payment **reversal** (a negative `payments` row linked to the original, reason required, audited,
  restricted to `billing.write` plus a manager key) so `amount_paid` falls and the invoice can be voided. No new tables if the
  `payments` model accepts a reversal flag (check `billing/models.py` first).
- **Better long-term fix.** Credit notes and refunds through the payment provider (Stripe) with finance summary and reports
  taking reversals into account.
- **Dependencies, risk, effort, success.** Finance summary, billing summary, receipts and Reports revenue must treat reversals;
  that is the regression surface (High). Effort L. Success: cancelling a paid order ends cancelled, stock restored, invoice void,
  money shown reversed in Billing, Finance and Reports revenue with equal figures.
- **Test and rollback.** Extend `test_order_flows.py` (cancel after confirm) with a paid case and `test_money_and_states.py` for
  reversal rules and currency; compare Billing, Finance and Reports totals. Rollback: remove the route; reversal rows stay
  (they are data).  **Product decision needed first:** refund policy.

### BL-03 (MR): business events never notify

- **What is wrong.** `notify(` has producers only in HR onboarding, inventory low stock and pi modules. Approvers, accountants
  and integration admins are never told.
- **Who and evidence.** Managers waiting on quotes, accountants after payments, admins after failed deliveries. Grep of
  `notify(` over `api/**` (hits: `hr/onboarding.py:608`, `inventory/service.py:284`, pi files); no call in `quotes/`, `orders/`,
  `billing/`, `finance/`, `integrations/`. The Failures and Health pages exist (`web/features/integrations/*`) but do not alert.
- **Root cause.** The notification service (`notifications/service.py:27-60`) was built for low stock and onboarding; later modules
  did not adopt it.
- **Smallest safe fix.** Three producers using `dedupe_key`: quote submitted (`permission="quotes.approve"`, link
  `/quotes/approvals`), payment recorded (`permission="billing.read"`), integration delivery or sync failed (`permission="integrations.operate"`).
- **Better long-term fix.** A small producer hook on the existing `emit()` outbox events so modules do not each call `notify`, plus per-user preferences.
- **Dependencies, risk, effort, success.** Uses the audience-by-permission model (no migration). Risk Low; noise (use dedupe keys).
  Effort M. Success: a manager sees a bell item with a working link within one request of a quote being submitted.
- **Test and rollback.** Integration tests beside `test_notifications.py` for audience (only holders of the key) and dedupe.
  Rollback: remove the three calls.

### BL-04 (CD): the "denied" audit filter shows only sign-in problems

- **What is wrong.** The audit page lets you filter by outcome `denied`, but forbidden business actions produce no event.
- **Who and evidence.** Admins investigating abuse. `core/exceptions.py:82-85` (the 403 handler writes nothing);
  `outcome="denied"` is written only at `auth/service.py:199,254` and `pi_saas/connections.py:381`; UI filter in
  `web/features/admin/audit-page.tsx` (outcome select) and `audit/routes.py:42`.
- **Root cause.** Permission failure is raised in many places and nothing observes it.
- **Smallest safe fix.** In `WorkspaceScope.require` callers' common path (`access/dependencies.py:117-125` for declarative checks) record one `denied` audit event per (user, action, minute) using the existing `record()` on a separate short transaction; do not record for read routes unless desired.
- **Better long-term fix.** A single authorisation-failure hook with throttling and a "security" view in the audit page.
- **Dependencies, risk, effort, success.** The handler has no session; recording must not roll back with the failed request.
  Flooding risk (throttle). Effort M, regression Medium. Success: calling a write route without the key adds one `denied`
  row visible with the filter.
- **Test and rollback.** Integration test in `test_rbac.py` style: forbidden POST creates one event, ten repeats create one per window. Rollback: remove the hook.

### BL-05 (CD): a double-submitted payment is recorded twice

- **What is wrong.** `PaymentCreate` has no idempotency key; two identical requests inside the remaining balance create two payments.
- **Who and evidence.** Accountants on slow connections. `billing/schemas.py:31-37`, `billing/routes.py:70-78`,
  `billing/service.py:331-338` (only an overpayment guard). Other integration operations do carry a `request_id`.
- **Root cause.** Missing client request id on this one money-writing route. (Impact SUSPECTED: depends on whether the web
  disables the button while pending; I did not read the form.)
- **Smallest safe fix.** Optional `request_id: UUID` in `PaymentCreate`, unique per `(tenant_id, environment_id, request_id)`
  on `payments` (migration), return the existing row on replay; the web sends a fresh id per dialog open.
- **Better long-term fix.** Same pattern for invoices, expenses and orders create.
- **Dependencies, risk, effort, success.** One migration (check `alembic heads` first), schema and web dialog change. Effort S. Success: replaying the same request id returns the same payment and the balance moves once.
- **Test and rollback.** Extend `test_invoice_and_payment_rules`. Rollback: the column is nullable; revert code, leave the column.

### BL-06 (MR): the branch feature is disconnected at both ends

- **What is wrong.** Branch records exist, the API accepts an active `branch_id`, and nothing reads it; the web never sends it.
- **Who and evidence.** Multi-branch businesses expecting scoped data. `auth/schemas.py:100-104`, `auth/service.py:481-517`,
  `access/dependencies.py:104`, no `scope.branch_id` consumer in `api/**` outside tenants (grep), `web/features/auth/service.ts:116-119`.
- **Root cause.** Scoping by branch was never specified; only inventory locations and departments carry a `branch_id`.
- **Smallest safe fix.** Decide what a branch scopes. Until decided, label Branches as an organisation list in the UI copy so
  nobody expects filtering. (No code.)
- **Better long-term fix.** Scope inventory first (locations already have `branch_id`), then orders and invoices, through
  `WorkspaceRepository` predicates, with an explicit "all branches" permission.
- **Dependencies, risk, effort, success.** Owner decision, then M-L work touching every module; regression risk Medium.
  Success: a user with an active branch sees only that branch's stock and orders.
- **Test and rollback.** Matrix-style test per scoped entity. Rollback: feature flag per module.

### BL-07 (CD): list routes without a permission

- **What is wrong.** Branches, departments, environments, products, workspace settings and organisation can be read by any member.
- **Who and evidence.** Low-privilege members (viewers, billing) learn structure and settings. `tenants/organization_routes.py:44,66-69,97-100`,
  `environments/routes.py:48-49`, `products/routes.py:19-20`, `business_settings/routes.py:18`; nav gates need `admin.organization.manage` and others (`navigation/definitions.py`). Same tenant only.
- **Root cause.** Bare `Scope` instead of `Depends(require(...))`.
- **Smallest safe fix.** Add the same key the nav item uses to the list routes **except** departments and branches, which the HR
  departments page also reads (`web/features/hr/departments-page.tsx:57`): give those a `any_permissions` of
  `admin.organization.manage` or `hr.read`. Check Inventory and Members pages, which also read branches, first.
- **Better long-term fix.** A route-permission lint test that fails when a `workspace_scope` route has neither `require` nor a declared exemption.
- **Dependencies, risk, effort, success.** Web pages that read these lists as a convenience (branch pickers) must be checked; effort S; regression Low-Medium.
  Success: a viewer gets 403 on each list while the pages that need them still load for their roles.
- **Test and rollback.** Add the lists to `test_system_role_route_matrix` (`test_rbac.py:145`). Rollback: revert.

### BL-08 (MR, suspected): own-quote approval

- **What is wrong.** `transition("approve")` checks only `quotes.approve`; the creator can approve.
- **Who and evidence.** Businesses wanting four-eyes approval. `quotes/service.py:268-281`.
- **Root cause.** No separation-of-duties rule.
- **Smallest safe fix.** Workspace setting `quote_self_approval` (default allow, to keep today's behaviour); when off, refuse with `SELF_APPROVAL` if `quote.created_by` equals `scope.user_id` (confirm the column name in `quotes/models.py`).
- **Better long-term fix.** Approval policies by amount.
- **Dependencies, risk, effort, success.** Needs the `business_settings` field (migration). Effort S. Success: with the setting off, the creator gets 422, another approver succeeds.
- **Test and rollback.** Extend `test_quote_state_machine_rejects_illegal_moves`. Rollback: default allow.

### BL-09 (MR, suspected): customer merge gate

- **What is wrong.** Merge moves every row with `customer_id` and deletes the duplicate, for any `customers.write` holder.
- **Who and evidence.** Sales, Support and Member roles. `customers/merge.py:93-135,186-191`; roles in `access/permissions.py:84-150`.
- **Root cause.** Reuse of the ordinary write key for an irreversible action.
- **Smallest safe fix.** New key `customers.merge` held by manager, admin, owner (permission catalog plus system role presets), required in `merge()`.
- **Better long-term fix.** Merge preview showing counts per table, and a soft-delete window.
- **Dependencies, risk, effort, success.** Catalog and role presets (existing custom roles will not have the key). Effort S. Success: a Sales user gets 403 on merge; manager succeeds.
- **Test and rollback.** Extend `test_customer_merge.py` and the route matrix. Rollback: revert; no data change.

### BL-10 (MR, tests): extend the isolation matrix

- **What is wrong.** The matrix covers 22 entities and none of integrations, API keys, customer files, HR onboarding, agent actions, workflows.
- **Who and evidence.** Whole product; no leak seen, but proof is missing. `tests/integration/test_isolation_matrix.py` (540 lines, `build_tenant_a` seeds listed entities); route list in map section 3.
- **Root cause.** The matrix pre-dates those modules.
- **Smallest safe fix.** Add rows for `integration_connection`, `webhook`, `api_key`, `customer_file`, `employee_onboarding`, `workspace_agent_action`, `workflow_run`, asserting 404 for tenant B and for staging.
- **Better long-term fix.** Generate the list from `Base.metadata` tables with `tenant_id` and fail when a table is neither covered nor exempt.
- **Dependencies, risk, effort, success.** Needs the disposable database and the lock; tests only. Effort M. Success: matrix fails if a new tenant table has no coverage.
- **Test and rollback.** The change is the test; rollback is deleting it.

### BL-11 (UF): quotes never expire by themselves

- **What is wrong.** Validity only blocks send and accept; status stays `sent` and pipeline numbers keep counting it.
- **Who and evidence.** Sales teams. `quotes/service.py:271`, no quote job in `worker.py:104-122`.
- **Root cause.** No scheduled sweep.
- **Smallest safe fix.** Daily cron that moves `sent` quotes with `valid_until < today` to `expired` through `QuoteService.transition` (audited).
- **Better long-term fix.** Pre-expiry reminder via BL-03 notifications.
- **Dependencies, risk, effort, success.** Worker cron entry; effort S. Success: overdue quotes show `expired` the next morning with an audit row.
- **Test and rollback.** Unit test of the sweep over a seeded quote. Rollback: remove the cron entry.

### BL-12 (MR): categories and departments lack basic maintenance

- **What is wrong.** No PATCH or DELETE for categories; department rename route exists with no UI; no department delete route though the service supports it.
- **Who and evidence.** Admins fixing typos. Route census (`catalog` has POST/GET only); `web/features/catalog/service.ts:56-58`;
  `web/features/admin/service.ts:187-198`; `tests/integration/test_tenant_isolation.py:146,170` (service delete tested).
- **Root cause.** CRUD never completed.
- **Smallest safe fix.** `PATCH /catalog/categories/{id}` (name, status) with audit; department rename dialog; `DELETE /organization/departments/{id}` returning `OrganizationConflict` when employees reference it.
- **Better long-term fix.** Category tree and reorder.
- **Dependencies, risk, effort, success.** Check employee `department_id` FK behaviour before the delete. Effort S. Success: rename and archive work and are audited.
- **Test and rollback.** Extend `test_business_modules.py`, add matrix cases. Rollback: remove routes.

### BL-13 (UF): audit filters and export

- **What is wrong.** Filter by action prefix, entity and outcome only.
- **Who and evidence.** Admins investigating a person or period. `audit/routes.py:34-45`; page `web/features/admin/audit-page.tsx:53-174`.
- **Root cause.** Initial scope.
- **Smallest safe fix.** `actor_user_id`, `created_from`, `created_to` query params and two selectors.
- **Better long-term fix.** CSV export and retention setting.
- **Dependencies, risk, effort, success.** Existing index check on `audit_events` (not read; see map section 8). Effort S. Success: filtering by actor and date narrows `total`.
- **Test and rollback.** Extend the matrix audit assertions. Rollback: revert.

### BL-14 (UF): duplicate departments pages

- **What is wrong.** `web/features/hr/departments-page.tsx` (367 lines) and `web/features/admin/departments-page.tsx` (242 lines) duplicate one dataset.
- **Who and evidence.** Maintainers and users (different capabilities). The two page entries `web/app/(app)/hr/departments/page.tsx`, `settings/departments/page.tsx`.
- **Root cause.** Built for two nav areas.
- **Smallest safe fix.** Make the HR page import the admin component (or the reverse), keep both routes.
- **Better long-term fix.** One departments feature with entry points.
- **Dependencies, risk, effort, success.** Compare the two (the HR copy shows a roster, `hr/departments-page.tsx:60`). Effort S. Success: one component, both routes render it.
- **Test and rollback.** `routes.spec.ts` smoke. Rollback: revert.

### BL-15 (CD): customer file upload and delete are not audited

- **What is wrong.** Both write a customer activity entry only.
- **Who and evidence.** Admins reviewing who removed a customer document. `customers/file_routes.py:52,84`; other customer mutations call `record` (`customers/service.py:105,140,162,251`).
- **Root cause.** The file routes were added after the service's audit pattern.
- **Smallest safe fix.** `record(session, "customer.file_added|file_removed", scope=..., entity_type="customer_file", entity_id=...)` next to each `log_activity`.
- **Better long-term fix.** None needed.
- **Dependencies, risk, effort, success.** None. Effort S. Success: both actions appear in the audit page.
- **Test and rollback.** Extend `test_customer_files.py`. Rollback: revert.

## 4. Items 16 to 26

Short form (symptom, evidence, smallest fix); promote any to F3 on request.

- BL-16: `web/features/finance/receivables-page.tsx:27,118-146`; add a server-side aging endpoint when volume needs it.
- BL-17: `web/features/hr/departments-page.tsx:251-257` create mutation; hide the create button unless `can("admin.organization.manage")`. SUSPECTED.
- BL-18: withdrawn (see table).
- BL-19: `pi_saas/requests.py:738-790`; add `Depends(require("pi.inbox.reply"))` so the check is visible in route census.
- BL-20: `web/features/overview/overview-page.tsx:250` is the only link to `/workflows`; add a nav entry or remove the link.
- BL-21: `api/modules/sales/service.py:95-103`; product choice, ask the owner.
- BL-22: `api/modules/integrations/workflow_routes.py:147-240` (S3 files) beside `customers/file_routes.py` (database files); document which to use.
- BL-23: optional; build only on customer request.
- BL-24: `api/core/rate_limit.py:29-31,56-60`; accepted design, durable login lockout covers credentials.
- BL-25: `workspace_agent/routes.py:185-214`; require `reports.read` or the source key per summary.
- BL-26: carried from `capability-map.md` B13, not re-verified here.

## 5. Dependencies between items

BL-03 feeds BL-11 (expiry reminders). BL-02 needs a refund policy decision and touches Reports and Finance (regression risk).
BL-07 must wait for a check of every web page that calls the branch and department lists (Inventory, Members, HR). BL-01 and BL-04
both touch `auth/` and the audit service; schedule them in different commits. BL-10 should land before BL-07 so the new gates
are proven by the matrix.
