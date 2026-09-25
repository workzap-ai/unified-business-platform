# Integration platform

Status (2026-09-25): provider adapters and business workflows are implemented. Business
tests use real PostgreSQL and mocked provider networks; they do not prove real email
delivery or paid transactions. Read-only live checks are recorded in
[INTEGRATION_CHECK_2026-09-25.md](INTEGRATION_CHECK_2026-09-25.md). Redis-dependent behavior
uses fakes in the workstation tests; Redis is not running locally.

HTTP contract: [contracts/integrations-api.md](contracts/integrations-api.md).

## Using integrations in business workflows

Connecting a provider verifies credentials. Configure its business use in the connection's
**Use this integration** panel:

- Resend, SMTP, SendGrid, Slack and generic webhooks: choose business events, add email
  recipients where applicable, and save with automatic delivery enabled. New events become
  durable operations; historical events are not replayed. `notification.created` also lets
  existing application notifications, including PI handoffs, reach the configured channel.
- Email: **Email invoice** on issued invoices queues a summary for the customer's saved
  email. The latest verified workspace email connection is selected. It does not require
  event alerts to be enabled. Check operation history for delivery status.
- Stripe: **Create payment link** on an open invoice creates a hosted Checkout Session.
  Configure the displayed inbound endpoint in Stripe for `checkout.session.completed` and
  `checkout.session.async_payment_succeeded`, including its signing secret. Verified payment
  callbacks update the invoice once. An inconsistent payment or changed invoice balance
  requires review. Stripe sandbox uses test payments; use a test workspace for that work.
- S3: invoice, customer and order detail screens now support upload, attachment download and
  deletion. Storage keys contain tenant/environment IDs; record permissions apply.
- WhatsApp: **Use for PI messaging** links the verified number to PI without another token
  setup. PI must be installed/enabled, and the integration needs an app secret and verification
  token. Point Meta at the integration endpoint shown on the connection. Inbound messages and
  delivery receipts enter the existing PI pipeline. Token rotation and disabling propagate
  to PI. Legacy PI connections remain supported.
- API keys: use scoped bearer keys on `/api/v1/external/customers` or
  `/api/v1/external/invoices/{id}`. Revocation, expiry and creator permission changes apply.

Delivery runs through the existing production ARQ cron. Development inline mode now scans
durable integration work every 15 seconds, including failed queue submissions. Operation
history refreshes in the connection screen. An interrupted send requires explicit review;
idempotent retries keep the same operation ID and stop before the provider's 24-hour window.
Email sending still requires a verified domain and valid account credentials; no provider
connection or alert recipient is silently created. Planned catalog providers remain planned.

Apply Alembic revision `3ad535597720` before starting this version; it adds workflow/operation
tables and an optional link from PI's WhatsApp connection to its integration connection.

## Architecture

```
business services ──emit()──▶ outbox_events ──dispatch_outbox──▶ integration_deliveries ──deliver_webhook──▶ tenant endpoints
                                  (same transaction)            (unique per subscription+event)      (signed, retried, dead letter)

provider ──POST /api/v1/webhooks/{key}/{token}──▶ verify signature ─▶ integration_inbound_events ─▶ process_inbound_event ─▶ handler
                                                  (token → connection → tenant/env)   (unique connection+provider_event_id)

UI ─▶ /api/v1/integrations/* ─▶ IntegrationService ─▶ ConnectionRuntime.call ─▶ circuit ▸ rate limit ▸ adapter ▸ OutboundClient
```

| Piece | Location | Notes |
| --- | --- | --- |
| Outbound HTTP + SSRF guard | `app/integrations/http.py` | Every provider call and webhook delivery |
| Retry / circuit / rate limit | `retry.py`, `circuit.py`, `rate_limit.py` | Circuit persisted on the connection row |
| Credentials | `crypto.py` | MultiFernet; hints only |
| Definitions + adapter contract | `registry.py`, `catalog.py`, `providers/*` | `planned` = no adapter |
| Runtime (policy + health recording) | `runtime.py` | Status state machine |
| OAuth2 + PKCE | `oauth.py` | Server-side state |
| Inbound webhooks | `webhooks.py`, `modules/integrations/webhook_routes.py` | Public route |
| Outbox + deliveries | `outbox.py`, `events.py`, `signing.py` | One event catalog |
| Sync engine | `sync.py` | Stripe customers pull |
| Email | `email.py` | Templates + transport choice |
| Worker jobs | `jobs.py` (registered in `app/worker.py`) | cron sweep every minute |
| Module (models, API) | `app/modules/integrations/` | Migration `0004_integration_platform` |

