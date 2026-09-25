import { z } from "zod";

/**
 * Integrations API contract (docs/contracts/integrations-api.md, v1). Both the live and
 * demo adapters return data that passes these schemas. Secrets are write-only: no schema
 * here has a field that could carry a credential value, except the two one-time
 * "created" payloads (webhook signing secret, API key secret) the contract defines.
 */

export const CATEGORIES = [
  "messaging",
  "ai",
  "email",
  "storage",
  "payments",
  "calendar",
  "accounting",
  "commerce",
  "collaboration",
  "automation",
  "identity",
] as const;
export const AUTH_TYPES = [
  "api_key",
  "bearer_token",
  "basic_auth",
  "oauth2",
  "oauth2_pkce",
  "webhook_secret",
  "signature_secret",
  "service_account",
  "none",
] as const;
export const AVAILABILITY = ["available", "beta", "planned"] as const;
export const CONNECTION_STATUSES = [
  "draft",
  "connecting",
  "connected",
  "degraded",
  "expired",
  "revoked",
  "disabled",
  "error",
] as const;
export const MODES = ["sandbox", "production"] as const;
export const SYNC_DIRECTIONS = [
  "none",
  "pull",
  "push",
  "bidirectional",
] as const;
export const HEALTH = ["healthy", "degraded", "failing", "unknown"] as const;
export const CIRCUIT_STATES = ["closed", "open", "half_open"] as const;
export const EVENT_STATUSES = [
  "received",
  "queued",
  "processing",
  "processed",
  "ignored",
  "failed",
  "dead_letter",
] as const;
export const WORK_STATUSES = [
  "pending",
  "running",
  "succeeded",
  "failed",
  "dead_letter",
  "cancelled",
  "paused",
] as const;
export const FIELD_TYPES = [
  "text",
  "url",
  "email",
  "password",
  "number",
  "select",
  "boolean",
] as const;

const id = z.string().min(1);
const ts = z.string();
const tsNullable = z.string().nullable();

export const configFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.enum(FIELD_TYPES),
  required: z.boolean(),
  secret: z.boolean(),
  help: z.string().nullable().optional(),
  // The API sends null for non-select fields.
  options: z
    .array(z.object({ value: z.string(), label: z.string() }))
    .nullish(),
});

export const definitionSchema = z.object({
  key: z.string(),
  name: z.string(),
  description: z.string(),
  category: z.enum(CATEGORIES),
  provider: z.string(),
  availability: z.enum(AVAILABILITY),
  auth_type: z.enum(AUTH_TYPES),
  capabilities: z.array(z.string()),
  supported_scopes: z.array(z.string()),
  required_scopes: z.array(z.string()),
  webhook_support: z.boolean(),
  sync_support: z.array(z.enum(SYNC_DIRECTIONS)),
  supports_sandbox: z.boolean(),
  documentation_url: z.string().nullable(),
  version: z.string(),
  config_schema: z.array(configFieldSchema),
  connection_count: z.number().int().nonnegative(),
});

export const connectionSchema = z.object({
  id,
  integration_key: z.string(),
  display_name: z.string(),
  status: z.enum(CONNECTION_STATUSES),
  mode: z.enum(MODES),
  environment_id: z.string(),
  health: z.enum(HEALTH),
  circuit_state: z.enum(CIRCUIT_STATES),
  last_success_at: tsNullable,
  last_failure_at: tsNullable,
  last_error: z.string().nullable(),
  last_health_check_at: tsNullable,
  connected_at: tsNullable,
  expires_at: tsNullable,
  created_at: ts,
  updated_at: ts,
});

export const credentialStateSchema = z.object({
  key: z.string(),
  set: z.boolean(),
  hint: z.string().nullable().optional(),
});

export const activitySchema = z.object({
  at: ts,
  kind: z.string(),
  outcome: z.string(),
  message: z.string(),
});

export const connectionDetailSchema = connectionSchema.extend({
  config: z.record(z.string(), z.unknown()),
  credentials: z.array(credentialStateSchema),
  scopes: z.array(z.string()),
  sync_direction: z.enum(SYNC_DIRECTIONS),
  health_detail: z.object({
    latency_ms: z.number().nullable(),
    consecutive_failures: z.number().int().nonnegative(),
    rate_limited_until: tsNullable,
  }),
  recent_activity: z.array(activitySchema),
});

export const testResultSchema = z.object({
  ok: z.boolean(),
  status: z.enum(CONNECTION_STATUSES),
  latency_ms: z.number().nullable(),
  message: z.string(),
  checked_at: ts,
});

export const eventTypeSchema = z.object({
  key: z.string(),
  description: z.string(),
});

export const webhookSubscriptionSchema = z.object({
  id,
  name: z.string(),
  url: z.string(),
  event_types: z.array(z.string()),
  enabled: z.boolean(),
  secret_hint: z.string().nullable(),
  last_delivery_at: tsNullable,
  last_delivery_status: z.enum(WORK_STATUSES).nullable(),
  failure_count: z.number().int().nonnegative(),
  created_at: ts,
  updated_at: ts,
});

export const webhookSubscriptionCreatedSchema =
  webhookSubscriptionSchema.extend({ signing_secret: z.string() });

export const deliverySchema = z.object({
  id,
  subscription_id: z.string(),
  event_type: z.string(),
  event_id: z.string(),
  status: z.enum(WORK_STATUSES),
  attempt_count: z.number().int().nonnegative(),
  response_status: z.number().int().nullable(),
  last_error: z.string().nullable(),
  next_attempt_at: tsNullable,
  created_at: ts,
  delivered_at: tsNullable,
});

