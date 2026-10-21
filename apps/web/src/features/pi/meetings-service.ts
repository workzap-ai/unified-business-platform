import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * Meetings board: every meeting pi and the team arranged, free time, Google busy
 * time and the customers still waiting for a time.
 * Backend: apps/api/app/modules/pi_saas/meeting_board.py (/api/v1/pi/meetings).
 * Times in `local` / `starts_at` inputs are business-local "YYYY-MM-DDTHH:MM".
 */

export const MEETING_STATUSES = [
  "scheduled",
  "live",
  "awaiting_outcome",
  "done",
  "no_show",
  "cancelled",
] as const;
export type MeetingStatus = (typeof MEETING_STATUSES)[number];

export const WEEKDAYS = [
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
  "sat",
  "sun",
] as const;
export type Weekday = (typeof WEEKDAYS)[number];

export const meetingSchema = z.object({
  id: z.string(),
  conversation_id: z.string(),
  customer_id: z.string().nullable().catch(null),
  customer_name: z.string().catch("Customer"),
  phone: z.string().nullable().catch(null),
  starts_at: z.string(),
  ends_at: z.string(),
  local: z.string().catch(""),
  label: z.string().catch(""),
  minutes: z.number().catch(30),
  how: z.string().catch(""),
  link: z.string().catch(""),
  place: z.string().catch(""),
  note: z.string().catch(""),
  status: z.enum(MEETING_STATUSES).catch("scheduled"),
  outcome: z.string().catch(""),
  change_to: z.string().nullable().catch(null),
  change_label: z.string().nullable().catch(null),
  calendar_event: z.boolean().catch(false),
  actionable: z.boolean().catch(false),
  topic: z.string().catch(""),
});
export type Meeting = z.infer<typeof meetingSchema>;

const dayHoursSchema = z.object({
  open: z.boolean().catch(false),
  start: z.string().catch("09:00"),
  end: z.string().catch("18:00"),
});
export type DayHours = z.infer<typeof dayHoursSchema>;

const closed: DayHours = { open: false, start: "09:00", end: "18:00" };

export const freeSlotSchema = z.object({
  starts_at: z.string(),
  local: z.string(),
  label: z.string().catch(""),
});
export type FreeSlot = z.infer<typeof freeSlotSchema>;

export const bookingSchema = z.object({
  id: z.string(),
  customer_name: z.string().catch("Customer"),
  starts_at: z.string(),
  ends_at: z.string(),
  status: z.string().catch(""),
  conversation_id: z.string().nullable().catch(null),
});
export type Booking = z.infer<typeof bookingSchema>;

export const waitingSchema = z.object({
  request_id: z.string(),
  conversation_id: z.string(),
  customer_name: z.string().catch("Customer"),
  question: z.string().catch(""),
  priority: z.enum(["normal", "high"]).catch("normal"),
  asked_local: z.string().nullable().catch(null),
  asked_label: z.string().nullable().catch(null),
  how: z.string().catch(""),
  created_at: z.string().catch(""),
  topic: z.string().catch(""),
});
export type WaitingRequest = z.infer<typeof waitingSchema>;

export const meetingBoardSchema = z.object({
  timezone: z.string().catch("UTC"),
  zone_name: z.string().catch(""),
  now: z.string(),
  start: z.string(),
  days: z.number().catch(7),
  hours: z.object({
    mon: dayHoursSchema.catch(closed),
    tue: dayHoursSchema.catch(closed),
    wed: dayHoursSchema.catch(closed),
    thu: dayHoursSchema.catch(closed),
    fri: dayHoursSchema.catch(closed),
    sat: dayHoursSchema.catch(closed),
    sun: dayHoursSchema.catch(closed),
  }),
  calendar: z.enum(["none", "connected", "error"]).catch("none"),
  busy: z
    .array(z.object({ starts_at: z.string(), ends_at: z.string() }))
    .catch([]),
  meetings: z.array(meetingSchema),
  upcoming: z.array(meetingSchema).catch([]),
  needs_outcome: z.array(meetingSchema).catch([]),
  history: z.array(meetingSchema).catch([]),
  bookings: z.array(bookingSchema).catch([]),
  free: z.array(freeSlotSchema).catch([]),
  waiting: z.array(waitingSchema).catch([]),
  stats: z.object({
    today: z.number().catch(0),
    this_week: z.number().catch(0),
    waiting: z.number().catch(0),
    change_requests: z.number().catch(0),
    needs_outcome: z.number().catch(0),
    done: z.number().catch(0),
    no_show: z.number().catch(0),
  }),
});
export type MeetingBoard = z.infer<typeof meetingBoardSchema>;

const changeResultSchema = z.object({
  ok: z.boolean().catch(true),
  told_customer: z.boolean().catch(false),
  calendar_moved: z.boolean().nullable().optional(),
  calendar_removed: z.boolean().nullable().optional(),
});
export type MeetingChangeResult = z.infer<typeof changeResultSchema>;

const okSchema = z.object({ ok: z.boolean().catch(true) });

export const bookResultSchema = z.object({
  ok: z.boolean().catch(true),
  conversation_id: z.string(),
  /** e.g. "Saturday 17 October, 10:30 AM" (business time). */
  label: z.string().nullable().catch(null),
  link: z
    .string()
    .nullable()
    .catch("")
    .transform((v) => v ?? ""),
  /** False when WhatsApp's 24-hour window is closed: share the link yourself. */
  told_customer: z.boolean().catch(false),
});
export type BookMeetingResult = z.infer<typeof bookResultSchema>;

export type BookMeetingInput = {
  customer_id: string;
  /** Business-local "YYYY-MM-DDTHH:MM". */
  starts_at: string;
  duration_minutes?: number;
  how?: "google_meet" | "video" | "link" | "in_person";
  link?: string;
  place?: string;
  /** What it's about; told to the customer. */
  note?: string;
};

export type MoveMeetingInput = {
  conversation_id: string;
  starts_at: string;
  duration_minutes?: number;
  notify?: boolean;
};

const path = (conversationId: string, action: string) =>
  `/pi/meetings/${encodeURIComponent(conversationId)}/${action}`;

export const meetingsService = {
  board: (start: string | null, days = 7) =>
    apiRequest("GET", "/pi/meetings", meetingBoardSchema, {
      query: { start: start ?? undefined, days },
    }),
  /** Book a meeting for a customer (from their profile); pi tells them on WhatsApp. */
  book: (body: BookMeetingInput) =>
    apiRequest("POST", "/pi/meetings/book", bookResultSchema, { body }),
  move: ({ conversation_id, ...body }: MoveMeetingInput) =>
    apiRequest("POST", path(conversation_id, "move"), changeResultSchema, {
      body,
    }),
  acceptChange: (conversationId: string) =>
    apiRequest(
      "POST",
      path(conversationId, "accept-change"),
      changeResultSchema,
    ),
  cancel: ({
    conversation_id,
    ...body
  }: {
    conversation_id: string;
    reason?: string;
    notify?: boolean;
  }) =>
    apiRequest("POST", path(conversation_id, "cancel"), changeResultSchema, {
      body,
    }),
  remind: (conversationId: string) =>
    apiRequest("POST", path(conversationId, "remind"), changeResultSchema),
  outcome: ({
    conversation_id,
    ...body
  }: {
    conversation_id: string;
    status: "done" | "no_show";
    note?: string;
  }) =>
    apiRequest("POST", path(conversation_id, "outcome"), okSchema, { body }),
};
