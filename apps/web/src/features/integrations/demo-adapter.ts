/**
 * Demo adapter for the Integrations contract. Mirrors the server's business rules
 * (validation, state machines, write-only secrets) against fictional sample data and
 * never contacts a provider: test results are derived from the seeded state.
 */
import { ApiError } from "@/services/api-client";
import { demoDelay } from "@/lib/data-mode";
import { demoId, paginate } from "@/demo/store";
import { DEMO_USER, demoSession } from "@/demo/workspace";
import type { IntegrationsService } from "./service";
import {
  DEMO_DEFINITIONS,
  DEMO_EVENT_TYPES,
  demoIntegrations,
  type DemoConnection,
} from "./demo-data";
import {
  canJob,
  DISABLEABLE,
  isOAuth,
  outboundUrlProblem,
  RETRYABLE_DELIVERY,
  RETRYABLE_EVENT,
  TESTABLE,
} from "./lib";
import {
  apiKeyCreatedSchema,
  apiKeySchema,
  connectionDetailSchema,
  connectionSchema,
  definitionSchema,
  deliverySchema,
  failureSchema,
  healthSchema,
  inboundEventSchema,
  syncJobSchema,
  testResultSchema,
  webhookSubscriptionCreatedSchema,
  webhookSubscriptionSchema,
  type ConnectionStatus,
  type Failure,
  type IntegrationDefinition,
  type TestResult,
  type WebhookSubscription,
} from "./types";

const now = () => new Date().toISOString();
const state = () => demoIntegrations();

function notFound(): never {
  throw new ApiError(404, "RESOURCE_NOT_FOUND");
}
function conflict(message: string): never {
  throw new ApiError(409, "CONFLICT", undefined, message);
}
function invalid(message: string, fields: Record<string, string> = {}): never {
  throw new ApiError(422, "VALIDATION_ERROR", undefined, message, fields);
}

function definitionOf(key: string) {
  return DEMO_DEFINITIONS.find((d) => d.key === key);
}

function findConnection(id: string) {
  return state().connections.find((c) => c.id === id) ?? notFound();
}

function hash(text: string) {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

function randomToken(length: number) {
  const alphabet =
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
}

function log(
  connection: DemoConnection,
  kind: string,
  outcome: string,
  message: string,
) {
  connection.recent_activity.unshift({ at: now(), kind, outcome, message });
  connection.recent_activity = connection.recent_activity.slice(0, 25);
  connection.updated_at = now();
}

function detail(connection: DemoConnection) {
  return connectionDetailSchema.parse(connection);
}

function validateConfig(
  definition: Omit<IntegrationDefinition, "connection_count">,
  config: Record<string, unknown>,
  credentials: Record<string, string> | null,
) {
  const fields: Record<string, string> = {};
  for (const field of definition.config_schema) {
    if (field.secret) {
      if (credentials === null) continue;
      const value = credentials[field.key];
      if (field.required && !value?.trim())
        fields[`credentials.${field.key}`] = `${field.label} is required`;
      else if (value && value.length < 8)
        fields[`credentials.${field.key}`] =
          `${field.label} must be at least 8 characters`;
      continue;
    }
    const value = config[field.key];
    const empty =
      value === undefined || value === null || String(value).trim() === "";
    if (field.required && empty && field.type !== "boolean") {
      fields[`config.${field.key}`] = `${field.label} is required`;
      continue;
    }
    if (empty) continue;
    if (field.type === "url") {
      const problem = outboundUrlProblem(String(value));
      if (problem) fields[`config.${field.key}`] = problem;
    }
    if (
      field.type === "email" &&
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value))
    )
      fields[`config.${field.key}`] = "Enter a valid email address";
    if (field.type === "number" && !Number.isFinite(Number(value)))
      fields[`config.${field.key}`] = "Enter a number";
    if (
      field.type === "select" &&
      !field.options?.some((o) => o.value === String(value))
    )
      fields[`config.${field.key}`] = "Choose one of the listed options";
  }
  if (Object.keys(fields).length)
    invalid("Some fields need attention.", fields);
}

function behaviorFor(config: Record<string, unknown>) {
  const url = String(config.url ?? config.endpoint ?? "");
  return /fail|invalid|unreachable|denied/i.test(url) ? "auth_failed" : "ok";
}

