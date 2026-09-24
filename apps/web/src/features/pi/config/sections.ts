/**
 * Section slugs shared by route files (server) and section pages (client). Kept free of
 * "use client" so server components can validate slugs and call notFound().
 */

export const ANALYTICS_SECTIONS = [
  { slug: "conversations", label: "Conversations" },
  { slug: "agent-runs", label: "Agent runs" },
  { slug: "ai-usage", label: "AI usage" },
  { slug: "fallbacks", label: "Fallbacks" },
  { slug: "handoffs", label: "Handoffs" },
  { slug: "tool-activity", label: "Tool activity" },
] as const;

export type AnalyticsSection = (typeof ANALYTICS_SECTIONS)[number]["slug"];

export function isAnalyticsSection(slug: string): slug is AnalyticsSection {
  return ANALYTICS_SECTIONS.some((s) => s.slug === slug);
}

export const SETTINGS_SECTIONS = [
  {
    slug: "business-hours",
    key: "business_hours",
    label: "Business hours",
    description: "When PI replies and what happens outside hours.",
  },
  {
    slug: "response-rules",
    key: "response_rules",
    label: "Response rules",
    description: "Language, tone, length, greeting and sign-off.",
  },
  {
    slug: "ai-configuration",
    key: "ai_config",
    label: "AI configuration",
    description: "Model tiers for routing and replies, clarifications.",
  },
  {
    slug: "provider-configuration",
    key: "provider_config",
    label: "Provider configuration",
    description: "Fallback order, retries and timeouts.",
  },
  {
    slug: "tool-permissions",
    key: "tool_permissions",
    label: "Tool permissions",
    description: "Which tools PI may use in this workspace.",
  },
  {
    slug: "agent-configuration",
    key: null,
    label: "Agent configuration",
    description: "Enable or disable PI's agents.",
  },
  {
    slug: "handoff-rules",
    key: "handoff_rules",
    label: "Handoff rules",
    description: "When PI hands a conversation to your team.",
  },
  {
    slug: "knowledge-configuration",
    key: "knowledge_config",
    label: "Knowledge",
    description: "Retrieval depth, relevance and semantic search.",
  },
  {
    slug: "whatsapp-configuration",
    key: "whatsapp_config",
    label: "WhatsApp",
    description: "Read receipts, typing indicator and media.",
  },
  {
    slug: "permissions",
    key: "permissions",
    label: "Permissions",
    description: "What each role can do in PI.",
  },
] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number]["slug"];

export function isSettingsSection(slug: string): slug is SettingsSection {
  return SETTINGS_SECTIONS.some((s) => s.slug === slug);
}
