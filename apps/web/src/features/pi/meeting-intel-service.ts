import { z } from "zod";
import { ApiError, API_BASE, apiRequest } from "@/services/api-client";

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

export const SPEAKER_ROLES = ["customer", "staff", "other", "unknown"] as const;
export type SpeakerRole = (typeof SPEAKER_ROLES)[number];

const speakerSchema = z.object({
  id: z.string(),
  label: z.string(),
  role: z.enum(SPEAKER_ROLES).catch("unknown"),
});
export type Speaker = z.infer<typeof speakerSchema>;

const detailSchema = meetingSchema.extend({
  participants: z.array(z.string()).catch([]),
  // who each speaker is, as confirmed by a person; "unknown" until then
  speakers: z.array(speakerSchema).catch([]),
  // every line of the transcript; `segments` is one page of it
  segments_total: z.number().catch(0),
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
  // The answer comes only from this meeting's transcript; `sources` are the lines it cites.
  ask: (id: string, question: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/ask`,
      z.object({
        found: z.boolean().catch(false),
        answer: z.string().catch(""),
        partial: z.boolean().catch(false),
        sources: z
          .array(
            z.object({
              ordinal: z.number(),
              speaker: z.string().catch(""),
              role: z.string().catch("unknown"),
              start_ms: z.number().catch(0),
              text: z.string().catch(""),
            }),
          )
          .catch([]),
      }),
      { body: { question }, timeoutMs: 60_000 },
    ),
  setSpeakerRole: (id: string, speakerId: string, role: SpeakerRole) =>
    apiRequest("PATCH", `${BASE}/${id}/speakers/${speakerId}`, speakerSchema, {
      body: { role },
    }),
  importTranscript: (id: string, text: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/transcript`,
      meetingSchema.extend({ lines: z.number(), speakers: z.number() }),
      { body: { text } },
    ),
  // One recorded part (a few minutes of audio) is transcribed inside the request. Sending the
  // same index again replaces that part, so a retry never duplicates words. Audio is not kept.
  uploadPart: (
    id: string,
    part: {
      index: number;
      offsetMs: number;
      durationMs: number;
      audio: Blob;
      keep?: boolean;
    },
  ) => {
    const form = new FormData();
    form.set("index", String(part.index));
    form.set("offset_ms", String(Math.round(part.offsetMs)));
    form.set("duration_ms", String(Math.round(part.durationMs)));
    form.set("file", part.audio, "part");
    if (part.keep) form.set("keep", "true");
    return apiRequest(
      "POST",
      `${BASE}/${id}/recording/parts`,
      z.object({
        part: z.number(),
        segments: z.number(),
        saved: z.boolean().catch(false),
      }),
      { body: form, timeoutMs: 120_000 },
    );
  },
  // Is a storage bucket connected (Settings -> Integrations)? Saving a recording needs one.
  storageConnected: () =>
    apiRequest(
      "GET",
      "/integrations/capabilities",
      z.object({ storage: z.boolean().catch(false) }),
    ),
  // Say yes to SAVING the recording (separate from recording it); the server keeps who and when.
  saveConsent: (id: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/recording/save-consent`,
      z.object({ media_consent_at: z.string() }),
    ),
  // One part of the video (a couple of minutes), saved in the workspace's own storage.
  uploadVideo: (
    id: string,
    part: { index: number; offsetMs: number; durationMs: number; video: Blob },
  ) => {
    const form = new FormData();
    form.set("offset_ms", String(Math.round(part.offsetMs)));
    form.set("duration_ms", String(Math.round(part.durationMs)));
    form.set("file", part.video, "part");
    return apiRequest(
      "POST",
      `${BASE}/${id}/recording/media/video/${part.index}`,
      z.object({ kind: z.string(), part: z.number(), bytes: z.number() }),
      { body: form, timeoutMs: 180_000 },
    );
  },
  // The saved parts with short-lived links to play them (they expire after an hour).
  recording: (id: string) =>
    apiRequest(
      "GET",
      `${BASE}/${id}/recording`,
      z.object({
        retention_until: z.string().nullable().catch(null),
        parts: z
          .array(
            z.object({
              kind: z.enum(["audio", "video"]),
              index: z.number(),
              offset_ms: z.number().catch(0),
              duration_ms: z.number().catch(0),
              bytes: z.number().catch(0),
              mime: z.string().catch(""),
              url: z.string(),
            }),
          )
          .catch([]),
      }),
    ),
  // Live requirement mapping for one recorded part. Proposals only; best effort.
  analysePart: (id: string, index: number) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/analyse/part/${index}`,
      z.object({ part: z.number(), insights: z.number(), dropped: z.number() }),
      { timeoutMs: 90_000 },
    ),
  // The transcript a page at a time, so a meeting of any length can be read to the end.
  transcriptPage: (id: string, offset: number) =>
    apiRequest(
      "GET",
      `${BASE}/${id}/transcript`,
      z.object({
        total: z.number(),
        next_offset: z.number().nullable(),
        segments: z.array(segmentSchema),
      }),
      { query: { offset, limit: 500 } },
    ),
  transcriptDownloadHref: (id: string) =>
    `${API_BASE}${BASE}/${id}/transcript/download`,
  // The host's recorder says it has begun: the meeting's clock starts (once). Guests are placed
  // on this clock by the server.
  recordingStarted: (id: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/recording/start`,
      z.object({ recording_started_at: z.string().nullable().catch(null) }),
    ),
  // The meeting link (people who open it record their own microphone into this meeting).
  inviteStatus: (id: string) =>
    apiRequest(
      "GET",
      `${BASE}/${id}/invite`,
      z.object({
        enabled: z.boolean().catch(false),
        open: z.boolean().catch(false),
        expires_at: z.string().nullable().catch(null),
        guests: z
          .array(
            z.object({
              id: z.string(),
              slot: z.number(),
              label: z.string(),
              joined_at: z.string(),
              removed: z.boolean().catch(false),
            }),
          )
          .catch([]),
      }),
    ),
  // The token comes back once and is never stored in clear: the page builds the link from it.
  createInvite: (id: string, input: { hours: number; max_guests: number }) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/invite`,
      z.object({ token: z.string(), expires_at: z.string() }),
      { body: input },
    ),
  revokeInvite: (id: string) =>
    apiRequest(
      "DELETE",
      `${BASE}/${id}/invite`,
      z.object({ closed: z.number() }),
    ),
  removeGuest: (id: string, guestId: string) =>
    apiRequest(
      "DELETE",
      `${BASE}/${id}/guests/${guestId}`,
      z.object({ removed: z.boolean() }),
    ),
  completeRecording: (
    id: string,
    input: { duration_ms: number; parts: number; skipped: number },
  ) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/recording/complete`,
      meetingSchema.extend({ skipped: z.number().catch(0) }),
      { body: input },
    ),
  // One call reads as many parts of the transcript as fit in about 40 seconds and saves them; the
  // answer says how far it got (`complete`, `done` of `total`). Use `analyseAll` to carry on until
  // the whole meeting is read.
  analyse: (id: string) =>
    apiRequest(
      "POST",
      `${BASE}/${id}/analyse`,
      meetingSchema.extend({
        insights: z.number(),
        dropped: z.number(),
        complete: z.boolean().catch(true),
        done: z.number().catch(0),
        total: z.number().catch(0),
      }),
      { timeoutMs: 120_000 },
    ),
  // Keeps calling `analyse` until every part is read. When a provider is rate-limited a call may
  // read nothing: it waits and asks again, and gives up only after several calls in a row got
  // nowhere (what was read stays saved, so pressing the button again carries on).
  analyseAll: async (
    id: string,
    onProgress?: (done: number, total: number) => void,
  ) => {
    let stalls = 0;
    let best = -1;
    for (let round = 0; round < 60; round++) {
      try {
        const r = await meetingIntelService.analyse(id);
        onProgress?.(r.done, r.total);
        if (r.complete) return r;
        if (r.done > best) {
          best = r.done;
          stalls = 0;
        } else stalls += 1;
      } catch (e) {
        stalls += 1;
        if (stalls >= 5) throw e;
      }
      if (stalls >= 5)
        throw new ApiError(
          502,
          "MEETING_ANALYSIS_FAILED",
          undefined,
          "The analysis could not be completed; try again",
        );
      await new Promise((r) => setTimeout(r, stalls === 0 ? 1500 : 15_000));
    }
    throw new ApiError(
      502,
      "MEETING_ANALYSIS_FAILED",
      undefined,
      "The analysis could not be completed; try again",
    );
  },
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
