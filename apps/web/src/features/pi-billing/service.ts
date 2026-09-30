import { apiRequest } from "@/services/api-client";

export interface CollectionSettings {
  seller_name: string;
  seller_address: string;
  support_email: string;
  bank_enabled: boolean;
  bank_name: string;
  account_title: string;
  iban: string;
  bank_instructions: string;
  cash_enabled: boolean;
  cash_instructions: string;
}
export interface PlatformSettings {
  collection: CollectionSettings;
  can_edit: boolean;
  runtime: {
    kapso: {
      key_configured: boolean;
      webhook_configured: boolean;
      webhook_path: string;
    };
    stripe: {
      key_configured: boolean;
      webhook_configured: boolean;
      mode: string;
      webhook_path: string;
    };
    ai: {
      provider: string;
      key_configured: boolean;
      models: Record<string, string>;
    }[];
    provider_order: string[];
    encryption_configured: boolean;
    pi_public_url: string;
  };
}
export interface BillingPlan {
  key: string;
  name: string;
  description: string;
  status: string;
  monthly_price: string | null;
  currency: string;
  manual_monthly_price_pkr: string | null;
  stripe_price_id: string | null;
  stripe_price_configured: boolean;
  trial_days: number;
  allowances: Record<string, number | null>;
}
export interface CollectedPayment {
  id: string;
  tenant_id: string;
  business_name: string;
  plan: string;
  plan_name: string;
  amount: string;
  currency: string;
  method: string;
  status: string;
  months: number;
  created_at: string;
  payer_name: string;
  reference: string;
  paid_on: string | null;
  note: string;
  has_proof: boolean;
  receipt_number: string | null;
  review_note: string;
  refund_reason: string | null;
  instructions: Record<string, string>;
}
export interface BillingSummary {
  period: string;
  received_pkr: string;
  refunded_pkr: string;
  net_pkr: string;
  pending_count: number;
  stripe_paid: { currency: string; amount: string }[];
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Operator {
  role: string;
  capabilities: string[];
}
const root = "/operator/pi";
export const piBillingService = {
  me: () => apiRequest<Operator>("GET", root + "/me", null),
  settings: () =>
    apiRequest<PlatformSettings>("GET", root + "/billing/settings", null),
  saveSettings: (body: CollectionSettings) =>
    apiRequest<PlatformSettings>("PUT", root + "/billing/settings", null, {
      body,
    }),
  plans: () => apiRequest<BillingPlan[]>("GET", root + "/plans", null),
  savePlan: (key: string, body: unknown) =>
    apiRequest<BillingPlan>("PUT", root + `/plans/${key}`, null, { body }),
  payments: (status: string, page: number) =>
    apiRequest<Page<CollectedPayment>>(
      "GET",
      root + "/billing/payments",
      null,
      { query: { status: status || undefined, page, page_size: 20 } },
    ),
  summary: () =>
    apiRequest<BillingSummary>("GET", root + "/billing/summary", null),
  accounts: (search: string) =>
    apiRequest<Page<{ tenant_id: string; name: string; plan: string }>>(
      "GET",
      root + "/accounts",
      null,
      { query: { search, page_size: 100 } },
    ),
  review: (payment: CollectedPayment, body: unknown) =>
    apiRequest<CollectedPayment>(
      "POST",
      root +
        `/billing/accounts/${payment.tenant_id}/payments/${payment.id}/review`,
      null,
      { body },
    ),
  refund: (payment: CollectedPayment, body: unknown) =>
    apiRequest<CollectedPayment>(
      "POST",
      root +
        `/billing/accounts/${payment.tenant_id}/payments/${payment.id}/refund`,
      null,
      { body },
    ),
  cash: (tenant: string, body: unknown) =>
    apiRequest<CollectedPayment>(
      "POST",
      root + `/billing/accounts/${tenant}/cash`,
      null,
      { body },
    ),
};
