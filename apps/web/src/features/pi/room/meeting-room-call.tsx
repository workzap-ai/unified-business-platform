"use client";

import "@stream-io/video-react-sdk/dist/css/styles.css";
import { useEffect, useRef, useState } from "react";
import {
  CallingState,
  CancelCallButton,
  OwnCapability,
  SpeakerLayout,
  StreamCall,
  StreamTheme,
  StreamVideo,
  StreamVideoClient,
  ToggleAudioPublishingButton,
  ToggleVideoPublishingButton,
  useCallStateHooks,
  type Call,
  type StreamVideoParticipant,
} from "@stream-io/video-react-sdk";
import { MonitorOff, MonitorUp, Users, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/app/states";
import type { RoomCredentials } from "../meeting-room-service";
import { PiAvatar } from "./pi-avatar";

/**
 * The call itself. Loaded only on a room page (it carries the video SDK, about 4 MB unpacked), and
 * only in the browser. The person has already agreed on the page that shows this: nothing here asks
 * for the camera or microphone until they press Join. pi is shown as present, and the live captions
 * are for the people in the room; the transcript that is kept comes from the server after the call.
 */

/** Tells the page when the call closed under the person (the host ended it or removed them). */
function EndWatch({ onClosed }: { onClosed: () => void }) {
  const { useCallCallingState } = useCallStateHooks();
  const state = useCallCallingState();
  useEffect(() => {
    if (state === CallingState.LEFT) onClosed();
  }, [state, onClosed]);
  return null;
}

/** The agent's id in the room (the server's `AGENT_USER`): never a staff or guest id. */
const PI_USER = "pi_agent";

/** What a tile shows while a person's camera is off: pi gets its own face that pulses while it talks. */
function Face({ participant }: { participant: StreamVideoParticipant }) {
  const isPi = participant.userId === PI_USER;
  const initials = (participant.name || participant.userId || "?")
    .trim()
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="flex size-full items-center justify-center bg-surface-muted">
      <div className="relative">
        {participant.isSpeaking && (
          <span
            aria-hidden
            className="absolute -inset-3 animate-ping rounded-full bg-primary/25"
          />
        )}
        {isPi ? (
          <div
            className={`relative flex size-28 items-center justify-center rounded-full bg-surface ring-4 transition-transform ${
              participant.isSpeaking
                ? "scale-105 ring-primary"
                : "ring-transparent"
            }`}
          >
            <PiAvatar
              expression={participant.isSpeaking ? "greet" : "rest"}
              size={84}
              className={participant.isSpeaking ? "animate-pulse" : ""}
            />
          </div>
        ) : (
          <div
            className={`relative flex size-20 items-center justify-center rounded-full bg-muted text-xl font-semibold text-foreground ring-4 ${
              participant.isSpeaking ? "ring-primary" : "ring-transparent"
            }`}
          >
            {initials}
          </div>
        )}
      </div>
    </div>
  );
}

