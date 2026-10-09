import { z } from "zod";
import {
  apiRequest,
  ApiError,
  decimal,
  errorMessage,
  ServiceNotConnectedError,
} from "@/services/api-client";
import { select } from "@/lib/data-mode";

/**
 * Deal flow: a proposal from pi's brief, sending proposals and invoices on WhatsApp,
 * what the customer did with them, and the workspace's deal automation.
 * Backend: apps/api/app/modules/pi_saas/deal_routes.py (/api/v1/pi/deals).
 */

export const DEAL_PAYMENT_METHODS = [
  "auto",
  "stripe",
  "bank_transfer",
  "mobile_wallet",
  "cash",
] as const;
export type DealPaymentMethod = (typeof DEAL_PAYMENT_METHODS)[number];

export const DEAL_PAYMENT_METHOD_LABELS: Record<DealPaymentMethod, string> = {
  auto: "Best available",
  stripe: "Card (Stripe)",
  bank_transfer: "Bank transfer",
  mobile_wallet: "Mobile wallet",
  cash: "Cash",
};

const settingsFields = {
  auto_proposal: z.boolean().catch(true),
  auto_followups: z.boolean().catch(true),
  auto_receipt: z.boolean().catch(true),
  receipt_whatsapp: z.boolean().catch(true),
  receipt_email: z.boolean().catch(true),
  receipt_customer_details: z.boolean().catch(true),
  receipt_project_details: z.boolean().catch(true),
  receipt_line_items: z.boolean().catch(true),
  receipt_footer: z.string().catch(""),
  auto_order: z.boolean(),
  auto_invoice: z.boolean(),
  auto_payment_request: z.boolean(),
  thank_you_on_paid: z.boolean(),
  payment_method: z.enum(DEAL_PAYMENT_METHODS).catch("auto"),
  template_name: z.string().catch(""),
  template_language: z.string().catch(""),
};
const settingsInputSchema = z.object(settingsFields);
export const dealSettingsSchema = z.object({
  ...settingsFields,
  payment_methods: z.array(z.string()).catch([]),
});
export type DealSettings = z.infer<typeof dealSettingsSchema>;
export type DealSettingsInput = z.infer<typeof settingsInputSchema>;

export const proposalCreatedSchema = z.object({
  quote_id: z.string(),
  number: z.string(),
});
export type ProposalCreated = z.infer<typeof proposalCreatedSchema>;

export const DELIVERY_STATES = ["sent", "waiting", "manual"] as const;
export type DeliveryState = (typeof DELIVERY_STATES)[number];

export const deliveryResultSchema = z.object({
  document_id: z.string(),
  delivery: z.enum(DELIVERY_STATES),
  link: z.string(),
  share: z.string().nullable(),
  message: z.string(),
});
export type DeliveryResult = z.infer<typeof deliveryResultSchema>;

export type StartDealInput = {
  phone: string;
  name?: string;
  title?: string;
  notes?: string;
};
export const dealStartedSchema = z.object({
  customer_id: z.string(),
  lead_id: z.string(),
});
export type DealStarted = z.infer<typeof dealStartedSchema>;

export const DOCUMENT_RESPONSES = ["accepted", "changes", "rejected"] as const;
export type DocumentResponse = (typeof DOCUMENT_RESPONSES)[number];

export const dealDocumentSchema = z.object({
  id: z.string(),
  kind: z.string(),
  delivery: z.string(),
  viewed_at: z.string().nullable(),
  response: z.enum(DOCUMENT_RESPONSES).nullable().catch(null),
  response_note: z.string().nullable().catch(null),
  responded_at: z.string().nullable(),
  created_at: z.string(),
});
export type DealDocument = z.infer<typeof dealDocumentSchema>;

export const dealBoardItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  stage: z.string(),
  source: z.string(),
  updated_at: z.string(),
  conversation_id: z.string().nullable(),
  customer: z
    .object({
      id: z.string(),
      name: z.string(),
      phone: z.string().nullable(),
    })
    .nullable(),
  proposal: z
    .object({
      id: z.string(),
      number: z.string(),
      status: z.string(),
      total: decimal,
      currency: z.string(),
      delivery: z.string().nullable(),
      viewed: z.boolean(),
      response: z.enum(DOCUMENT_RESPONSES).nullable().catch(null),
    })
    .nullable(),
  invoice: z
    .object({
      id: z.string(),
      number: z.string(),
      status: z.string(),
      total: decimal,
      amount_paid: decimal,
      currency: z.string(),
    })
    .nullable(),
  next: z.string(),
});
export type DealBoardItem = z.infer<typeof dealBoardItemSchema>;
export const dealBoardSchema = z.object({
  items: z.array(dealBoardItemSchema),
  counts: z.record(z.string(), z.number()),
});
export type DealBoard = z.infer<typeof dealBoardSchema>;

export const JOURNEY_ACTIONS = [
  "",
  "edit",
  "proposal_from_brief",
  "send_proposal",
  "send_invoice",
] as const;
export type JourneyAction = (typeof JOURNEY_ACTIONS)[number];

