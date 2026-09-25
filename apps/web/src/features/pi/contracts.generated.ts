// Generated from types.ts by scripts/generate-pi-contracts.mjs. Do not edit.
import { z } from "zod";
import type * as Pi from "./types";
export const ConversationStatusSchema: z.ZodType<Pi.ConversationStatus> =
  z.union([z.literal("open"), z.literal("closed")]);
export const ConversationModeSchema: z.ZodType<Pi.ConversationMode> = z.union([
  z.literal("ai"),
  z.literal("human"),
]);
export const HandoffStatusSchema: z.ZodType<Pi.HandoffStatus> = z.union([
  z.literal("open"),
  z.literal("closed"),
  z.literal("assigned"),
  z.literal("in_progress"),
  z.literal("resolved"),
]);
export const HandoffReasonSchema: z.ZodType<Pi.HandoffReason> = z.union([
  z.literal("customer_request"),
  z.literal("low_confidence"),
  z.literal("provider_failure"),
  z.literal("policy"),
  z.literal("tool_failure"),
  z.literal("complaint"),
  z.literal("sensitive"),
  z.literal("manual"),
]);
export const AgentKeySchema: z.ZodType<Pi.AgentKey> = z.union([
  z.literal("router"),
  z.literal("customer_memory"),
  z.literal("support"),
  z.literal("requirement"),
  z.literal("sales_order"),
  z.literal("handoff"),
]);
export const ProviderNameSchema: z.ZodType<Pi.ProviderName> = z.union([
  z.literal("openai"),
  z.literal("gemini"),
  z.literal("groq"),
]);
export const ConversationSchema: z.ZodType<Pi.Conversation> = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  customer_phone: z.union([z.null(), z.string()]),
  status: z.union([z.literal("open"), z.literal("closed")]),
  mode: z.union([z.literal("ai"), z.literal("human")]),
  assigned_label: z.union([z.null(), z.string()]),
  last_message_at: z.string(),
  last_message_preview: z.string(),
  last_sender: z.union([
    z.literal("ai"),
    z.literal("human"),
    z.literal("customer"),
    z.literal("system"),
  ]),
  unread_count: z.number(),
  language: z.union([
    z.null(),
    z.literal("en"),
    z.literal("ur"),
    z.literal("roman_ur"),
  ]),
  handoff_id: z.union([z.null(), z.string()]),
  handoff_status: z.union([
    z.null(),
    z.literal("open"),
    z.literal("closed"),
    z.literal("assigned"),
    z.literal("in_progress"),
    z.literal("resolved"),
  ]),
  last_intent: z.union([z.null(), z.string()]),
  summary: z.string(),
  pending_confirmation: z.boolean(),
});
export const ToolEventSchema: z.ZodType<Pi.ToolEvent> = z.object({
  tool: z.string(),
  status: z.union([
    z.literal("success"),
    z.literal("denied"),
    z.literal("error"),
    z.literal("confirmation_required"),
  ]),
  summary: z.string(),
});
export const MessageSchema: z.ZodType<Pi.Message> = z.object({
  id: z.string(),
  conversation_id: z.string(),
  direction: z.union([z.literal("inbound"), z.literal("outbound")]),
  sender_type: z.union([
    z.literal("ai"),
    z.literal("human"),
    z.literal("customer"),
    z.literal("system"),
  ]),
  message_type: z.union([
    z.literal("text"),
    z.literal("audio"),
    z.literal("image"),
    z.literal("interactive"),
    z.literal("other"),
  ]),
  body: z.string(),
  media: z.union([
    z.null(),
    z.object({
      mime_type: z.string(),
      size: z.number(),
      duration_s: z.union([z.undefined(), z.number()]).optional(),
      transcript: z.union([z.undefined(), z.string()]).optional(),
      description: z.union([z.undefined(), z.string()]).optional(),
    }),
  ]),
  status: z.union([
    z.literal("received"),
    z.literal("processed"),
    z.literal("skipped"),
    z.literal("failed"),
    z.literal("queued"),
    z.literal("processing"),
    z.literal("sent"),
    z.literal("delivered"),
    z.literal("read"),
  ]),
  error_code: z.union([z.null(), z.string()]),
  agent_key: z.union([
    z.null(),
    z.literal("router"),
    z.literal("customer_memory"),
    z.literal("support"),
    z.literal("requirement"),
    z.literal("sales_order"),
    z.literal("handoff"),
  ]),
  sent_by_label: z.union([z.null(), z.string()]),
  created_at: z.string(),
  tool_events: z.array(
    z.object({
      tool: z.string(),
      status: z.union([
        z.literal("success"),
        z.literal("denied"),
        z.literal("error"),
        z.literal("confirmation_required"),
      ]),
      summary: z.string(),
    }),
  ),
  confirmation: z.union([
    z.null(),
    z.object({
      kind: z.literal("order_summary"),
      status: z.union([
        z.literal("pending"),
        z.literal("confirmed"),
        z.literal("cancelled"),
        z.literal("expired"),
      ]),
      reference: z.string(),
      total: z.string(),
      currency: z.string(),
    }),
  ]),
});
export const AgentRunSchema: z.ZodType<Pi.AgentRun> = z.object({
  id: z.string(),
  message_id: z.string(),
  status: z.union([
    z.literal("handoff"),
    z.literal("skipped"),
    z.literal("failed"),
    z.literal("running"),
    z.literal("completed"),
  ]),
  intent: z.union([z.null(), z.string()]),
  confidence: z.union([z.null(), z.number()]),
  agent_path: z.array(
    z.union([
      z.literal("router"),
      z.literal("customer_memory"),
      z.literal("support"),
      z.literal("requirement"),
      z.literal("sales_order"),
      z.literal("handoff"),
    ]),
  ),
  provider: z.union([
    z.null(),
    z.literal("openai"),
    z.literal("gemini"),
    z.literal("groq"),
  ]),
  model_alias: z.union([z.null(), z.string()]),
  fallback_used: z.boolean(),
  latency_ms: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  tools: z.array(
    z.object({
      tool: z.string(),
      status: z.union([
        z.literal("success"),
        z.literal("denied"),
        z.literal("error"),
        z.literal("confirmation_required"),
      ]),
      summary: z.string(),
    }),
  ),
  created_at: z.string(),
});
export const ConversationContextSchema: z.ZodType<Pi.ConversationContext> =
  z.object({
    conversation: z.object({
      id: z.string(),
      customer_id: z.string(),
      customer_name: z.string(),
      customer_phone: z.union([z.null(), z.string()]),
      status: z.union([z.literal("open"), z.literal("closed")]),
      mode: z.union([z.literal("ai"), z.literal("human")]),
      assigned_label: z.union([z.null(), z.string()]),
      last_message_at: z.string(),
      last_message_preview: z.string(),
      last_sender: z.union([
        z.literal("ai"),
        z.literal("human"),
        z.literal("customer"),
        z.literal("system"),
      ]),
      unread_count: z.number(),
      language: z.union([
        z.null(),
        z.literal("en"),
        z.literal("ur"),
        z.literal("roman_ur"),
      ]),
      handoff_id: z.union([z.null(), z.string()]),
      handoff_status: z.union([
        z.null(),
        z.literal("open"),
        z.literal("closed"),
        z.literal("assigned"),
        z.literal("in_progress"),
        z.literal("resolved"),
      ]),
      last_intent: z.union([z.null(), z.string()]),
      summary: z.string(),
      pending_confirmation: z.boolean(),
    }),
    memory: z.array(
      z.object({
        id: z.string(),
        kind: z.union([
          z.literal("requirement"),
          z.literal("preference"),
          z.literal("context"),
        ]),
        content: z.string(),
        created_at: z.string(),
      }),
    ),
    knowledge_used: z.array(
      z.object({ title: z.string(), source: z.string(), snippet: z.string() }),
    ),
    recent_orders: z.array(
      z.object({
        id: z.string(),
        number: z.string(),
        status: z.string(),
        total: z.string(),
        created_at: z.string(),
      }),
    ),
    open_quotes: z.array(
      z.object({
        id: z.string(),
        number: z.string(),
        status: z.string(),
        total: z.string(),
      }),
    ),
    balance: z.union([z.null(), z.string()]),
    currency: z.string(),
    runs: z.array(
      z.object({
        id: z.string(),
        message_id: z.string(),
        status: z.union([
          z.literal("handoff"),
          z.literal("skipped"),
          z.literal("failed"),
          z.literal("running"),
          z.literal("completed"),
        ]),
        intent: z.union([z.null(), z.string()]),
        confidence: z.union([z.null(), z.number()]),
        agent_path: z.array(
          z.union([
            z.literal("router"),
            z.literal("customer_memory"),
            z.literal("support"),
            z.literal("requirement"),
            z.literal("sales_order"),
            z.literal("handoff"),
          ]),
        ),
        provider: z.union([
          z.null(),
          z.literal("openai"),
          z.literal("gemini"),
          z.literal("groq"),
        ]),
        model_alias: z.union([z.null(), z.string()]),
        fallback_used: z.boolean(),
        latency_ms: z.number(),
        input_tokens: z.number(),
        output_tokens: z.number(),
        tools: z.array(
          z.object({
            tool: z.string(),
            status: z.union([
              z.literal("success"),
              z.literal("denied"),
              z.literal("error"),
              z.literal("confirmation_required"),
            ]),
            summary: z.string(),
          }),
        ),
        created_at: z.string(),
      }),
    ),
  });
