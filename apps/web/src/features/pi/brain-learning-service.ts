import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * What pi's learning brain is doing: health, nightly digests, examples, question wordings,
 * lessons ("Teach pi"), drafted industry packs and the change log. Everything here is opt-in per
 * workspace and sits below pi's rules. Backend: apps/api/app/modules/pi/brain_learning_routes.py
 * (/api/v1/pi/brain-learning) and brain_health_routes.py (/api/v1/pi/brain-health).
 */

const settingSchema = z.object({
  value: z.number(),
  default: z.number(),
  low: z.number(),
  high: z.number(),
});

export const brainHealthSchema = z.object({
  days: z.number(),
  pi_mode: z.string().catch("standard"),
  learning_frozen: z.boolean().catch(true),
  metrics: z
    .object({
      scored: z.number().catch(0),
      average_reward: z.number().optional(),
      confusion_rate: z.number().optional(),
      correction_rate: z.number().optional(),
      opt_out_rate: z.number().optional(),
    })
    .catch({ scored: 0 }),
  settings: z.record(z.string(), settingSchema).catch({}),
});
export type BrainHealth = z.infer<typeof brainHealthSchema>;

export const learningRunSchema = z.object({
  id: z.string(),
  started_at: z.string(),
  frozen: z.boolean().catch(false),
  digest: z.record(z.string(), z.unknown()).catch({}),
});
export type LearningRun = z.infer<typeof learningRunSchema>;

export const learningChangeSchema = z.object({
  id: z.string(),
  kind: z.string(),
  risk: z.string().catch("low"),
  status: z.string(),
  reason: z.string().catch(""),
  created_at: z.string(),
});
export type LearningChange = z.infer<typeof learningChangeSchema>;

export const learningExampleSchema = z.object({
  id: z.string(),
  status: z.string(),
  language: z.string().catch("en"),
  person: z.string().catch(""),
  reply: z.string().catch(""),
  reward: z.number().catch(0),
  uses: z.number().catch(0),
  retired_reason: z.string().catch(""),
  created_at: z.string(),
});
export type LearningExample = z.infer<typeof learningExampleSchema>;

export const questionArmSchema = z.object({
  id: z.string(),
  slot: z.string(),
  language: z.string().catch("en"),
  text: z.string(),
  status: z.string(),
  uses: z.number().catch(0),
  success_rate: z.number().catch(0),
  traffic_cap: z.number().catch(1),
  created_by: z.string().catch("seed"),
});
export type QuestionArm = z.infer<typeof questionArmSchema>;

export const lessonSchema = z.object({
  id: z.string(),
  text: z.string(),
  scope: z.record(z.string(), z.string()).catch({}),
  risk: z.string().catch("HIGH"),
  status: z.string(),
  created_by: z.string().catch("staff"),
  author_id: z.string().nullable().catch(null),
  reason: z.string().catch(""),
  uses: z.number().catch(0),
  created_at: z.string(),
});
export type Lesson = z.infer<typeof lessonSchema>;

export const learnedPackSchema = z.object({
  id: z.string(),
  key: z.string(),
  title: z.string(),
  status: z.string(),
  care_approved: z.boolean().catch(false),
  content: z.record(z.string(), z.unknown()).catch({}),
  businesses: z.number().catch(0),
  descriptions: z.array(z.string()).catch([]),
  shadow_conversations: z.number().catch(0),
  created_at: z.string(),
});
export type LearnedPack = z.infer<typeof learnedPackSchema>;

const base = "/pi/brain-learning";
const items = <T extends z.ZodTypeAny>(schema: T) =>
  z.object({ items: z.array(schema) });

export const brainLearningService = {
  health: (days = 7) =>
    apiRequest("GET", `/pi/brain-health?days=${days}`, brainHealthSchema),
  runs: () => apiRequest("GET", `${base}/runs`, items(learningRunSchema)),
  runNow: () =>
    apiRequest(
      "POST",
      `${base}/run`,
      z.object({ frozen: z.boolean().catch(false) }),
    ),
  changes: () =>
    apiRequest("GET", `${base}/changes`, items(learningChangeSchema)),
  examples: () =>
    apiRequest("GET", `${base}/examples`, items(learningExampleSchema)),
  retireExample: (id: string, reason: string) =>
    apiRequest("POST", `${base}/examples/${id}/retire`, learningExampleSchema, {
      body: { reason },
    }),
  arms: () => apiRequest("GET", `${base}/arms`, items(questionArmSchema)),
  addArm: (slot: string, language: string, text: string) =>
    apiRequest("POST", `${base}/arms`, questionArmSchema, {
      body: { slot, language, text },
    }),
  retireArm: (id: string) =>
    apiRequest("POST", `${base}/arms/${id}/retire`, questionArmSchema),
  lessons: () => apiRequest("GET", `${base}/lessons`, items(lessonSchema)),
  teach: (text: string, state: string, language: string) =>
    apiRequest("POST", `${base}/lessons`, lessonSchema, {
      body: { text, state: state || null, language: language || null },
    }),
  approveLesson: (id: string) =>
    apiRequest("POST", `${base}/lessons/${id}/approve`, lessonSchema, {
      body: {},
    }),
  rejectLesson: (id: string) =>
    apiRequest("POST", `${base}/lessons/${id}/reject`, lessonSchema, {
      body: {},
    }),
  retireLesson: (id: string) =>
    apiRequest("POST", `${base}/lessons/${id}/retire`, lessonSchema, {
      body: {},
    }),
  packs: () => apiRequest("GET", `${base}/packs`, items(learnedPackSchema)),
  approveListening: (id: string) =>
    apiRequest(
      "POST",
      `${base}/packs/${id}/approve-listening`,
      learnedPackSchema,
    ),
  approveCare: (id: string, care: string[], scopeRule: string) =>
    apiRequest("POST", `${base}/packs/${id}/approve-care`, learnedPackSchema, {
      body: { care, scope_rule: scopeRule },
    }),
  rejectPack: (id: string) =>
    apiRequest("POST", `${base}/packs/${id}/reject`, learnedPackSchema),
  retirePack: (id: string) =>
    apiRequest("POST", `${base}/packs/${id}/retire`, learnedPackSchema),
};
