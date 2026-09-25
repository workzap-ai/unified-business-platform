import { humanize } from "@/lib/format";
import type {
  AuthType,
  Category,
  ConnectionStatus,
  IntegrationDefinition,
  JobAction,
  WorkStatus,
} from "./types";

/** Business rules shared by the UI and the demo adapter (the API enforces them too). */

export const CATEGORY_LABELS: Record<Category, string> = {
  messaging: "Messaging",
  ai: "AI",
  email: "Email",
  storage: "Storage",
  payments: "Payments",
  calendar: "Calendar",
  accounting: "Accounting",
  commerce: "Commerce",
  collaboration: "Collaboration",
  automation: "Automation",
  identity: "Identity",
};

export const AUTH_LABELS: Record<AuthType, string> = {
  api_key: "API key",
  bearer_token: "Bearer token",
  basic_auth: "Username and password",
  oauth2: "OAuth 2.0",
  oauth2_pkce: "OAuth 2.0 (PKCE)",
  webhook_secret: "Webhook secret",
  signature_secret: "Signing secret",
  service_account: "Service account",
  none: "No authentication",
};

export const isOAuth = (authType: AuthType) =>
  authType === "oauth2" || authType === "oauth2_pkce";

/** Sync-job state machine: which actions are valid from each status. */
export const JOB_ACTIONS: Record<WorkStatus, JobAction[]> = {
  pending: ["pause", "cancel"],
  running: ["pause", "cancel"],
  paused: ["resume", "cancel"],
  failed: ["retry"],
  dead_letter: ["retry"],
  succeeded: [],
  cancelled: [],
};

export function canJob(status: WorkStatus, action: JobAction) {
  return JOB_ACTIONS[status].includes(action);
}

/** Statuses from which a connection can be tested, enabled or disabled. */
export const TESTABLE: ConnectionStatus[] = [
  "draft",
  "connecting",
  "connected",
  "degraded",
  "expired",
  "error",
];
export const DISABLEABLE: ConnectionStatus[] = [
  "draft",
  "connecting",
  "connected",
  "degraded",
  "expired",
  "error",
];

export const RETRYABLE_EVENT = ["failed", "dead_letter", "ignored"];
export const RETRYABLE_DELIVERY = ["failed", "dead_letter"];

/** Scopes that grant write, admin or destructive access are flagged, never hidden. */
export function isElevatedScope(scope: string) {
  return /(write|manage|admin|delete|full|send|messaging|payments?|refund)/i.test(
    scope,
  );
}

/** Sync entities come from `sync_<entity>` capabilities on the definition. */
export function syncEntities(definition: IntegrationDefinition | undefined) {
  if (!definition) return [];
  if (!definition.sync_support.some((d) => d !== "none")) return [];
  return definition.capabilities
    .filter((c) => c.startsWith("sync_"))
    .map((c) => c.slice(5));
}

export function supportsSync(definition: IntegrationDefinition | undefined) {
  return syncEntities(definition).length > 0;
}

export function capabilityLabel(capability: string) {
  return humanize(capability);
}

const PRIVATE_HOST =
  /^(localhost|.*\.localhost|.*\.local|.*\.internal|metadata\.google\.internal|0\.0\.0\.0|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|169\.254\.\d+\.\d+|\[?::1\]?|\[?f[cd][0-9a-f]{2}:.*)$/i;

/**
 * Client-side pre-check for outbound URLs (the server does the authoritative SSRF check
 * with DNS resolution). Returns an error message or null.
 */
export function outboundUrlProblem(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    return "Enter a full URL, e.g. https://hooks.example.com/orders";
  }
  if (url.protocol !== "https:") return "Only HTTPS endpoints are allowed";
  if (url.username || url.password)
    return "Don't put credentials in the URL; use the signing secret";
  if (PRIVATE_HOST.test(url.hostname))
    return "Private, loopback and internal addresses are not allowed";
  return null;
}

export function maskHint(hint: string | null | undefined) {
  return hint ? `set • ${hint}` : "set";
}

export function formatLatency(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function permissionReason(permission: string) {
  return `Requires the ${permission} permission`;
}
