import { z } from "zod";
import { apiBlob, apiRequest } from "@/services/api-client";

/**
 * The solution documents and quotes pi drafts, and the bank transfers waiting for the team.
 * A reviewer approves every document before the customer sees it; only staff confirm a
 * payment. Backend: apps/api/app/modules/pi/brain_doc_routes.py (/api/v1/pi/brain-documents).
 */

export const brainDocumentSchema = z.object({
  id: z.string(),
  ref: z.string(),
  kind: z.enum(["solution", "quote"]).catch("solution"),
  version: z.number().catch(1),
  status: z.string(),
  offer_id: z.string().nullable().catch(null),
  customer_id: z.string(),
  conversation_id: z.string(),
  language: z.string().catch("en"),
  content: z.record(z.string(), z.unknown()).catch({}),
  total: z.string().nullable().catch(null),
  currency: z.string().nullable().catch(null),
  valid_until: z.string().nullable().catch(null),
  drafted_by: z.string().nullable().catch(null),
  approved_by: z.string().nullable().catch(null),
  approved_at: z.string().nullable().catch(null),
  sent_at: z.string().nullable().catch(null),
  review_notes: z.string().nullable().catch(null),
  blockers: z.array(z.string()).catch([]),
  created_at: z.string(),
});
export type BrainDocument = z.infer<typeof brainDocumentSchema>;

export const brainPaymentSchema = z.object({
  id: z.string(),
  status: z.string(),
  quote_id: z.string(),
  quote_ref: z.string().nullable().catch(null),
  total: z.string().nullable().catch(null),
  currency: z.string().nullable().catch(null),
  customer_id: z.string(),
  conversation_id: z.string(),
  claimed_at: z.string().nullable().catch(null),
  confirmed_at: z.string().nullable().catch(null),
  reference: z.string().nullable().catch(null),
  created_at: z.string(),
});
export type BrainPayment = z.infer<typeof brainPaymentSchema>;

/** What a reviewer can change (the API ignores anything left out). */
export type DocumentPatch = {
  covers?: string[];
  needs?: string[];
  included?: string[];
  not_included?: string[];
  payment?: string;
  cost?: { total?: string; currency?: string; tax_text?: string };
  time?: { estimate?: string };
  valid_until?: string;
  review_notes?: string;
};

const base = "/pi/brain-documents";

export const brainDocumentsService = {
  list: () =>
    apiRequest("GET", base, z.object({ items: z.array(brainDocumentSchema) })),
  payments: () =>
    apiRequest(
      "GET",
      `${base}/payments`,
      z.object({ items: z.array(brainPaymentSchema) }),
    ),
  edit: (id: string, patch: DocumentPatch) =>
    apiRequest("PATCH", `${base}/${id}`, brainDocumentSchema, { body: patch }),
  approve: (id: string) =>
    apiRequest("POST", `${base}/${id}/approve`, brainDocumentSchema),
  revise: (id: string, patch: DocumentPatch) =>
    apiRequest("POST", `${base}/${id}/revise`, brainDocumentSchema, {
      body: patch,
    }),
  send: (offerId: string) =>
    apiRequest(
      "POST",
      `${base}/offers/${offerId}/send`,
      z.object({ queued: z.number().catch(0) }),
    ),
  confirmPayment: (id: string, reference: string, note: string) =>
    apiRequest(
      "POST",
      `${base}/payments/${id}/confirm`,
      brainPaymentSchema.extend({ notified: z.boolean().catch(false) }),
      { body: { reference, note } },
    ),
  pdf: (id: string) => apiBlob(`${base}/${id}/pdf`),
};