export const HandoffSchema: z.ZodType<Pi.Handoff> = z.object({
  id: z.string(),
  conversation_id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  status: z.union([
    z.literal("open"),
    z.literal("closed"),
    z.literal("assigned"),
    z.literal("in_progress"),
    z.literal("resolved"),
  ]),
  reason: z.union([
    z.literal("customer_request"),
    z.literal("low_confidence"),
    z.literal("provider_failure"),
    z.literal("policy"),
    z.literal("tool_failure"),
    z.literal("complaint"),
    z.literal("sensitive"),
    z.literal("manual"),
  ]),
  priority: z.union([
    z.literal("normal"),
    z.literal("high"),
    z.literal("urgent"),
  ]),
  summary: z.string(),
  assigned_label: z.union([z.null(), z.string()]),
  created_by_label: z.string(),
  created_at: z.string(),
  assigned_at: z.union([z.null(), z.string()]),
  resolved_at: z.union([z.null(), z.string()]),
  resolution_note: z.string(),
});
export const AgentSchema: z.ZodType<Pi.Agent> = z.object({
  id: z.string(),
  key: z.union([
    z.literal("router"),
    z.literal("customer_memory"),
    z.literal("support"),
    z.literal("requirement"),
    z.literal("sales_order"),
    z.literal("handoff"),
  ]),
  name: z.string(),
  role: z.string(),
  description: z.string(),
  enabled: z.boolean(),
  current_version: z.number(),
  model_alias: z.union([
    z.literal("fast"),
    z.literal("balanced"),
    z.literal("reasoning"),
  ]),
  temperature: z.string(),
  tools: z.array(z.string()),
  runs_7d: z.number(),
  success_rate: z.number(),
  avg_latency_ms: z.number(),
  last_run_at: z.union([z.null(), z.string()]),
});
export const AgentVersionSchema: z.ZodType<Pi.AgentVersion> = z.object({
  id: z.string(),
  agent_id: z.string(),
  version: z.number(),
  status: z.union([
    z.literal("active"),
    z.literal("archived"),
    z.literal("draft"),
  ]),
  instructions: z.string(),
  model_alias: z.union([
    z.literal("fast"),
    z.literal("balanced"),
    z.literal("reasoning"),
  ]),
  temperature: z.string(),
  note: z.string(),
  created_by_label: z.string(),
  created_at: z.string(),
});
export const ToolDefinitionSchema: z.ZodType<Pi.ToolDefinition> = z.object({
  key: z.string(),
  name: z.string(),
  description: z.string(),
  capability: z.union([
    z.literal("read"),
    z.literal("draft"),
    z.literal("mutation"),
    z.literal("communication"),
  ]),
  permission: z.string(),
  requires_confirmation: z.boolean(),
  enabled: z.boolean(),
  calls_7d: z.number(),
  failures_7d: z.number(),
  last_called_at: z.union([z.null(), z.string()]),
});
export const WhatsAppConnectionSchema: z.ZodType<Pi.WhatsAppConnection> =
  z.object({
    id: z.string(),
    provider: z.literal("meta_cloud"),
    phone_number_id: z.string(),
    display_phone_number: z.string(),
    business_account_id: z.string(),
    display_name: z.string(),
    status: z.union([
      z.literal("error"),
      z.literal("pending"),
      z.literal("active"),
      z.literal("disabled"),
    ]),
    has_access_token: z.boolean(),
    webhook_url: z.string(),
    webhook_verified: z.boolean(),
    verified_at: z.union([z.null(), z.string()]),
    last_inbound_at: z.union([z.null(), z.string()]),
    last_outbound_at: z.union([z.null(), z.string()]),
    last_error_code: z.union([z.null(), z.string()]),
    last_error_at: z.union([z.null(), z.string()]),
    messages_24h: z.object({
      inbound: z.number(),
      outbound: z.number(),
      failed: z.number(),
    }),
  });
