import { z } from "zod";
import { apiRequest, API_BASE, DemoError } from "@/services/api-client";

const demo = process.env.NEXT_PUBLIC_DATA_MODE === "demo";
export const ruleSchema = z.object({
  enabled: z.boolean(),
  event_types: z.array(z.string()),
  recipients: z.array(z.string()),
});
export type WorkflowRule = z.infer<typeof ruleSchema>;
const operationSchema = z.object({
  id: z.string(),
  connection_id: z.string(),
  kind: z.string(),
  status: z.string(),
  attempts: z.number(),
  last_error: z.string().nullable(),
  created_at: z.string(),
  entity_type: z.string().nullable(),
  entity_id: z.string().nullable(),
  output: z.record(z.string(), z.unknown()),
});
export type IntegrationOperation = z.infer<typeof operationSchema>;
const rules = new Map<string, WorkflowRule>();

export const workflowService = {
  rule: (id: string): Promise<WorkflowRule> =>
    demo
      ? Promise.resolve(
          rules.get(id) ?? { enabled: false, event_types: [], recipients: [] },
        )
      : apiRequest(
          "GET",
          `/integrations/connections/${id}/workflow`,
          ruleSchema,
        ),
  save: (id: string, data: WorkflowRule): Promise<WorkflowRule> => {
    if (demo) {
      rules.set(id, data);
      return Promise.resolve(data);
    }
    return apiRequest(
      "PUT",
      `/integrations/connections/${id}/workflow`,
      ruleSchema,
      { body: data },
    );
  },
  operations: (id: string): Promise<IntegrationOperation[]> =>
    demo
      ? Promise.resolve([])
      : apiRequest(
          "GET",
          `/integrations/connections/${id}/operations`,
          z.array(operationSchema),
        ),
  retry: (id: string, acknowledge: boolean) =>
    apiRequest(
      "POST",
      `/integrations/operations/${id}/retry`,
      operationSchema,
      { body: { acknowledge_duplicate_risk: acknowledge } },
    ),
  activatePi: (id: string) => {
    if (demo)
      throw new DemoError(
        "Connect a real WhatsApp account in live mode to enable PI messaging.",
      );
    return apiRequest(
      "POST",
      `/integrations/connections/${id}/activate-pi`,
      z.object({ status: z.string(), connection_id: z.string() }),
    );
  },
  capabilities: () =>
    demo
      ? Promise.resolve({ email: false, storage: false, payments: false })
      : apiRequest(
          "GET",
          "/integrations/capabilities",
          z.object({
            email: z.boolean(),
            storage: z.boolean(),
            payments: z.boolean(),
          }),
        ),
  checkout: (id: string) =>
    apiRequest("POST", `/billing/invoices/${id}/checkout`, operationSchema),
  emailInvoice: (id: string, requestId: string) =>
    apiRequest("POST", `/billing/invoices/${id}/email`, operationSchema, {
      body: { request_id: requestId },
    }),
  files: (type: string, id: string): Promise<IntegrationOperation[]> =>
    demo
      ? Promise.resolve([])
      : apiRequest(
          "GET",
          `/files/records/${type}/${id}`,
          z.array(operationSchema),
        ),
  upload: (type: string, id: string, file: File, requestId: string) => {
    const data = new FormData();
    data.set("file", file);
    data.set("request_id", requestId);
    return apiRequest("POST", `/files/records/${type}/${id}`, operationSchema, {
      body: data,
      timeoutMs: 120000,
    });
  },
  remove: (id: string) => apiRequest<void>("DELETE", `/files/${id}`, null),
  downloadUrl: (id: string) => `${API_BASE}/files/${id}/download`,
};
