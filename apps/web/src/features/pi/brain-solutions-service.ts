import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * The solutions pi learns, per industry: versions (`solutions/{industry}@1.N`) with their
 * evidence, the ideas with their numbers, and what a person must decide. Backend:
 * apps/api/app/modules/pi/solution_routes.py (/api/v1/pi/solutions), permission
 * pi.settings.manage.
 */

export const solutionVersionSchema = z.object({
  version: z.string(),
  status: z.string(),
  changes: z.array(z.string()).catch([]),
  evidence: z.record(z.string(), z.unknown()).catch({}),
  created_at: z.string().nullable().catch(null),
  rolled_back_at: z.string().nullable().catch(null),
});
export type SolutionVersion = z.infer<typeof solutionVersionSchema>;

export const solutionIndustrySchema = z.object({
  industry: z.string(),
  seeded: z.boolean().catch(true),
  latest: solutionVersionSchema,
  versions: z.number().catch(0),
});
export type SolutionIndustry = z.infer<typeof solutionIndustrySchema>;

export const sampleReplySchema = z
  .object({
    person: z.string().catch(""),
    pi: z.string().catch(""),
    language: z.string().optional(),
  })
  .nullable()
  .catch(null);

export const solutionDetailSchema = z.object({
  industry: z.string(),
  sample_reply: sampleReplySchema,
  versions: z.array(solutionVersionSchema).catch([]),
  ideas: z.number().catch(0),
});
export type SolutionDetail = z.infer<typeof solutionDetailSchema>;

export const solutionIdeaSchema = z.object({
  id: z.string(),
  industry: z.string(),
  problem: z.string().catch(""),
  language: z.string().catch("en"),
  text: z.string(),
  kind: z.string().catch(""),
  status: z.string(),
  uses: z.number().catch(0),
  source: z.string().catch(""),
  traffic_cap: z.number().catch(1),
  feedback: z.number().catch(0),
  retired_reason: z.string().catch(""),
});
export type SolutionIdea = z.infer<typeof solutionIdeaSchema>;

export const catalogueProposalSchema = z.object({
  id: z.string(),
  need: z.string(),
  industries: z.array(z.string()).catch([]),
  count: z.number().catch(0),
});
export type CatalogueProposal = z.infer<typeof catalogueProposalSchema>;

export const solutionReviewSchema = z.object({
  ideas: z.array(solutionIdeaSchema).catch([]),
  proposals: z.array(catalogueProposalSchema).catch([]),
});

export const IDEA_STATUSES = [
  "review",
  "testing",
  "active",
  "retired",
] as const;

/** A version that a rollback would undo: learned (not the @1.0 seed) and still live or shadow. */
export function isRollbackable(v: Pick<SolutionVersion, "version" | "status">) {
  return (
    v.version.replace(/^@/, "") !== "1.0" &&
    (v.status === "live" || v.status === "shadow")
  );
}

/** Rejecting needs a short reason of at least a few characters. */
export function rejectReasonOk(reason: string) {
  return reason.trim().length >= 3;
}

const base = "/pi/solutions";
const enc = encodeURIComponent;

export const brainSolutionsService = {
  overview: () =>
    apiRequest(
      "GET",
      base,
      z.object({ industries: z.array(solutionIndustrySchema) }),
    ),
  review: () => apiRequest("GET", `${base}/review`, solutionReviewSchema),
  arms: (industry?: string, status?: string) => {
    const q = new URLSearchParams();
    if (industry) q.set("industry", industry);
    if (status) q.set("status", status);
    const qs = q.toString();
    return apiRequest(
      "GET",
      `${base}/arms${qs ? `?${qs}` : ""}`,
      z.object({ items: z.array(solutionIdeaSchema) }),
    );
  },
  detail: (industry: string) =>
    apiRequest("GET", `${base}/${enc(industry)}`, solutionDetailSchema),
  rollback: (industry: string) =>
    apiRequest(
      "POST",
      `${base}/${enc(industry)}/rollback`,
      z.object({ industry: z.string(), rolled_back: z.string() }),
    ),
  decideIdea: (id: string, approve: boolean, reason = "") =>
    apiRequest("POST", `${base}/ideas/${id}/decide`, solutionIdeaSchema, {
      body: { approve, reason },
    }),
  decideProposal: (id: string, approve: boolean, reason = "") =>
    apiRequest(
      "POST",
      `${base}/proposals/${id}/decide`,
      z.object({ id: z.string(), status: z.string() }),
      { body: { approve, reason } },
    ),
};