export const WebhookEventSchema: z.ZodType<Pi.WebhookEvent> = z.object({
  id: z.string(),
  event_key: z.string(),
  kind: z.union([
    z.literal("message"),
    z.literal("status"),
    z.literal("unknown"),
  ]),
  status: z.union([
    z.literal("received"),
    z.literal("processed"),
    z.literal("failed"),
    z.literal("queued"),
    z.literal("ignored"),
  ]),
  summary: z.string(),
  duplicate_count: z.number(),
  attempts: z.number(),
  error_code: z.union([z.null(), z.string()]),
  created_at: z.string(),
  processed_at: z.union([z.null(), z.string()]),
});
export const KnowledgeSourceSchema: z.ZodType<Pi.KnowledgeSource> = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.union([
    z.literal("policy"),
    z.literal("company_info"),
    z.literal("faq"),
    z.literal("catalog"),
    z.literal("approved_answer"),
    z.literal("file"),
  ]),
  description: z.string(),
  status: z.union([z.literal("active"), z.literal("disabled")]),
  documents: z.number(),
  ready: z.number(),
  failed: z.number(),
  updated_at: z.string(),
});
export const KnowledgeDocumentSchema: z.ZodType<Pi.KnowledgeDocument> =
  z.object({
    id: z.string(),
    source_id: z.string(),
    source_name: z.string(),
    title: z.string(),
    mime_type: z.string(),
    byte_size: z.number(),
    status: z.union([
      z.literal("failed"),
      z.literal("processing"),
      z.literal("pending"),
      z.literal("ready"),
    ]),
    chunk_count: z.number(),
    error_code: z.union([z.null(), z.string()]),
    created_by_label: z.string(),
    created_at: z.string(),
    processed_at: z.union([z.null(), z.string()]),
    body: z.union([z.undefined(), z.string()]).optional(),
  });
