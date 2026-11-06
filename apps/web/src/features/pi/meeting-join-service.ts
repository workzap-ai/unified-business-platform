import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * What a person opening a meeting link can do, with no account: see what the meeting is called,
 * join it (agreeing that their voice is recorded and turned into text), and send their own
 * microphone in one-minute parts. They can read nothing back.
 * Backend: apps/api/app/modules/pi_meetings/guest_routes.py (/api/v1/public/meeting-join).
 */

const BASE = "/public/meeting-join";

export const meetingJoinService = {
  look: (token: string) =>
    apiRequest("GET", `${BASE}/${token}`, z.object({ title: z.string() })),
  join: (token: string, input: { name: string; consent: boolean }) =>
    apiRequest(
      "POST",
      `${BASE}/${token}`,
      z.object({
        guest_token: z.string(),
        slot: z.number(),
        label: z.string(),
      }),
      { body: input },
    ),
  // The part's number (0, 1, 2, ...) and length are all that is sent about time: the server
  // places the part, and sending the same number again replaces it. The token goes in a header
  // so it never lands in a URL or an access log.
  sendPart: (
    guestToken: string,
    part: { seq: number; durationMs: number; audio: Blob },
  ) => {
    const form = new FormData();
    form.set("seq", String(part.seq));
    form.set("duration_ms", String(Math.round(part.durationMs)));
    form.set("file", part.audio, "part");
    return apiRequest(
      "POST",
      `${BASE}/guest/parts`,
      z.object({ segments: z.number(), again: z.boolean().optional() }),
      {
        body: form,
        timeoutMs: 120_000,
        headers: { "X-Guest-Token": guestToken },
      },
    );
  },
  // The person stops: their token sends nothing more.
  leave: (guestToken: string) =>
    apiRequest("POST", `${BASE}/guest/leave`, z.object({ left: z.boolean() }), {
      headers: { "X-Guest-Token": guestToken },
    }),
};
