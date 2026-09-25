import { ApiError, DemoError, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { rng } from "@/demo/random";
import { demoPi } from "./demo-data";
import { piLive } from "./live";
import type {
  Agent,
  AgentKey,
  AgentVersion,
  AnalyticsRange,
  Conversation,
  ConversationContext,
  Handoff,
  HandoffReason,
  HandoffStatus,
  KnowledgeDocument,
  KnowledgeSource,
  Message,
  PiAnalytics,
  PiOverview,
  PiSettings,
  ToolDefinition,
  WebhookEvent,
  WhatsAppConnection,
} from "./types";

export type ConversationFilters = {
  search?: string;
  status?: string;
  mode?: string;
  assignment?: "mine" | "unassigned" | "";
  unread?: boolean;
  page?: number;
};

export type AgentTestResult = {
  simulated: boolean;
  intent: string;
  confidence: number;
  route: AgentKey[];
  tools: string[];
  note: string;
};

export interface PiService {
  overview(): Promise<PiOverview>;
  conversations(filters: ConversationFilters): Promise<Page<Conversation>>;
  context(id: string): Promise<ConversationContext>;
  /** Permanently removes one remembered fact (privacy); the audit log records the action. */
  deleteMemory(conversationId: string, memoryId: string): Promise<void>;
  messages(id: string): Promise<Message[]>;
  sendMessage(id: string, body: string): Promise<Message>;
  takeover(id: string): Promise<Conversation>;
  returnToAi(id: string): Promise<Conversation>;
  closeConversation(id: string): Promise<Conversation>;
  markRead(id: string): Promise<void>;
  handoffs(status?: string): Promise<Handoff[]>;
  createHandoff(
    conversationId: string,
    reason: HandoffReason,
    summary: string,
  ): Promise<Handoff>;
  updateHandoff(
    id: string,
    action: "assign" | "start" | "resolve" | "close" | "reopen",
    payload?: { assignee?: string; note?: string },
  ): Promise<Handoff>;
  agents(): Promise<Agent[]>;
  agent(id: string): Promise<Agent>;
  versions(agentId: string): Promise<AgentVersion[]>;
  publishVersion(
    agentId: string,
    input: Pick<
      AgentVersion,
      "instructions" | "model_alias" | "temperature" | "note"
    >,
  ): Promise<AgentVersion>;
  rollback(agentId: string, versionId: string): Promise<AgentVersion>;
  setAgentEnabled(agentId: string, enabled: boolean): Promise<Agent>;
  setAgentTool(agentId: string, tool: string, enabled: boolean): Promise<Agent>;
  testAgent(message: string): Promise<AgentTestResult>;
  tools(): Promise<ToolDefinition[]>;
  setToolEnabled(key: string, enabled: boolean): Promise<ToolDefinition>;
  connection(): Promise<WhatsAppConnection | null>;
  saveConnection(input: {
    phone_number_id: string;
    display_phone_number: string;
    business_account_id: string;
    display_name: string;
    access_token?: string;
  }): Promise<WhatsAppConnection>;
  setConnectionStatus(
    status: "active" | "disabled",
  ): Promise<WhatsAppConnection>;
  events(filters: {
    status?: string;
    kind?: string;
    page?: number;
  }): Promise<Page<WebhookEvent>>;
  replayEvent(id: string): Promise<WebhookEvent>;
  sources(): Promise<KnowledgeSource[]>;
  createSource(input: {
    name: string;
    kind: KnowledgeSource["kind"];
    description: string;
  }): Promise<KnowledgeSource>;
  setSourceStatus(
    id: string,
    status: KnowledgeSource["status"],
  ): Promise<KnowledgeSource>;
  documents(filters: {
    sourceId?: string;
    status?: string;
    search?: string;
  }): Promise<KnowledgeDocument[]>;
  document(id: string): Promise<KnowledgeDocument>;
  addDocument(input: {
    source_id: string;
    title: string;
    body: string;
    mime_type: string;
  }): Promise<KnowledgeDocument>;
  retryDocument(id: string): Promise<KnowledgeDocument>;
  analytics(range: AnalyticsRange): Promise<PiAnalytics>;
  settings(): Promise<PiSettings>;
  updateSettings<K extends keyof PiSettings>(
    section: K,
    value: PiSettings[K],
  ): Promise<PiSettings>;
}

/* Live: every method calls the PI API (see ./live.ts). States that need a connected
   WhatsApp number or AI providers (delivery, automated replies) come from the backend as
   explicit statuses and error codes; nothing is simulated in live mode. */
const live = piLive;

/* Demo --------------------------------------------------------------------------------- */

const OPERATOR = "Amina Rahman";

function conv(id: string) {
  const c = demoPi().conversations.find((x) => x.id === id);
  if (!c) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return c;
}

function systemMessage(conversationId: string, body: string) {
  const message: Message = {
    id: demoId("msg"),
    conversation_id: conversationId,
    direction: "outbound",
    sender_type: "system",
    message_type: "text",
    body,
    media: null,
    status: "processed",
    error_code: null,
    agent_key: null,
    sent_by_label: null,
    created_at: new Date().toISOString(),
    tool_events: [],
    confirmation: null,
  };
  (demoPi().messages[conversationId] ??= []).push(message);
}

function handoff(id: string) {
  const h = demoPi().handoffs.find((x) => x.id === id);
  if (!h) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return h;
}

const HANDOFF_FLOW: Record<
  HandoffStatus,
  ("assign" | "start" | "resolve" | "close" | "reopen")[]
> = {
  open: ["assign", "start", "close"],
  assigned: ["assign", "start", "close"],
  in_progress: ["assign", "resolve"],
  resolved: ["close", "reopen"],
  closed: ["reopen"],
};
export { HANDOFF_FLOW };

function dayKeys(days: number) {
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(Date.now() - (days - 1 - i) * 86400000);
    return d.toISOString().slice(0, 10);
  });
}