/** Honest simulated test: derived from the connection's seeded behavior and state. */
function runTest(connection: DemoConnection): TestResult {
  const checkedAt = now();
  const definition = definitionOf(connection.integration_key);
  connection.last_health_check_at = checkedAt;
  const missing = connection.credentials.filter((c) => !c.set);
  if (missing.length) {
    connection.status = "error";
    connection.health = "failing";
    connection.last_failure_at = checkedAt;
    connection.last_error =
      "Credentials are missing. Rotate credentials to add them.";
    log(connection, "test", "failure", connection.last_error);
    return {
      ok: false,
      status: connection.status,
      latency_ms: null,
      message: connection.last_error,
      checked_at: checkedAt,
    };
  }
  if (definition && isOAuth(definition.auth_type) && !connection.connected_at) {
    connection.last_error = "Authorization hasn't been completed yet.";
    log(connection, "test", "failure", connection.last_error);
    return {
      ok: false,
      status: connection.status,
      latency_ms: null,
      message: connection.last_error,
      checked_at: checkedAt,
    };
  }
  if (connection.behavior === "rate_limited") {
    const until = new Date(Date.now() + 20 * 60_000);
    const failures = connection.health_detail.consecutive_failures + 1;
    connection.health_detail = {
      latency_ms: 960 + (hash(checkedAt) % 200),
      consecutive_failures: failures,
      rate_limited_until: until.toISOString(),
    };
    connection.circuit_state = failures >= 5 ? "open" : "half_open";
    connection.health = failures >= 5 ? "failing" : "degraded";
    connection.status = "degraded";
    connection.last_failure_at = checkedAt;
    const hhmm = until.toISOString().slice(11, 16);
    connection.last_error = `Provider is rate limiting this connection (HTTP 429). Try again after ${hhmm} UTC.`;
    log(connection, "test", "failure", connection.last_error);
    return {
      ok: false,
      status: connection.status,
      latency_ms: connection.health_detail.latency_ms,
      message: connection.last_error,
      checked_at: checkedAt,
    };
  }
  if (connection.behavior === "auth_failed") {
    connection.status = "error";
    connection.health = "failing";
    connection.last_failure_at = checkedAt;
    connection.health_detail = {
      ...connection.health_detail,
      latency_ms: 240,
      consecutive_failures: connection.health_detail.consecutive_failures + 1,
    };
    connection.last_error =
      "The endpoint rejected the test request (HTTP 401). Check the URL and secret.";
    log(connection, "test", "failure", connection.last_error);
    return {
      ok: false,
      status: connection.status,
      latency_ms: 240,
      message: connection.last_error,
      checked_at: checkedAt,
    };
  }
  const latency = 120 + (hash(connection.id + checkedAt) % 140);
  connection.status = "connected";
  connection.health = "healthy";
  connection.circuit_state = "closed";
  connection.last_success_at = checkedAt;
  connection.last_error = null;
  connection.connected_at ??= checkedAt;
  connection.health_detail = {
    latency_ms: latency,
    consecutive_failures: 0,
    rate_limited_until: null,
  };
  log(connection, "test", "success", "Connection verified");
  return {
    ok: true,
    status: "connected",
    latency_ms: latency,
    message: "Connection verified",
    checked_at: checkedAt,
  };
}

function sessionInfo() {
  const session = demoSession();
  return {
    permissions: new Set(session?.permissions ?? []),
    kind: session?.environment?.kind ?? "production",
  };
}

function subscriptionOf(id: string) {
  return state().webhooks.find((w) => w.id === id) ?? notFound();
}

function validateWebhook(input: {
  name?: string;
  url?: string;
  event_types?: string[];
}) {
  const fields: Record<string, string> = {};
  if (input.name !== undefined && !input.name.trim())
    fields.name = "Name is required";
  if (input.name && input.name.length > 80)
    fields.name = "Keep the name under 80 characters";
  if (input.url !== undefined) {
    const problem = outboundUrlProblem(input.url);
    if (problem) fields.url = problem;
  }
  if (input.event_types !== undefined) {
    if (!input.event_types.length)
      fields.event_types = "Choose at least one event type";
    else if (
      input.event_types.some((t) => !DEMO_EVENT_TYPES.some((e) => e.key === t))
    )
      fields.event_types = "Unknown event type";
  }
  if (Object.keys(fields).length)
    invalid("Some fields need attention.", fields);
}

