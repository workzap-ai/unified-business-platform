"use client";

import { useState, type ReactNode } from "react";
import { Bot, CheckCircle2, Mic, Video } from "lucide-react";
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
import { PiAvatar } from "./pi-avatar";

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
      <div className="space-y-4 py-2 text-center" role="status">
        <span className="mx-auto flex size-14 items-center justify-center rounded-full bg-success/15">
          <CheckCircle2 className="size-7 text-success" aria-hidden />
        </span>
        <div className="space-y-1">
          <p className="text-base font-semibold">
            {done === "ended" ? "The call has closed" : "Thank you for joining"}
          </p>
          <p className="text-sm text-muted-foreground">
            {done === "ended"
              ? "The host ended the call or removed you from it. You can close this page."
              : "You left the call. You can close this page, or join again if you left by mistake."}
          </p>
        </div>
        {done === "left" && (
          <Button variant="secondary" onClick={() => setDone(false)}>
            <Video /> Join again
          </Button>
        )}
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
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <PiAvatar expression="greet" size={48} decorative />
        <div className="min-w-0">
          <p className="text-sm font-semibold">
            You are about to join a video call
          </p>
          <p className="text-xs text-muted-foreground">
            pi, Workzap&apos;s AI assistant, will be in the room. Three things
            to know:
          </p>
        </div>
      </div>
      <ul className="space-y-3">
        <Point
          icon={<Bot className="size-4" aria-hidden />}
          title="pi is an AI"
        >
          It listens and writes down what is said. If the host allows it, pi can
          also speak: it always says first that it is an AI, and its voice is
          computer-generated.
        </Point>
        <Point
          icon={<Mic className="size-4" aria-hidden />}
          title="Your voice becomes text"
        >
          {audio
            ? "Your voice is recorded for a moment only to turn it into text, then deleted. "
            : "What you say is turned into text for this meeting. "}
          Phone, card and ID numbers are removed from the text.
        </Point>
        <Point
          icon={<Video className="size-4" aria-hidden />}
          title="Camera and screen stay off"
        >
          Until you turn them on. If you do, the people in the room see them
          live. Video is never recorded or saved.
        </Point>
      </ul>
      <details className="group rounded-lg border border-border bg-surface-muted px-3 py-2 text-sm">
        <summary className="cursor-pointer select-none font-medium marker:text-muted-foreground">
          More details
        </summary>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-muted-foreground">
          <li>
            The host&apos;s team can read the text. pi may summarise it, and
            after their review points can be saved to your record.
          </li>
          <li>You can leave at any time.</li>
        </ul>
      </details>
      <div className="space-y-1.5">
        <Label htmlFor="room-name">Your name (optional)</Label>
        <Input
          id="room-name"
          value={name}
          maxLength={60}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
          placeholder="So everyone knows who is speaking"
        />
      </div>
      <label className="flex items-start gap-2.5 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 shrink-0 accent-primary"
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
      <div className="space-y-2">
        <Button
          className="h-11 w-full text-base"
          disabled={!agreed || busy}
          loading={busy}
          onClick={() => void enter()}
        >
          <Video /> Join the call
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          {agreed
            ? "Your browser will ask to use your microphone. Press Allow so people can hear you."
            : "Tick the box above to continue."}
        </p>
      </div>
    </div>
  );
}

function Point({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        {icon}
      </span>
      <div className="min-w-0 text-sm">
        <p className="font-medium">{title}</p>
        <p className="text-muted-foreground">{children}</p>
      </div>
    </li>
  );
}
