**Owner OS and Pi: project code analysis — 30 September 2026**

The project contains a substantial working business platform and a separate Pi SaaS application. Core business flows, permissions, migrations and the existing browser suites pass local verification. Release readiness is still held back by reproducible behavior gaps, failing style checks and incomplete live-provider acceptance. Adding a WhatsApp token alone does not establish that the complete production service works.

This was an analysis pass. Application code, existing tests, configuration and migrations were left unchanged. The repository already contained extensive uncommitted work; this report describes that working tree, not just the last commit.

**Scope and project map**

Inventory covered 776 source, test and migration files, totaling 163,362 lines, including generated source data. All source areas were inventoried; manual reading concentrated on architecture, trust boundaries, business state changes, Pi message processing, money, external integrations and deployment. This is not a claim that every line received the same depth of manual review.

| Area | Files / lines | Current responsibility |
| --- | --- | --- |
| `apps/api/app` | 256 / 47,294 | FastAPI backend; authentication, workspace permissions, business modules, integration framework, AI gateway, Pi runtime and Pi SaaS |
| `apps/api/tests` | 64 / 15,084 | Unit and PostgreSQL integration tests |
| `apps/api/migrations` | 15 / 7,022 | Alembic schema history, through revision 0011 |
| `apps/web/src` | 364 / 77,218 | Owner OS Next.js application, embedded Pi administration, operator console and subscription collection administration |
| `apps/web/tests` | 15 / 1,985 | Browser journeys, client contracts and navigation checks |
| `apps/pi/src` | 57 / 14,107 | Separate customer-facing Pi application: onboarding, inbox, teaching, campaigns, settings and billing |
| `apps/pi/tests` | 5 / 652 | Pi browser journeys with API responses mocked at the network boundary |

The API follows a modular monolith structure: route handlers call scoped services and repositories over PostgreSQL. Redis/ARQ performs background work. Owner OS and Pi share backend services but use separate authentication audiences and cookies. Workspace selection is held in the server session; permissions and active membership are rechecked on requests. Browser permission checks control presentation; backend checks remain authoritative.

The business platform includes customers, service/product catalog, sales leads, quotes, orders, inventory, invoices/payments, finance, HR/onboarding, reports, settings, notifications and audit history. Pi adds knowledge, conversations, controlled tools, human handoff, WhatsApp delivery, media processing and follow-ups. `pi_saas` adds business onboarding, provider provisioning, plans and usage, customer payments, manual subscription collection, operator support, campaigns, forms, connectors and weekly digests.

**Verification results**

Tests used disposable local PostgreSQL databases. No production database migrations, real customer messages, charges, refunds or live provider calls were performed. Provider-facing integration tests used test doubles.

| Check | Result |
| --- | --- |
| Existing backend suite | **576 passed, 1 skipped**, after correcting an audit-runner environment setting; details below |
| Independent review probes | **8 failed assertions, 1 passing control** across 9 cases; failures reproduce findings F1–F5 |
| Backend mypy | Pass: 256 source files |
| Backend Ruff formatting | Pass: 335 files |
| Backend Ruff lint | Fail: one I001 in migration 0008 |
| Owner OS and Pi ESLint | Both pass |
| Owner OS and Pi TypeScript | Both pass |
| Production frontend builds | Both pass in isolated source copies |
| Owner OS browser suite | **43/43 pass**, including the registered-route sweep; demo data |
| Pi browser suite | **16/16 pass**, with API mocks; includes mobile layouts and permission states |
| Fresh migration upgrade and schema comparison | Pass, no unexpected schema changes |
| Migration round trip on a second disposable DB | Upgrade → downgrade to base → upgrade → schema comparison: pass |
| Frontend Prettier | Fail: web `tsconfig.json`; Pi `tests/app.spec.ts` and `tsconfig.json`. Web also reports five ignored local `.cache` artifacts |
| npm production dependency audit | Both apps report zero known vulnerabilities in this run |
| Python dependency advisory audit | Not run: `pip-audit` is not installed locally |
| Real Redis/ARQ integration smoke test | Skipped because this audit did not start Redis or set `RUN_INTEGRATION=1` |
| Docker/container smoke test | Not run: Docker command unavailable in this environment |

