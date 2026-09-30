import { apiRequest } from "@/services/api-client";

/**
 * Platform operator console (Owner OS). Calls /api/v1/operator/*, which re-checks the
 * operator's membership and capabilities on every request. Live API only: there is no
 * sample-data adapter because operator data is cross-business by nature.
 */

export interface OperatorMe {
  role: string;
  role_name: string;
  capabilities: string[];
}

export interface BusinessRow {
  tenant_id: string;
  name: string;
  setup_state: string;
  status: string;
  onboarding_step: number;
  help_requested: boolean;
  plan: string | null;
  subscription_status: string | null;
  connection_status: string;
  created_at: string;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReadinessItem {
  key: string;
  label: string;
  done: boolean;
}

export interface BusinessDetail {
  tenant_id: string;
  name: string;
  status: string;
  setup_state: string;
  onboarding_step: number;
  offer_type: string;
  language: string;
  timezone: string;
  country: string;
  help_requested_at: string | null;
  launched_at: string | null;
  readiness: ReadinessItem[];
  connections: {
    environment: string;
    provider: string;
    status: string;
    display_phone_number: string | null;
    connection_type: string | null;
    health: { status: string } | null;
    problem: string | null;
    number_request: {
      status?: string;
      country?: string;
      quote?: { monthly_price: string; currency: string } | null;
    } | null;
    last_event_at: string | null;
  }[];
  support_grants: {
    id: string;
    scope: string;
    status: string;
    expires_at: string | null;
    requested_by: string;
  }[];
  customer_payment_methods: string[];
  subscription?: {
    plan: string;
    status: string;
    trial_ends_at: string | null;
    current_period_end: string | null;
    grace_ends_at: string | null;
    billing_provider: string;
    spend_limit: string | null;
  } | null;
  invoices?: {
    number: string;
    status: string;
    amount_due: string;
    currency: string;
  }[];
  usage?: { production: Record<string, string>; test: Record<string, string> };
}

export interface WorkspaceRow {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  members: number;
  products: string[];
  kind: "pi" | "owner_os";
  pi_setup_state: string | null;
  is_member: boolean;
}

export interface Summary {
  businesses: number;
  by_state: Record<string, number>;
  needs_attention: { tenant_id: string; name: string; state: string }[];
  signals: Record<string, number> | null;
  generated_at: string;
}

export interface Health {
  failed_messages_24h: number;
  failed_webhook_events: number;
  failed_provider_events: number;
  failed_billing_events: number;
  accounts_action_required: number;
  subscriptions_past_due: number;
  help_requests: number;
  number_requests: number;
  configuration: {
    whatsapp_provider: boolean;
    provider_webhook_secret: boolean;
    billing: boolean;
    billing_webhook_secret: boolean;
    job_queue: string;
    ai_providers: string[];
  };
}

export interface Plan {
  key: string;
  name: string;
  description: string;
  status: string;
  monthly_price: string | null;
  currency: string;
  trial_days: number;
  allowances: Record<string, number | null>;
  features: string[];
  stripe_price_configured: boolean;
}

export interface TeamView {
  members: {
    id: string;
    email: string;
    name: string;
    role: string;
    status: string;
    capabilities: string[];
  }[];
  roles: Record<
    string,
    { name: string; description: string; capabilities: string[] }
  >;
  capabilities: string[];
}

export interface FailedEvent {
  id: string;
  event_type: string;
  tenant_id: string | null;
  attempts: number;
  error_code: string | null;
  created_at: string;
}

const base = "/operator/pi";
type Query = Record<string, string | number | boolean | undefined>;

export interface AgentaAnswer {
  answer: string;
  topic: string;
  generated_by: "model" | "template";
  links: { label: string; href: string }[];
  generated_at: string;
}

export interface OperatorWeek {
  since: string;
  week: Partial<
    Record<
      "new_businesses" | "went_live" | "messages_received" | "pi_replies",
      number
    >
  >;
}

export const operatorService = {
  weekly: () => apiRequest<OperatorWeek>("GET", `${base}/weekly`, null),
  agenta: (question: string) =>
    apiRequest<AgentaAnswer>("POST", `${base}/agenta/ask`, null, {
      body: { question },
    }),
  me: () => apiRequest<OperatorMe>("GET", `${base}/me`, null),
  summary: () => apiRequest<Summary>("GET", `${base}/summary`, null),
  health: () => apiRequest<Health>("GET", `${base}/health`, null),
  businesses: (query: Query) =>
    apiRequest<Paged<BusinessRow>>("GET", `${base}/accounts`, null, { query }),
  business: (id: string) =>
    apiRequest<BusinessDetail>("GET", `${base}/accounts/${id}`, null),
  pause: (id: string, reason: string) =>
    apiRequest("POST", `${base}/accounts/${id}/pause`, null, {
      body: { reason },
    }),
  resume: (id: string) =>
    apiRequest("POST", `${base}/accounts/${id}/resume`, null, { body: {} }),
  accountStatus: (id: string, status: "active" | "suspended", reason: string) =>
    apiRequest("POST", `${base}/accounts/${id}/status`, null, {
      body: { status, reason },
    }),
  requestSupport: (
    id: string,
    body: { scope: string; reason: string; days: number },
  ) =>
    apiRequest("POST", `${base}/accounts/${id}/support-requests`, null, {
      body,
    }),
  subscription: (
    id: string,
    body: {
      plan?: string;
      status?: string;
      extend_trial_days?: number;
      reason: string;
    },
  ) =>
    apiRequest("POST", `${base}/accounts/${id}/subscription`, null, { body }),
  numberQuote: (
    id: string,
    body: {
      monthly_price: string;
      setup_fee: string;
      currency: string;
      phone_number_preview: string;
      note: string;
    },
  ) =>
    apiRequest("POST", `${base}/accounts/${id}/number-quote`, null, { body }),
  numberLink: (id: string) =>
    apiRequest("POST", `${base}/accounts/${id}/number-link`, null, {
      body: {},
    }),
  plans: () => apiRequest<Plan[]>("GET", `${base}/plans`, null),
  updatePlan: (
    key: string,
    body: Partial<Plan> & { stripe_price_id?: string },
  ) => apiRequest<Plan>("PUT", `${base}/plans/${key}`, null, { body }),
  team: () => apiRequest<TeamView>("GET", `${base}/team`, null),
  addOperator: (body: { email: string; role: string }) =>
    apiRequest("POST", `${base}/team`, null, { body }),
  revokeOperator: (id: string) =>
    apiRequest("DELETE", `${base}/team/${id}`, null),
  assign: (tenantId: string, operatorId: string) =>
    apiRequest("POST", `${base}/accounts/${tenantId}/assignments`, null, {
      body: { operator_id: operatorId },
    }),
  failedEvents: () =>
    apiRequest<FailedEvent[]>("GET", `${base}/events/failed`, null),
  replay: (id: string) =>
    apiRequest("POST", `${base}/events/${id}/replay`, null, { body: {} }),
  workspaces: (query: Query) =>
    apiRequest<Paged<WorkspaceRow>>("GET", "/operator/workspaces", null, {
      query,
    }),
  workspaceStatus: (
    id: string,
    status: "active" | "inactive",
    reason: string,
  ) =>
    apiRequest("POST", `/operator/workspaces/${id}/status`, null, {
      body: { status, reason },
    }),
};
