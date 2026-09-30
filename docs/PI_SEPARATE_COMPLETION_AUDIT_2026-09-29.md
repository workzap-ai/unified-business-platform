# Standalone Pi: UI delivery and completion audit

Date: 29 September 2026. Baseline: [original Pi requirements](PI_WHATSAPP_SAAS_CLAUDE_PROMPT.md). This is a review of the current working tree; it is not a claim that every requirement has shipped.

**Verdict: the existing standalone Pi screens have a consistent new UI, but the complete product brief is not finished.** Several requested external integrations and operator workflows remain incomplete. Local tests do not establish live provider readiness.

## UI delivered

The canvas/graph has been removed. The app now uses warm neutral surfaces, forest-green accents, consistent cards and forms, a redesigned desktop sidebar and header, mobile navigation, and dark-mode colors.

- Landing/pricing, sign-in and sign-up: new layouts, clearly labelled illustrative conversation, accessible password visibility controls.
- Home: real API status and metrics, attention items, shortcuts to customers and assistant configuration.
- Inbox and customer screens: refreshed layout, conversations, customer profile, permissions and existing actions retained.
- My Pi: assistant dashboard with knowledge, behaviour, tools and follow-up links; no draggable canvas.
- Onboarding: all five steps, new-business screen, progress and help controls share the new style.
- Settings: overview, WhatsApp, connection callback, team, billing and business details share the new style.

Review locally at `http://localhost:3200`, `/home`, `/my-pi`, `/inbox`, `/setup` and `/settings`. Protected pages require a standalone Pi session. Owner OS is a separate application at port 3000.

This work changes Pi frontend files and adds this audit. It does not edit the backend implementation or amend the two failing backend tests. Other working-tree changes must not be attributed to this UI delivery.

## Evidence and limits

| Check | Result | What it establishes |
| --- | --- | --- |
| ESLint on `apps/pi/src` | Passed | Static frontend checks |
| Prettier on changed frontend files | Passed | Formatting |
| Isolated production build and TypeScript | Passed | All current app routes compile without using the other development server's build cache |
| Existing Playwright suite | 8 passed; repeated successfully on final localhost:3200 build | Sign-in redirect, actual-status rendering, outage rendering, Inbox approval visibility, viewer restrictions, disabled unavailable tools, 390/1440px layouts; API fixtures |
| Broader browser layout sweep | 108 passed screen/viewport checks | 27 route/state combinations at 390, 768, 1024 and 1440px; no horizontal overflow, uncaught browser errors or unexpected API error responses with the supplied fixtures |
| Final My Pi readability adjustment | 4 additional viewport checks passed | Larger text and single-column phone cards checked after the final CSS change |
| Dark theme and password visibility | Checked in Chromium | Dark media preference and accessible show/hide interaction; not a full accessibility certification |
| Backend unit/integration selection | **148 passed, 2 failed, 150 collected** | Real disposable PostgreSQL database; migration to head; local API/services with provider doubles |
| Authorized live WhatsApp/Stripe/AI journeys | **Not performed** | No real messages sent, numbers purchased or customer charges made by this audit |

Backend test evidence is in `.cache/pi-ui-audit/backend.log` and `backend-results.xml`. Browser evidence is in `.cache/pi-ui-audit/browser-results.json`, `playwright-results.json` and `screenshots/`. Screenshots use explicit test fixtures, not a claim about the current account's customers or connection.

Review screenshots: [Home](pi-saas/screenshots/redesign-1440-home.png), [Inbox](pi-saas/screenshots/redesign-1440-inbox-conversation-1.png), [My Pi](pi-saas/screenshots/redesign-1440-my-pi.png), [mobile My Pi](pi-saas/screenshots/redesign-390-my-pi.png), [Tools](pi-saas/screenshots/redesign-1440-my-pi-tools.png), [Billing](pi-saas/screenshots/redesign-1440-settings-billing.png), [onboarding](pi-saas/screenshots/redesign-1440-setup-step-1.png), [sign-in](pi-saas/screenshots/redesign-1440-sign-in.png), [landing](pi-saas/screenshots/redesign-1440-landing.png), [dark Home](pi-saas/screenshots/redesign-dark-home.png).

Final local build: `gDCIvhhNWwXtQB-vSzfqZ`, served from `.cache/pi-complete-ui-preview/app` at `http://localhost:3200`. The snapshot source matched `apps/pi/src` before promotion. Landing, sign-in, My Pi, proxied public plans and API readiness returned HTTP 200. Only the previous owned preview was replaced; the independent development listener, Owner OS and shared API were preserved. Use `localhost`, as a separate development listener also occupies the wildcard address on port 3200.

The backend run created a unique local PostgreSQL test database and removed only that database afterward. Redis was deliberately unavailable in that test configuration; rate-limit-unavailable warnings do not prove production Redis operation. Migration upgrade was exercised; this run did not repeat downgrade/restore testing.

