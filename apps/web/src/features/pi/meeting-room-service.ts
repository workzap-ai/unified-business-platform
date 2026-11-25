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
});
export type MeetingRoom = z.infer<typeof roomSchema>;

export const roomPersonSchema = z.object({
  id: z.string(),
  label: z.string().catch("Guest"),
  staff: z.boolean().catch(false),
  removed: z.boolean().catch(false),
});
export type RoomPerson = z.infer<typeof roomPersonSchema>;

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
  staffToken: (meetingId: string) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/token`,
      roomCredentialsSchema,
    ),
  end: (meetingId: string) =>
    apiRequest(
      "POST",
      `${BASE}/${meetingId}/room/end`,
      z.object({ room: roomSchema }),
    ),
  // A guest who joined by link asks to enter the room: the token is for their own id.
  guestToken: (guestToken: string) =>
    apiRequest("POST", "/public/meeting-room/token", roomCredentialsSchema, {
      headers: { "X-Guest-Token": guestToken },
    }),
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
  MEETING_ROOM_STAFF: "Staff cannot be removed here. End the call instead.",
  MEETING_CONSENT_REQUIRED:
    "Confirm that everyone in the room will be told first.",
  ROOM_PROVIDER_KEY_REJECTED:
    "The video room service did not accept our key. Ask the platform owner to check it.",
  ROOM_PROVIDER_BUSY: "The video room service is busy. Try again shortly.",
  ROOM_PROVIDER_UNREACHABLE:
    "The video room service could not be reached. Try again in a moment.",
};
