import { humanize } from "@/lib/format";
import type { AgentKey, HandoffReason, HandoffStatus, ProviderHealth, ProviderName } from "../types";

/** Query keys for PI workspace data. Invalidate the `["pi"]` prefix after PI mutations. */
export const piKeys = {
  all: ["pi"] as const,
  overview: ["pi", "overview"] as const,
  conversations: (filters: Record<string, unknown>) => ["pi", "conversations", filters] as const,
  messages: (id: string) => ["pi", "messages", id] as const,
  context: (id: string) => ["pi", "context", id] as const,
  handoffs: (status?: string) => ["pi", "handoffs", status ?? "all"] as const,
  agents: ["pi", "agents"] as const,
  tools: ["pi", "tools"] as const,
};

export const HANDOFF_REASON_LABELS: Record<HandoffReason, string> = {
  customer_request: "Customer asked for a person",
  low_confidence: "Low confidence",
  provider_failure: "AI provider unavailable",
  policy: "Needs team approval",
  tool_failure: "Tool failure",
  complaint: "Complaint",
  sensitive: "Sensitive topic",
  manual: "Created by operator",
};

export const HANDOFF_REASONS = Object.keys(HANDOFF_REASON_LABELS) as HandoffReason[];

export const AGENT_LABELS: Record<AgentKey, string> = {
  router: "Router",
  customer_memory: "Customer memory",
  support: "Support",
  requirement: "Requirements",
  sales_order: "Sales & orders",
  handoff: "Handoff",
};

export function agentLabel(key: AgentKey | null | undefined, names?: Map<string, string>) {
  if (!key) return "PI";
  return names?.get(key) ?? AGENT_LABELS[key] ?? humanize(key);
}

export const PROVIDER_LABELS: Record<ProviderName, string> = {
  openai: "OpenAI",
  gemini: "Google Gemini",
  groq: "Groq",
};

export const PROVIDER_ROLE_LABELS: Record<ProviderHealth["role"], string> = {
  primary: "Primary",
  fallback: "Fallback",
  secondary_fallback: "Secondary fallback",
};

export function toolLabel(key: string, names?: Map<string, string>) {
  return names?.get(key) ?? humanize(key);
}

/** URL slug ↔ handoff status. */
export const HANDOFF_SLUGS: Record<string, HandoffStatus> = {
  open: "open",
  assigned: "assigned",
  "in-progress": "in_progress",
  resolved: "resolved",
  closed: "closed",
};

export function slugForStatus(status: HandoffStatus) {
  return status === "in_progress" ? "in-progress" : status;
}

export function formatMs(ms: number | null | undefined) {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

export const inboxHref = (conversationId: string) => `/pi/inbox?conversation=${encodeURIComponent(conversationId)}`;