function withSecret(subscription: WebhookSubscription) {
  const secret = `whsec_${randomToken(32)}`;
  subscription.secret_hint = `…${secret.slice(-4)}`;
  subscription.updated_at = now();
  return webhookSubscriptionCreatedSchema.parse({
    ...subscription,
    signing_secret: secret,
  });
}

function failures(): Failure[] {
  const s = state();
  const rows: Failure[] = [];
  for (const d of s.deliveries) {
    if (!RETRYABLE_DELIVERY.includes(d.status)) continue;
    const sub = s.webhooks.find((w) => w.id === d.subscription_id);
    rows.push({
      id: d.id,
      kind: "delivery",
      connection_id: null,
      integration_key: null,
      summary: `${d.event_type} to ${sub?.name ?? "deleted subscription"}: ${d.last_error ?? "delivery failed"}`,
      error_code: d.response_status ? `HTTP_${d.response_status}` : "TIMEOUT",
      attempt_count: d.attempt_count,
      status: d.status,
      occurred_at: d.created_at,
      can_retry: Boolean(sub?.enabled),
    });
  }
  for (const e of s.events) {
    if (!["failed", "dead_letter"].includes(e.status)) continue;
    rows.push({
      id: e.id,
      kind: "event",
      connection_id: e.connection_id,
      integration_key: e.integration_key,
      summary: `Inbound ${e.event_type} could not be processed`,
      error_code: e.error_code,
      attempt_count: e.attempt_count,
      status: e.status,
      occurred_at: e.received_at,
      can_retry: e.signature_verified,
    });
  }
  for (const j of s.jobs) {
    if (!["failed", "dead_letter"].includes(j.status)) continue;
    rows.push({
      id: j.id,
      kind: "job",
      connection_id: j.connection_id,
      integration_key: j.integration_key,
      summary: `${j.entity} ${j.mode} sync: ${j.last_error ?? "failed"}`,
      error_code: "SYNC_FAILED",
      attempt_count: 1,
      status: j.status,
      occurred_at: j.finished_at ?? j.created_at,
      can_retry: true,
    });
  }
  return rows
    .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
    .map((f) => failureSchema.parse(f));
}

