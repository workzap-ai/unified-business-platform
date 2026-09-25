# Integrations API contract (v1)

## Business workflow routes (2026-09-25)

Paths below include `/api/v1`. Session routes retain active workspace/environment and
CSRF checks; public API-key routes use bearer credentials exclusively.

| Route | Permission / behavior |
| --- | --- |
| `GET /integrations/capabilities` | Signed-in workspace; `{email, storage, payments}` readiness |
| `GET /integrations/connections/{id}/workflow` | `integrations.read`; `{enabled, event_types, recipients}` |
| `PUT /integrations/connections/{id}/workflow` | `integrations.manage`; same body, supported events, verified connection, email recipients required when enabled |
| `GET /integrations/connections/{id}/operations` | `integrations.read`; latest 100 durable business operations |
| `POST /integrations/operations/{id}/retry` | `integrations.operate`; failed notification only; `{acknowledge_duplicate_risk:true}` required for `needs_review` |
| `POST /integrations/connections/{id}/activate-pi` | `integrations.manage` + `pi.whatsapp.manage`, PI installed/enabled; `{status, connection_id}` |
| `POST /billing/invoices/{id}/checkout` | `billing.write`; open invoice, connected Stripe with signing secret; returns durable checkout operation |
| `POST /billing/invoices/{id}/email` | `billing.write`; `{request_id: UUID}`; customer email, connected email provider; 202 operation, not delivery confirmation |
| `GET /files/records/{type}/{id}` | Record read permission; attachment operations, latest 100 |
| `POST /files/records/{type}/{id}` | Record write permission; multipart `file` + `request_id`; non-empty, configured cap up to 25 MiB; 201 operation |
| `GET /files/{id}/download` | Record read permission; attachment disposition, octet-stream, private/no-store |
| `DELETE /files/{id}` | Record write permission; idempotent S3 delete, 204 |
| `GET /external/customers` | Bearer API key with `customers.read`; paginated customers |
| `GET /external/invoices/{id}` | Bearer API key with `billing.read`; invoice detail |

`type` is `customer`, `order`, or `invoice`. Operation fields: `id`, `connection_id`,
`kind` (`notification|checkout|file`), `status`, `attempts`, `last_error`, `created_at`,
`entity_type`, `entity_id`, `output`. Statuses: `pending|running|succeeded|failed|needs_review|cancelled`.
No credentials or recipient addresses are returned in operation history. Checkout output
includes hosted Stripe `url`, connection `mode`, and `payment_state`; file output includes
`name`, `size`, and workspace-prefixed storage `key`.

Saving an enabled event workflow applies only to new events, never historical backlog.
Disconnecting/disabling or removing a recipient/event cancels matching queued alerts.
Resend and generic webhook delivery use a stable operation ID across bounded retries.
Uncertain non-idempotent sends and interrupted claims require review before retry.
Generic receivers must deduplicate `X-Platform-Delivery-Id`. Invoice email and file requests
reuse the supplied UUID on transport retries. A reused file UUID with different bytes is
rejected. Stripe checkout callbacks never trust invoice metadata: the server retrieves the
session and checks amount, currency, client reference and mode before recording one payment.
An invoice balance changed after checkout creation requires manual payment reconciliation.

## Connection management

The backend (`apps/api/app/modules/integrations`) and the web app
(`apps/web/src/features/integrations`) both implement this contract. Change it here first.

All routes are under `/api/v1/integrations`, require a session (cookie + CSRF on mutations)
and are scoped to the session's active tenant **and environment**. Permissions:
`integrations.read` (GET), `integrations.manage` (connect/configure/disconnect),
`integrations.operate` (retry/replay/resync/test), `api_keys.manage` (API keys).
Errors use the standard envelope `{"error":{"code","message","details","request_id"}}`.
Lists use `Page<T>` = `{items, total, page, page_size}` with `page`/`page_size` query params
(page_size ≤ 100). Timestamps are ISO-8601 UTC strings. IDs are UUID strings.