/** Live timer, how many people are here, and what pi is doing right now. */
function RoomBar() {
  const { useParticipants } = useCallStateHooks();
  const participants = useParticipants();
  const pi = participants.find((p) => p.userId === PI_USER);
  const people = participants.filter((p) => p.userId !== PI_USER).length;
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const clock = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
  const piText = !pi
    ? "pi writes the transcript"
    : pi.isSpeaking
      ? "pi is speaking"
      : "pi is listening";
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-2.5 py-1 font-medium">
        <span
          aria-hidden
          className="size-2 animate-pulse rounded-full bg-red-500"
        />
        Live {clock}
      </span>
      <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-2.5 py-1">
        <Users className="size-3.5" aria-hidden /> {people}{" "}
        {people === 1 ? "person" : "people"}
      </span>
      <span
        aria-live="polite"
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium ${
          pi?.isSpeaking
            ? "bg-primary text-primary-foreground"
            : "bg-surface-muted"
        }`}
      >
        <PiAvatar expression="micro" size={16} decorative /> {piText} (AI)
      </span>
    </div>
  );
}

/** Share your screen: one clear button, a banner while sharing, and plain words when it cannot work. */
function ShareScreen({ onError }: { onError: (message: string) => void }) {
  const { useScreenShareState, useHasPermissions } = useCallStateHooks();
  const { screenShare, isMute } = useScreenShareState();
  const allowed = useHasPermissions(OwnCapability.SCREENSHARE);
  const supported =
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getDisplayMedia === "function";
  const sharing = !isMute;
  const disabled = !supported || !allowed;
  async function toggle() {
    onError("");
    try {
      await screenShare.toggle();
    } catch (e) {
      const name = (e as { name?: string })?.name;
      onError(
        name === "NotAllowedError"
          ? "Screen sharing was cancelled or not allowed. Press Share again and choose a screen or window."
          : "Could not share your screen. Try again.",
      );
    }
  }
  return (
    <button
      type="button"
      onClick={() => void toggle()}
      disabled={disabled}
      aria-pressed={sharing}
      title={
        !supported
          ? "Screen sharing is not available in this browser or on this device (phones usually cannot share a screen)."
          : !allowed
            ? "You are not allowed to share your screen in this room."
            : sharing
              ? "Stop sharing your screen"
              : "Share your screen"
      }
      className={`inline-flex h-11 items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        sharing
          ? "bg-primary text-primary-foreground"
          : "bg-surface-muted hover:bg-muted"
      }`}
    >
      {sharing ? (
        <MonitorOff className="size-4" aria-hidden />
      ) : (
        <MonitorUp className="size-4" aria-hidden />
      )}
      {sharing ? "Stop sharing" : "Share screen"}
    </button>
  );
}

function SharingBanner() {
  const { useScreenShareState } = useCallStateHooks();
  const { isMute } = useScreenShareState();
  if (isMute) return null;
  return (
    <p
      role="status"
      className="rounded-lg bg-primary/10 px-3 py-2 text-xs font-medium text-primary"
    >
      You are sharing your screen. Everyone in the room, and pi, can see it. pi
      does not read it; only what is said is written down.
    </p>
  );
}

function Captions() {
  const { useCallClosedCaptions } = useCallStateHooks();
  const captions = useCallClosedCaptions() as unknown as Array<{
    text?: string;
    speaker_id?: string;
    user?: { name?: string; id?: string };
  }>;
  const lines = captions.slice(-2).filter((c) => c.text);
  return (
    <div
      aria-live="polite"
      className="min-h-10 rounded-lg bg-surface-muted px-3 py-2 text-sm"
    >
      {lines.length === 0 ? (
        <span className="text-muted-foreground">
          Live captions appear here while people speak.
        </span>
      ) : (
        lines.map((c, i) => (
          <p key={i}>
            <span className="font-medium">
              {c.user?.name || c.user?.id || c.speaker_id || "Speaker"}:
            </span>{" "}
            {c.text}
          </p>
        ))
      )}
    </div>
  );
}

export function MeetingRoomCall({
  credentials,
  onLeft,
}: {
  credentials: RoomCredentials;
  // `ended` when the call closed under them (the host ended it or removed them)
  onLeft: (reason?: "ended") => void;
}) {
  const [live, setLive] = useState<{
    client: StreamVideoClient;
    call: Call;
  } | null>(null);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");
  const kept = useRef<{ client: StreamVideoClient; call: Call } | null>(null);
  const left = useRef(false);

  // the client is made only when the person presses Join, and closed when this page goes away
  useEffect(
    () => () => {
      const s = kept.current;
      kept.current = null;
      if (!s) return;
      void s.call.leave().catch(() => undefined);
      void s.client.disconnectUser().catch(() => undefined);
    },
    [],
  );

  async function join() {
    setJoining(true);
    setError("");
    const client = new StreamVideoClient({
      apiKey: credentials.api_key,
      user: { id: credentials.user_id, name: credentials.name },
      token: credentials.token,
    });
    const call = client.call(credentials.call_type, credentials.call_id);
    kept.current = { client, call };
    try {
      await call.join();
      try {
        await call.microphone.enable();
      } catch {
        setError(
          "The browser did not allow the microphone. Allow it for this page to be heard.",
        );
      }
      setLive({ client, call });
    } catch {
      kept.current = null;
      void client.disconnectUser().catch(() => undefined);
      setError(
        "Could not join the room. It may have ended, or the connection failed. Try again.",
      );
    } finally {
      setJoining(false);
    }
  }

  function leave(reason?: "ended") {
    if (left.current) return;
    left.current = true;
    onLeft(reason);
  }

  if (!live) {
    return (
      <div className="space-y-3">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <PiAvatar expression="micro" size={18} decorative /> pi (AI) is in
          this room and writes a transcript. It may speak if the host allows it,
          and says it is an AI first.
        </p>
        {error && <Notice tone="danger">{error}</Notice>}
        <Button
          onClick={() => void join()}
          loading={joining}
          disabled={joining}
        >
          <Video /> {error ? "Try again" : "Join the room"}
        </Button>
      </div>
    );
  }
  return (
    <StreamVideo client={live.client}>
      <StreamCall call={live.call}>
        <StreamTheme>
          <div className="space-y-3 [&_.str-video__participant-details]:text-white [&_.str-video__participant-details__name]:text-white">
            <RoomBar />
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <PiAvatar expression="micro" size={16} decorative /> pi (AI) is
              writing a transcript of this call.
            </p>
            {error && <Notice tone="danger">{error}</Notice>}
            <SharingBanner />
            <div className="h-[60dvh] min-h-72 overflow-hidden rounded-xl border border-border">
              <SpeakerLayout
                participantsBarPosition="bottom"
                VideoPlaceholder={Face}
              />
            </div>
            <Captions />
            <div className="str-video__call-controls flex flex-wrap items-center justify-center gap-2">
              <ToggleAudioPublishingButton />
              <ToggleVideoPublishingButton />
              <ShareScreen onError={setError} />
              <CancelCallButton onLeave={() => leave()} />
            </div>
            <EndWatch onClosed={() => leave("ended")} />
          </div>
        </StreamTheme>
      </StreamCall>
    </StreamVideo>
  );
}