Two existing tests still assume the previous catalog of 18 tools:

1. `tests/integration/test_pi_tools.py::test_catalog_is_complete_and_typed` compares the whole catalog to the previous exact set.
2. `tests/integration/test_pi_management.py::test_agent_versions_are_immutable_and_rollback_republishes` expects the tools response length to be 18.

The current catalog has 25 tools, including seven additions: `check_availability`, `create_booking`, `cancel_booking`, `get_bookings`, `create_task`, `create_ticket`, and `get_project_status`. These failures are consistent with outdated test expectations. The suite remains **failing** until the tool change and its intended contract are reviewed and those expectations are updated; the tests were not weakened to produce a green result.

## Requirement matrix

“Implemented / locally checked” means evidence exists for the listed scope, not that every possible edge case or production deployment is verified. “Partial” means a requested operation or integration remains. “Unverified” is not a pass.

| Requirement | Status | Current evidence and remaining work |
| --- | --- | --- |
| Separate customer Pi app, landing, auth, tenant switcher | Implemented / locally checked | `apps/pi`, `pi_saas/app_routes.py`, provisioning and session-audience tests. Separate `pi_session` and `pi_csrf` cookies. A live account login was not repeated in this UI audit. |
| Shared backend with independent Pi audience/origins/CSRF | Implemented / locally checked | `core/audience.py`, middleware, auth dependencies and `test_pi_saas.py`; no separate copied backend. |
| Business/customer/environment isolation | Implemented / selected local checks | Two businesses for one owner, scoped conversations and tools tested. This run does not exhaustively prove every cache, vector, media and job path. |
| Trusted inbound routing, signed events, duplicates/retries | Implemented / local provider doubles | Kapso connection/event services, event jobs and webhook deduplication tests. Real project payloads, delivery ambiguity and operational reconciliation still need provider checks. |
| Backend permissions, delegated/customer scope, takeover | Implemented / selected local checks | Registry, record-scoped Inbox, scoped service identity and approval tests. Full permission-by-operation acceptance coverage remains broader than this selected suite. |
| Client role presets, operator roles, support grants | Implemented API / partial UI | Client team and grant UI exists. Operator services enforce scope and audit. Full role customization and operator management UI are not delivered. |
| Five-step resumable onboarding and help request | Implemented / locally checked | Business, offers, connection, help configuration and preview/launch; readiness gates are tested. All five steps were rendered in browser fixtures. |
| Existing WhatsApp number, coexistence, callbacks, health | Implemented / live verification pending | `kapso.py`, `connections.py`, WhatsApp UI. Verify real consent, coexistence eligibility, callback completion, health, reconnect and disconnect in the selected provider account. |
| New-number selection, live inventory, actual charges | Partial | Operator-reviewed request, quote and explicit confirmation exist. There is no verified end-to-end live inventory/pricing/reservation purchase flow. Listed target countries are not evidence of available numbers. |
| Do not expose provider secrets/IDs in ordinary setup | Implemented UI / reviewed | Customer setup presents guided actions and business settings. Secrets remain server configuration. |
| Services, commerce and hybrid conversations | Implemented / selected local checks | Service-conversation brief, catalog/order tools and policy paths exist; full commercial acceptance still includes the gaps below. |
| Price policies and untrusted-content boundaries | Implemented / selected local checks | Multilingual price-policy and review-fix tests passed; catalog tools/registry constrain authority. No claim of exhaustive adversarial coverage. |
| Human approval, takeover/resume, unknown question escalation | Implemented / locally checked | Inbox permissions, held replies, Ask Owner and runtime checks covered by selected tests. |
| Customer memory, correction, deletion, export | Implemented / partial | Scoped profile, memory edits/deletion and controlled export exist. Dedicated client retention controls and a complete retention lifecycle were not found in the current UI. |
| Website/text knowledge approval and publication | Implemented / locally checked | `teach.py`, website import, drafts/publish and atomic-publication tests. |
| Teach Pi uploads/recorded updates | Partial | Standalone UI supports text and website teaching. Shared document upload API exists, but standalone upload/record UI and its complete review journey are missing. |
| Image/audio/document/video understanding | Existing shared capability / partial verification | Existing pipeline, knowledge-job and video tests ran. Full provider-backed media processing, private storage, limits, retries and usage acceptance were not established by this audit. |
| Controlled typed tool registry | Implemented / test expectations need review | 25 catalog entries with scope/policy checks; 2 stale catalog-count tests fail. A tool category name in onboarding alone is not completion. |
| Booking availability, creation, cancellation | Native implementation / locally checked | `work.py`, `work_handlers.py`, services/bookings UI; concurrency and customer-agreed offered-slot tests passed. |
| Google Calendar, staff calendars, rescheduling | **Remaining** | Native booking service explicitly does not write an external calendar. No Google Calendar adapter found in current provider code; full reschedule/staff-calendar workflow absent. |
| CRM/customer history/brief | Native implementation / partial scope | Native customer/profile/brief tools exist. Verify the full assignment/stage/field operation matrix; no external CRM is required as the initial adapter. |
| Tasks/projects and support tickets | Native implementation / partial UI | Work services, scoped task/ticket routes, creation tools and project-status tool exist. Full standalone task/ticket management UI and all requested workflow operations are not present. |
| Quotes/invoices/PDF approvals and send | Partial | Shared quote draft/invoice lookup and pricing services exist. The complete standalone PDF approval, version and authorized-send journey is not established by the current UI/catalog. |
| Customer checkout/deposit links and signed payment status | **Remaining** | `payments` is disabled in standalone tool selection; its named operations are absent from the executable Pi catalog. Pi subscription billing is separate from a business collecting customer payments. |
| Native catalog/inventory/orders | Implemented / selected local checks | Catalog, stock, totals, order confirmation and customer-scoped retrieval tools exist and were exercised in shared Pi tests. |
| Shopify adapter and store authorization | **Remaining** | No executable Shopify provider adapter found. Owner OS integration demo metadata is not a working integration. |
| Consent-based follow-ups and cancellation | Implemented foundation / partial | One-reminder service, consent, cancellation and language/template configuration exist. Full scheduling, quiet-hours and template-provider lifecycle still require end-to-end acceptance. |
| Campaigns and WhatsApp Flows | **Remaining** | Campaign model exists; no complete execution/API/UI workflow found. Model/table existence does not satisfy this requirement. |
| Email/meeting invitations | **Remaining for Pi tool workflow** | General Resend/SendGrid/SMTP transports exist; no complete Pi authorized email/meeting-invitation tool and configuration journey found. |
| Home reporting, weekly business/operator digests | Partial | Scoped Home counters and operator summary API exist. Scheduled weekly digests, destinations and complete client/operator summary UI are not established. |
| Owner OS operator management and Pi Agenta | API foundation / **UI and agent integration remaining** | `/api/v1/operator/pi` has accounts, grants, status/actions, roles and summary services. No frontend calls to this operator API or complete Pi Agenta integration found in `apps/web/src`. |
| Pi subscription lifecycle, invoices, billing controls | Implemented / local signed-event checks | `billing.py`, entitlement services, client billing UI and signed webhook tests. Verify configured prices, checkout/portal, plan changes, cancel and invoices using a Stripe sandbox account. |
| Metering/caps, storage, seats, numbers and spend | Partial | Message/AI/media counters, seat reporting and spend limit exist. Full applicable storage/number/provider-cost accounting and all dimension caps need completion/verification. |
| Jobs, health, failed-event replay, operational readiness | Partial | Bounded event attempts, lifecycle sweep and operator replay APIs exist. Production Redis/worker monitoring, backup/restore rehearsal and operational runbook remain unverified. |
| Responsive customer UI with loading/error states | Delivered / fixture browser checks | Existing standalone routes restyled and tested across four widths; active/outage/permission states covered in existing suite. Formal accessibility audit and every state/interaction remain outside this result. |
| Preserve Owner OS Pi compatibility | Selected backend regressions checked | Existing shared Pi suites included. Owner OS frontend was not modified by this redesign or comprehensively retested; the entire repository cannot be declared regression-free. |
| Diagrams, permission matrix, configuration/runbook handoff | Partial | Original brief, status/review files and `.env.example` exist. The promised consolidated `docs/PI_SAAS.md` is still absent. This audit supplies current status, not the entire missing implementation/runbook. |