### Data model and isolation

All tables are `WorkspaceRow`s (tenant + environment, composite FK to
`environments(tenant_id, id)`); child tables reference `integration_connections`,
`integration_webhook_subscriptions`, `outbox_events` and `integration_sync_jobs` through
`(tenant_id, environment_id, id)`. A sandbox connection in staging can never be referenced
from production rows. All API queries go through `WorkspaceRepository`; guessed IDs from
other tenants/environments return 404 (tested).

Idempotency constraints: `(connection_id, provider_event_id)` on inbound events,
`(subscription_id, outbox_event_id)` on deliveries, one active (`pending|running`) sync job
per connection+entity, globally unique API key prefix and webhook endpoint-token hash.

### Connection status

`draft → connecting → connected ⇄ degraded`, `→ expired` (OAuth), `→ error`, `→ disabled`,
`→ revoked` (terminal; credentials destroyed, row kept for audit). Transitions are enforced
by `runtime.CONNECTION_STATES`. Health (`healthy|degraded|failing|unknown`), latency,
consecutive failures, circuit state and `rate_limited_until` are recorded by every call;
`GET /integrations/health` only reads them and never calls providers.

### Outbound HTTP policy (SSRF)

`validate_outbound_url` runs on **every** request (not only at save time):

* https only; plain http only for hosts in `OUTBOUND_HTTP_ALLOWLIST`, which production
  refuses to start with;
* no userinfo, no whitespace/backslashes, URL ≤ 2048 chars;
* ports: 443 (80 for allowlisted http) plus `OUTBOUND_ALLOWED_PORTS`;
* numeric host encodings other than canonical IPv4/IPv6 are rejected (`2130706433`,
  `0x7f000001`, `0177.0.0.1`, `127.1`);
* `localhost`, `*.localhost`, `*.localdomain`, `*.internal`, `metadata.google.internal`
  are rejected;
* DNS is resolved and **every** answer must be public unicast: loopback, RFC 1918,
  link-local, CGNAT (100.64/10), multicast, reserved, unspecified, IPv6 ULA (fc00::/7),
  IPv4-mapped / 6to4 / Teredo / NAT64 embeddings of those, and the metadata endpoints
  169.254.169.254 and fd00:ec2::254 are refused;
* redirects are never followed (a 3xx is an error), responses are streamed with a size cap
  (gzip/deflate decoded with an output cap), TLS verification is on (forced in
  production), connect/read/write/pool timeouts plus a total deadline.

**Residual risk — DNS rebinding.** The address check and httpx's own connect-time
resolution are separate lookups; a hostile resolver with a zero TTL can pass the check and
then answer with a private address. The resolved IP is not pinned (pinning breaks SNI/TLS
verification with plain httpx). Production mitigation: route egress through a proxy or
network policy that blocks private/metadata ranges. The same applies to SMTP.

Logs: `integration_http` events carry only `provider` (host), `operation` (method +
outcome), `status_code`, `duration_ms` via the allowlisted formatter — never URLs with
query strings, headers or bodies. `redaction.py` masks Authorization/API keys/tokens/
secrets/signatures in stored payloads and any text we persist.

### Retries, circuit breaker, rate limits

* Classification (`errors.py`): 5xx/408/network → `retryable`; 429 → `rate_limited`
  (honours `Retry-After`, capped); 401/403 → `auth` (never retried; connection → `error`);
  other 4xx → `permanent`; malformed/oversized → `invalid_response`; a **non-idempotent**
  call that timed out → `ambiguous` (never blindly retried — e.g. a WhatsApp send).
* In-call retries (`with_retry`): bounded exponential backoff with full jitter. Durable
  retries (deliveries, events, sync jobs): exponential with jitter
  (`DELIVERY_BACKOFF_BASE_SECONDS` … `_MAX_SECONDS`), then `dead_letter`.