Secrets are **write-only**: no response ever contains a credential value. Credential
fields are reported as `{ "key": "api_key", "set": true, "hint": "…a1b2" }` at most.

## Enumerations

- `category`: `messaging | ai | email | storage | payments | calendar | accounting | commerce | collaboration | automation | identity`
- `auth_type`: `api_key | bearer_token | basic_auth | oauth2 | oauth2_pkce | webhook_secret | signature_secret | service_account | none`
- `availability` (definition): `available | beta | planned` (`planned` = registered but no adapter; cannot be connected)
- `connection status`: `draft | connecting | connected | degraded | expired | revoked | disabled | error`
- `mode`: `sandbox | production`
- `sync_direction`: `none | pull | push | bidirectional`
- `health`: `healthy | degraded | failing | unknown`
- `circuit_state`: `closed | open | half_open`
- inbound event `status`: `received | queued | processing | processed | ignored | failed | dead_letter`
- delivery / job `status`: `pending | running | succeeded | failed | dead_letter | cancelled | paused`

## Directory

`GET /integrations/definitions` → `IntegrationDefinition[]`

```json
{
  "key": "generic_webhook", "name": "Generic webhook", "description": "…",
  "category": "automation", "provider": "Generic", "availability": "available",
  "auth_type": "signature_secret", "capabilities": ["send_webhook"],
  "supported_scopes": [], "required_scopes": [], "webhook_support": false,
  "sync_support": ["none"], "supports_sandbox": false, "documentation_url": null,
  "version": "1",
  "config_schema": [
    {"key": "url", "label": "Endpoint URL", "type": "url", "required": true, "secret": false, "help": "HTTPS only"},
    {"key": "signing_secret", "label": "Signing secret", "type": "password", "required": true, "secret": true, "help": null}
  ],
  "connection_count": 0
}
```

`config_schema[].type`: `text | url | email | password | number | select | boolean`
(`select` adds `options: [{value,label}]`). `secret: true` fields go to encrypted credentials;
the rest to plain configuration.

## Connections

- `GET /integrations/connections?integration_key=&status=` → `Page<Connection>`
- `POST /integrations/connections` body `{integration_key, display_name, mode, config: {…}, credentials: {…}}` → `Connection` (status `draft`, or `connected` if the create-time test passes)
- `GET /integrations/connections/{id}` → `ConnectionDetail`
- `PATCH /integrations/connections/{id}` body `{display_name?, config?}` → `ConnectionDetail`
- `PUT /integrations/connections/{id}/credentials` body `{credentials: {…}}` (rotate) → `ConnectionDetail`
- `POST /integrations/connections/{id}/test` → `TestResult` (`integrations.operate`)
- `POST /integrations/connections/{id}/enable` | `/disable` → `ConnectionDetail`
- `DELETE /integrations/connections/{id}` → 204 (disconnect: revokes credentials, status `revoked`; row kept for audit)
- `POST /integrations/connections/{id}/oauth/start` → `{authorization_url}` (OAuth definitions only)
- `GET /integrations/oauth/callback?state=&code=` → 302 to `/settings/integrations/connections/{id}?oauth=ok|error`

```json
// Connection
{
  "id": "…", "integration_key": "generic_webhook", "display_name": "Zapier hook",
  "status": "connected", "mode": "production", "environment_id": "…",
  "health": "healthy", "circuit_state": "closed",
  "last_success_at": "…", "last_failure_at": null, "last_error": null,
  "last_health_check_at": "…", "connected_at": "…", "expires_at": null,
  "created_at": "…", "updated_at": "…"
}
// ConnectionDetail = Connection + 
{
  "config": {"url": "https://hooks.example.com/abc"},
  "credentials": [{"key": "signing_secret", "set": true, "hint": "…9f2c"}],
  "scopes": [], "sync_direction": "none",
  "health_detail": {"latency_ms": 180, "consecutive_failures": 0, "rate_limited_until": null},
  "recent_activity": [{"at": "…", "kind": "test", "outcome": "success", "message": "Connection verified"}]
}
// TestResult
{"ok": true, "status": "connected", "latency_ms": 180, "message": "Connection verified", "checked_at": "…"}
```