## Outstanding acceptance sequence

1. Review the seven new tool contracts and update the two legacy catalog assertions; rerun the affected tests.
2. Finish Google Calendar and Shopify authorization/adapters, Pi customer payment links, email/invitation actions and their contract tests.
3. Complete standalone upload/record teaching, task/ticket workflows, advanced booking operations, campaign/Flows and digest functionality.
4. Build the scoped Owner OS operator UI and connect Pi Agenta to the same authorized services.
5. Complete applicable metering/retention controls and the architecture, permissions, provider-setup and operations handoff.
6. Run provider sandbox journeys with configured credentials, then explicitly authorized live acceptance. Record provider results separately from mocks.

The existing configuration examples name `PI_APP_ORIGINS`, `PI_APP_PUBLIC_URL`, `KAPSO_API_KEY`, `KAPSO_WEBHOOK_SECRET`, `PI_BILLING_STRIPE_SECRET_KEY`, and `PI_BILLING_STRIPE_WEBHOOK_SECRET`. Subscription plans also need configured Stripe price IDs. Their presence as configuration fields does not prove valid credentials or provider readiness. The unimplemented Google/Shopify/customer-payment/email paths need code and connection flows, not merely credentials.

The older `PI_SAAS_STATUS.md` is behind the working tree: it still lists the frontend, native bookings/tasks/tickets and playground as unfinished. This audit accounts for the actual newer code while retaining the remaining gaps.
