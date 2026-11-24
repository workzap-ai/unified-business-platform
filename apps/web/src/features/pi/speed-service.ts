import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * Live inbox events and the speed report. Backend: apps/api/app/modules/pi/events_routes.py and
 * speed.py (/api/v1/pi/events/...). Aggregates and signals only: no message text, name or number.
 */

const spread = z
  .object({
    p50: z.number(),
    p90: z.number(),
    avg: z.number(),
    max: z.number(),
  })
  .nullable()
  .catch(null);

export const speedSchema = z.object({
  replies: z.object({
    hours: z.number(),
    replies: z.number().catch(0),
    with_send_timing: z.number().catch(0),
    total_s: spread,
    stages_s: z.record(z.string(), spread).catch({}),
  }),
  live: z.object({
    enabled: z.boolean().catch(false),
    publishing: z.boolean().catch(false),
    samples: z.number().catch(0),
    server_lag_ms: spread,
    screen_ms: spread,
    total_ms: spread,
    slowest_ms: spread,
    slowest_part: z.string().nullable().catch(null),
  }),
});
export type Speed = z.infer<typeof speedSchema>;
export type Spread = NonNullable<z.infer<typeof spread>>;

const ticketSchema = z.object({
  enabled: z.boolean(),
  ticket: z.string().optional(),
});

export const piSpeedService = {
  get: (hours: number) =>
    apiRequest("GET", "/pi/events/speed", speedSchema, { query: { hours } }),
  ticket: () => apiRequest("POST", "/pi/events/ticket", ticketSchema),
  timing: (
    lagMs: number,
    screenMs: number,
    slowestMs: number,
    slowest: string,
  ) => {
    const cap = (n: number) => Math.min(600_000, Math.round(n));
    return apiRequest("POST", "/pi/events/timing", null, {
      body: {
        lag_ms: cap(lagMs),
        screen_ms: cap(screenMs),
        slowest_ms: cap(slowestMs),
        slowest,
      },
    });
  },
};