`last_error` and `message` are safe, human-readable strings; never provider stack traces or
raw payloads.

## Outbound webhooks (tenant automation)

- `GET /integrations/event-types` → `[{key, description}]` (e.g. `customer.created`, `order.confirmed`, `invoice.paid`, `handoff.created`)
- `GET /integrations/webhooks` → `Page<WebhookSubscription>`
- `POST /integrations/webhooks` body `{name, url, event_types: string[], enabled}` → `WebhookSubscriptionCreated` (includes `signing_secret` **once**)
- `PATCH /integrations/webhooks/{id}` body `{name?, url?, event_types?, enabled?}` → `WebhookSubscription`
- `POST /integrations/webhooks/{id}/rotate-secret` → `WebhookSubscriptionCreated`
- `DELETE /integrations/webhooks/{id}` → 204
- `GET /integrations/webhooks/{id}/deliveries` → `Page<Delivery>`
- `POST /integrations/deliveries/{id}/retry` → `Delivery` (`integrations.operate`)

```json
// WebhookSubscription
{"id","name","url","event_types":["order.confirmed"],"enabled":true,"secret_hint":"…a1b2",
 "last_delivery_at":null,"last_delivery_status":null,"failure_count":0,"created_at","updated_at"}
// Delivery
{"id","subscription_id","event_type","event_id","status":"succeeded","attempt_count":1,
 "response_status":200,"last_error":null,"next_attempt_at":null,"created_at","delivered_at"}
```

Outbound URLs must pass SSRF validation (https, public DNS, no private/loopback/link-local/
metadata ranges, redirects not followed).

## Inbound events

- `GET /integrations/events?connection_id=&status=&event_type=` → `Page<InboundEvent>`
- `POST /integrations/events/{id}/replay` → `InboundEvent` (`integrations.operate`; idempotent)

```json
{"id","connection_id","integration_key","provider_event_id","event_type","status",
 "signature_verified":true,"attempt_count":1,"received_at","processed_at","error_code":null,
 "correlation_id":"…"}
```

## Sync jobs

- `GET /integrations/jobs?connection_id=&status=` → `Page<SyncJob>`
- `POST /integrations/connections/{id}/sync` body `{entity, mode: "incremental"|"full"}` → `SyncJob` (only when the definition supports sync)
- `POST /integrations/jobs/{id}/pause` | `/resume` | `/cancel` | `/retry` → `SyncJob`

```json
{"id","connection_id","integration_key","entity":"customers","direction":"pull",
 "mode":"incremental","status":"succeeded","cursor":null,
 "stats":{"discovered":0,"created":0,"updated":0,"skipped":0,"failed":0,"conflicts":0},
 "started_at","finished_at","last_error":null,"created_at"}
```

## Failures (dead letter)

`GET /integrations/failures` → `Page<Failure>`: inbound events, deliveries and jobs in
`failed`/`dead_letter`.

```json
{"id","kind":"delivery"|"event"|"job","connection_id":null,"integration_key","summary",
 "error_code","attempt_count","status","occurred_at","can_retry":true}
```

Retry goes through the kind-specific endpoint above.

## Health

`GET /integrations/health` →
```json
{"summary":{"connected":2,"degraded":0,"failing":0,"disabled":1},
 "connections":[{"id","display_name","integration_key","status","health","circuit_state",
   "latency_ms":180,"last_success_at","last_failure_at","rate_limited_until":null,
   "webhook_state":"healthy"|"failing"|"not_applicable","sync_state":"idle"|"running"|"failing"|"not_applicable"}]}
```

Health is computed from recorded calls and the last test; reading it never calls providers
or mutates business data.