* Circuit: opens after `CIRCUIT_FAILURE_THRESHOLD` counted failures (retryable, rate
  limited, ambiguous, malformed), rejects calls for `CIRCUIT_COOLDOWN_SECONDS`, then allows
  one half-open probe. State lives in DB columns, so all processes agree.
* Rate limits: Redis token buckets per connection and per tenant+provider (tenant bucket =
  3× one connection) so tenants cannot starve each other or multiply budget by adding
  connections. If Redis is down we **fail open to conservative**: an in-process bucket at
  `INTEGRATION_RATE_LIMIT_FALLBACK_PER_MINUTE` (default 20/min) per process. Provider 429s
  set `rate_limited_until` on the connection and are respected before any call.

### Credentials

`SECRETS_ENCRYPTION_KEY` (Fernet). Rotation: put the new key first
(`SECRETS_ENCRYPTION_KEY=new,old` or `SECRETS_ENCRYPTION_PREVIOUS_KEYS=old`), deploy,
re-encrypt with `CredentialManager.rotate()`, then remove the old key. Storing credentials
without a key fails closed (`503 ENCRYPTION_NOT_CONFIGURED`); production startup requires the
key while `INTEGRATIONS_ENABLED=true`. The API exposes only `{key, set, hint}` (last 4
chars for secrets ≥ 12 chars). Tests assert serialized API responses and audit details
never contain credential values.

> PI's legacy `app/modules/pi/whatsapp.py` builds `Fernet(SECRETS_ENCRYPTION_KEY)` directly:
> keep a single key in that variable and use `SECRETS_ENCRYPTION_PREVIOUS_KEYS` for retired
> keys until PI delegates to `CredentialManager`.

### Inbound webhooks

`POST /api/v1/webhooks/{integration_key}/{endpoint_token}` — public (no session, no CSRF).
`PublicWebhookOriginExemption` (in `app.main`, wrapping `OriginCheckMiddleware`) strips the
`Origin` header on exactly this path shape; every other route is still origin-checked.
Pipeline: body cap (`WEBHOOK_MAX_BODY_BYTES`, 413) → connection by SHA-256 of the 256-bit
endpoint token (never by payload IDs; unknown/disabled/revoked → generic 404) → adapter
signature check (+ timestamp window where the provider signs one) → normalize → insert
idempotently → commit → enqueue `process_inbound_event` → fast 200. Stored payload is the
redacted normalized event data (size-limited, `payload_truncated` flag) plus the SHA-256 of
the raw body; payloads are nulled after `WEBHOOK_PAYLOAD_RETENTION_DAYS` by the sweep.
`GET` on the same URL answers provider verification handshakes (Meta `hub.challenge`).

Handlers: `@webhooks.register_handler(integration_key, event_type)` — async
`(session, system_scope, event) -> "processed" | "ignored"`; must be idempotent (replay
re-runs them). Without a handler events are marked `ignored` and remain replayable. **No
business handlers are registered yet** (Stripe events are recorded, not acted upon).

### Outbox and outbound webhooks

Wire business events with (inside the business transaction, before commit):

```python
from app.integrations.outbox import EntityRef, emit

await emit(session, scope, "invoice.paid",
           {"invoice_id": str(invoice.id), "number": invoice.number,
            "amount": str(invoice.total), "currency": invoice.currency},
           EntityRef("invoice", invoice.id))
```

Signature: `emit(session: AsyncSession, scope: WorkspaceScope, event_type: str,
payload: dict[str, Any], entity_ref: EntityRef | None = None, *, origin: str | None = None,
correlation_id: str | None = None) -> OutboxEvent`. Event types must be in
`app/integrations/events.py` (`ValueError` otherwise); payload ≤ 64 KiB JSON, no secrets,
money as decimal strings. `emit` only flushes; it commits or rolls back with the caller.

Deliveries are signed: `X-Platform-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret,
"<t>." + body)>`, plus `X-Platform-Event`, `X-Platform-Delivery` and a stable
`Idempotency-Key: <event_id>:<subscription_id>`. Receivers verify with
`signing.verify_signature_header` semantics and a ±5 minute tolerance. Subscription secrets
are stored encrypted (we must sign with them) and shown once (create / rotate).