export const ProviderHealthSchema: z.ZodType<Pi.ProviderHealth> = z.object({
  name: z.union([z.literal("openai"), z.literal("gemini"), z.literal("groq")]),
  role: z.union([
    z.literal("primary"),
    z.literal("fallback"),
    z.literal("secondary_fallback"),
  ]),
  configured: z.boolean(),
  status: z.union([
    z.literal("unknown"),
    z.literal("healthy"),
    z.literal("degraded"),
    z.literal("down"),
    z.literal("unconfigured"),
  ]),
  success_rate: z.number(),
  p50_ms: z.number(),
  requests_24h: z.number(),
});
export const PiOverviewSchema: z.ZodType<Pi.PiOverview> = z.object({
  period_days: z.number(),
  conversations_active: z.number(),
  conversations_total: z.number(),
  unresolved: z.number(),
  open_handoffs: z.number(),
  messages_in: z.number(),
  messages_out: z.number(),
  ai_responses: z.number(),
  automation_rate: z.number(),
  avg_response_ms: z.number(),
  p95_response_ms: z.number(),
  fallback_count: z.number(),
  tool_calls: z.number(),
  tool_failures: z.number(),
  whatsapp: z.union([
    z.null(),
    z.object({
      status: z.union([
        z.literal("error"),
        z.literal("pending"),
        z.literal("active"),
        z.literal("disabled"),
      ]),
      display_phone_number: z.string(),
      last_inbound_at: z.union([z.null(), z.string()]),
    }),
  ]),
  knowledge: z.object({
    sources: z.number(),
    documents_ready: z.number(),
    documents_failed: z.number(),
    passages: z.number(),
  }),
  providers: z.array(
    z.object({
      name: z.union([
        z.literal("openai"),
        z.literal("gemini"),
        z.literal("groq"),
      ]),
      role: z.union([
        z.literal("primary"),
        z.literal("fallback"),
        z.literal("secondary_fallback"),
      ]),
      configured: z.boolean(),
      status: z.union([
        z.literal("unknown"),
        z.literal("healthy"),
        z.literal("degraded"),
        z.literal("down"),
        z.literal("unconfigured"),
      ]),
      success_rate: z.number(),
      p50_ms: z.number(),
      requests_24h: z.number(),
    }),
  ),
  volume: z.array(
    z.object({
      day: z.string(),
      inbound: z.number(),
      ai: z.number(),
      human: z.number(),
    }),
  ),
  agent_activity: z.array(
    z.object({
      agent: z.union([
        z.literal("router"),
        z.literal("customer_memory"),
        z.literal("support"),
        z.literal("requirement"),
        z.literal("sales_order"),
        z.literal("handoff"),
      ]),
      runs: z.number(),
    }),
  ),
  auto_reply_enabled: z.boolean(),
});
export const AnalyticsRangeSchema: z.ZodType<Pi.AnalyticsRange> = z.union([
  z.literal(7),
  z.literal(30),
  z.literal(90),
]);
export const PiAnalyticsSchema: z.ZodType<Pi.PiAnalytics> = z.object({
  range: z.union([z.literal(7), z.literal(30), z.literal(90)]),
  currency_note: z.string(),
  conversations: z.array(
    z.object({ day: z.string(), started: z.number(), resolved: z.number() }),
  ),
  messages: z.array(
    z.object({
      day: z.string(),
      inbound: z.number(),
      outbound_ai: z.number(),
      outbound_human: z.number(),
    }),
  ),
  latency: z.array(
    z.object({ day: z.string(), p50: z.number(), p95: z.number() }),
  ),
  runs_by_agent: z.array(
    z.object({
      agent: z.union([
        z.literal("router"),
        z.literal("customer_memory"),
        z.literal("support"),
        z.literal("requirement"),
        z.literal("sales_order"),
        z.literal("handoff"),
      ]),
      runs: z.number(),
      failures: z.number(),
    }),
  ),
  intents: z.array(z.object({ intent: z.string(), count: z.number() })),
  tools: z.array(
    z.object({
      tool: z.string(),
      success: z.number(),
      failed: z.number(),
      denied: z.number(),
    }),
  ),
  handoffs_by_reason: z.array(
    z.object({
      reason: z.union([
        z.literal("customer_request"),
        z.literal("low_confidence"),
        z.literal("provider_failure"),
        z.literal("policy"),
        z.literal("tool_failure"),
        z.literal("complaint"),
        z.literal("sensitive"),
        z.literal("manual"),
      ]),
      count: z.number(),
    }),
  ),
  handoffs_by_day: z.array(
    z.object({ day: z.string(), opened: z.number(), resolved: z.number() }),
  ),
  fallbacks: z.array(z.object({ day: z.string(), count: z.number() })),
  fallback_pairs: z.array(
    z.object({
      from: z.union([
        z.literal("openai"),
        z.literal("gemini"),
        z.literal("groq"),
      ]),
      to: z.union([
        z.literal("handoff"),
        z.literal("openai"),
        z.literal("gemini"),
        z.literal("groq"),
      ]),
      count: z.number(),
      top_reason: z.string(),
    }),
  ),
  provider_usage: z.array(
    z.object({
      day: z.string(),
      openai: z.number(),
      gemini: z.number(),
      groq: z.number(),
    }),
  ),
  tokens: z.array(
    z.object({ day: z.string(), input: z.number(), output: z.number() }),
  ),
  cost_estimate: z.union([
    z.null(),
    z.array(z.object({ day: z.string(), amount: z.number() })),
  ]),
  totals: z.object({
    conversations: z.number(),
    messages: z.number(),
    ai_responses: z.number(),
    runs: z.number(),
    tool_calls: z.number(),
    handoffs: z.number(),
    fallbacks: z.number(),
    failure_rate: z.number(),
    input_tokens: z.number(),
    output_tokens: z.number(),
    cost_estimate_usd: z.union([z.null(), z.number()]),
  }),
});
export const PiSettingsSchema: z.ZodType<Pi.PiSettings> = z.object({
  auto_reply_enabled: z.boolean(),
  timezone: z.string(),
  business_hours: z.object({
    enabled: z.boolean(),
    days: z.object({
      mon: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
      tue: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
      wed: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
      thu: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
      fri: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
      sat: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
      sun: z.object({ open: z.boolean(), start: z.string(), end: z.string() }),
    }),
    outside_hours: z.union([
      z.literal("reply"),
      z.literal("reply_with_notice"),
      z.literal("handoff_only"),
    ]),
    notice: z.string(),
  }),
  response_rules: z.object({
    language: z.union([
      z.literal("en"),
      z.literal("ur"),
      z.literal("roman_ur"),
      z.literal("auto"),
    ]),
    max_reply_chars: z.number(),
    tone: z.union([
      z.literal("friendly"),
      z.literal("formal"),
      z.literal("concise"),
    ]),
    greeting: z.string(),
    sign_off: z.string(),
  }),
  ai_config: z.object({
    router_alias: z.union([z.literal("fast"), z.literal("balanced")]),
    reply_alias: z.union([
      z.literal("fast"),
      z.literal("balanced"),
      z.literal("reasoning"),
    ]),
    temperature: z.string(),
    clarify_before_handoff: z.number(),
  }),
  provider_config: z.object({
    order: z.array(
      z.union([z.literal("openai"), z.literal("gemini"), z.literal("groq")]),
    ),
    retry_transient: z.boolean(),
    max_retries: z.number(),
    timeout_seconds: z.number(),
  }),
  tool_permissions: z.record(z.string(), z.boolean()),
  handoff_rules: z.object({
    keywords: z.array(z.string()),
    low_confidence_threshold: z.string(),
    max_failed_turns: z.number(),
    handoff_on_complaint: z.boolean(),
    notify_roles: z.array(z.string()),
  }),
  knowledge_config: z.object({
    top_k: z.number(),
    min_score: z.string(),
    semantic_enabled: z.boolean(),
    cite_sources_to_operators: z.boolean(),
  }),
  whatsapp_config: z.object({
    send_read_receipts: z.boolean(),
    typing_indicator: z.boolean(),
    media_voice: z.boolean(),
    media_images: z.boolean(),
    max_media_mb: z.number(),
  }),
  permissions: z.array(
    z.object({
      role: z.string(),
      view_inbox: z.boolean(),
      reply: z.boolean(),
      takeover: z.boolean(),
      configure: z.boolean(),
    }),
  ),
});