export const demoIntegrationsService: IntegrationsService = {
  async definitions() {
    await demoDelay();
    const connections = state().connections;
    return DEMO_DEFINITIONS.map((d) =>
      definitionSchema.parse({
        ...d,
        connection_count: connections.filter(
          (c) => c.integration_key === d.key && c.status !== "revoked",
        ).length,
      }),
    );
  },

  async connections({ integration_key, status, page = 1, pageSize = 25 }) {
    await demoDelay();
    const rows = state()
      .connections.filter(
        (c) =>
          (!integration_key || c.integration_key === integration_key) &&
          (!status || c.status === status),
      )
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map((c) => connectionSchema.parse(c));
    return paginate(rows, page, pageSize);
  },

  async connection(id) {
    await demoDelay();
    return detail(findConnection(id));
  },

  async createConnection(input) {
    await demoDelay(450);
    const definition = definitionOf(input.integration_key);
    if (!definition)
      invalid("Unknown integration.", {
        integration_key: "Unknown integration",
      });
    if (definition.availability === "planned")
      conflict(`${definition.name} is planned and can't be connected yet.`);
    const name = input.display_name.trim();
    if (!name)
      invalid("Some fields need attention.", {
        display_name: "Name is required",
      });
    if (name.length > 80)
      invalid("Some fields need attention.", {
        display_name: "Keep the name under 80 characters",
      });
    if (input.mode === "sandbox" && !definition.supports_sandbox)
      invalid("Some fields need attention.", {
        mode: `${definition.name} has no sandbox mode`,
      });
    if (
      state().connections.some(
        (c) =>
          c.integration_key === definition.key &&
          c.status !== "revoked" &&
          c.display_name.toLowerCase() === name.toLowerCase(),
      )
    )
      throw new ApiError(
        409,
        "CONFLICT",
        undefined,
        "A connection with this name already exists.",
        { display_name: "A connection with this name already exists" },
      );
    validateConfig(definition, input.config, input.credentials);
    const created = now();
    const secretFields = definition.config_schema.filter((f) => f.secret);
    const config: Record<string, unknown> = {};
    for (const f of definition.config_schema)
      if (
        !f.secret &&
        input.config[f.key] !== undefined &&
        input.config[f.key] !== ""
      )
        config[f.key] =
          f.type === "number"
            ? Number(input.config[f.key])
            : input.config[f.key];
    const connection: DemoConnection = {
      id: demoId("con"),
      integration_key: definition.key,
      display_name: name,
      status: "draft",
      mode: input.mode,
      environment_id: demoSession()?.environment?.id ?? "",
      health: "unknown",
      circuit_state: "closed",
      last_success_at: null,
      last_failure_at: null,
      last_error: null,
      last_health_check_at: null,
      connected_at: null,
      expires_at: null,
      created_at: created,
      updated_at: created,
      // Only whether a secret is set and its last 4 characters are kept.
      credentials: secretFields.map((f) => {
        const value = input.credentials[f.key] ?? "";
        return {
          key: f.key,
          set: value.length > 0,
          hint: value ? `…${value.slice(-4)}` : null,
        };
      }),
      config,
      scopes: [],
      sync_direction:
        definition.sync_support.find((d) => d !== "none") ?? "none",
      health_detail: {
        latency_ms: null,
        consecutive_failures: 0,
        rate_limited_until: null,
      },
      recent_activity: [],
      behavior: behaviorFor(config),
    };
    log(
      connection,
      "created",
      "success",
      `Connection created by ${DEMO_USER.display_name}`,
    );
    state().connections.unshift(connection);
    if (!isOAuth(definition.auth_type)) runTest(connection);
    else {
      connection.last_error =
        "Authorize access with the provider to finish connecting.";
    }
    return connectionSchema.parse(connection);
  },

  async updateConnection(id, patch) {
    await demoDelay(300);
    const connection = findConnection(id);
    if (connection.status === "revoked")
      conflict("Disconnected connections can't be edited.");
    const definition = definitionOf(connection.integration_key)!;
    if (patch.display_name !== undefined) {
      const name = patch.display_name.trim();
      if (!name)
        invalid("Some fields need attention.", {
          display_name: "Name is required",
        });
      connection.display_name = name;
    }
    if (patch.config) {
      const merged = { ...connection.config, ...patch.config };
      validateConfig(definition, merged, null);
      for (const f of definition.config_schema)
        if (!f.secret && merged[f.key] !== undefined)
          connection.config[f.key] =
            f.type === "number" ? Number(merged[f.key]) : merged[f.key];
      connection.behavior =
        connection.behavior === "rate_limited"
          ? "rate_limited"
          : behaviorFor(connection.config);
    }
    log(connection, "config_updated", "success", "Configuration updated");
    return detail(connection);
  },

  async rotateCredentials(id, credentials) {
    await demoDelay(350);
    const connection = findConnection(id);
    const definition = definitionOf(connection.integration_key)!;
    const secretFields = definition.config_schema.filter((f) => f.secret);
    if (!secretFields.length)
      conflict("This integration authorizes with OAuth; reconnect instead.");
    const fields: Record<string, string> = {};
    for (const f of secretFields) {
      const value = credentials[f.key];
      if (!value?.trim())
        fields[`credentials.${f.key}`] = `${f.label} is required`;
      else if (value.length < 8)
        fields[`credentials.${f.key}`] =
          `${f.label} must be at least 8 characters`;
    }
    if (Object.keys(fields).length)
      invalid("Some fields need attention.", fields);
    connection.credentials = secretFields.map((f) => ({
      key: f.key,
      set: true,
      hint: `…${credentials[f.key]!.slice(-4)}`,
    }));
    if (["revoked", "expired", "error"].includes(connection.status)) {
      connection.status = "draft";
      connection.health = "unknown";
    }
    log(connection, "credentials_rotated", "success", "Credentials rotated");
    return detail(connection);
  },

  async testConnection(id) {
    await demoDelay(700);
    const connection = findConnection(id);
    if (connection.status === "revoked")
      conflict(
        "This connection was disconnected. Reconnect it before testing.",
      );
    if (connection.status === "disabled")
      conflict("This connection is disabled. Enable it before testing.");
    if (!TESTABLE.includes(connection.status))
      conflict("This connection can't be tested right now.");
    return testResultSchema.parse(runTest(connection));
  },

  async enableConnection(id) {
    await demoDelay(400);
    const connection = findConnection(id);
    if (connection.status !== "disabled")
      conflict("Only disabled connections can be enabled.");
    connection.status = "draft";
    log(connection, "enabled", "info", `Enabled by ${DEMO_USER.display_name}`);
    runTest(connection);
    return detail(connection);
  },

  async disableConnection(id) {
    await demoDelay(300);
    const connection = findConnection(id);
    if (!DISABLEABLE.includes(connection.status))
      conflict("This connection can't be disabled in its current state.");
    connection.status = "disabled";
    connection.health = "unknown";
    log(
      connection,
      "disabled",
      "info",
      `Disabled by ${DEMO_USER.display_name}`,
    );
    return detail(connection);
  },

  async disconnect(id) {
    await demoDelay(400);
    const connection = findConnection(id);
    if (connection.status === "revoked") conflict("Already disconnected.");
    connection.status = "revoked";
    connection.health = "unknown";
    connection.circuit_state = "closed";
    connection.credentials = connection.credentials.map((c) => ({
      key: c.key,
      set: false,
      hint: null,
    }));
    connection.scopes = [];
    connection.health_detail = {
      latency_ms: null,
      consecutive_failures: 0,
      rate_limited_until: null,
    };
    log(
      connection,
      "disconnected",
      "info",
      "Disconnected; credentials revoked",
    );
  },

  async startOAuth(id) {
    await demoDelay(300);
    const connection = findConnection(id);
    const definition = definitionOf(connection.integration_key)!;
    if (!isOAuth(definition.auth_type))
      conflict("This integration doesn't use OAuth.");
    if (connection.status === "disabled")
      conflict("Enable the connection before reconnecting.");
    // Sample-data mode has no provider: complete a simulated authorization and send the
    // browser to the same callback destination the API's OAuth callback redirects to.
    const at = now();
    connection.status = "connected";
    connection.health = "healthy";
    connection.circuit_state = "closed";
    connection.connected_at = at;
    connection.last_success_at = at;
    connection.last_error = null;
    connection.scopes = [...definition.required_scopes];
    log(
      connection,
      "oauth",
      "success",
      "Sample authorization completed (no provider contacted)",
    );
    return {
      authorization_url: `${window.location.origin}/settings/integrations/connections/${id}?oauth=ok`,
    };
  },

  async eventTypes() {
    await demoDelay(120);
    return DEMO_EVENT_TYPES;
  },

  async webhooks({ page = 1, pageSize = 25 }) {
    await demoDelay();
    const rows = [...state().webhooks]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((w) => webhookSubscriptionSchema.parse(w));
    return paginate(rows, page, pageSize);
  },

  async createWebhook(input) {
    await demoDelay(400);
    validateWebhook(input);
    const created = now();
    const subscription: WebhookSubscription = {
      id: demoId("whk"),
      name: input.name.trim(),
      url: input.url.trim(),
      event_types: [...new Set(input.event_types)],
      enabled: input.enabled,
      secret_hint: null,
      last_delivery_at: null,
      last_delivery_status: null,
      failure_count: 0,
      created_at: created,
      updated_at: created,
    };
    state().webhooks.unshift(subscription);
    return withSecret(subscription);
  },

  async updateWebhook(id, patch) {
    await demoDelay(300);
    const subscription = subscriptionOf(id);
    validateWebhook(patch);
    Object.assign(subscription, {
      ...(patch.name !== undefined && { name: patch.name.trim() }),
      ...(patch.url !== undefined && { url: patch.url.trim() }),
      ...(patch.event_types !== undefined && {
        event_types: [...new Set(patch.event_types)],
      }),
      ...(patch.enabled !== undefined && { enabled: patch.enabled }),
      updated_at: now(),
    });
    return webhookSubscriptionSchema.parse(subscription);
  },

  async rotateWebhookSecret(id) {
    await demoDelay(350);
    return withSecret(subscriptionOf(id));
  },

  async deleteWebhook(id) {
    await demoDelay(300);
    subscriptionOf(id);
    const s = state();
    s.webhooks = s.webhooks.filter((w) => w.id !== id);
    s.deliveries = s.deliveries.filter((d) => d.subscription_id !== id);
  },

  async deliveries(subscriptionId, { page = 1, pageSize = 25 }) {
    await demoDelay();
    subscriptionOf(subscriptionId);
    const rows = state()
      .deliveries.filter((d) => d.subscription_id === subscriptionId)
      .map((d) => deliverySchema.parse(d));
    return paginate(rows, page, pageSize);
  },

  async retryDelivery(id) {
    await demoDelay(500);
    const delivery = state().deliveries.find((d) => d.id === id) ?? notFound();
    if (!RETRYABLE_DELIVERY.includes(delivery.status))
      conflict("Only failed deliveries can be retried.");
    const subscription = subscriptionOf(delivery.subscription_id);
    if (!subscription.enabled)
      conflict("Enable the subscription before retrying its deliveries.");
    const at = now();
    delivery.attempt_count += 1;
    delivery.next_attempt_at = null;
    if (/fail|invalid|unreachable|denied/i.test(subscription.url)) {
      delivery.status = "failed";
      delivery.response_status = 401;
      delivery.last_error = "Endpoint returned HTTP 401 Unauthorized";
    } else {
      delivery.status = "succeeded";
      delivery.response_status = 200;
      delivery.last_error = null;
      delivery.delivered_at = at;
    }
    subscription.last_delivery_at = at;
    subscription.last_delivery_status = delivery.status;
    subscription.failure_count = state().deliveries.filter(
      (d) =>
        d.subscription_id === subscription.id &&
        RETRYABLE_DELIVERY.includes(d.status),
    ).length;
    return deliverySchema.parse(delivery);
  },

  async events({ connection_id, status, event_type, page = 1, pageSize = 25 }) {
    await demoDelay();
    const rows = state()
      .events.filter(
        (e) =>
          (!connection_id || e.connection_id === connection_id) &&
          (!status || e.status === status) &&
          (!event_type || e.event_type === event_type),
      )
      .map((e) => inboundEventSchema.parse(e));
    return paginate(rows, page, pageSize);
  },

  async replayEvent(id) {
    await demoDelay(500);
    const event = state().events.find((e) => e.id === id) ?? notFound();
    if (!event.signature_verified)
      conflict("Events with an unverified signature can't be replayed.");
    if (event.status === "processed") return inboundEventSchema.parse(event);
    if (!RETRYABLE_EVENT.includes(event.status))
      conflict("This event is still being processed.");
    event.attempt_count += 1;
    event.status = "processed";
    event.processed_at = now();
    event.error_code = null;
    return inboundEventSchema.parse(event);
  },

  async jobs({ connection_id, status, page = 1, pageSize = 25 }) {
    await demoDelay();
    const rows = state()
      .jobs.filter(
        (j) =>
          (!connection_id || j.connection_id === connection_id) &&
          (!status || j.status === status),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((j) => syncJobSchema.parse(j));
    return paginate(rows, page, pageSize);
  },

  async startSync(connectionId, input) {
    await demoDelay(400);
    const connection = findConnection(connectionId);
    const definition = definitionOf(connection.integration_key)!;
    if (!definition.sync_support.some((d) => d !== "none"))
      conflict(`${definition.name} doesn't support sync.`);
    if (!["connected", "degraded"].includes(connection.status))
      conflict("Only connected integrations can sync.");
    if (!definition.capabilities.includes(`sync_${input.entity}`))
      invalid("Some fields need attention.", {
        entity: "This entity can't be synced",
      });
    const job = syncJobSchema.parse({
      id: demoId("job"),
      connection_id: connectionId,
      integration_key: connection.integration_key,
      entity: input.entity,
      direction: connection.sync_direction,
      mode: input.mode,
      status: "pending",
      cursor: null,
      stats: {
        discovered: 0,
        created: 0,
        updated: 0,
        skipped: 0,
        failed: 0,
        conflicts: 0,
      },
      started_at: null,
      finished_at: null,
      last_error: null,
      created_at: now(),
    });
    state().jobs.unshift(job);
    log(
      connection,
      "sync",
      "info",
      `${input.entity} ${input.mode} sync queued`,
    );
    return job;
  },

  async jobAction(id, action) {
    await demoDelay(350);
    const job = state().jobs.find((j) => j.id === id) ?? notFound();
    if (!canJob(job.status, action))
      conflict(
        `A ${job.status.replace("_", " ")} job can't be ${action === "retry" ? "retried" : `${action}d`}.`,
      );
    const at = now();
    if (action === "pause") job.status = "paused";
    if (action === "resume")
      job.status = job.started_at ? "running" : "pending";
    if (action === "cancel") {
      job.status = "cancelled";
      job.finished_at = at;
    }
    if (action === "retry") {
      job.status = "pending";
      job.last_error = null;
      job.started_at = null;
      job.finished_at = null;
    }
    return syncJobSchema.parse(job);
  },

  async failures({ page = 1, pageSize = 25 }) {
    await demoDelay();
    return paginate(failures(), page, pageSize);
  },

  async health() {
    await demoDelay();
    const s = state();
    const active = s.connections.filter((c) => c.status !== "revoked");
    const rows = active.map((c) => {
      const definition = definitionOf(c.integration_key);
      const events = s.events.filter((e) => e.connection_id === c.id);
      const jobs = s.jobs.filter((j) => j.connection_id === c.id);
      return {
        id: c.id,
        display_name: c.display_name,
        integration_key: c.integration_key,
        status: c.status,
        health: c.health,
        circuit_state: c.circuit_state,
        latency_ms: c.health_detail.latency_ms,
        last_success_at: c.last_success_at,
        last_failure_at: c.last_failure_at,
        rate_limited_until: c.health_detail.rate_limited_until,
        webhook_state: !definition?.webhook_support
          ? "not_applicable"
          : events.some((e) => ["failed", "dead_letter"].includes(e.status))
            ? "failing"
            : "healthy",
        sync_state: !definition?.sync_support.some((d) => d !== "none")
          ? "not_applicable"
          : jobs.some((j) => j.status === "running")
            ? "running"
            : jobs.some((j) => ["failed", "dead_letter"].includes(j.status))
              ? "failing"
              : "idle",
      };
    });
    const count = (fn: (status: ConnectionStatus, health: string) => boolean) =>
      active.filter((c) => fn(c.status, c.health)).length;
    return healthSchema.parse({
      summary: {
        connected: count((st) => st === "connected"),
        degraded: count((_, h) => h === "degraded"),
        failing: count((_, h) => h === "failing"),
        disabled: count((st) => st === "disabled"),
      },
      connections: rows,
    });
  },

  async apiKeys() {
    await demoDelay();
    return [...state().apiKeys]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((k) => apiKeySchema.parse(k));
  },

  async createApiKey(input) {
    await demoDelay(400);
    const { permissions, kind } = sessionInfo();
    const fields: Record<string, string> = {};
    if (!input.name.trim()) fields.name = "Name is required";
    else if (input.name.length > 80)
      fields.name = "Keep the name under 80 characters";
    if (!input.scopes.length) fields.scopes = "Choose at least one scope";
    else if (input.scopes.some((s) => !permissions.has(s)))
      fields.scopes = "A key can't have permissions your role doesn't have";
    if (
      input.expires_in_days !== null &&
      (!Number.isInteger(input.expires_in_days) ||
        input.expires_in_days < 1 ||
        input.expires_in_days > 365)
    )
      fields.expires_in_days = "Choose between 1 and 365 days";
    if (Object.keys(fields).length)
      invalid("Some fields need attention.", fields);
    const env = kind === "production" ? "live" : "test";
    const prefix = `pk_${env}_${randomToken(6).toLowerCase()}`;
    const secret = `${prefix}_${randomToken(32)}`;
    const created = now();
    const key = apiKeySchema.parse({
      id: demoId("key"),
      name: input.name.trim(),
      prefix,
      scopes: [...new Set(input.scopes)].sort(),
      created_at: created,
      expires_at:
        input.expires_in_days === null
          ? null
          : new Date(
              Date.now() + input.expires_in_days * 86_400_000,
            ).toISOString(),
      last_used_at: null,
      revoked_at: null,
      created_by_name: DEMO_USER.display_name,
    });
    state().apiKeys.unshift(key);
    return apiKeyCreatedSchema.parse({ ...key, secret });
  },

  async revokeApiKey(id) {
    await demoDelay(300);
    const key = state().apiKeys.find((k) => k.id === id) ?? notFound();
    if (key.revoked_at) conflict("This key is already revoked.");
    key.revoked_at = now();
  },
};
