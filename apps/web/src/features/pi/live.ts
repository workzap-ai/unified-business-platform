import { z } from "zod";
import { apiRequest, pageSchema } from "@/services/api-client";
import type { PiService } from "./service";
import * as schema from "./contracts.generated";

export const piLive: PiService = {
  overview: () => apiRequest("GET", "/pi/overview", schema.PiOverviewSchema),
  conversations: (filters) =>
    apiRequest(
      "GET",
      "/pi/conversations",
      pageSchema(schema.ConversationSchema),
      { query: filters },
    ),
  context: (id) =>
    apiRequest(
      "GET",
      `/pi/conversations/${id}/context`,
      schema.ConversationContextSchema,
    ),
  deleteMemory: async (_conversationId, memoryId) => {
    await apiRequest("DELETE", `/pi/memory/${memoryId}`, null);
  },
  messages: (id) =>
    apiRequest(
      "GET",
      `/pi/conversations/${id}/messages`,
      z.array(schema.MessageSchema),
    ),
  sendMessage: (id, body) =>
    apiRequest(
      "POST",
      `/pi/conversations/${id}/messages`,
      schema.MessageSchema,
      { body: { body } },
    ),
  takeover: (id) =>
    apiRequest(
      "POST",
      `/pi/conversations/${id}/actions/takeover`,
      schema.ConversationSchema,
    ),
  returnToAi: (id) =>
    apiRequest(
      "POST",
      `/pi/conversations/${id}/actions/return-to-ai`,
      schema.ConversationSchema,
    ),
  closeConversation: (id) =>
    apiRequest(
      "POST",
      `/pi/conversations/${id}/actions/close`,
      schema.ConversationSchema,
    ),
  markRead: async (id) => {
    await apiRequest(
      "POST",
      `/pi/conversations/${id}/actions/read`,
      schema.ConversationSchema,
    );
  },
  handoffs: (status) =>
    apiRequest("GET", "/pi/handoffs", z.array(schema.HandoffSchema), {
      query: { status },
    }),
  createHandoff: (id, reason, summary) =>
    apiRequest(
      "POST",
      `/pi/conversations/${id}/handoff`,
      schema.HandoffSchema,
      { body: { reason, summary } },
    ),
  updateHandoff: (id, action, payload) =>
    apiRequest("POST", `/pi/handoffs/${id}/actions`, schema.HandoffSchema, {
      body: { action, ...payload },
    }),
  agents: () => apiRequest("GET", "/pi/agents", z.array(schema.AgentSchema)),
  agent: (id) => apiRequest("GET", `/pi/agents/${id}`, schema.AgentSchema),
  versions: (id) =>
    apiRequest(
      "GET",
      `/pi/agents/${id}/versions`,
      z.array(schema.AgentVersionSchema),
    ),
  publishVersion: (id, input) =>
    apiRequest("POST", `/pi/agents/${id}/versions`, schema.AgentVersionSchema, {
      body: input,
    }),
  rollback: (id, versionId) =>
    apiRequest(
      "POST",
      `/pi/agents/${id}/versions/${versionId}/rollback`,
      schema.AgentVersionSchema,
    ),
  setAgentEnabled: (id, enabled) =>
    apiRequest("PUT", `/pi/agents/${id}/enabled`, schema.AgentSchema, {
      body: { enabled },
    }),
  setAgentTool: (id, tool, enabled) =>
    apiRequest("PUT", `/pi/agents/${id}/tools/${tool}`, schema.AgentSchema, {
      body: { enabled },
    }),
  testAgent: (message) =>
    apiRequest(
      "POST",
      "/pi/agent-test",
      z.object({
        simulated: z.boolean(),
        intent: z.string(),
        confidence: z.number(),
        route: z.array(schema.AgentKeySchema),
        tools: z.array(z.string()),
        note: z.string(),
      }),
      { body: { body: message } },
    ),
  tools: () =>
    apiRequest("GET", "/pi/tools", z.array(schema.ToolDefinitionSchema)),
  setToolEnabled: (key, enabled) =>
    apiRequest("PUT", `/pi/tools/${key}/enabled`, schema.ToolDefinitionSchema, {
      body: { enabled },
    }),
  connection: () =>
    apiRequest(
      "GET",
      "/pi/whatsapp",
      schema.WhatsAppConnectionSchema.nullable(),
    ),
  saveConnection: (input) =>
    apiRequest("PUT", "/pi/whatsapp", schema.WhatsAppConnectionSchema, {
      body: input,
    }),
  setConnectionStatus: (status) =>
    apiRequest("PUT", "/pi/whatsapp/status", schema.WhatsAppConnectionSchema, {
      body: { status },
    }),
  events: (filters) =>
    apiRequest(
      "GET",
      "/pi/whatsapp/events",
      pageSchema(schema.WebhookEventSchema),
      { query: filters },
    ),
  replayEvent: (id) =>
    apiRequest(
      "POST",
      `/pi/whatsapp/events/${id}/replay`,
      schema.WebhookEventSchema,
    ),
  sources: () =>
    apiRequest(
      "GET",
      "/pi/knowledge/sources",
      z.array(schema.KnowledgeSourceSchema),
    ),
  createSource: (input) =>
    apiRequest("POST", "/pi/knowledge/sources", schema.KnowledgeSourceSchema, {
      body: input,
    }),
  setSourceStatus: (id, status) =>
    apiRequest(
      "PUT",
      `/pi/knowledge/sources/${id}/status`,
      schema.KnowledgeSourceSchema,
      { body: { status } },
    ),
  documents: ({ sourceId, ...params }) =>
    apiRequest(
      "GET",
      "/pi/knowledge/documents",
      z.array(schema.KnowledgeDocumentSchema),
      { query: { ...params, source_id: sourceId } },
    ),
  document: (id) =>
    apiRequest(
      "GET",
      `/pi/knowledge/documents/${id}`,
      schema.KnowledgeDocumentSchema,
    ),
  addDocument: (input) =>
    apiRequest(
      "POST",
      "/pi/knowledge/documents",
      schema.KnowledgeDocumentSchema,
      { body: input },
    ),
  retryDocument: (id) =>
    apiRequest(
      "POST",
      `/pi/knowledge/documents/${id}/retry`,
      schema.KnowledgeDocumentSchema,
    ),
  analytics: (range) =>
    apiRequest("GET", "/pi/analytics", schema.PiAnalyticsSchema, {
      query: { range },
    }),
  settings: () => apiRequest("GET", "/pi/settings", schema.PiSettingsSchema),
  updateSettings: (section, value) =>
    apiRequest("PATCH", `/pi/settings/${section}`, schema.PiSettingsSchema, {
      body: { value },
    }),
};
