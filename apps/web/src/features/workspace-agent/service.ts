import { z } from "zod";
import { apiRequest, apiStream } from "@/services/api-client";

const record = z.record(z.string(), z.unknown());
export const contextSchema = z.object({
  name: z.string(),
  user_id: z.string(),
  membership_id: z.string(),
  roles: z.array(z.string()),
  tenant_id: z.string(),
  environment_id: z.string(),
  permissions: z.array(z.string()),
  read_areas: z.array(z.string()),
  actions: z.array(z.string()),
  specialists: z.array(z.string()),
  ai_enabled: z.boolean(),
});
export const proposalSchema = z.object({
  id: z.string(),
  operation: z.string(),
  preview: record,
  status: z.enum(["pending", "applied", "cancelled"]),
  expires_at: z.string(),
  result: z.object({ count: z.number(), ids: z.array(z.string()) }).nullable(),
});
export const resultSchema = z.object({
  area: z.string(),
  specialist: z.string(),
  route: z.string(),
  items: z.array(record),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  sample_only: z.boolean().optional(),
  search: z.string().optional(),
  count_unit: z.string().optional(),
  exact: z.boolean().optional(),
  untrusted_content: z.boolean().optional(),
  scope: z.string().optional(),
  customer: z.string().optional(),
  title: z.string().optional(),
  stored_summary: z.string().optional(),
});
export const signalSchema = z.object({
  key: z.string(),
  area: z.string(),
  severity: z.enum(["critical", "warning", "info"]),
  count: z.number(),
  title: z.string(),
  suggestion: z.string(),
  route: z.string(),
  amounts: z
    .array(z.object({ currency: z.string(), outstanding: z.string() }))
    .optional(),
});
const monitorSchema = z.object({
  generated_at: z.string(),
  checked_areas: z.array(z.string()),
  signals: z.array(signalSchema),
  healthy: z.boolean(),
});
export const kpiSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: z.number(),
  unit: z.enum(["currency", "count", "percent", "days"]),
  currency: z.string().nullable(),
  previous: z.number().nullable(),
  change_pct: z.number().nullable(),
  good: z.enum(["up", "down"]),
  detail: z.string(),
  compare: z.string().nullish(),
});
const cell = z.union([z.string(), z.number(), z.null()]);
export const chartSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string(),
  kind: z.enum(["bar", "line", "area"]),
  x_key: z.string(),
  x_label: z.string(),
  series: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      dashed: z.boolean().optional(),
    }),
  ),
  data: z.array(z.record(z.string(), cell)),
  unit: z.enum(["currency", "count", "percent", "days"]),
  currency: z.string().nullable(),
  stacked: z.boolean(),
});
const tableSchema = z.object({
  title: z.string(),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), cell)),
  note: z.string().optional(),
});
export const analyticsSchema = z.object({
  area: z.literal("analytics"),
  topic: z.string(),
  currency: z.string(),
  months: z.number(),
  kpis: z.array(kpiSchema),
  charts: z.array(chartSchema),
  tables: z.array(tableSchema),
  notes: z.array(z.string()),
  checked_areas: z.array(z.string()),
  generated_at: z.string(),
});
const level = z.enum(["high", "medium", "low"]);
const recommendationSchema = z.object({
  action: z.string(),
  why: z.string(),
  impact: level,
  effort: level,
  page: z.string().nullable(),
});
export const teamSchema = z.object({
  area: z.literal("team"),
  question: z.string(),
  mode: z.enum(["ai", "rules"]),
  brief: z.object({
    answer: z.string(),
    recommendation: z.string(),
    options: z.array(
      z.object({
        name: z.string(),
        pros: z.array(z.string()),
        cons: z.array(z.string()),
        expected_impact: z.string(),
      }),
    ),
    risks: z.array(z.string()),
    next_steps: z.array(recommendationSchema),
    confidence: level,
    assumptions: z.array(z.string()),
  }),
  specialists: z.array(
    z.object({
      role: z.string(),
      title: z.string(),
      headline: z.string(),
      findings: z.array(z.string()),
      risks: z.array(z.string()),
      opportunities: z.array(z.string()),
      recommendations: z.array(recommendationSchema),
      confidence: level,
      data_gaps: z.array(z.string()),
    }),
  ),
  consulted: z.array(z.string()),
  kpis: z.array(kpiSchema),
  checked_areas: z.array(z.string()),
});
const replySchema = z.object({
  message: z.string(),
  results: z.array(resultSchema),
  proposals: z.array(proposalSchema),
  signals: z.array(signalSchema).default([]),
  analytics: z.array(analyticsSchema).default([]),
  team: teamSchema.nullable().default(null),
  navigate: z.string().nullable().optional(),
  mode: z.string(),
  notice: z.string().optional(),
  follow_ups: z.array(z.string()).default([]),
});
export type StreamEvent =
  | { type: "thinking" }
  | { type: "note"; text: string }
  | { type: "step"; tool: string; label: string }
  | { type: "step_done"; tool: string; ok: boolean }
  | { type: "reply"; reply: z.infer<typeof replySchema> }
  | { type: "error"; message: string };