The first full backend run returned 575 passed, 1 failed and 1 skipped. The failure came from the audit runner setting `JOB_QUEUE_MODE=inline` globally while a unit test deliberately constructs production settings, which require ARQ. Removing that global override resolved it: all 8 tests in that file and then all 310 unit tests passed. The reported aggregate result counts each existing test once; it is not a second uninterrupted full-suite run.

Frontend copies used the same application source and installed dependencies. Snapshot-only configuration adjusted Turbopack's root to include linked dependencies, the resulting standalone server path, and browser ports 3319/3329. Initial snapshot-root and missing-browser-path errors were harness problems and were corrected before the reported successful runs.

**Confirmed findings, ordered by priority**

P1 means address before broad customer use; P2 means a functional or release-process defect; P3 means a maintenance concern. These priorities reflect impact and the demonstrated conditions.

**F1 — P1: a stale Pi tab can save data into another selected business.**

Evidence: `apps/pi/src/lib/api.ts:52`, `apps/pi/src/lib/session.tsx:118`, `apps/api/app/modules/access/dependencies.py:26`, `apps/api/app/modules/pi_saas/app_routes.py:272` and `:388`.

Pi requests send CSRF protection but omit the existing expected-workspace headers. Selecting business B changes the shared server session, while another tab can still display a form for business A. Saving that stale form applies its input to B. A probe created A and B, selected B, then submitted the stale A name; B was renamed. A control sending `X-Workspace-Tenant` for A correctly received HTTP 409.

This is a same-user, multi-business context error; the probe does not demonstrate access to another owner's unauthorized business. The same missing request context also deserves testing when switching between test and production environments.

Remedy: bind Pi reads and writes to the business and environment that rendered the screen, send the backend's expected-workspace guards, and coordinate cache/request invalidation on switching. Add a two-tab browser regression and a delayed-request regression.

**F2 — P1: queued campaign messages can bypass a newly exhausted allowance or newly started quiet hours.**

Evidence: `apps/api/app/modules/pi_saas/campaigns.py:406` and `:481`; `apps/api/app/modules/pi/runtime.py:833`; `apps/api/app/modules/pi_saas/entitlement.py:127`.

Dispatch checks quiet hours and remaining allowance before enqueueing. Delivery rechecks campaign cancellation, consent and human takeover, but does not recheck the campaign's quiet window. Exhausted allowances turn off automation; campaign messages have sender type `system`, while the delivery guard applies that automation restriction to sender type `ai`.

Two independent probes queued an allowed campaign and then (a) consumed its remaining message allowance, or (b) advanced the clock into the campaign's preconfigured quiet interval. Each still called the fake provider once. No real messages were sent.

Remedy: re-evaluate campaign automation, allowance and quiet hours immediately before delivery. Use an atomic quota reservation or equivalent concurrency control so multiple queued batches cannot spend the same remaining allowance. Quiet-hour deferral must preserve eventual delivery without duplicate sends.

**F3 — P2: the factual price guard matches numbers without binding their currency or meaning.**

Evidence: `apps/api/app/modules/pi/guard.py:171` and `:185`.

`evidence_amounts` collects every numeric value from serialized facts. The validator accepts `The price is USD 150.00.` both when the evidence says price 150 PKR and when it says quantity 150 with price 20 USD. Both probes expected rejection and failed.

This demonstrates a validator weakness under supplied model output; it does not establish that a real model produced these replies. Service-mode no-price protection is a separate policy with passing existing tests. The weakness matters when price disclosure is enabled and facts are supposed to constrain an answer.

Remedy: validate typed monetary evidence with amount, currency and the associated offering/field. Inventory counts, IDs and other numbers must not authorize a price claim. Retain the existing service no-price checks.

**F4 — P2: a full manual subscription refund leaves the invoice view showing paid in full.**

Evidence: `apps/api/app/modules/pi_saas/manual_billing.py:419`, `apps/api/app/modules/pi_saas/app_routes.py:739`, `apps/pi/src/features/settings.tsx:1067`.

The refund operation records the refund and adjusts subscription access, but does not update or attach a refund representation to the platform invoice returned by the billing view. After an approved PKR 2,500 payment was fully refunded, the linked invoice still had status `paid` and amount paid `2500.00`; the frontend renders that status directly.

