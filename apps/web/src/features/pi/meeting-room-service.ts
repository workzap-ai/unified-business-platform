import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * pi's own video rooms. Staff open a room and join from the app; a customer joins from the meeting
 * link. The browser only ever receives a token for its own id and this one call; the words come back
 * to the server from the video service after the call, never from this page.
 * Backend: apps/api/app/modules/pi_meetings/room_routes.py.
 */

const BASE = "/pi/meeting-intel";

export const roomSchema = z.object({
  id: z.string(),
  meeting_id: z.string(),
  state: z.string(),
  live: z.boolean().catch(false),
  // each voice is recorded briefly to write the transcript, then deleted
  audio: z.boolean().catch(false),
  transcript_state: z.string().catch("none"),
  lines: z.number().catch(0),
  started_at: z.string().nullable().catch(null),
  ended_at: z.string().nullable().catch(null),
  // pi speaking in the room: the host's switches, and whether the agent is really in the call
  pi: z
    .object({
      mode: z.enum(["off", "speak"]).catch("off"),
      muted: z.boolean().catch(false),
      intake: z.boolean().catch(false),
      here: z.boolean().catch(false),
    })
    .catch({ mode: "off", muted: false, intake: false, here: false }),
});
export type MeetingRoom = z.infer<typeof roomSchema>;

export const roomPersonSchema = z.object({
  id: z.string(),
  label: z.string().catch("Guest"),
  staff: z.boolean().catch(false),
  removed: z.boolean().catch(false),
  // the host is holding this person muted
  muted: z.boolean().catch(false),
});
export type RoomPerson = z.infer<typeof roomPersonSchema>;

// The live view of a call: captions with their translation, and (for staff only) pi's tips and
// notes. The agent writes it on the server; this page only reads it by polling.
export const liveLineSchema = z.object({
  n: z.number(),
  v: z.number(),
  role: z.enum(["staff", "customer", "pi"]).catch("customer"),
  name: z.string().catch(""),
  text: z.string().catch(""),
  lang: z.string().catch(""),
  tr: z.string().optional(),
  tr_lang: z.string().optional(),
});
export type LiveLine = z.infer<typeof liveLineSchema>;
export const liveTipSchema = z.object({
  n: z.number(),
  v: z.number(),
  kind: z.enum(["tip", "note"]).catch("tip"),
  text: z.string().catch(""),
  note_kind: z.string().optional(),
});
export type LiveTip = z.infer<typeof liveTipSchema>;
export const liveViewSchema = z.object({
  seq: z.number().catch(0),
  reset: z.boolean().catch(false),
  lines: z.array(liveLineSchema).catch([]),
  tips: z.array(liveTipSchema).catch([]),
  enabled: z
    .object({
      live: z.boolean().catch(false),
      copilot: z.boolean().catch(false),
    })
    .catch({ live: false, copilot: false }),
});
export type LiveView = z.infer<typeof liveViewSchema>;
// How this browser entered the room, so the live view asks the right door (staff or guest).
export type RoomEntry =
  { kind: "staff"; meetingId: string } | { kind: "guest"; token: string };
let entered: RoomEntry | null = null;

export const roomCredentialsSchema = z.object({
  api_key: z.string(),
  call_type: z.string(),
  call_id: z.string(),
  user_id: z.string(),
  name: z.string(),
  token: z.string(),
  expires_in: z.number().catch(7200),
});
export type RoomCredentials = z.infer<typeof roomCredentialsSchema>;

