/**
 * PI product contracts (designed ahead of the PI API; the backend phase implements
 * these shapes over the existing pi_* tables). Operator-facing only: nothing here
 * exposes prompts, provider credentials or raw provider errors.
 */

export type ConversationStatus = "open" | "closed";
export type ConversationMode = "ai" | "human";
export type HandoffStatus =
  "open" | "assigned" | "in_progress" | "resolved" | "closed";
export type HandoffReason =
  | "customer_request"
  | "low_confidence"
  | "provider_failure"
  | "policy"
  | "tool_failure"
  | "complaint"
  | "sensitive"
  | "manual";
export type AgentKey =
  | "router"
  | "customer_memory"
  | "support"
  | "requirement"
  | "sales_order"
  | "handoff";
export type ProviderName = "openai" | "gemini" | "groq";

export type Conversation = {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string | null;
  status: ConversationStatus;
  mode: ConversationMode;
  assigned_label: string | null;
  last_message_at: string;
  last_message_preview: string;
  last_sender: "customer" | "ai" | "human" | "system";
  unread_count: number;
  language: string | null;
  handoff_id: string | null;
  handoff_status: HandoffStatus | null;
  last_intent: string | null;
  summary: string;
  pending_confirmation: boolean;
};

export type ToolEvent = {
  tool: string;
  status: "success" | "denied" | "error" | "confirmation_required";
  summary: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  direction: "inbound" | "outbound";
  sender_type: "customer" | "ai" | "human" | "system";
  message_type: "text" | "audio" | "image" | "video" | "interactive" | "other";
  body: string;
  media: {
    mime_type: string;
    size: number;
    duration_s?: number;
    transcript?: string;
    description?: string;
  } | null;
  status:
    | "received"
    | "processed"
    | "skipped"
    | "failed"
    | "queued"
    | "processing"
    | "sent"
    | "delivered"
    | "read";
  error_code: string | null;
  agent_key: AgentKey | null;
  sent_by_label: string | null;
  created_at: string;
  tool_events: ToolEvent[];
  confirmation: {
    kind: "order_summary";
    status: "pending" | "confirmed" | "cancelled" | "expired";
    reference: string;
    total: string;
    currency: string;
  } | null;
};

export type AgentRun = {
  id: string;
  message_id: string;
  status: "running" | "completed" | "failed" | "handoff" | "skipped";
  intent: string | null;
  confidence: number | null;
  agent_path: AgentKey[];
  provider: ProviderName | null;
  model_alias: string | null;
  fallback_used: boolean;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  tools: ToolEvent[];
  created_at: string;
};

export type ConversationContext = {
  conversation: Conversation;
  service_brief?: {
    requirements?: Record<string, string>;
    missing?: string[];
    reminder_consent?: string;
    ready_for_team?: boolean;
    awaiting_customer?: boolean;
  };
  followup_due_at?: string | null;
  memory: {
    id: string;
    kind: "preference" | "requirement" | "context";
    content: string;
    created_at: string;
  }[];
  knowledge_used: { title: string; source: string; snippet: string }[];
  recent_orders: {
    id: string;
    number: string;
    status: string;
    total: string;
    created_at: string;
  }[];
  open_quotes: { id: string; number: string; status: string; total: string }[];
  balance: string | null;
  currency: string;
  runs: AgentRun[];
};

export type Handoff = {
  id: string;
  conversation_id: string;
  customer_id: string;
  customer_name: string;
  status: HandoffStatus;
  reason: HandoffReason;
  priority: "normal" | "high" | "urgent";
  summary: string;
  assigned_label: string | null;
  created_by_label: string;
  created_at: string;
  assigned_at: string | null;
  resolved_at: string | null;
  resolution_note: string;
};

export type Agent = {
  id: string;
  key: AgentKey;
  name: string;
  role: string;
  description: string;
  enabled: boolean;
  current_version: number;
  model_alias: "fast" | "balanced" | "reasoning";
  temperature: string;
  tools: string[];
  runs_7d: number;
  success_rate: number;
  avg_latency_ms: number;
  last_run_at: string | null;
};

export type AgentVersion = {
  id: string;
  agent_id: string;
  version: number;
  status: "active" | "archived" | "draft";
  instructions: string;
  model_alias: Agent["model_alias"];
  temperature: string;
  note: string;
  created_by_label: string;
  created_at: string;
};

export type ToolDefinition = {
  key: string;
  name: string;
  description: string;
  capability: "read" | "draft" | "mutation" | "communication";
  permission: string;
  requires_confirmation: boolean;
  enabled: boolean;
  calls_7d: number;
  failures_7d: number;
  last_called_at: string | null;
};

export type WhatsAppConnection = {
  id: string;
  provider: "meta_cloud";
  phone_number_id: string;
  display_phone_number: string;
  business_account_id: string;
  display_name: string;
  status: "pending" | "active" | "disabled" | "error";
  has_access_token: boolean;
  webhook_url: string;
  webhook_verified: boolean;
  verified_at: string | null;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  last_error_code: string | null;
  last_error_at: string | null;
  messages_24h: { inbound: number; outbound: number; failed: number };
};