The refund record itself exists. The problem is inconsistent invoice presentation, not a demonstrated loss of the refund record. Preserve appropriate accounting history: add a linked credit/refund representation or derive a clear refunded/net-payment view rather than merely erasing the original payment. This issue is also acknowledged in the existing Pi SaaS handoff.

**F5 — P2: document search promises customer-name matching but searches only document numbers.**

Evidence: `apps/web/src/features/documents/orders-list-page.tsx:188`, `apps/web/src/features/documents/quotes-list-page.tsx:196`; corresponding API services at `orders/service.py:128` and `quotes/service.py:76`.

The placeholder says “Search number or customer…”. For both orders and quotes, a freshly created document was found by its number but returned zero results for its existing customer's name. Invoice search has the same number-only predicate in `apps/api/app/modules/billing/service.py:112`, despite the same frontend promise; that third path was inspected, not separately reproduced.

Remedy: add a correctly scoped customer-name predicate to each search query, or narrow the UI promise if customer-name search is intentionally unavailable. Check pagination totals and tenant isolation with the new predicate.

**F6 — P2: current mandatory style checks fail.**

`apps/api/migrations/versions/0008_pi_billing_pi_subscription_collections.py:7` fails Ruff I001 because imports are unsorted. Owner OS `tsconfig.json` fails Prettier. Both checks are required by `.github/workflows/checks.yml`, so the current source cannot pass that pipeline unchanged.

Pi also has two formatting failures, although its app is not currently checked by CI. Five additional web formatting warnings came from ignored local cache files; those are a local command hygiene problem, not evidence of five additional clean-checkout CI failures. Exclude local audit artifacts and fix the actual source formatting separately.

**F7 — P2: standalone Pi lacks the CI and container coverage provided to Owner OS.**

Evidence: `.github/workflows/checks.yml`, `docker-compose.yml`.

Frontend build, lint, typecheck, browser and npm-audit jobs target `apps/web`. The compose stack includes API, worker and Owner OS web, but no Pi frontend service. Pi passes the local tests above, but later regressions in that separate application would not be caught by the current frontend pipeline.

Remedy: add Pi to the CI matrix and document/test its actual deployment path. Container parity is needed if compose is intended to deploy the entire product; a separately managed Pi deployment is also valid if explicit and tested.

**Additional code-review findings**

- **P2, scale-dependent:** `pi_saas/digests.py:261` selects at most 500 launched active businesses without a cursor or a predicate excluding already processed businesses. At more than 500 eligible businesses, later accounts can be repeatedly omitted. The fixed limit was verified in source; a 501-business workload was not run. Process deterministic batches with continuation or select businesses still due for the digest.
- **P3, documentation drift:** `docs/ARCHITECTURE.md` still describes unauthenticated Stage 2 behavior and Pi as future work; parts of `docs/PROJECT_STATUS.md` contradict its newer sections about completed backend and live UI work. Use one current status entrypoint and mark historical sections explicitly.
- **P3, maintainability:** several files combine over 1,000 lines of route, UI or runtime logic. Examples include Pi app routes, settings/inbox/setup screens, integration service logic and the operator pages. Extract bounded services and screen sections when changing them, backed by behavior-level tests. Large size alone is not a runtime defect.

**What is working and worth preserving**

- Authentication uses server-held sessions, password hashing, audience separation and CSRF checks. Scoped repositories, permissions and database relationships protect business data; integration tests cover unauthorized and cross-tenant cases.
- Core lifecycle tests exercise service discovery, quote approval/conversion, order progression, invoice creation and payment settlement. Inventory and money paths use transactional controls and Decimal-based calculations.
- Pi has controlled business tools, approved knowledge, internal conversation briefs, human takeover and safe provider-failure handling. Existing tests cover no-price service replies, consent, reminder cancellation, opt-out and stale generated replies.
- Customer payments and the platform's own subscription collection are separate domains. Operator access has explicit roles and support-access checks.
- External work has webhook validation, durable records, idempotency and retry/reconciliation paths. Those protections need to remain intact when addressing campaign delivery and quotas.
- Both UIs have passing local browser coverage, including responsive layouts and permission-dependent actions. Demo/mocked browser success does not replace a real frontend-to-provider acceptance run.