export const journeyStepSchema = z.object({
  key: z.string(),
  label: z.string(),
  at: z.string().nullable(),
  done: z.boolean(),
  detail: z.string().catch(""),
});
export type JourneyStep = z.infer<typeof journeyStepSchema>;

export const dealJourneySchema = z.object({
  lead_id: z.string(),
  stage: z.string(),
  steps: z.array(journeyStepSchema),
  next: z.object({
    title: z.string(),
    detail: z.string(),
    action: z.enum(JOURNEY_ACTIONS).catch(""),
    href: z.string().catch(""),
    auto: z.boolean().catch(false),
  }),
  quote_id: z.string().nullable(),
  invoice_id: z.string().nullable(),
  order_id: z.string().nullable(),
  reminder: z
    .object({ kind: z.string(), at: z.string() })
    .nullable()
    .optional()
    .catch(null),
});
export type DealJourney = z.infer<typeof dealJourneySchema>;

export const paymentLinkSentSchema = z.object({
  whatsapp: deliveryResultSchema.nullable(),
  pay_link: z.string().nullable().catch(null),
  email: z.string().nullable().catch(null),
  email_error: z.string().nullable().catch(null),
});
export type PaymentLinkSent = z.infer<typeof paymentLinkSentSchema>;

export interface DealService {
  settings(): Promise<DealSettings>;
  saveSettings(input: DealSettingsInput): Promise<DealSettingsInput>;
  proposalFromLead(leadId: string): Promise<ProposalCreated>;
  sendQuote(quoteId: string): Promise<DeliveryResult>;
  sendInvoice(invoiceId: string): Promise<DeliveryResult>;
  start(input: StartDealInput): Promise<DealStarted>;
  documents(
    filter: { quote_id: string } | { invoice_id: string },
  ): Promise<DealDocument[]>;
  board(): Promise<DealBoard>;
  journey(leadId: string): Promise<DealJourney>;
  sendPaymentLink(
    invoiceId: string,
    channels?: { whatsapp?: boolean; email?: boolean },
  ): Promise<PaymentLinkSent>;
}

const live: DealService = {
  settings: () => apiRequest("GET", "/pi/deals/settings", dealSettingsSchema),
  saveSettings: (input) =>
    apiRequest("PUT", "/pi/deals/settings", settingsInputSchema, {
      body: input,
    }),
  proposalFromLead: (leadId) =>
    apiRequest(
      "POST",
      `/pi/deals/leads/${leadId}/proposal`,
      proposalCreatedSchema,
    ),
  sendQuote: (quoteId) =>
    apiRequest(
      "POST",
      `/pi/deals/quotes/${quoteId}/send`,
      deliveryResultSchema,
    ),
  sendInvoice: (invoiceId) =>
    apiRequest(
      "POST",
      `/pi/deals/invoices/${invoiceId}/send`,
      deliveryResultSchema,
    ),
  start: (input) =>
    apiRequest("POST", "/pi/deals/start", dealStartedSchema, { body: input }),
  documents: (filter) =>
    apiRequest("GET", "/pi/deals/documents", z.array(dealDocumentSchema), {
      query: filter,
    }),
  board: () => apiRequest("GET", "/pi/deals/board", dealBoardSchema),
  journey: (leadId) =>
    apiRequest("GET", `/pi/deals/leads/${leadId}/journey`, dealJourneySchema),
  sendPaymentLink: (invoiceId, channels = {}) =>
    apiRequest(
      "POST",
      `/billing/invoices/${invoiceId}/payment-link/send`,
      paymentLinkSentSchema,
      { body: channels },
    ),
};

function notConnected(): never {
  throw new ServiceNotConnectedError("Deal flow");
}

// Sample data has no WhatsApp channel: the deal flow is live-only.
const demo: DealService = {
  settings: async () => notConnected(),
  saveSettings: async () => notConnected(),
  proposalFromLead: async () => notConnected(),
  sendQuote: async () => notConnected(),
  sendInvoice: async () => notConnected(),
  start: async () => notConnected(),
  documents: async () => [],
  board: async () => notConnected(),
  journey: async () => notConnected(),
  sendPaymentLink: async () => notConnected(),
};

export const dealService = select<DealService>({ demo, live });

const DEAL_ERRORS: Record<string, string> = {
  QUOTE_NOT_PRICED: "Add prices first",
  QUOTE_NEEDS_APPROVAL: "A manager needs to approve this proposal first",
  LEAD_HAS_NO_CUSTOMER: "Link this lead to a customer first",
  PHONE_INVALID: "Enter the WhatsApp number with country code",
  TEMPLATE_INCOMPLETE: "Give both the template name and its language",
};

/** Plain words for a deal-flow error; falls back to the shared safe message. */
export function dealErrorMessage(error: unknown, fallback?: string) {
  if (error instanceof ApiError && DEAL_ERRORS[error.code])
    return DEAL_ERRORS[error.code];
  return errorMessage(error, fallback);
}