const demo: PiService = {
  async overview() {
    await demoDelay(220);
    const pi = demoPi();
    const r = rng(pi.conversations.length + 11);
    const open = pi.conversations.filter((c) => c.status === "open");
    const scale = pi.conversations.length > 10 ? 1 : 0.04;
    const volume = dayKeys(14).map((day, i) => {
      const inbound = Math.round(
        (160 + Math.sin(i / 2) * 30 + r.int(-20, 25) + i * 3) * scale,
      );
      const human = Math.round(inbound * (0.06 + r.next() * 0.04));
      return {
        day: day.slice(5),
        inbound,
        ai: Math.max(0, inbound - human),
        human,
      };
    });
    return {
      period_days: 7,
      conversations_active: open.length,
      conversations_total: Math.round(
        pi.conversations.length * (scale === 1 ? 14 : 1),
      ),
      unresolved: open.filter(
        (c) => c.last_sender === "customer" || c.handoff_status,
      ).length,
      open_handoffs: pi.handoffs.filter((h) =>
        ["open", "assigned", "in_progress"].includes(h.status),
      ).length,
      messages_in: volume.slice(-7).reduce((s, v) => s + v.inbound, 0),
      messages_out: volume.slice(-7).reduce((s, v) => s + v.ai + v.human, 0),
      ai_responses: volume.slice(-7).reduce((s, v) => s + v.ai, 0),
      automation_rate: 0.91,
      avg_response_ms: 1840,
      p95_response_ms: 4120,
      fallback_count: scale === 1 ? 23 : 0,
      tool_calls: pi.tools.reduce((s, t) => s + t.calls_7d, 0),
      tool_failures: pi.tools.reduce((s, t) => s + t.failures_7d, 0),
      whatsapp: pi.connection
        ? {
            status: pi.connection.status,
            display_phone_number: pi.connection.display_phone_number,
            last_inbound_at: pi.connection.last_inbound_at,
          }
        : null,
      knowledge: {
        sources: pi.sources.filter((s) => s.status === "active").length,
        documents_ready: pi.documents.filter((d) => d.status === "ready")
          .length,
        documents_failed: pi.documents.filter((d) => d.status === "failed")
          .length,
        passages: pi.documents.reduce((s, d) => s + d.chunk_count, 0),
      },
      providers: pi.settings.provider_config.order.map((name, i) => ({
        name,
        role: (["primary", "fallback", "secondary_fallback"] as const)[i]!,
        configured: true,
        status: name === "openai" && scale === 1 ? "degraded" : "healthy",
        success_rate: name === "openai" ? 0.974 : 0.996,
        p50_ms: [1450, 1720, 690][i]!,
        requests_24h: Math.round([1880, 41, 3][i]! * scale),
      })),
      volume,
      agent_activity: pi.agents.map((a) => ({ agent: a.key, runs: a.runs_7d })),
      auto_reply_enabled: pi.settings.auto_reply_enabled,
    };
  },
  async conversations({ search, status, mode, assignment, unread, page = 1 }) {
    await demoDelay();
    const rows = demoPi().conversations.filter(
      (c) =>
        (!status || c.status === status) &&
        (!mode || c.mode === mode) &&
        (!unread || c.unread_count > 0) &&
        (assignment !== "mine" || c.assigned_label === OPERATOR) &&
        (assignment !== "unassigned" || !c.assigned_label) &&
        (!search ||
          matches(c.customer_name, search) ||
          matches(c.last_message_preview, search) ||
          matches(c.customer_phone, search)),
    );
    return paginate(
      rows.map((c) => ({ ...c })),
      page,
      50,
    );
  },
  async deleteMemory(conversationId, memoryId) {
    await demoDelay(120);
    const pi = demoPi();
    const rows = pi.memory[conversationId] ?? [];
    if (!rows.some((m) => m.id === memoryId))
      throw new ApiError(404, "RESOURCE_NOT_FOUND");
    pi.memory[conversationId] = rows.filter((m) => m.id !== memoryId);
  },
  async context(id) {
    await demoDelay(150);
    const pi = demoPi();
    const c = conv(id);
    const business = demoBusiness();
    const orders = business.orders
      .filter((o) => o.customer_id === c.customer_id)
      .slice(0, 4);
    const quotes = business.quotes
      .filter(
        (q) =>
          q.customer_id === c.customer_id &&
          ["draft", "pending_approval", "approved", "sent"].includes(q.status),
      )
      .slice(0, 3);
    const open = business.invoices.filter(
      (i) =>
        i.customer_id === c.customer_id &&
        ["issued", "partially_paid"].includes(i.status),
    );
    const balance = open.reduce((s, i) => s + Number(i.balance_due), 0);
    return {
      conversation: { ...c },
      memory: pi.memory[id] ?? [],
      knowledge_used: pi.knowledgeUsed[id] ?? [],
      recent_orders: orders.map((o) => ({
        id: o.id,
        number: o.number,
        status: o.status,
        total: o.total,
        created_at: o.created_at,
      })),
      open_quotes: quotes.map((q) => ({
        id: q.id,
        number: q.number,
        status: q.status,
        total: q.total,
      })),
      balance: balance.toFixed(2),
      currency: business.settings.default_currency,
      runs: [...(pi.runs[id] ?? [])].reverse(),
    };
  },
  async messages(id) {
    await demoDelay(120);
    conv(id);
    return [...(demoPi().messages[id] ?? [])];
  },
  async sendMessage(id, body) {
    await demoDelay(300);
    const c = conv(id);
    if (c.mode !== "human")
      throw new DemoError(
        "Take over the conversation before replying. PI is handling it.",
      );
    if (!body.trim()) throw new DemoError("Write a message first.");
    if (body.length > 4096)
      throw new DemoError("WhatsApp messages are limited to 4,096 characters.");
    const message: Message = {
      id: demoId("msg"),
      conversation_id: id,
      direction: "outbound",
      sender_type: "human",
      message_type: "text",
      body,
      media: null,
      status: "sent",
      error_code: null,
      agent_key: null,
      sent_by_label: OPERATOR,
      created_at: new Date().toISOString(),
      tool_events: [],
      confirmation: null,
    };
    demoPi().messages[id]!.push(message);
    Object.assign(c, {
      last_message_at: message.created_at,
      last_message_preview: body.slice(0, 120),
      last_sender: "human",
    });
    setTimeout(() => (message.status = "delivered"), 1200);
    return message;
  },
  async takeover(id) {
    await demoDelay(200);
    const c = conv(id);
    c.mode = "human";
    c.assigned_label = OPERATOR;
    systemMessage(
      id,
      `${OPERATOR} took over the conversation. Automatic replies are paused.`,
    );
    const h = c.handoff_id
      ? demoPi().handoffs.find((x) => x.id === c.handoff_id)
      : null;
    if (h && ["open", "assigned"].includes(h.status))
      Object.assign(h, {
        status: "in_progress",
        assigned_label: OPERATOR,
        assigned_at: h.assigned_at ?? new Date().toISOString(),
      });
    if (h) c.handoff_status = h.status;
    return { ...c };
  },
  async returnToAi(id) {
    await demoDelay(200);
    const c = conv(id);
    c.mode = "ai";
    systemMessage(
      id,
      `${OPERATOR} returned the conversation to PI. Automatic replies resumed.`,
    );
    return { ...c };
  },
  async closeConversation(id) {
    await demoDelay(200);
    const c = conv(id);
    c.status = "closed";
    return { ...c };
  },
  async markRead(id) {
    conv(id).unread_count = 0;
  },
  async handoffs(status) {
    await demoDelay();
    return demoPi()
      .handoffs.filter((h) => !status || h.status === status)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((h) => ({ ...h }));
  },
  async createHandoff(conversationId, reason, summary) {
    await demoDelay(250);
    const c = conv(conversationId);
    if (
      c.handoff_id &&
      ["open", "assigned", "in_progress"].includes(c.handoff_status ?? "")
    )
      return handoff(c.handoff_id);
    const h: Handoff = {
      id: demoId("ho"),
      conversation_id: c.id,
      customer_id: c.customer_id,
      customer_name: c.customer_name,
      status: "open",
      reason,
      priority: reason === "complaint" ? "high" : "normal",
      summary,
      assigned_label: null,
      created_by_label: OPERATOR,
      created_at: new Date().toISOString(),
      assigned_at: null,
      resolved_at: null,
      resolution_note: "",
    };
    demoPi().handoffs.unshift(h);
    Object.assign(c, { handoff_id: h.id, handoff_status: "open" });
    return h;
  },
  async updateHandoff(id, action, payload = {}) {
    await demoDelay(250);
    const h = handoff(id);
    if (!HANDOFF_FLOW[h.status].includes(action))
      throw new ApiError(
        422,
        "INVALID_TRANSITION",
        undefined,
        `A handoff cannot ${action} from ${h.status.replace("_", " ")}`,
      );
    const now = new Date().toISOString();
    if (action === "assign")
      Object.assign(h, {
        status: h.status === "in_progress" ? "in_progress" : "assigned",
        assigned_label: payload.assignee ?? OPERATOR,
        assigned_at: now,
      });
    if (action === "start")
      Object.assign(h, {
        status: "in_progress",
        assigned_label: h.assigned_label ?? OPERATOR,
        assigned_at: h.assigned_at ?? now,
      });
    if (action === "resolve")
      Object.assign(h, {
        status: "resolved",
        resolved_at: now,
        resolution_note: payload.note ?? "",
      });
    if (action === "close") Object.assign(h, { status: "closed" });
    if (action === "reopen")
      Object.assign(h, { status: "open", resolved_at: null });
    const c = demoPi().conversations.find((x) => x.id === h.conversation_id);
    if (c) {
      c.handoff_status = h.status;
      if (action === "start") {
        c.mode = "human";
        c.assigned_label = h.assigned_label;
      }
    }
    return { ...h };
  },
  async agents() {
    await demoDelay();
    return demoPi().agents.map((a) => ({ ...a }));
  },
  async agent(id) {
    await demoDelay(100);
    const a = demoPi().agents.find((x) => x.id === id || x.key === id);
    if (!a) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    return { ...a };
  },
  async versions(agentId) {
    await demoDelay(100);
    const agent = await demo.agent(agentId);
    return demoPi()
      .versions.filter((v) => v.agent_id === agent.id)
      .sort((a, b) => b.version - a.version);
  },
  async publishVersion(agentId, input) {
    await demoDelay(350);
    const pi = demoPi();
    const agent = pi.agents.find((a) => a.id === agentId)!;
    for (const v of pi.versions)
      if (v.agent_id === agentId && v.status === "active")
        v.status = "archived";
    const next =
      Math.max(
        ...pi.versions
          .filter((v) => v.agent_id === agentId)
          .map((v) => v.version),
      ) + 1;
    const version: AgentVersion = {
      id: demoId("ver"),
      agent_id: agentId,
      version: next,
      status: "active",
      created_by_label: OPERATOR,
      created_at: new Date().toISOString(),
      ...input,
    };
    pi.versions.push(version);
    Object.assign(agent, {
      current_version: next,
      model_alias: input.model_alias,
      temperature: input.temperature,
    });
    return version;
  },
  async rollback(agentId, versionId) {
    await demoDelay(300);
    const source = demoPi().versions.find(
      (v) => v.id === versionId && v.agent_id === agentId,
    );
    if (!source) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    return demo.publishVersion(agentId, {
      instructions: source.instructions,
      model_alias: source.model_alias,
      temperature: source.temperature,
      note: `Rollback to v${source.version}`,
    });
  },
  async setAgentEnabled(agentId, enabled) {
    await demoDelay(200);
    const agent = demoPi().agents.find((a) => a.id === agentId)!;
    if (agent.key === "router" && !enabled)
      throw new DemoError(
        "The router can't be disabled; turn off auto-replies in PI settings instead.",
      );
    agent.enabled = enabled;
    return { ...agent };
  },
  async setAgentTool(agentId, tool, enabled) {
    await demoDelay(200);
    const agent = demoPi().agents.find((a) => a.id === agentId)!;
    agent.tools = enabled
      ? [...new Set([...agent.tools, tool])]
      : agent.tools.filter((t) => t !== tool);
    return { ...agent };
  },
  async testAgent(message) {
    await demoDelay(500);
    const text = message.toLowerCase();
    const rules: [RegExp, string, AgentKey, string[]][] = [
      [
        /human|person|agent|manager|insaan|banda/,
        "human_request",
        "handoff",
        ["create_handoff"],
      ],
      [
        /refund|broken|cracked|complain|damaged|kharab/,
        "complaint",
        "handoff",
        ["get_customer_orders", "create_handoff"],
      ],
      [
        /stock|available|in stock|hai\?|mil jayega/,
        "product_availability",
        "sales_order",
        ["search_products", "check_inventory"],
      ],
      [
        /order.*(where|status)|kahan hai|track/,
        "order_status",
        "support",
        ["get_order"],
      ],
      [
        /price|kitne ka|cost|rate/,
        "pricing",
        "sales_order",
        ["search_products", "get_product"],
      ],
      [
        /website|app|design|seo/,
        "requirement",
        "requirement",
        ["search_products", "create_quote_draft"],
      ],
      [
        /ignore|system prompt|instructions|admin mode/,
        "unknown",
        "support",
        [],
      ],
      [/hi|hello|salam|assalam/, "greeting", "support", []],
    ];
    const hit = rules.find(([re]) => re.test(text));
    const [, intent, agent, tools] = hit ?? [
      null,
      "support",
      "support" as AgentKey,
      ["search_knowledge_base"],
    ];
    return {
      simulated: true,
      intent,
      confidence: hit ? 0.86 : 0.48,
      route: ["router", "customer_memory", agent],
      tools,
      note: hit
        ? "Keyword simulation on sample data — no AI provider was called."
        : "Low confidence: PI would ask a clarifying question, then hand off if it stays unclear.",
    };
  },
  async tools() {
    await demoDelay();
    return demoPi().tools.map((t) => ({ ...t }));
  },
  async setToolEnabled(key, enabled) {
    await demoDelay(200);
    const tool = demoPi().tools.find((t) => t.key === key);
    if (!tool) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (key === "send_whatsapp_message" && !enabled)
      throw new DemoError(
        "PI can't reply without the send tool. Turn off auto-replies instead.",
      );
    tool.enabled = enabled;
    demoPi().settings.tool_permissions[key] = enabled;
    return { ...tool };
  },
  async connection() {
    await demoDelay(120);
    const c = demoPi().connection;
    return c ? { ...c } : null;
  },
  async saveConnection(input) {
    await demoDelay(500);
    if (!/^[0-9]{5,32}$/.test(input.phone_number_id))
      throw new ApiError(
        422,
        "VALIDATION_ERROR",
        undefined,
        "Phone number ID must be digits from the WhatsApp Manager",
      );
    const pi = demoPi();
    const existing = pi.connection;
    pi.connection = {
      id: existing?.id ?? demoId("wa"),
      provider: "meta_cloud",
      phone_number_id: input.phone_number_id,
      display_phone_number: input.display_phone_number,
      business_account_id: input.business_account_id,
      display_name: input.display_name,
      status: existing?.status ?? "pending",
      has_access_token:
        Boolean(input.access_token) || Boolean(existing?.has_access_token),
      webhook_url: "https://app.example.com/api/v1/pi/webhooks/whatsapp",
      webhook_verified: existing?.webhook_verified ?? false,
      verified_at: existing?.verified_at ?? null,
      last_inbound_at: existing?.last_inbound_at ?? null,
      last_outbound_at: existing?.last_outbound_at ?? null,
      last_error_code: null,
      last_error_at: null,
      messages_24h: existing?.messages_24h ?? {
        inbound: 0,
        outbound: 0,
        failed: 0,
      },
    };
    return { ...pi.connection };
  },
  async setConnectionStatus(status) {
    await demoDelay(300);
    const c = demoPi().connection;
    if (!c) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (status === "active" && !c.has_access_token)
      throw new DemoError("Add an access token before activating the number.");
    c.status = status;
    return { ...c };
  },
  async events({ status, kind, page = 1 }) {
    await demoDelay();
    return paginate(
      demoPi().events.filter(
        (e) => (!status || e.status === status) && (!kind || e.kind === kind),
      ),
      page,
      25,
    );
  },
  async replayEvent(id) {
    await demoDelay(400);
    const e = demoPi().events.find((x) => x.id === id);
    if (!e) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (e.status !== "failed")
      throw new DemoError(
        "Only failed events can be replayed. Processed events are deduplicated.",
      );
    Object.assign(e, {
      status: "processed",
      attempts: e.attempts + 1,
      error_code: null,
      processed_at: new Date().toISOString(),
    });
    return { ...e };
  },
  async sources() {
    await demoDelay();
    return demoPi().sources.map((s) => ({ ...s }));
  },
  async createSource(input) {
    await demoDelay(250);
    const source: KnowledgeSource = {
      id: demoId("src"),
      status: "active",
      documents: 0,
      ready: 0,
      failed: 0,
      updated_at: new Date().toISOString(),
      ...input,
    };
    demoPi().sources.push(source);
    return source;
  },
  async setSourceStatus(id, status) {
    await demoDelay(200);
    const s = demoPi().sources.find((x) => x.id === id);
    if (!s) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    s.status = status;
    return { ...s };
  },
  async documents({ sourceId, status, search }) {
    await demoDelay();
    return demoPi()
      .documents.filter(
        (d) =>
          (!sourceId || d.source_id === sourceId) &&
          (!status || d.status === status) &&
          (!search || matches(d.title, search)),
      )
      .map((d) => ({ ...d }));
  },
  async document(id) {
    await demoDelay(100);
    const d = demoPi().documents.find((x) => x.id === id);
    if (!d) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    return { ...d };
  },
  async addDocument(input) {
    await demoDelay(400);
    const pi = demoPi();
    const source = pi.sources.find((s) => s.id === input.source_id);
    if (!source) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (new Blob([input.body]).size > 1024 * 1024)
      throw new DemoError("Documents are limited to 1 MB of text.");
    const doc: KnowledgeDocument = {
      id: demoId("doc"),
      source_id: source.id,
      source_name: source.name,
      title: input.title,
      mime_type: input.mime_type,
      byte_size: new Blob([input.body]).size,
      status: "processing",
      chunk_count: 0,
      error_code: null,
      created_by_label: OPERATOR,
      created_at: new Date().toISOString(),
      processed_at: null,
      body: input.body,
    };
    pi.documents.unshift(doc);
    source.documents += 1;
    setTimeout(() => {
      doc.status = "ready";
      doc.chunk_count = Math.max(1, Math.ceil(input.body.length / 900));
      doc.processed_at = new Date().toISOString();
      source.ready += 1;
    }, 2500);
    return { ...doc };
  },
  async retryDocument(id) {
    await demoDelay(300);
    const d = demoPi().documents.find((x) => x.id === id);
    if (!d) throw new ApiError(404, "RESOURCE_NOT_FOUND");
    if (d.status !== "failed")
      throw new DemoError("Only failed documents can be retried.");
    Object.assign(d, { status: "processing", error_code: null });
    setTimeout(
      () =>
        Object.assign(d, {
          status: "failed",
          error_code: "UNSUPPORTED_ENCODING",
          processed_at: new Date().toISOString(),
        }),
      2500,
    );
    return { ...d };
  },
  async analytics(range) {
    await demoDelay(250);
    const pi = demoPi();
    const scale =
      pi.conversations.length > 10 ? 1 : pi.conversations.length ? 0.05 : 0;
    const r = rng(range * 97 + pi.conversations.length);
    const keys = dayKeys(range);
    const label = (d: string) => d.slice(5);
    const conversations = keys.map((d, i) => {
      const started = Math.round(
        (42 + Math.sin(i / 3) * 8 + r.int(-6, 8)) * scale,
      );
      return {
        day: label(d),
        started,
        resolved: Math.max(0, started - r.int(0, 5)),
      };
    });
    const messages = keys.map((d, i) => {
      const inbound = Math.round(
        (165 + Math.sin(i / 2.5) * 25 + r.int(-18, 22)) * scale,
      );
      const human = Math.round(inbound * (0.05 + r.next() * 0.05));
      return {
        day: label(d),
        inbound,
        outbound_ai: inbound - human,
        outbound_human: human,
      };
    });
    const latency = keys.map((d) => ({
      day: label(d),
      p50: scale ? 1500 + r.int(-200, 300) : 0,
      p95: scale ? 3800 + r.int(-500, 900) : 0,
    }));
    const fallbacks = keys.map((d, i) => ({
      day: label(d),
      count: scale ? (i === Math.floor(range * 0.6) ? 14 : r.int(0, 4)) : 0,
    }));
    const usage = keys.map((d, i) => ({
      day: label(d),
      openai: Math.round(messages[i]!.outbound_ai * 1.9),
      gemini: fallbacks[i]!.count * 2,
      groq: fallbacks[i]!.count > 8 ? 3 : 0,
    }));
    const tokens = keys.map((d, i) => ({
      day: label(d),
      input: usage[i]!.openai * 1300,
      output: usage[i]!.openai * 140,
    }));
    const sum = <T>(rows: T[], f: (x: T) => number) =>
      rows.reduce((s, x) => s + f(x), 0);
    const reasons: HandoffReason[] = [
      "customer_request",
      "complaint",
      "policy",
      "low_confidence",
      "provider_failure",
      "tool_failure",
    ];
    const handoffCounts = [34, 18, 22, 11, 3, 2].map((n) =>
      Math.round(n * scale * (range / 30)),
    );
    return {
      range,
      currency_note:
        "Estimated AI cost uses configured per-token rates; it is not a provider invoice.",
      conversations,
      messages,
      latency,
      runs_by_agent: pi.agents.map((a) => ({
        agent: a.key,
        runs: Math.round(a.runs_7d * (range / 7)),
        failures: Math.round(a.runs_7d * (range / 7) * (1 - a.success_rate)),
      })),
      intents: [
        "product_availability",
        "order_status",
        "support",
        "pricing",
        "order",
        "greeting",
        "complaint",
        "human_request",
        "requirement",
        "unknown",
      ].map((intent, i) => ({
        intent,
        count: Math.round(
          [410, 260, 380, 190, 150, 220, 40, 60, 30, 55][i]! *
            scale *
            (range / 30),
        ),
      })),
      tools: pi.tools
        .filter((t) => t.calls_7d > 0)
        .map((t) => ({
          tool: t.key,
          success: Math.round(t.calls_7d * (range / 7)),
          failed: Math.round(t.failures_7d * (range / 7)),
          denied: t.key === "get_customer_balance" ? Math.round(3 * scale) : 0,
        })),
      handoffs_by_reason: reasons.map((reason, i) => ({
        reason,
        count: handoffCounts[i]!,
      })),
      handoffs_by_day: keys.map((d) => ({
        day: label(d),
        opened: scale ? r.int(0, 5) : 0,
        resolved: scale ? r.int(0, 5) : 0,
      })),
      fallbacks,
      fallback_pairs: scale
        ? [
            {
              from: "openai",
              to: "gemini",
              count: Math.round(38 * (range / 30)),
              top_reason: "rate_limit",
            },
            {
              from: "openai",
              to: "gemini",
              count: Math.round(6 * (range / 30)),
              top_reason: "timeout",
            },
            {
              from: "gemini",
              to: "groq",
              count: 3,
              top_reason: "provider_unavailable",
            },
            {
              from: "groq",
              to: "handoff",
              count: 1,
              top_reason: "all_providers_failed",
            },
          ]
        : [],
      provider_usage: usage,
      tokens,
      cost_estimate: scale
        ? tokens.map((t) => ({
            day: t.day,
            amount:
              Math.round((t.input * 0.0000025 + t.output * 0.00001) * 100) /
              100,
          }))
        : null,
      totals: {
        conversations: sum(conversations, (x) => x.started),
        messages: sum(
          messages,
          (x) => x.inbound + x.outbound_ai + x.outbound_human,
        ),
        ai_responses: sum(messages, (x) => x.outbound_ai),
        runs: sum(messages, (x) => x.inbound),
        tool_calls: pi.tools.reduce((s, t) => s + t.calls_7d, 0) * (range / 7),
        handoffs: handoffCounts.reduce((a, b) => a + b, 0),
        fallbacks: sum(fallbacks, (x) => x.count),
        failure_rate: scale ? 0.012 : 0,
        input_tokens: sum(tokens, (x) => x.input),
        output_tokens: sum(tokens, (x) => x.output),
        cost_estimate_usd: scale
          ? Math.round(
              sum(tokens, (t) => t.input * 0.0000025 + t.output * 0.00001) *
                100,
            ) / 100
          : null,
      },
    };
  },
  async settings() {
    await demoDelay(120);
    return structuredClone(demoPi().settings);
  },
  async updateSettings(section, value) {
    await demoDelay(350);
    const settings = demoPi().settings;
    if (section === "provider_config") {
      const order = (value as PiSettings["provider_config"]).order;
      if (new Set(order).size !== order.length || order.length === 0)
        throw new DemoError("Choose each provider once, in fallback order.");
    }
    settings[section] = structuredClone(value);
    if (section === "tool_permissions") {
      // One source of truth: the tool catalog reflects workspace tool permissions.
      const permissions = value as PiSettings["tool_permissions"];
      for (const tool of demoPi().tools)
        if (tool.key in permissions) tool.enabled = permissions[tool.key]!;
    }
    return structuredClone(settings);
  },
};

export const piService = select<PiService>({ demo, live });