export type ChatTurn = { role: "user" | "assistant"; content: string };
export type AgentContext = z.infer<typeof contextSchema>;
export type Proposal = z.infer<typeof proposalSchema>;
export type ToolResult = z.infer<typeof resultSchema>;
export type Signal = z.infer<typeof signalSchema>;
export type MonitorReport = z.infer<typeof monitorSchema>;
export type Reply = z.infer<typeof replySchema>;
export type Kpi = z.infer<typeof kpiSchema>;
export type ChartSpec = z.infer<typeof chartSchema>;
export type AnalyticsBlock = z.infer<typeof analyticsSchema>;
export type TeamBrief = z.infer<typeof teamSchema>;
const base = "/workspace-agent";
export const agentService = {
  context: () => apiRequest("GET", `${base}/context`, contextSchema),
  monitor: () => apiRequest("GET", `${base}/monitor`, monitorSchema),
  analytics: (topic = "report", months = 12) =>
    apiRequest("GET", `${base}/analytics`, analyticsSchema, {
      query: { topic, months },
    }),
  team: (question: string, signal?: AbortSignal) =>
    apiRequest("POST", `${base}/team`, teamSchema, {
      body: { question },
      signal,
      timeoutMs: 120000,
    }),
  pending: () =>
    apiRequest("GET", `${base}/proposals`, z.array(proposalSchema)),
  /** The agent, streamed: each real step as it happens, then the validated reply. */
  chatStream: (
    message: string,
    history: ChatTurn[],
    current_page: string,
    onEvent: (event: StreamEvent) => void,
    signal: AbortSignal,
  ) =>
    apiStream<StreamEvent>(
      `${base}/chat/stream`,
      { message, history, current_page },
      (event) =>
        onEvent(
          event.type === "reply"
            ? { type: "reply", reply: replySchema.parse(event.reply) }
            : event,
        ),
      signal,
    ),
  chat: (
    message: string,
    history: string[],
    current_page: string,
    signal: AbortSignal,
  ) =>
    apiRequest("POST", `${base}/chat`, replySchema, {
      body: { message, history, current_page },
      signal,
      timeoutMs: 120000,
    }),
  read: (area: string, page = 1, search = "") =>
    apiRequest("POST", `${base}/read`, resultSchema, {
      body: { area, page, search },
    }),
  propose: (operation: string, args: Record<string, unknown>) =>
    apiRequest("POST", `${base}/proposals`, proposalSchema, {
      body: { operation, arguments: args },
    }),
  decide: (id: string, decision: "confirm" | "cancel") =>
    apiRequest("POST", `${base}/proposals/${id}/decision`, proposalSchema, {
      body: { decision },
    }),
  document: (
    file: File,
    purpose: "summary" | "employees",
    signal: AbortSignal,
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("purpose", purpose);
    return apiRequest("POST", `${base}/documents`, replySchema, {
      body,
      signal,
      timeoutMs: 120000,
    });
  },
};