### Sync engine

`integration_sync_jobs` (`pending → running → succeeded | failed | paused | cancelled |
dead_letter`), `integration_sync_attempts`, `integration_sync_cursors`,
`integration_sync_conflicts`, `integration_external_refs`. Jobs run in the worker one page
at a time, checkpointing stats + cursor after each page and re-reading their status so a
pause/cancel takes effect between pages; failed jobs are auto-retried by the sweep (max 3
attempts); non-retryable errors go to `dead_letter`. Loop prevention: each external ref
stores the last fingerprint and `last_write_origin`; unchanged or self-originated records
are skipped. A definition can only declare sync when its adapter implements a sync source
(enforced at registration); all others report `sync_support: ["none"]`.

### Email

`EmailService(session, settings, http, scope).send_template(name, to, variables)` uses the
workspace's connected `smtp`/`resend`/`sendgrid` connection, else the platform SMTP from
`PLATFORM_SMTP_*`, else `503 EMAIL_NOT_CONFIGURED`. Templates (`invitation`,
`handoff_notification`, `integration_failure`, `system_alert`) are fixed in code: plain text
+ HTML with every variable escaped, CR/LF stripped, links restricted to http(s), unknown
variables rejected. Routes never accept HTML.

### API keys

Format `pk_live_<8 hex>_<secret>` (production environments) / `pk_test_…`. Only SHA-256 of
the full key is stored; lookup by the public prefix; constant-time compare. Scopes ⊆ the
creator's permissions and never `api_keys.manage`. At use, effective permissions = scopes ∩
the creator's current grants; revoked/expired keys, inactive creator membership, tenant or
environment fail with 401. `app.modules.integrations.api_keys.ApiKeyScope` is the FastAPI
dependency for the external API routes: it yields a system `WorkspaceScope` pinned to the
key's tenant+environment (repositories isolate exactly as for users). `last_used_at` is
updated at most once a minute; a per-key Redis rate limit (600/min, fail-open) applies.

## Providers

All adapters: credentials encrypted, tests are read-only, calls through `OutboundClient`.
**Live verification: UNVERIFIED** for all.

