import { z } from "zod";
import { apiRequest } from "@/services/api-client";

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
const replySchema = z.object({
  message: z.string(),
  results: z.array(resultSchema),
  proposals: z.array(proposalSchema),
  signals: z.array(signalSchema).default([]),
  navigate: z.string().nullable().optional(),
  mode: z.string(),
  notice: z.string().optional(),
});
export type AgentContext = z.infer<typeof contextSchema>;
export type Proposal = z.infer<typeof proposalSchema>;
export type ToolResult = z.infer<typeof resultSchema>;
export type Signal = z.infer<typeof signalSchema>;
export type MonitorReport = z.infer<typeof monitorSchema>;
export type Reply = z.infer<typeof replySchema>;
const base = "/workspace-agent";
export const agentService = {
  context: () => apiRequest("GET", `${base}/context`, contextSchema),
  monitor: () => apiRequest("GET", `${base}/monitor`, monitorSchema),
  pending: () =>
    apiRequest("GET", `${base}/proposals`, z.array(proposalSchema)),
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
