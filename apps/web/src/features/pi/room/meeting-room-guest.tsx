"use client";

import { useState } from "react";
import { CheckCircle2, Lock, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Notice } from "@/components/app/states";
import { ApiError } from "@/services/api-client";
import { meetingJoinService } from "../meeting-join-service";
import {
  meetingRoomService,
  type RoomCredentials,
} from "../meeting-room-service";
import { MeetingRoomCall } from "./meeting-room-lazy";

/**
 * A customer opening the meeting link of a video room. They see what happens to their voice, give an
 * optional name and agree; only then is a token made for them (their own id, this one call) and the
 * room offered. Nothing asks for the camera or microphone before they press Join in the room.
 */

const KEPT = (token: string) => `meeting-room-guest:${token}`;
function kept(token: string): string {
  try {
    return window.sessionStorage.getItem(KEPT(token)) ?? "";
  } catch {
    return "";
  }
}
function keep(token: string, guest: string) {
  try {
    if (guest) window.sessionStorage.setItem(KEPT(token), guest);
    else window.sessionStorage.removeItem(KEPT(token));
  } catch {
    // a private window may refuse storage: a reload then asks again
  }
}

function why(e: unknown): string {
  if (e instanceof ApiError && e.code === "MEETING_ROOM_CLOSED")
    return "This room is not open. Ask the host to open it, then try again.";
  if (e instanceof ApiError && e.code === "MEETING_ROOM_REMOVED")
    return "The host removed you from this room, so you cannot join it again.";
  if (e instanceof ApiError && e.code === "MEETING_ROOM_FULL")
    return "This room is full.";
  if (e instanceof ApiError && e.code === "MEETING_ROOM_PAUSED")
    return "Video rooms are paused right now. Ask the host.";
  if (e instanceof ApiError && e.code === "MEETING_FULL")
    return "This meeting link is full.";
  if (e instanceof ApiError && e.status === 404)
    return "This link is not open any more.";
  return "Could not join. Check your connection and try again.";
}

export function MeetingRoomGuest({
  token,
  audio = false,
}: {
  token: string;
  audio?: boolean;
}) {
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [credentials, setCredentials] = useState<RoomCredentials | null>(null);
  const [done, setDone] = useState<false | "left" | "ended">(false);

  async function enter() {
    setBusy(true);
    setError("");
    try {
      // the same person after a reload keeps their place; a new visit joins with consent
      let guest = kept(token);
      if (guest) {
        try {
          await meetingJoinService.resume(guest);
        } catch {
          guest = "";
        }
      }
      if (!guest) {
        const joined = await meetingJoinService.join(token, {
          name: name.trim(),
          consent: true,
        });
        guest = joined.guest_token;
        keep(token, guest);
      }
      setCredentials(await meetingRoomService.guestToken(guest));
    } catch (e) {
      setError(why(e));
    } finally {
      setBusy(false);
    }
  }

  if (done)
    return (
      <div className="space-y-2" role="status">
        <p className="flex items-center gap-2 text-sm font-medium">
          <CheckCircle2 className="size-4 text-success" aria-hidden />
          {done === "ended"
            ? "The call has closed"
            : "Thank you, you can close this page"}
        </p>
        <p className="text-xs text-muted-foreground">
          {done === "ended"
            ? "The host ended the call or removed you from it. You can close this page."
            : "You left the call. If you left by mistake, open the link again."}
        </p>
      </div>
    );
  if (credentials)
    return (
      <MeetingRoomCall
        credentials={credentials}
        onLeft={(reason) => {
          setCredentials(null);
          setDone(reason ?? "left");
        }}
      />
    );
  return (
    <div className="space-y-3">
      <div className="space-y-1.5 rounded-lg border border-border bg-surface-muted p-3 text-xs">
        <p className="flex items-center gap-1.5 font-medium">
          <Lock className="size-3.5" aria-hidden /> Before you join
        </p>
        <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
          <li>
            This is a video call. pi, an AI assistant, is in the room: it
            listens and writes down what is said. It does not speak.
          </li>
          <li>
            {audio
              ? "Your voice is recorded briefly, only to turn what you say into text for this meeting. The recording is deleted as soon as the text is made. Phone, card and ID numbers are taken out of the text."
              : "What you say is turned into text for this meeting. Phone, card and ID numbers are taken out of the text."}
          </li>
          <li>
            The host&apos;s team can read it. pi may summarise it, and after
            their review points from it can be saved to the customer&apos;s
            record.
          </li>
          <li>You can leave at any time.</li>
        </ul>
      </div>
      <div>
        <Label htmlFor="room-name">Your name (optional)</Label>
        <Input
          id="room-name"
          value={name}
          maxLength={60}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
          placeholder="So the transcript says who spoke"
        />
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-primary"
          checked={agreed}
          disabled={busy}
          onChange={(e) => setAgreed(e.target.checked)}
        />
        <span>
          {audio
            ? "I agree that my voice is recorded briefly and transcribed by pi (an AI) for this meeting."
            : "I agree that what I say is transcribed by pi (an AI) for this meeting."}
        </span>
      </label>
      {error && <Notice tone="danger">{error}</Notice>}
      <Button
        disabled={!agreed || busy}
        loading={busy}
        onClick={() => void enter()}
      >
        <Video /> Continue to the room
      </Button>
    </div>
  );
}
