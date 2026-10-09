import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * The request desk: what pi asked the team, and the team's answers. When the team
 * answers, the chat goes back to pi, which replies to the customer itself.
 * Backend: apps/api/app/modules/pi_saas/requests.py (/api/v1/pi/requests).
 */

export const REQUEST_KINDS = [
  "question",
  "price",
  "review_document",
  "approve",
  "meeting",
  "other",
] as const;
export type RequestKind = (typeof REQUEST_KINDS)[number];

export const REQUEST_KIND_LABELS: Record<RequestKind, string> = {
  question: "Question",
  price: "Price a proposal",
  review_document: "Review a document",
  approve: "Approve a proposal",
  meeting: "Arrange a meeting",
  other: "Other",
};

export const piRequestSchema = z.object({
  id: z.string(),
  kind: z.enum(REQUEST_KINDS).catch("other"),
  priority: z.enum(["normal", "high"]).catch("normal"),
  status: z.string(),
  question: z.string(),
  context: z.string().catch(""),
  answer: z.string().nullable(),
  conversation_id: z.string(),
  customer_id: z.string(),
  customer_name: z.string().nullable().catch(null),
  lead_id: z.string().nullable(),
  quote_id: z.string().nullable(),
  file_id: z.string().nullable(),
  created_at: z.string(),
  resolved_at: z.string().nullable(),
});
export type PiRequest = z.infer<typeof piRequestSchema>;

const listSchema = z.object({
  items: z.array(piRequestSchema),
  open: z.number().catch(0),
});

export const piRequestsService = {
  list: (status: "open" | "done" | "all") =>
    apiRequest("GET", "/pi/requests", listSchema, { query: { status } }),
  answer: (id: string, answer: string, saveAsKnowledge: boolean) =>
    apiRequest("POST", `/pi/requests/${id}/answer`, piRequestSchema, {
      body: { answer, save_as_knowledge: saveAsKnowledge },
    }),
  dismiss: (id: string) =>
    apiRequest("POST", `/pi/requests/${id}/dismiss`, piRequestSchema),
};
