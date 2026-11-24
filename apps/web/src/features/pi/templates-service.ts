import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * WhatsApp templates: the messages WhatsApp lets pi start outside a live chat. List, create (with
 * {{1}} variables), edit, and send a first message to one number. Backend:
 * apps/api/app/modules/pi_saas/whatsapp_tools.py (/api/v1/pi/whatsapp/templates). Reading needs
 * pi.read; creating, editing and sending need pi.settings.manage.
 */

export const templateSchema = z.object({
  id: z.string().catch(""),
  name: z.string(),
  language: z.string(),
  status: z.string().catch(""),
  category: z.string().catch(""),
  body: z.string().catch(""),
  variables: z.number().catch(0),
  fillable: z.boolean().catch(false),
});
export type Template = z.infer<typeof templateSchema>;

const listSchema = z.object({
  templates: z.array(templateSchema),
  number: z.string().nullable().catch(null),
  connected: z.boolean().catch(false),
});

const doneSchema = z.object({}).passthrough();

export type NewTemplate = {
  name: string;
  language: string;
  category: "UTILITY" | "MARKETING";
  body: string;
  examples: string[];
};

export const sendRowSchema = z.object({
  id: z.string(),
  batch_id: z.string(),
  phone: z.string(),
  person: z.string().catch(""),
  template: z.string(),
  language: z.string().catch(""),
  values: z.array(z.string()).catch([]),
  source: z.string().catch(""),
  status: z.string(),
  error: z.string().nullable().catch(null),
  created_at: z.string(),
  sent_at: z.string().nullable().catch(null),
  conversation_id: z.string().nullable().catch(null),
});
export type SendRow = z.infer<typeof sendRowSchema>;

const historySchema = z.object({ items: z.array(sendRowSchema) });

const batchSchema = z.object({
  batch_id: z.string(),
  queued: z.number(),
  rejected: z.array(z.object({ phone: z.string(), reason: z.string() })),
  daily_cap: z.number().catch(200),
});
export type BatchResult = z.infer<typeof batchSchema>;

const audienceSchema = z.object({
  items: z.array(
    z.object({
      phone: z.string(),
      person: z.string().catch(""),
      label: z.string().catch(""),
    }),
  ),
});
export type AudienceRow = z.infer<typeof audienceSchema>["items"][number];

export type BatchInput = {
  name: string;
  language: string;
  rows: { phone: string; person: string; values: string[] }[];
  source: "paste" | "customers" | "nori";
  consent: boolean;
  consent_note: string;
};

export const piTemplatesService = {
  history: (params: { template?: string; phone?: string; status?: string }) =>
    apiRequest("GET", "/pi/whatsapp/templates/sends", historySchema, {
      query: { ...params, limit: 200 },
    }),
  audience: (source: "customers" | "nori", q: string) =>
    apiRequest("GET", "/pi/whatsapp/templates/audience", audienceSchema, {
      query: { source, q },
    }),
  queue: (input: BatchInput) =>
    apiRequest("POST", "/pi/whatsapp/templates/batches", batchSchema, {
      body: input,
    }),
  cancelBatch: (id: string) =>
    apiRequest(
      "POST",
      `/pi/whatsapp/templates/batches/${id}/cancel`,
      z.object({ cancelled: z.number() }),
    ),
  list: () => apiRequest("GET", "/pi/whatsapp/templates", listSchema),
  create: (input: NewTemplate) =>
    apiRequest("POST", "/pi/whatsapp/templates", doneSchema, { body: input }),
  edit: (id: string, input: { body: string; examples: string[] }) =>
    apiRequest("PUT", `/pi/whatsapp/templates/${id}`, doneSchema, {
      body: input,
    }),
  send: (input: {
    phone: string;
    name: string;
    language: string;
    values: string[];
    consent: boolean;
  }) =>
    apiRequest("POST", "/pi/whatsapp/templates/send", doneSchema, {
      body: input,
    }),
};
