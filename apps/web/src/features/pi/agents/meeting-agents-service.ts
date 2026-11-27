import { z } from "zod";
import { ApiError, apiRequest } from "@/services/api-client";

/**
 * Meeting agents (how pi listens and what it looks for in a meeting) and the chats that ask a
 * meeting questions. Live data only.
 * Backend contract: /pi/meeting-agents and /pi/meeting-intel/{id}/chats.
 */

export const AGENT_ICONS = [
  "sparkles",
  "briefcase",
  "handshake",
  "presentation",
  "graduation-cap",
  "flame",
  "headphones",
  "search",
  "heart",
  "shield",
  "rocket",
  "mic",
  "target",
  "lightbulb",
] as const;
export type AgentIcon = (typeof AGENT_ICONS)[number];

export const AGENT_COLORS = [
  "green",
  "violet",
  "blue",
  "amber",
  "rose",
  "teal",
  "indigo",
  "slate",
] as const;
export type AgentColor = (typeof AGENT_COLORS)[number];

export const DEFAULT_AGENT_KEY = "pi";

/** Limits the server enforces; the form mirrors them so a person sees them before sending. */
export const AGENT_LIMITS = {
  nameMin: 2,
  nameMax: 40,
  taglineMax: 80,
  instructionsMin: 20,
  instructionsMax: 1500,
  questionMin: 3,
  questionMax: 300,
} as const;

const strings = z.array(z.string()).catch([]);

export const agentSchema = z.object({
  key: z.string(),
  kind: z.enum(["builtin", "custom"]).catch("builtin"),
  name: z.string().catch("Agent"),
  tagline: z.string().catch(""),
  icon: z.string().catch("sparkles"),
  color: z.string().catch("green"),
  focus: strings,
  sample_questions: strings,
  instructions: z.string().catch(""),
  is_default: z.boolean().catch(false),
  can_edit: z.boolean().catch(false),
  created_at: z.string().nullable().catch(null),
});
export type Agent = z.infer<typeof agentSchema>;

/** Shown when a chat or meeting points at an agent that is no longer listed (archived). */
export const PI_AGENT: Agent = {
  key: DEFAULT_AGENT_KEY,
  kind: "builtin",
  name: "pi",
  tagline: "pi's own personality",
  icon: "sparkles",
  color: "green",
  focus: [],
  sample_questions: [
    "What did they say about the budget?",
    "What did they ask for?",
    "What are the next steps?",
  ],
  instructions: "",
  is_default: true,
  can_edit: false,
  created_at: null,
};

export const ARCHIVED_AGENT: Agent = {
  ...PI_AGENT,
  key: "archived",
  name: "Archived agent",
  tagline: "",
  color: "slate",
  is_default: false,
};

export type AgentInput = {
  name: string;
  tagline?: string;
  icon: string;
  color: string;
  instructions: string;
};

const checkSchema = z.object({
  ok: z.boolean().catch(true),
  reasons: strings,
});
export type AgentCheck = z.infer<typeof checkSchema>;

export const sourceSchema = z.object({
  ordinal: z.number(),
  speaker: z.string().catch(""),
  role: z.string().catch("unknown"),
  start_ms: z.number().catch(0),
  text: z.string().catch(""),
});
export type ChatSource = z.infer<typeof sourceSchema>;

export const chatSchema = z.object({
  id: z.string(),
  title: z.string().catch(""),
  agent_key: z.string().nullable().catch(null),
  created_at: z.string().nullable().catch(null),
  updated_at: z.string().nullable().catch(null),
  message_count: z.number().catch(0),
  last_text: z.string().nullable().catch(""),
});
export type Chat = z.infer<typeof chatSchema>;

export const messageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant"]).catch("assistant"),
  text: z.string().catch(""),
  found: z.boolean().catch(true),
  partial: z.boolean().catch(false),
  sources: z.array(sourceSchema).catch([]),
  created_at: z.string().nullable().catch(null),
});
export type ChatMessage = z.infer<typeof messageSchema>;

const chatDetailSchema = z.object({
  chat: chatSchema,
  messages: z.array(messageSchema).catch([]),
});
export type ChatDetail = z.infer<typeof chatDetailSchema>;

const AGENTS = "/pi/meeting-agents";
const chats = (meetingId: string) => `/pi/meeting-intel/${meetingId}/chats`;

export const meetingAgentsService = {
  list: () =>
    apiRequest(
      "GET",
      AGENTS,
      z.object({ agents: z.array(agentSchema).catch([]) }),
    ),
  create: (input: AgentInput) =>
    apiRequest("POST", AGENTS, agentSchema, { body: input }),
  // Live check while typing: short human sentences, never a block on its own.
  check: (instructions: string) =>
    apiRequest("POST", `${AGENTS}/check`, checkSchema, {
      body: { instructions },
    }),
  update: (key: string, input: Partial<AgentInput>) =>
    apiRequest("PATCH", `${AGENTS}/${key}`, agentSchema, { body: input }),
  // Archived, not erased: old chats keep working.
  archive: (key: string) =>
    apiRequest<void>("DELETE", `${AGENTS}/${key}`, null),
  setMeetingAgent: (meetingId: string, agentKey: string) =>
    apiRequest(
      "PUT",
      `/pi/meeting-intel/${meetingId}/agent`,
      z.object({ agent_key: z.string().nullable().catch(null) }),
      { body: { agent_key: agentKey } },
    ),

  listChats: (meetingId: string) =>
    apiRequest(
      "GET",
      chats(meetingId),
      z.object({ chats: z.array(chatSchema).catch([]) }),
    ),
  createChat: (meetingId: string, agentKey?: string) =>
    apiRequest("POST", chats(meetingId), chatSchema, {
      body: agentKey ? { agent_key: agentKey } : {},
    }),
  getChat: (meetingId: string, chatId: string) =>
    apiRequest("GET", `${chats(meetingId)}/${chatId}`, chatDetailSchema),
  updateChat: (
    meetingId: string,
    chatId: string,
    patch: { title?: string; agent_key?: string },
  ) =>
    apiRequest("PATCH", `${chats(meetingId)}/${chatId}`, chatSchema, {
      body: patch,
    }),
  deleteChat: (meetingId: string, chatId: string) =>
    apiRequest<void>("DELETE", `${chats(meetingId)}/${chatId}`, null),
  // Can take several seconds: the answer is written from the transcript.
  sendMessage: (meetingId: string, chatId: string, question: string) =>
    apiRequest(
      "POST",
      `${chats(meetingId)}/${chatId}/messages`,
      z.object({ user: messageSchema, assistant: messageSchema }),
      { body: { question }, timeoutMs: 60_000 },
    ),
};

/** The reasons an agent's instructions were refused (422), as short sentences. */
export function refusalReasons(error: unknown): string[] | null {
  if (
    !(error instanceof ApiError) ||
    error.code !== "AGENT_INSTRUCTIONS_REFUSED"
  )
    return null;
  const fromFields = Object.values(error.fields).filter(Boolean);
  if (fromFields.length > 0) return fromFields;
  return [
    error.serverMessage ||
      "Some of these instructions break a rule that always applies.",
  ];
}

export const ROLE_LABELS: Record<string, string> = {
  customer: "Customer",
  staff: "Team",
  other: "Other",
  unknown: "Speaker",
};
