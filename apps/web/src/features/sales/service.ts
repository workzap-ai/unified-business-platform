import { z } from "zod";
import { apiRequest, ApiError, pageSchema, type Page } from "@/services/api-client";
import { demoDelay, select } from "@/lib/data-mode";
import { demoBusiness } from "@/demo/business";
import { demoId, matches, paginate } from "@/demo/store";
import { toCents, centsToString } from "@/lib/format";
import { leadSchema, pipelineStageSchema, type Lead, type LeadStage, type ListParams, type PipelineStage } from "@/features/business/types";

export const LEAD_TRANSITIONS: Record<LeadStage, LeadStage[]> = {
  new: ["qualified", "lost"],
  qualified: ["proposal", "lost", "new"],
  proposal: ["won", "lost", "qualified"],
  won: [],
  lost: ["new"],
};

export type LeadInput = {
  title: string;
  customer_id?: string | null;
  estimated_value?: string | null;
  source?: "manual" | "website" | "referral";
  notes?: string;
};

export interface SalesService {
  pipeline(): Promise<PipelineStage[]>;
  leads(params: ListParams & { stage?: string }): Promise<Page<Lead>>;
  lead(id: string): Promise<Lead>;
  create(input: LeadInput): Promise<Lead>;
  update(id: string, input: Partial<LeadInput>): Promise<Lead>;
  move(id: string, stage: LeadStage): Promise<Lead>;
}

// Mutation responses (LeadView) omit list-only fields; fill them so callers get one shape.
const mutationLead = leadSchema.extend({
  customer_name: z.string().nullable().catch(null),
  next_stages: z.array(z.string()).catch([]),
});

const live: SalesService = {
  pipeline: () => apiRequest("GET", "/sales/pipeline", z.array(pipelineStageSchema)),
  leads: ({ page = 1, pageSize = 25, search, stage }) =>
    apiRequest("GET", "/sales/leads", pageSchema(leadSchema), { query: { page, page_size: pageSize, search, stage } }),
  lead: (id) => apiRequest("GET", `/sales/leads/${id}`, leadSchema),
  create: (input) => apiRequest("POST", "/sales/leads", mutationLead, { body: input }),
  update: (id, input) => apiRequest("PATCH", `/sales/leads/${id}`, mutationLead, { body: input }),
  move: (id, stage) => apiRequest("PUT", `/sales/leads/${id}/stage`, mutationLead, { body: { stage } }),
};

function find(id: string) {
  const lead = demoBusiness().leads.find((l) => l.id === id);
  if (!lead) throw new ApiError(404, "RESOURCE_NOT_FOUND");
  return lead;
}

const demo: SalesService = {
  async pipeline() {
    await demoDelay();
    const leads = demoBusiness().leads;
    return (["new", "qualified", "proposal", "won", "lost"] as const).map((stage) => {
      const rows = leads.filter((l) => l.stage === stage);
      return { stage, count: rows.length, value: centsToString(rows.reduce((s, l) => s + toCents(l.estimated_value), BigInt(0))) };
    });
  },
  async leads({ page = 1, pageSize = 50, search, stage }) {
    await demoDelay();
    const rows = demoBusiness()
      .leads.filter((l) => (!stage || l.stage === stage) && (!search || matches(l.title, search) || matches(l.customer_name, search)))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    return paginate(rows, page, pageSize);
  },
  async lead(id) {
    await demoDelay();
    return { ...find(id) };
  },
  async create(input) {
    await demoDelay(300);
    const business = demoBusiness();
    const customer = business.customers.find((c) => c.id === input.customer_id);
    const now = new Date().toISOString();
    const lead: Lead = {
      id: demoId("lead"), customer_id: customer?.id ?? null, title: input.title, stage: "new", source: input.source ?? "manual",
      estimated_value: input.estimated_value || null, currency: business.settings.default_currency, requirements: {}, missing_information: [],
      notes: input.notes ?? "", conversation_id: null, closed_at: null, created_at: now, updated_at: now,
      customer_name: customer?.name ?? null, next_stages: LEAD_TRANSITIONS.new,
    };
    business.leads.unshift(lead);
    return lead;
  },
  async update(id, input) {
    await demoDelay(250);
    const lead = find(id);
    Object.assign(lead, { ...input, updated_at: new Date().toISOString() });
    if (input.customer_id !== undefined) lead.customer_name = demoBusiness().customers.find((c) => c.id === input.customer_id)?.name ?? null;
    return { ...lead };
  },
  async move(id, stage) {
    await demoDelay(200);
    const lead = find(id);
    if (!LEAD_TRANSITIONS[lead.stage].includes(stage))
      throw new ApiError(422, "INVALID_TRANSITION", undefined, `A lead cannot move from ${lead.stage} to ${stage}`);
    lead.stage = stage;
    lead.next_stages = LEAD_TRANSITIONS[stage];
    lead.closed_at = stage === "won" || stage === "lost" ? new Date().toISOString() : null;
    lead.updated_at = new Date().toISOString();
    return { ...lead };
  },
};

export const salesService = select<SalesService>({ demo, live });
