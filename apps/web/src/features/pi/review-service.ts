import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * The staff review of one pi conversation and the "needs attention" list: the problem map as the
 * briefing, the four dials, the diagnosis and idea budget, why pi handed over, the Solution Box
 * and the live alerts (pi spec 8.11.1, 10.7, 6.5). Read-only; staff only (pi.handoffs.manage).
 * Backend: apps/api/app/modules/pi/staff_review_routes.py (/api/v1/pi/review). Notes use the
 * existing /pi/conversations/{id}/notes routes.
 */

export const ALERT_LEVELS = ["red", "amber", "yellow", "blue"] as const;
export type AlertLevel = (typeof ALERT_LEVELS)[number];

export const alertSchema = z.object({
  level: z.enum(ALERT_LEVELS).catch("blue"),
  key: z.string(),
  label: z.string(),
  detail: z.string().catch(""),
});
export type ReviewAlert = z.infer<typeof alertSchema>;

export const attentionItemSchema = z.object({
  conversation_id: z.string(),
  customer_ref: z.string(),
  phone: z.string(),
  language: z.string().nullable().catch(null),
  mode: z.string(),
  unread_count: z.number().catch(0),
  last_message_at: z.string(),
  alerts: z.array(alertSchema),
});
export type AttentionItem = z.infer<typeof attentionItemSchema>;

export const attentionSchema = z.object({
  items: z.array(attentionItemSchema),
  total: z.number().catch(0),
});

export const NODE_STATUSES = [
  "open",
  "confirmed",
  "in_box",
  "parked",
  "resolved",
  "stale",
] as const;

const nodeSchema = z.object({
  id: z.string(),
  number: z.number(),
  title: z.string(),
  category: z.string(),
  category_label: z.string().catch(""),
  subtype: z.string().nullable().catch(null),
  goal_verb: z.string().nullable().catch(null),
  status: z.enum(NODE_STATUSES).catch("open"),
  rank: z.number().nullable().catch(null),
  raised_voluntarily: z.boolean().catch(false),
});
export type MapNode = z.infer<typeof nodeSchema>;

const linkSchema = z.object({
  from: z.string(),
  to: z.string(),
  type: z.string(),
  evidence: z.string().catch("pi_inferred"),
});

const moveSchema = z.object({
  move: z.string(),
  reason: z.string().catch(""),
  had_question: z.boolean().catch(false),
  at: z.string(),
});

const hypothesisSchema = z.object({
  text: z.string(),
  confidence: z.string().catch("low"),
  status: z.string().catch("open"),
  confirmed_by_owner: z.boolean().catch(false),
  evidence_for: z.number().catch(0),
  evidence_against: z.number().catch(0),
  cheapest_test: z.string().catch(""),
});

const requestSchema = z.object({
  id: z.string(),
  kind: z.string(),
  status: z.string(),
  priority: z.string().catch("normal"),
  question: z.string().catch(""),
  context_summary: z.string().catch(""),
  created_at: z.string(),
});

export const reviewSchema = z.object({
  conversation: z.object({
    id: z.string(),
    customer_ref: z.string(),
    phone: z.string(),
    language: z.string().nullable().catch(null),
    mode: z.string(),
    status: z.string(),
    flow_state: z.string().nullable().catch(null),
    last_message_at: z.string(),
  }),
  map: z.object({
    version: z.number().nullable(),
    shared_version: z.number().nullable(),
    shared_at: z.string().nullable(),
    up_to_date_with_owner: z.boolean().catch(false),
    nodes: z.array(nodeSchema),
    links: z.array(linkSchema),
  }),
  thinking: z.object({
    dials: z.object({
      openness: z.number(),
      pace: z.string(),
      mode: z.string(),
      trust_trend: z.string(),
      fatigue: z.boolean().catch(false),
    }),
    posture: z.string(),
    messages_read: z.number().catch(0),
    moves: z.array(moveSchema),
    hypotheses: z.array(hypothesisSchema),
  }),
  diagnosis: z
    .object({
      main_problem: z.string().catch(""),
      likely_causes: z.array(z.string()).catch([]),
      suggested_next_question: z.string().catch(""),
      at: z.string().nullable().catch(null),
    })
    .nullable(),
  ideas: z.object({
    given_in_chat: z.number(),
    given_for_business: z.number(),
    per_problem_cap: z.number(),
    per_business_cap: z.number(),
    business_remaining: z.number(),
    rounds_by_problem: z.record(z.string(), z.number()).catch({}),
  }),
  handover: z.object({
    mode: z.string(),
    handoff: z
      .object({
        id: z.string(),
        status: z.string(),
        reason: z.string(),
        priority: z.string(),
        summary: z.string().catch(""),
        origin: z.string(),
        origin_text: z.string(),
        assigned_label: z.string().nullable().catch(null),
        created_at: z.string(),
      })
      .nullable(),
    requests: z.array(requestSchema),
  }),
  box: z.object({
    box: z
      .object({
        state: z.string(),
        version: z.number(),
        reviewer: z.string().nullable(),
        owner_ranking: z.array(z.unknown()).catch([]),
        map_version: z.number().nullable(),
        updated_at: z.string(),
      })
      .nullable(),
    offers: z.array(
      z.object({
        rule: z.string(),
        allowed: z.boolean(),
        blocked_reason: z.string().nullable(),
        at: z.string(),
      }),
    ),
  }),
  labels: z.object({
    intents: z.record(z.string(), z.number()).catch({}),
    message_labels: z.array(z.object({ label: z.string(), at: z.string() })),
    alerts: z.array(alertSchema),
  }),
});
export type ConversationReview = z.infer<typeof reviewSchema>;

export const noteSchema = z.object({
  id: z.string(),
  body: z.string(),
  author: z.string().nullable().catch(null),
  created_at: z.string(),
});
export type ReviewNote = z.infer<typeof noteSchema>;

/** Where a conversation's review lives; linked from the inbox, handoffs and requests. */
export const reviewHref = (conversationId: string) =>
  `/pi/review?c=${encodeURIComponent(conversationId)}`;

export const piReviewService = {
  attention: () => apiRequest("GET", "/pi/review/attention", attentionSchema),
  review: (conversationId: string) =>
    apiRequest(
      "GET",
      `/pi/review/conversations/${encodeURIComponent(conversationId)}`,
      reviewSchema,
    ),
  notes: (conversationId: string) =>
    apiRequest(
      "GET",
      `/pi/conversations/${encodeURIComponent(conversationId)}/notes`,
      z.array(noteSchema),
    ),
  addNote: (conversationId: string, body: string) =>
    apiRequest(
      "POST",
      `/pi/conversations/${encodeURIComponent(conversationId)}/notes`,
      noteSchema,
      { body: { body } },
    ),
};