export type WebhookEvent = {
  id: string;
  event_key: string;
  kind: "message" | "status" | "unknown";
  status: "received" | "queued" | "processed" | "ignored" | "failed";
  summary: string;
  duplicate_count: number;
  attempts: number;
  error_code: string | null;
  created_at: string;
  processed_at: string | null;
};

export type KnowledgeSource = {
  id: string;
  name: string;
  kind:
    "company_info" | "faq" | "policy" | "catalog" | "approved_answer" | "file";
  description: string;
  status: "active" | "disabled";
  documents: number;
  ready: number;
  failed: number;
  updated_at: string;
};

export type KnowledgeDocument = {
  id: string;
  source_id: string;
  source_name: string;
  title: string;
  mime_type: string;
  byte_size: number;
  status: "pending" | "processing" | "ready" | "failed";
  chunk_count: number;
  error_code: string | null;
  created_by_label: string;
  created_at: string;
  processed_at: string | null;
  body?: string;
};

export type ProviderHealth = {
  name: ProviderName;
  role: "primary" | "fallback" | "secondary_fallback";
  configured: boolean;
  status: "healthy" | "degraded" | "down" | "unconfigured" | "unknown";
  success_rate: number;
  p50_ms: number;
  requests_24h: number;
};

export type PiOverview = {
  period_days: number;
  conversations_active: number;
  conversations_total: number;
  unresolved: number;
  open_handoffs: number;
  messages_in: number;
  messages_out: number;
  ai_responses: number;
  automation_rate: number;
  avg_response_ms: number;
  p95_response_ms: number;
  fallback_count: number;
  tool_calls: number;
  tool_failures: number;
  whatsapp: Pick<
    WhatsAppConnection,
    "status" | "display_phone_number" | "last_inbound_at"
  > | null;
  knowledge: {
    sources: number;
    documents_ready: number;
    documents_failed: number;
    passages: number;
  };
  providers: ProviderHealth[];
  volume: { day: string; inbound: number; ai: number; human: number }[];
  agent_activity: { agent: AgentKey; runs: number }[];
  auto_reply_enabled: boolean;
};

export type AnalyticsRange = 7 | 30 | 90;

export type PiAnalytics = {
  range: AnalyticsRange;
  currency_note: string;
  conversations: { day: string; started: number; resolved: number }[];
  messages: {
    day: string;
    inbound: number;
    outbound_ai: number;
    outbound_human: number;
  }[];
  latency: { day: string; p50: number; p95: number }[];
  runs_by_agent: { agent: AgentKey; runs: number; failures: number }[];
  intents: { intent: string; count: number }[];
  tools: { tool: string; success: number; failed: number; denied: number }[];
  handoffs_by_reason: { reason: HandoffReason; count: number }[];
  handoffs_by_day: { day: string; opened: number; resolved: number }[];
  fallbacks: { day: string; count: number }[];
  fallback_pairs: {
    from: ProviderName;
    to: ProviderName | "handoff";
    count: number;
    top_reason: string;
  }[];
  provider_usage: {
    day: string;
    openai: number;
    gemini: number;
    groq: number;
  }[];
  tokens: { day: string; input: number; output: number }[];
  cost_estimate: { day: string; amount: number }[] | null;
  totals: {
    conversations: number;
    messages: number;
    ai_responses: number;
    runs: number;
    tool_calls: number;
    handoffs: number;
    fallbacks: number;
    failure_rate: number;
    input_tokens: number;
    output_tokens: number;
    cost_estimate_usd: number | null;
  };
};

export type PiSettings = {
  auto_reply_enabled: boolean;
  timezone: string;
  business_hours: {
    enabled: boolean;
    days: Record<
      "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun",
      { open: boolean; start: string; end: string }
    >;
    outside_hours: "reply" | "reply_with_notice" | "handoff_only";
    notice: string;
  };
  response_rules: {
    language: string;
    service_mode: "auto" | "service";
    max_reply_chars: number;
    tone: "friendly" | "formal" | "concise";
    greeting: string;
    sign_off: string;
  };
  ai_config: {
    router_alias: "fast" | "balanced";
    reply_alias: "fast" | "balanced" | "reasoning";
    temperature: string;
    clarify_before_handoff: number;
  };
  provider_config: {
    order: ProviderName[];
    retry_transient: boolean;
    max_retries: number;
    timeout_seconds: number;
  };
  tool_permissions: Record<string, boolean>;
  handoff_rules: {
    keywords: string[];
    low_confidence_threshold: string;
    max_failed_turns: number;
    handoff_on_complaint: boolean;
    notify_roles: string[];
  };
  knowledge_config: {
    top_k: number;
    min_score: string;
    semantic_enabled: boolean;
    cite_sources_to_operators: boolean;
  };
  whatsapp_config: {
    send_read_receipts: boolean;
    typing_indicator: boolean;
    media_voice: boolean;
    media_images: boolean;
    media_video: boolean;
    max_media_mb: number;
    reminder_enabled: boolean;
    reminder_after_days: number;
    reminder_templates: Record<string, { name: string; language: string }>;
  };
  permissions: {
    role: string;
    view_inbox: boolean;
    reply: boolean;
    takeover: boolean;
    configure: boolean;
  }[];
};
