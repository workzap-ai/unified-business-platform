import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * pi Health: what pi found wrong, what it fixed by itself, and its self-tests.
 * Backend: apps/api/app/modules/pi_saas/health.py, health_selftest.py
 * (/api/v1/pi/health).
 */

export const HEALTH_STATUSES = ["ok", "warning", "problem", "fixed"] as const;
export type HealthStatus = (typeof HEALTH_STATUSES)[number];

export const healthCheckSchema = z.object({
  key: z.string(),
  area: z.string(),
  status: z.enum(HEALTH_STATUSES).catch("warning"),
  title: z.string(),
  detail: z.string().catch(""),
  count: z.number().catch(0),
  fix: z.enum(["auto", "button", "settings"]).nullable().catch(null),
  href: z.string().nullable().catch(null),
  action: z.string().nullable().catch(null),
  last_fixed_at: z.string().nullable().catch(null),
});
export type HealthCheck = z.infer<typeof healthCheckSchema>;

const scenarioSchema = z.object({
  key: z.string(),
  title: z.string(),
  message: z.string().catch(""),
  passed: z.boolean().nullable(),
  reason: z.string().catch(""),
  reply: z.string().catch(""),
  retried: z.boolean().catch(false),
  hint: z.string().catch(""),
  href: z.string().nullable().catch(null),
  at: z.string(),
});
export type SelfTestScenario = z.infer<typeof scenarioSchema>;

export const healthSchema = z.object({
  score: z.number(),
  verdict: z.string(),
  counts: z.record(z.string(), z.number()).catch({}),
  checks: z.array(healthCheckSchema),
  areas: z.array(z.string()),
  fixed_recently: z.object({
    total: z.number(),
    items: z.array(
      z.object({
        check: z.string().nullable().catch(null),
        what: z.string().nullable().catch(null),
        count: z.number().catch(1),
        at: z.string(),
      }),
    ),
  }),
  trends: z.array(
    z.object({
      day: z.string(),
      replies: z.number(),
      held: z.number(),
      failed_sends: z.number(),
      fixes: z.number(),
    }),
  ),
  gaps: z.array(
    z.object({
      question: z.string(),
      asked: z.number(),
      last_asked_at: z.string(),
      href: z.string().catch("/pi/knowledge"),
    }),
  ),
  learning: z.object({
    answers_learned_30d: z.number().catch(0),
    open_questions: z.number().catch(0),
    drafts_waiting: z.number().catch(0),
  }),
  self_tests: z.object({
    last_run_at: z.string().nullable(),
    pass_rate: z.number().nullable(),
    passed: z.number().catch(0),
    total: z.number().catch(0),
    scenarios: z.array(scenarioSchema),
    daily: z.array(
      z.object({
        day: z.string(),
        passed: z.number(),
        total: z.number(),
        rate: z.number().nullable(),
      }),
    ),
  }),
  checked_at: z.string(),
});
export type PiHealth = z.infer<typeof healthSchema>;

export const piHealthService = {
  get: () => apiRequest("GET", "/pi/health", healthSchema),
  heal: () => apiRequest("POST", "/pi/health/heal", healthSchema),
  fix: (key: string) =>
    apiRequest(
      "POST",
      `/pi/health/fix/${encodeURIComponent(key)}`,
      healthSchema,
    ),
  selfTest: () => apiRequest("POST", "/pi/health/self-test", healthSchema),
};