export const meetingRoomService = {
  // Open a room. The person confirms everyone in it will be told the call is transcribed.
  open: (input: {
    title: string;
    customer_id?: string | null;
    language?: string;
    consent: boolean;
    // which agent listens; left out means pi's own personality
    agent_key?: string;
  }) =>
    apiRequest(
      "POST",
      `${BASE}/rooms`,
      z.object({
        meeting: z.object({ id: z.string(), title: z.string().catch("") }),
        room: roomSchema,
      }),
      { body: input },
    ),
  // What a new room will do here, so the page can say it before people agree.
  options: () =>
    apiRequest(
      "GET",
      `${BASE}/rooms/options`,
      z.object({ audio: z.boolean().catch(false) }),
    ),
  status: (meetingId: string) =>
    apiRequest(
      "GET",
      `${BASE}/${meetingId}/room`,
      z.object({
        room: roomSchema.nullable().catch(null),
        meeting_status: z.string().catch(""),
        // who has been given a seat; staff cannot be removed from here
        people: z.array(roomPersonSchema).catch([]),
        limits: z
          .object({ minutes: z.number(), people: z.number() })
          .catch({ minutes: 90, people: 8 }),
      }),
    ),
  // Take a guest out of the live call; they cannot come back.
  removePerson: (meetingId: string, participantId: string) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/people/${participantId}/remove`,
      z.object({ removed: z.boolean() }),
    ),
  // Hold one guest muted (the microphone is switched off and they cannot switch it on again), or
  // let them speak again.
  mutePerson: (meetingId: string, participantId: string, muted: boolean) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/people/${participantId}/mute`,
      z.object({ muted: z.boolean() }),
      { body: { muted } },
    ),
  staffToken: async (meetingId: string) => {
    const credentials = await apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/token`,
      roomCredentialsSchema,
    );
    entered = { kind: "staff", meetingId };
    return credentials;
  },
  // Which door this browser came in by (null before it entered).
  entry: (): RoomEntry | null => entered,
  // What changed in the live view since `after` (captions, translations, and for staff the tips).
  live: (entry: RoomEntry, after: number) =>
    entry.kind === "staff"
      ? apiRequest(
          "GET",
          `${BASE}/${entry.meetingId}/room/live?after=${after}`,
          liveViewSchema,
        )
      : apiRequest(
          "GET",
          `/public/meeting-room/live?after=${after}`,
          liveViewSchema,
          { headers: { "X-Guest-Token": entry.token } },
        ),
  // Staff keep one of pi's live notes: it becomes a DRAFT finding, reviewed like all the others.
  keepNote: (meetingId: string, note: number) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/live/keep`,
      z.object({ kept: z.boolean(), created: z.boolean() }),
      { body: { note } },
    ),
  // The host decides whether pi speaks, mutes it, or lets it lead with a lone customer. A field
  // left out stays as it was.
  setPi: (
    meetingId: string,
    input: { mode?: "off" | "speak"; muted?: boolean; intake?: boolean },
  ) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/pi`,
      z.object({ room: roomSchema }),
      { body: input },
    ),
  end: (meetingId: string) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/end`,
      z.object({ room: roomSchema }),
    ),
  // A guest who joined by link asks to enter the room: the token is for their own id.
  guestToken: async (guestToken: string) => {
    const credentials = await apiRequest(
      "POST",
      "/public/meeting-room/token",
      roomCredentialsSchema,
      { headers: { "X-Guest-Token": guestToken } },
    );
    entered = { kind: "guest", token: guestToken };
    return credentials;
  },
};

export const ROOM_REFUSED: Record<string, string> = {
  MEETING_ROOM_OFF: "Video rooms are not switched on for this workspace yet.",
  MEETING_ROOM_UNCONFIGURED:
    "The video room service is not set up yet. Ask the platform owner to finish its setup.",
  MEETING_ROOM_CLOSED: "This room is not open.",
  MEETING_ROOM_PAUSED: "Video rooms are paused for this workspace right now.",
  MEETING_ROOM_FULL: "This room is full.",
  MEETING_ROOM_REMOVED: "The host removed you from this room.",
  MEETING_ROOM_MONTH_LIMIT:
    "This month's video room time is used up. Ask the platform owner to raise it.",
  MEETING_ROOM_SPEAK_OFF:
    "pi speaking is not switched on for this workspace. Ask the platform owner.",
  MEETING_ROOM_STAFF: "Staff cannot be removed here. End the call instead.",
  MEETING_CONSENT_REQUIRED:
    "Confirm that everyone in the room will be told first.",
  ROOM_PROVIDER_KEY_REJECTED:
    "The video room service did not accept our key. Ask the platform owner to check it.",
  ROOM_PROVIDER_BUSY: "The video room service is busy. Try again shortly.",
  ROOM_PROVIDER_UNREACHABLE:
    "The video room service could not be reached. Try again in a moment.",
};