**Pi features and remaining acceptance work**

| Capability | Current code status | Remaining boundary |
| --- | --- | --- |
| Service conversation without disclosing price | Implemented, existing automated cases pass | Real model quality and broader multilingual cases still need acceptance |
| Conversation summary for the company | Internal briefs/memory implemented | Verify staff visibility and usefulness with representative real conversations |
| Reminder after inactivity | Scheduled template follow-up, consent and cancellation paths implemented | Working worker, approved language-specific template and live delivery validation |
| Audio, image and video input | Provider-backed transcription/vision/video paths and feature gates exist; integration tests use doubles | Compatible provider credentials/model capability and real media acceptance |
| Reply in the customer's language | Language-aware prompting and conversation state exist | “All languages” is not established by the current tests |
| Campaigns | Implemented and browser-tested | Fix F2, then validate actual provider delivery |
| Weekly company summaries | In-app and optional connected email implemented | WhatsApp delivery of weekly summaries is not built |
| WhatsApp forms and connectors | Forms, Google Calendar and Shopify paths implemented with contract tests | Real provider setup, permissions, callback and delivery checks |
| Manual/online billing | Implemented with local test coverage | Fix F4; live payment-provider acceptance remains separate |

Other acknowledged gaps include templates with variables, video-meeting links for bookings and per-number provider cost accounting. Password change exists, but self-service forgotten-password recovery and email verification are not implemented. These are product/operational gaps, not all release blockers for a controlled pilot.

For live WhatsApp acceptance, validate the selected connection mode and phone number, public signed webhook routing, active queue worker, provider capability, approved templates, account/plan/launch state and delivery-status callbacks. Use a designated test recipient and record inbound → AI processing → outbound → delivered behavior. A token alone cannot verify these dependencies. This audit neither tested nor changed existing live credentials.

**Security and deployment limits that still need verification**

`apps/api/app/integrations/http.py:18` explicitly documents a DNS-rebinding residual risk: addresses are validated, then HTTPX resolves the hostname again when connecting. Redirect and private-address checks exist, but address validation alone does not close that gap. Verify production egress isolation or implement a connection mechanism that preserves validated destinations and TLS verification. No rebinding exploit was attempted here.

Tenant isolation is implemented through scoped application queries and database constraints; the architecture does not enable RLS. Preserve that design's assumptions when adding raw SQL, workers and operator endpoints. Passing isolation tests is useful evidence, not proof of every possible query path.

Load behavior, real Redis worker operation, backup restoration, deployment secrets/egress settings, live WhatsApp/AI/Stripe acceptance and the Python dependency advisory scan were not established by this pass.

**Recommended implementation order**

1. Fix Pi request workspace binding and campaign delivery-time controls; promote the independent reproductions into permanent regression tests.
2. Correct typed price evidence, refund presentation and document search.
3. Clear mandatory formatting/lint failures and add standalone Pi CI coverage.
4. Address digest batching and consolidate current architecture/status documentation.
5. Run controlled live-provider acceptance and production worker/deployment checks before declaring the complete service ready.

**Local evidence**

Audit artifacts are retained under `.cache/project-audit-20260930/` and are ignored by Git:

- `inventory.json`, `baseline-hashes.json`, `audit-integrity.json`: inventory and integrity check. All 776 inventoried source/test/migration files had unchanged hashes at completion.
- `backend.xml`, `unit-clean-env.xml`: original suite results and corrected unit rerun.
- `test_audit_probes.py`, `probes.xml`: independent reproductions and the passing workspace-header control.
- `schema-roundtrip.log`: migration round-trip result.
- `frontends/web/browser-results.xml`, `frontends/pi/browser-results.xml`: successful browser runs.
- `web-dependency-audit.json`, `pi-dependency-audit.json`: npm audit results.

To reproduce the extra checks with the existing disposable local database setup:

```powershell
.venv\Scripts\python.exe .cache/project-audit-20260930/run_checks.py pytest -c pyproject.toml ../../.cache/project-audit-20260930/test_audit_probes.py -q --tb=short --show-capture=no -p no:cacheprovider
```

That command is expected to fail until F1–F5 are addressed. The runner disables application `.env` loading and points only at the explicitly named local test database.