export const inboundEventSchema = z.object({
  id,
  connection_id: z.string(),
  integration_key: z.string(),
  provider_event_id: z.string().nullable(),
  event_type: z.string(),
  status: z.enum(EVENT_STATUSES),
  signature_verified: z.boolean(),
  attempt_count: z.number().int().nonnegative(),
  received_at: ts,
  processed_at: tsNullable,
  error_code: z.string().nullable(),
  correlation_id: z.string().nullable(),
});

export const syncStatsSchema = z.object({
  discovered: z.number().int().nonnegative(),
  created: z.number().int().nonnegative(),
  updated: z.number().int().nonnegative(),
  skipped: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  conflicts: z.number().int().nonnegative(),
});

export const syncJobSchema = z.object({
  id,
  connection_id: z.string(),
  integration_key: z.string(),
  entity: z.string(),
  direction: z.enum(SYNC_DIRECTIONS),
  mode: z.enum(["incremental", "full"]),
  status: z.enum(WORK_STATUSES),
  cursor: z.string().nullable(),
  stats: syncStatsSchema,
  started_at: tsNullable,
  finished_at: tsNullable,
  last_error: z.string().nullable(),
  created_at: ts,
});

export const failureSchema = z.object({
  id,
  kind: z.enum(["delivery", "event", "job"]),
  connection_id: z.string().nullable(),
  integration_key: z.string().nullable(),
  summary: z.string(),
  error_code: z.string().nullable(),
  attempt_count: z.number().int().nonnegative(),
  status: z.string(),
  occurred_at: ts,
  can_retry: z.boolean(),
});

export const healthRowSchema = z.object({
  id,
  display_name: z.string(),
  integration_key: z.string(),
  status: z.enum(CONNECTION_STATUSES),
  health: z.enum(HEALTH),
  circuit_state: z.enum(CIRCUIT_STATES),
  latency_ms: z.number().nullable(),
  last_success_at: tsNullable,
  last_failure_at: tsNullable,
  rate_limited_until: tsNullable,
  webhook_state: z.enum(["healthy", "failing", "not_applicable"]),
  sync_state: z.enum(["idle", "running", "failing", "not_applicable"]),
});

export const healthSchema = z.object({
  summary: z.object({
    connected: z.number().int().nonnegative(),
    degraded: z.number().int().nonnegative(),
    failing: z.number().int().nonnegative(),
    disabled: z.number().int().nonnegative(),
  }),
  connections: z.array(healthRowSchema),
});

export const apiKeySchema = z.object({
  id,
  name: z.string(),
  prefix: z.string(),
  scopes: z.array(z.string()),
  created_at: ts,
  expires_at: tsNullable,
  last_used_at: tsNullable,
  revoked_at: tsNullable,
  created_by_name: z.string().nullable(),
});

export const apiKeyCreatedSchema = apiKeySchema.extend({ secret: z.string() });

export type Category = (typeof CATEGORIES)[number];
export type AuthType = (typeof AUTH_TYPES)[number];
export type Availability = (typeof AVAILABILITY)[number];
export type ConnectionStatus = (typeof CONNECTION_STATUSES)[number];
export type Mode = (typeof MODES)[number];
export type SyncDirection = (typeof SYNC_DIRECTIONS)[number];
export type Health = (typeof HEALTH)[number];
export type CircuitState = (typeof CIRCUIT_STATES)[number];
export type EventStatus = (typeof EVENT_STATUSES)[number];
export type WorkStatus = (typeof WORK_STATUSES)[number];
export type ConfigField = z.infer<typeof configFieldSchema>;
export type IntegrationDefinition = z.infer<typeof definitionSchema>;
export type Connection = z.infer<typeof connectionSchema>;
export type ConnectionDetail = z.infer<typeof connectionDetailSchema>;
export type CredentialState = z.infer<typeof credentialStateSchema>;
export type ConnectionActivity = z.infer<typeof activitySchema>;
export type TestResult = z.infer<typeof testResultSchema>;
export type EventType = z.infer<typeof eventTypeSchema>;
export type WebhookSubscription = z.infer<typeof webhookSubscriptionSchema>;
export type WebhookSubscriptionCreated = z.infer<
  typeof webhookSubscriptionCreatedSchema
>;
export type Delivery = z.infer<typeof deliverySchema>;
export type InboundEvent = z.infer<typeof inboundEventSchema>;
export type SyncJob = z.infer<typeof syncJobSchema>;
export type SyncStats = z.infer<typeof syncStatsSchema>;
export type Failure = z.infer<typeof failureSchema>;
export type HealthRow = z.infer<typeof healthRowSchema>;
export type IntegrationHealth = z.infer<typeof healthSchema>;
export type ApiKey = z.infer<typeof apiKeySchema>;
export type ApiKeyCreated = z.infer<typeof apiKeyCreatedSchema>;

export type ConnectionInput = {
  integration_key: string;
  display_name: string;
  mode: Mode;
  config: Record<string, unknown>;
  credentials: Record<string, string>;
};
export type ConnectionPatch = {
  display_name?: string;
  config?: Record<string, unknown>;
};
export type WebhookInput = {
  name: string;
  url: string;
  event_types: string[];
  enabled: boolean;
};
export type ApiKeyInput = {
  name: string;
  scopes: string[];
  expires_in_days: number | null;
};
export type JobAction = "pause" | "resume" | "cancel" | "retry";
export type ListQuery = { page?: number; pageSize?: number };