| Key | Purpose | Credentials / config | Test connection | Webhooks | Sync |
| --- | --- | --- | --- | --- | --- |
| `generic_webhook` | Signed JSON to any HTTPS endpoint (Zapier/Make/n8n) | `url`; `signing_secret` (≥16) | URL + DNS + SSRF validation, **no send** | outbound only | none |
| `slack` | Channel notifications via incoming webhook | `webhook_url` (secret) | URL shape + SSRF, **no post** | no | none |
| `whatsapp_meta` | WhatsApp Cloud API send/receive/media | `phone_number_id`, `business_account_id?`; `access_token`, `app_secret?` (falls back to `WHATSAPP_APP_SECRET`), `verify_token?` | `GET /{version}/{phone_number_id}?fields=display_phone_number,verified_name,quality_rating` | `X-Hub-Signature-256`; GET `hub.challenge`; no signed timestamp → replay protection = idempotency on message id | none |
| `smtp` | Email via own server | `host`, `port` (25/465/587/2525), `security`, `username?`, `from_address`, `from_name?`; `password` | connect, EHLO, STARTTLS, EHLO, AUTH, QUIT — **no send** | no | none |
| `resend` | Transactional email | `from_address`; `api_key` (`re_…`) | `GET /domains` (sending-only key's `restricted_api_key` 401 = valid) | no | none |
| `sendgrid` | Transactional email | `from_address`, `from_name?`; `api_key` (`SG.…`) | `GET /v3/scopes`, requires `mail.send` | no | none |
| `s3` | Files on S3 / R2 / MinIO | `endpoint_url`, `bucket`, `region` (`auto` for R2), `addressing` path/virtual, `key_prefix?`; `access_key_id`, `secret_access_key` | `HEAD` bucket (SigV4, own signer verified on AWS vectors) | no | none |
| `stripe` | Payment intents, events, customer linking | `secret_key` (`sk_/rk_` test for sandbox, live for production); `webhook_secret?` (`whsec_`) | `GET /v1/balance` | `Stripe-Signature` with `WEBHOOK_REPLAY_WINDOW_SECONDS` | customers **pull**, platform is source of truth (link by email, conflicts recorded, CRM never written) |

Planned (listed, not connectable, no adapter): `google_calendar`, `microsoft_calendar`,
`google_workspace`, `microsoft_graph`, `quickbooks`, `xero`, `shopify`, `woocommerce`,
`microsoft_teams`. Interfaces exist for calendar/accounting/commerce providers
(`registry.py`); the OAuth framework is ready (verified with a fake provider).

Per-provider limitations:

* **WhatsApp:** PI keeps its own platform-level webhook (`/api/v1/webhooks/whatsapp`) and
  send/media code in `app/modules/pi/whatsapp.py`; it was **not** refactored onto this
  adapter (concurrent PI work). Follow-up: have PI resolve its `WhatsAppConnection` to an
  integration connection and call `WhatsAppMetaProvider.send_text/get_media/parse_webhook`.
  Media downloads are limited to Meta's lookaside hosts and `MEDIA_MAX_BYTES`.
* **Slack:** incoming webhooks give no delivery receipt beyond `ok`; 404/`no_service` marks
  credentials invalid.
* **SMTP:** blocking smtplib runs in a worker thread with timeouts; DNS-rebinding residual
  risk as above; plaintext `none` is refused in production.
* **Resend/SendGrid:** sending uses provider idempotency where supported (Resend
  `Idempotency-Key`); SendGrid has none, so a timed-out send is `ambiguous`.
* **S3:** single-request PUT (≤ `STORAGE_MAX_UPLOAD_BYTES`, no multipart); presigned URLs
  capped at `STORAGE_SIGNED_URL_TTL_SECONDS`; use `providers.s3.scoped_key` for
  tenant/environment key prefixes in shared buckets.
* **Stripe:** API version is the account default (not pinned); Stripe customer listing is
  newest-first, so "incremental" re-pages but skips unchanged records by fingerprint.

## Test procedure

```bash
cd apps/api && source ../../.cache/test-env.sh
../../.venv/Scripts/pytest.exe tests/unit/test_integrations_*.py tests/integration/test_integrations_*.py
```

Unit: SSRF matrix, redirects, size caps, propagation, redaction/log safety, retry
classification and Retry-After, circuit transitions, token buckets (fake Redis + outage),
MultiFernet rotation, SigV4 vectors, per-adapter contract tests (success, 401, timeout, 5xx,
429, malformed JSON), signature/replay checks, templates. Integration (PostgreSQL):
lifecycle and secret non-disclosure, cross-tenant/cross-environment 404s, RBAC 403s,
webhook pipeline (valid/invalid/missing/stale signature, duplicates, unknown token,
oversize, handler + replay), outbox → signed delivery → retry → dead letter → idempotent
manual retry, redirect not followed, OAuth state tamper/reuse/expiry/foreign workspace,
missing scope, refresh + invalid grant, Stripe customer sync + controls, API keys, the
0004 permission backfill, circuit reporting.

Manual live test (per provider, sandbox accounts): create a connection in a staging
environment, `POST …/test`, then exercise one real operation from a Python shell with
`ConnectionRuntime`. Record results here before marking any provider VERIFIED.

## Production checklist

- [ ] `SECRETS_ENCRYPTION_KEY` set (single key while PI uses its legacy helper) and backed up;
      rotation runbook rehearsed.
- [ ] `INTEGRATIONS_PUBLIC_BASE_URL` / `OAUTH_REDIRECT_BASE_URL` are HTTPS and the OAuth
      redirect URI is registered exactly.
- [ ] Egress proxy / network policy blocks private and metadata ranges (DNS-rebinding
      mitigation); `OUTBOUND_HTTP_ALLOWLIST` empty (enforced).
- [ ] ARQ worker running with the `integrations_sweep` cron; Redis reachable (otherwise
      the conservative rate-limit fallback applies).
- [ ] `WEBHOOK_PAYLOAD_RETENTION_DAYS` agreed with the data-retention policy.
- [ ] Each provider verified live in sandbox and recorded above (currently UNVERIFIED).
- [ ] Business modules wired to `emit()` for the event catalog (not done in this change).
- [ ] Alerts on `dead_letter` deliveries/events/jobs and on connections in `error`.
