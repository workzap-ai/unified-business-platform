// Response contracts of /api/v1/pi-app (see apps/api/app/modules/pi_saas/app_routes.py
// and the shared PI routers). Money and quantities are decimal strings.

export type SetupState =
  | "draft"
  | "awaiting_connection"
  | "awaiting_approval"
  | "ready"
  | "active"
  | "paused"
  | "action_required";

export interface SessionView {
  user: {
    id: string;
    email: string;
    display_name: string;
    email_verified: boolean;
  };
  business: {
    id: string;
    name: string;
    setup_state: SetupState;
    onboarding_step: number;
    environment: "production" | "test";
  } | null;
  businesses: { id: string; name: string }[];
  permissions: string[];
  roles: string[];
}

export interface ReadinessItem {
  key: string;
  label: string;
  done: boolean;
  reason?: string | null;
}

export interface ConnectionView {
  status:
    | "draft"
    | "setup_pending"
    | "connected"
    | "action_required"
    | "disconnected";
  display_phone_number?: string | null;
  connection_type?: string | null;
  setup_url?: string | null;
  setup_expires_at?: string | null;
  health?: { status: string; checks: Record<string, string> } | null;
  health_checked_at?: string | null;
  problem?: string | null;
  number_request?: {
    status: string | null;
    country: string | null;
    quote: {
      monthly_price: string;
      setup_fee: string;
      currency: string;
      number?: string;
      note?: string;
    } | null;
  } | null;
}

export interface Account {
  name: string;
  business_category: string;
  language: string;
  timezone: string;
  country: string;
  website: string;
  description: string;
  offer_type: "services" | "products" | "both";
  currency: string;
  goals: string[];
  automation_mode: "human_approved" | "mixed" | "ai_led";
  price_disclosure: "exact" | "starting" | "quote" | "ask_team" | "hidden";
  tools: string[];
  whatsapp_choice: "existing" | "new" | null;
  setup_state: SetupState;
  onboarding_step: number;
  completed_steps: number[];
  help_requested_at: string | null;
  launched_at: string | null;
  paused_reason: string | null;
  readiness: ReadinessItem[];
  whatsapp: ConnectionView;
  tool_groups: string[];
  goals_available: string[];
}

export interface HomeView {
  name: string;
  setup_state: SetupState;
  active: boolean;
  plan_reason: string | null;
  metrics: {
    conversations_7d: number;
    pi_replies_7d: number;
    enquiries_7d: number;
    waiting_for_team: number;
    awaiting_approval: number;
    open_questions: number;
    ai_unavailable_24h: number;
    unread: number;
  };
  next_actions: { kind: string; label: string; href: string }[];
}

export interface Conversation {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string | null;
  status: "open" | "closed";
  mode: "ai" | "human";
  assigned_label: string | null;
  last_message_at: string;
  last_message_preview: string;
  last_sender: string;
  unread_count: number;
  language: string | null;
  handoff_id: string | null;
  handoff_status: string | null;
  summary: string;
  pending_confirmation: boolean;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  sender_type: "customer" | "ai" | "human" | "system";
  message_type: string;
  body: string;
  media: Record<string, unknown> | null;
  status: string;
  error_code: string | null;
  created_at: string;
  sent_by_label?: string | null;
  /** A problem map or journey card pi sent the customer on WhatsApp. */
  card?: { kind: string; image: string } | null;
}

export interface History {
  items: Message[];
  has_more: boolean;
  before: string | null;
  before_id: string | null;
}

export interface Plan {
  key: string;
  name: string;
  description: string;
  monthly_price: string | null;
  currency: string;
  trial_days: number;
  allowances: Record<string, number | null>;
  features: string[];
  purchasable: boolean;
  manual_monthly_price_pkr?: string | null;
}

export interface BillingView {
  subscription: {
    plan: string | null;
    status: string | null;
    entitled: boolean;
    reason: string | null;
    trial_ends_at: string | null;
    current_period_end: string | null;
    grace_ends_at: string | null;
    cancel_at_period_end: boolean;
    spend_limit: string | null;
    managed_online: boolean;
    billing_provider?: string | null;
  };
  plan: Plan | null;
  plans: Plan[];
  usage: {
    period: string;
    messages_sent: string;
    messages_received: string;
    ai_tokens: string;
    ai_cost: string;
    media_items: string;
    seats: number;
    test_messages_sent: string;
  };
  invoices: {
    number: string;
    status: string;
    amount_due: string;
    amount_paid: string;
    currency: string;
    period_start: string | null;
    period_end: string | null;
    url: string | null;
  }[];
  online_checkout: boolean;
}

export interface Draft {
  id: string;
  origin: string;
  title: string;
  content: string;
  customer_visible: boolean;
  status: string;
  created_at: string;
  source_note: string | null;
}

export interface StaffRequest {
  id: string;
  conversation_id: string;
  customer_id: string;
  question: string;
  context: string;
  created_at: string;
}