## API keys

- `GET /integrations/api-keys` → `ApiKey[]`
- `POST /integrations/api-keys` body `{name, scopes: string[], expires_in_days: number|null}` → `ApiKeyCreated` (includes `secret` **once**, format `pk_live_<prefix>_<secret>` / `pk_test_…` by environment kind)
- `DELETE /integrations/api-keys/{id}` → 204 (revoke)

```json
{"id","name","prefix":"pk_live_a1b2c3","scopes":["customers.read"],"created_at",
 "expires_at":null,"last_used_at":null,"revoked_at":null,"created_by_name":"…"}
```

`scopes` are permission keys and cannot exceed the creator's permissions.

## Implementation notes (backend, v1)

Clarifications and additive changes made while implementing; the web app may rely on them.

- **Additive:** `ConnectionDetail.webhook_url: string | null` — the provider callback URL
  for definitions with `webhook_support` (`{INTEGRATIONS_PUBLIC_BASE_URL}/api/v1/webhooks/{integration_key}/{endpoint_token}`); `null` when not applicable or not configured.
- Create endpoints (`POST /connections`, `/webhooks`, `/api-keys`, `/connections/{id}/sync`)
  answer **201**; other mutations 200 unless noted (204 for deletes).
- `POST /connections` runs the create-time test only when credentials were supplied and the
  definition is not OAuth; `PUT …/credentials` and `POST …/enable` also re-test and return the
  resulting status (`connected` or `error`).
- `mode: "sandbox"` is rejected (`422 SANDBOX_UNSUPPORTED`) for definitions with
  `supports_sandbox: false`. Stripe additionally requires test keys for sandbox and live keys
  for production.
- Secret fields sent inside `config` are rejected (`422 INVALID_CONFIGURATION`) so they can
  never be stored unencrypted. Without a server encryption key, credential writes fail with
  `503 ENCRYPTION_NOT_CONFIGURED`.
- `GET /oauth/callback` requires the session and `integrations.manage`. When the state is
  unknown, reused, expired or belongs to another user/workspace the redirect target is
  `/settings/integrations?oauth=error` (no connection id is revealed).
- Outbound webhook URLs failing SSRF validation → `422 URL_REJECTED`. Unknown event types →
  `422 UNKNOWN_EVENT_TYPE`. `DELETE /webhooks/{id}` soft-deletes and cancels pending
  deliveries (their status becomes `cancelled`).
- `POST /deliveries/{id}/retry` is idempotent: retrying a `pending`/`running` delivery returns
  it unchanged; `succeeded`/`cancelled` → `409 NOT_RETRYABLE`. `POST /events/{id}/replay` on an
  already `queued`/`processing` event returns it unchanged.
- Sync controls: `resume` only from `paused`, `retry` only from `failed`/`dead_letter`
  (`422 INVALID_TRANSITION` otherwise); a second active job for the same connection+entity →
  `409 RESOURCE_CONFLICT`.
- Provider-side errors raised by synchronous calls use the standard envelope with the
  integration error code (e.g. `PROVIDER_UNAVAILABLE` 503, `RATE_LIMITED` 429,
  `CIRCUIT_OPEN` 503). `TestResult` never errors for provider failures: it returns `ok: false`.
- API key `secret` format: `pk_live_<8 hex>_<43 chars>` (production environments) or
  `pk_test_…`; `prefix` is `pk_live_<8 hex>`. `api_keys.manage` can never be a key scope.
- `Failure.integration_key` for deliveries is `generic_webhook` (subscriptions are not bound
  to a connection); `connection_id` is `null` for them.
- Public inbound routes (not under `/integrations`): `POST|GET /api/v1/webhooks/{integration_key}/{endpoint_token}`
  (signature-authenticated; 404 unknown token, 401 bad/missing/stale signature, 400 invalid
  payload, 413 too large, 200 `{received, accepted, duplicates}`).
