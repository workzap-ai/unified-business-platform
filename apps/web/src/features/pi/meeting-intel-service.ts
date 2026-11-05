import { z } from "zod";
import { ApiError, apiRequest } from "@/services/api-client";

/**
 * Meeting intelligence: a meeting's transcript, what pi understood from it, and the review that
 * decides what reaches the customer's memory. Live data only (no sample data).
 * Backend: apps/api/app/modules/pi_meetings/routes.py (/api/v1/pi/meeting-intel).
 */

export const INSIGHT_KINDS = [
  "summary",
  "problem",
  "requirement_explicit",
  "requirement_implicit",
  "root_cause",
  "impact",
  "decision",
  "commitment",
  "action",
  "question",
  "risk",
  "next_step",
] as const;
export type InsightKind = (typeof INSIGHT_KINDS)[number];

export const INSIGHT_LABELS: Record<InsightKind, string> = {
  summary: "Summary",
  problem: "Problem",
  requirement_explicit: "Asked for",
  requirement_implicit: "Likely need",
  root_cause: "Root cause",
  impact: "Impact",
  decision: "Decision",
  commitment: "Commitment",
  action: "Action",
  question: "Open question",
  risk: "Risk",
  next_step: "Next step",
};

export const BASES = [
  "stated",
  "inferred",
  "estimate",
  "recommendation",
] as const;
export type Basis = (typeof BASES)[number];

/** Why an insight is trusted: "stated" is what a person said; the rest is pi's own conclusion. */
export const BASIS_LABELS: Record<Basis, string> = {
  stated: "Said in the meeting",
  inferred: "pi's conclusion",
  estimate: "pi's estimate",
  recommendation: "pi's suggestion",
};

export const MEETING_STATUS_LABELS: Record<string, string> = {
  created: "Waiting for a transcript",
  uploaded: "Uploaded",
  transcribing: "Transcribing",
  analysing: "Ready to analyse",
  review: "Ready to review",
  approved: "Reviewed",
  failed: "Needs a retry",
};

export const meetingSchema = z.object({
  id: z.string(),
  title: z.string().catch(""),
  customer_id: z.string().nullable().catch(null),
  source: z.string().catch("upload"),
  status: z.string().catch("created"),
  language: z.string().catch(""),
  consent_at: z.string().nullable().catch(null),
  has_recording: z.boolean().catch(false),
  duration_ms: z.number().catch(0),
  held_at: z.string().nullable().catch(null),
  retention_until: z.string().nullable().catch(null),
  failure_reason: z.string().catch(""),
  created_at: z.string().nullable().catch(null),
});
export type Meeting = z.infer<typeof meetingSchema>;

export const insightSchema = z.object({
  id: z.string(),
  kind: z.enum(INSIGHT_KINDS).catch("summary"),
  basis: z.enum(BASES).catch("inferred"),
  text: z.string(),
  confidence: z.number().catch(0),
  segment_refs: z.array(z.number()).catch([]),
  owner_label: z.string().catch(""),
  due_text: z.string().catch(""),
  review_status: z
    .enum(["pending", "approved", "rejected", "edited"])
    .catch("pending"),
  written_to_brain: z.boolean().catch(false),
  brain_ref: z.string().catch(""),
});
export type Insight = z.infer<typeof insightSchema>;

export const segmentSchema = z.object({
  ordinal: z.number(),
  start_ms: z.number().catch(0),
  end_ms: z.number().catch(0),
  speaker: z.string().catch(""),
  text: z.string(),
});
export type Segment = z.infer<typeof segmentSchema>;

const detailSchema = meetingSchema.extend({
  participants: z.array(z.string()).catch([]),
  segments: z.array(segmentSchema).catch([]),
  insights: z.array(insightSchema).catch([]),
});
export type MeetingDetail = z.infer<typeof detailSchema>;

const hitSchema = z.object({
  meeting_id: z.string(),
  title: z.string().catch(""),
  ordinal: z.number().catch(0),
  start_ms: z.number().catch(0),
  text: z.string(),
});
export type SearchHit = z.infer<typeof hitSchema>;

const approvedSchema = insightSchema.extend({
  wrote: z.string().catch(""),
  note: z.string().catch(""),
});
export type Approved = z.infer<typeof approvedSchema>;

export type NewMeeting = {
  title: string;
  consent_given: boolean;
  consent_note?: string;
  customer_id?: string | null;
};

const BASE = "/pi/meeting-intel";

export const meetingIntelService = {
  list: () =>
    apiRequest(
      "GET",
      BASE,
      z.object({ items: z.array(meetingSchema).catch([]) }),
    ),
  get: (id: string) => apiRequest("GET", `${BASE}/${id}`, detailSchema),
  search: (q: string) =>
    apiRequest(
      "GET",
      `${BASE}/search`,
      z.object({ items: z.array(hitSchema) }),
      {
        query: { q },
      },
    ),
  create: (input: NewMeeting) =>
    apiRequest("POST", BASE, meetingSchema, { body: input }),
  linkCustomer: (id: string, customerId: string) =>
    apiRequest("PATCH", `${BASE}/${id}/customer`, meetingSchema, {
      body: { customer_id: customerId },
    }),
  importTranscript: (id: string, text: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/transcript`,
      meetingSchema.extend({ lines: z.number(), speakers: z.number() }),
      { body: { text } },
    ),
  // Runs the analysis inside the request (a few model calls): allow it longer than the default.
  analyse: (id: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/analyse`,
      meetingSchema.extend({ insights: z.number(), dropped: z.number() }),
      { timeoutMs: 120_000 },
    ),
  approve: (id: string, insightId: string, editedText = "") =>
    apiRequest(
      "POST",
      `${BASE}/${id}/insights/${insightId}/approve`,
      approvedSchema,
      { body: { edited_text: editedText } },
    ),
  reject: (id: string, insightId: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/insights/${insightId}/reject`,
      insightSchema,
    ),
  remove: (id: string) =>
    apiRequest("DELETE", `${BASE}/${id}`, z.object({ deleted: z.boolean() })),
};

/** The feature is off until the workspace switches it on (response_rules.brain.meeting_intel). */
export function isSwitchedOff(error: unknown): boolean {
  return error instanceof ApiError && error.code === "MEETING_INTEL_OFF";
}

/** "1:05" for a position in a recording; "" when the transcript has no timing (an import). */
export function clock(ms: number): string {
  if (!ms || ms < 0) return "";
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** What approving this insight will do, said before the reviewer clicks (mirrors brain_bridge.py). */
export function approvalEffect(insight: Insight): string {
  const stated = insight.basis === "stated";
  if (stated && insight.kind === "problem")
    return "Added to the customer's problem list, with their own words as evidence.";
  if (stated && (insight.kind === "decision" || insight.kind === "commitment"))
    return "Saved to the customer's memory as a decision.";
  if (
    ["action", "next_step", "question"].includes(insight.kind) &&
    insight.basis !== "estimate"
  )
    return "Sent to Requests for your team.";
  return stated
    ? "Marked as reviewed."
    : "Marked as reviewed. It stays pi's own conclusion and is never saved as something the customer said.";
}
