# Integration verification — 2026-09-25

The integration application passes its selected automated checks, but the configured
external services are not all operational. **210 automated tests passed.** A fresh
production web build also passed. Live checks used the configuration in `apps/api/.env`
and the existing local workspace session; credentials are excluded from this report.

## Live results

| Feature | Result | Evidence / limitation |
| --- | --- | --- |
| API and website proxy | Passed initially | `/api/v1/health/live` and `/api/v1/health/ready` returned 200 through both API and website. The local website later stopped; the existing startup script restored it before live page verification. |
| Neon PostgreSQL | Passed | Read-only connection and queries succeeded. Observed migration revision: `0005_employee_onboarding`. The source tree also contains `0006_pi_service_conversations`, which was not applied by this audit. |
| Integration pages | Passed | Directory, Resend, outbound webhooks, inbound events, jobs, failures, health, API keys, and the connected Resend detail page rendered against the real API. No captured page exceptions, failed integration API responses, or horizontal overflow on the eight checked overview pages at 1440px. |
| Resend | Authentication passed; delivery unverified | The saved connection decrypted successfully and its read-only provider health check passed in 1,050 ms. The provider reported **0 verified domains**. No email was sent, so delivery and sender-domain readiness are not established. |
| OpenAI | Failed generation | Model listing returned 200 and included the configured models. A tiny `gpt-4o-mini` chat request returned HTTP 429 with `credit_balance_exhausted`. |
| Gemini | Failed generation | Default transport could not connect. IPv4 transport successfully listed models, including both configured chat models with `generateContent` support. Actual generation using `gemini-2.5-flash-lite` and `gemini-2.5-flash` still returned HTTP 404 / `NOT_FOUND`. Listing alone does not establish that generation works. |
| Groq | Failed configured chat models | Authentication/model listing returned 200. `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` returned HTTP 404 / `model_not_found`; neither was in the account's returned model list. The configured vision model was also absent from that list. |
| Redis / ARQ | Unavailable locally | Port 6379 was unreachable. The current API uses `JOB_QUEUE_MODE=inline`; successful readiness therefore does not verify Redis or an ARQ worker. |
| Render.com hosting | No setup found | No Render deployment configuration, Render service URL, or Render credential setting was found in the inspected project/configuration. No hosted deployment was verified. |

Resend was the only active saved integration. No active connections were configured for
Generic webhook, WhatsApp Meta, Slack, SMTP, SendGrid, S3, or Stripe. PI's separate
WhatsApp connection table was also empty. These adapters have automated test coverage,
but their real accounts and operations were not verified.

Google Calendar, Google Workspace, Microsoft Graph, Microsoft Calendar, Microsoft Teams,
QuickBooks, Shopify, WooCommerce, and Xero remain marked **planned** in the catalog;
they are not connectable implementations.

## Automated verification

| Check | Result | What it establishes |
| --- | --- | --- |
| Integration adapter, HTTP, resilience, and SigV4 unit suites | 115 passed | Adapter behavior using mocked providers; URL/SSRF policy, response limits, error handling, retries, signatures, credential handling. |
| Integration API and domain-event suites on disposable local PostgreSQL | 22 passed | Connection lifecycle, write-only secrets, tenant/environment isolation, permissions, inbound webhook verification/deduplication/replay, outbound delivery/retry/dead-letter flow, OAuth/PKCE, Stripe sync controls, API keys, and transaction-scoped events. Provider calls are mocked. |
| AI gateway/media/embedding, Neon configuration, and AI usage suites | 62 passed | AI adapter/fallback/media logic and database configuration behavior. These do not prove real provider generation availability. |
| Chromium integration UI suite | 10 passed | Demo-mode connection flow, failure display, secret reveal/revocation, webhook creation, retries, sync controls, empty environments, role gating, and 390px mobile overflow. |
| Live integration API contract suite | 1 passed | Actual FastAPI/PostgreSQL responses parse using the frontend's Zod schemas. Used an isolated local API on port 8001 and the disposable `_test` database. |
| Fresh Next.js production build | Passed | Compilation, TypeScript checking, and static page generation using a separate ignored build directory. |

Selected commands, from the repository root unless noted:

```powershell
# The existing helper reads only the disposable local test database credentials.
.\.venv\Scripts\python.exe .cache/run_pi_checks.py pytest -q tests/integration/test_integrations_api.py tests/integration/test_domain_events.py -p no:cacheprovider
.\.venv\Scripts\python.exe .cache/run_pi_checks.py pytest -q tests/unit/test_ai_gateway.py tests/unit/test_ai_media_providers.py tests/unit/test_media_embeddings.py tests/unit/test_database_neon.py tests/integration/test_ai_usage.py -p no:cacheprovider

# From apps/api:
..\..\.venv\Scripts\python.exe -m pytest -q tests/unit/test_integrations_adapters.py tests/unit/test_integrations_http.py tests/unit/test_integrations_resilience.py tests/unit/test_integrations_sigv4.py -p no:cacheprovider

# From apps/web, with the separate demo build prepared:
$env:NEXT_DIST_DIR='.next-integration-audit'
$env:NEXT_PUBLIC_DATA_MODE='demo'
npm.cmd run build
$env:PLAYWRIGHT_BROWSERS_PATH='../../.cache/ms-playwright'
npx.cmd playwright test tests/integrations.spec.ts --workers=2 --output=../../.cache/integration-audit-browser

# With the isolated test API running on 8001:
$env:LIVE_BASE_URL='http://127.0.0.1:8001'
npx.cmd playwright test --config playwright.live.config.ts tests/integrations.live.spec.ts --output=../../.cache/integration-contract-browser
```

Local diagnostics and sanitized live results are under `.cache/`:
`integration_live_audit.py`, `integration-live-audit-results.json`,
`live_integration_pages.cjs`, and `integration-live-pages-results.json`.
The JSON provider results record the initial default-transport run; the IPv4 follow-up
results are recorded in the table above.

## Follow-up needed

1. Restore OpenAI credit and repeat a real generation check.
2. Resolve Gemini connectivity and its generation 404 responses; model listing succeeds
   over IPv4 but is insufficient evidence of a working model.
3. Configure and verify currently available Groq chat/vision models. No provider model
   selections were changed during this audit.
4. Establish Resend sender-domain readiness and perform an explicitly requested delivery
   test to a chosen recipient.
5. Provide Redis and an ARQ worker before relying on durable background processing.
6. Review the pending database migration before using the newer PI service-conversation
   features. No live database schema changes were made during this audit.

This was a functional integration check, not a production deployment or load test.
No emails, WhatsApp messages, Slack posts, charges, or hosted deployments were initiated.
