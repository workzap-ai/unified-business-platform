"use client";

import "@stream-io/video-react-sdk/dist/css/styles.css";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
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
import { Mic, MonitorOff, MonitorUp, Users, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/app/states";
import type { RoomCredentials } from "../meeting-room-service";
import { PiAvatar } from "./pi-avatar";
import { toRomanUrdu } from "./roman-urdu";
import { CopilotPanel, LiveCaptions, useRoomLive } from "./live-view";
import { BlurButton, NoiseButton, QualityProviders } from "./quality-controls";
import {
  PiEye,
  PiScreenBanner,
  usePiAgent,
  usePiScreen,
} from "./pi-screen-watch";
import { SpriteAgent, LIVE_AGENTS } from "../agents/live/sprite-agent";
import { useVoiceShape } from "../agents/live/voice-shape";
import { ScreenCompanion } from "../agents/live/screen-companion";

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
  const screen = usePiScreen();
  const agentKey = usePiAgent();
  const voice = useVoiceShape(isPi ? participant.audioStream : null);
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
        {isPi && LIVE_AGENTS.has(agentKey) ? (
          <div className="relative">
            <SpriteAgent
              agentKey={agentKey}
              level={participant.audioLevel ?? 0}
              voice={voice}
              speaking={participant.isSpeaking}
              listening={!participant.isSpeaking}
              screen={screen.state}
              size={176}
              label="pi, an AI agent"
              className={`rounded-3xl ring-4 ${
                participant.isSpeaking ? "ring-primary" : "ring-transparent"
              }`}
            />
            <PiEye state={screen.state} />
          </div>
        ) : isPi ? (
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
            <PiEye state={screen.state} />
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

/** The agent's cut-out character at the corner of the stage while a screen is shared. */
function Companion() {
  const { useParticipants } = useCallStateHooks();
  const pi = useParticipants().find((p) => p.userId === PI_USER);
  const screen = usePiScreen();
  const agentKey = usePiAgent();
  const voice = useVoiceShape(pi?.audioStream);
  return (
    <ScreenCompanion
      voice={voice}
      agentKey={agentKey}
      state={screen.state}
      level={pi?.audioLevel ?? 0}
      speaking={pi?.isSpeaking ?? false}
    />
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
      aria-label={sharing ? "Stop sharing your screen" : "Share your screen"}
      className={`flex size-11 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        sharing
          ? "bg-primary text-primary-foreground"
          : "bg-muted text-foreground hover:bg-muted/70"
      }`}
    >
      {sharing ? (
        <MonitorOff className="size-5" aria-hidden />
      ) : (
        <MonitorUp className="size-5" aria-hidden />
      )}
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
      className="min-h-12 rounded-xl border border-border bg-surface-muted px-3 py-2.5 text-sm"
    >
      {lines.length === 0 ? (
        <span className="text-muted-foreground">
          Captions appear here while people speak.
        </span>
      ) : (
        lines.map((c, i) => (
          <p key={i} className="leading-snug">
            <span className="mr-1.5 inline-block rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
              {c.user?.name || c.user?.id || c.speaker_id || "Speaker"}
            </span>
            {toRomanUrdu(c.text ?? "")}
          </p>
        ))
      )}
    </div>
  );
}

type MicState = "idle" | "asking" | "ok" | "blocked" | "missing";

/**
 * A microphone check before joining, started only by a button press (the person has agreed to the
 * room, but nothing asks for the microphone until they choose to test it or join). It shows a level
 * bar so "nobody can hear me" is found before the call, not during it. Nothing is recorded or sent:
 * the sound is measured in the browser and dropped when the check stops.
 */
function useMicCheck() {
  const [state, setState] = useState<MicState>("idle");
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState(false);
  const stopper = useRef<() => void>(() => undefined);
  const stop = useCallback(() => stopper.current(), []);
  const start = useCallback(async () => {
    stopper.current();
    setState("asking");
    setHeard(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      let alive = true;
      let frame = 0;
      const tick = () => {
        if (!alive) return;
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) {
          const d = (v - 128) / 128;
          sum += d * d;
        }
        const now = Math.min(1, Math.sqrt(sum / data.length) * 6);
        setLevel(now);
        if (now > 0.12) setHeard(true);
        frame = requestAnimationFrame(tick);
      };
      tick();
      setState("ok");
      stopper.current = () => {
        alive = false;
        cancelAnimationFrame(frame);
        stream.getTracks().forEach((t) => t.stop());
        void context.close().catch(() => undefined);
        stopper.current = () => undefined;
        setLevel(0);
      };
    } catch (e) {
      const name = (e as { name?: string })?.name;
      setState(name === "NotFoundError" ? "missing" : "blocked");
    }
  }, []);
  useEffect(() => () => stopper.current(), []);
  return { state, level, heard, start, stop };
}

function micMessage(state: MicState, heard: boolean): string {
  switch (state) {
    case "asking":
      return "Your browser is asking for permission. Press Allow.";
    case "ok":
      return heard
        ? "I can hear you. The microphone works."
        : "Say a few words: the bar should move.";
    case "blocked":
      return "The microphone is blocked. Click the lock icon next to the address, allow Microphone, then press Test again. You can still join and listen.";
    case "missing":
      return "No microphone was found. You can still join and listen.";
    default:
      return "Press Test, then say a few words. The bar should move.";
  }
}

/** The step before the call: a microphone check, then one clear Join button. */
function Lobby({
  joining,
  error,
  onJoin,
}: {
  joining: boolean;
  error: string;
  onJoin: () => void;
}) {
  const mic = useMicCheck();
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <PiAvatar expression="rest" size={44} decorative />
        <div className="min-w-0">
          <p className="text-sm font-semibold">Ready to join?</p>
          <p className="text-xs text-muted-foreground">
            Check your microphone first, so people can hear you.
          </p>
        </div>
      </div>
      <div className="space-y-2.5 rounded-xl border border-border bg-surface-muted p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-sm font-medium">
            <Mic className="size-4" aria-hidden /> Microphone
          </span>
          <Button
            size="sm"
            variant="secondary"
            disabled={joining || mic.state === "asking"}
            onClick={() => void mic.start()}
          >
            {mic.state === "ok" ? "Test again" : "Test my microphone"}
          </Button>
        </div>
        <div
          className="h-2.5 overflow-hidden rounded-full border border-border bg-surface"
          role="meter"
          aria-label="Microphone level"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(mic.level * 100)}
        >
          <div
            className={`h-full rounded-full transition-[width] duration-75 ${
              mic.heard ? "bg-success" : "bg-primary"
            }`}
            style={{ width: `${Math.round(mic.level * 100)}%` }}
          />
        </div>
        <p
          aria-live="polite"
          className={`text-xs ${
            mic.state === "blocked" || mic.state === "missing"
              ? "text-warning"
              : "text-muted-foreground"
          }`}
        >
          {micMessage(mic.state, mic.heard)}
        </p>
      </div>
      {error && <Notice tone="danger">{error}</Notice>}
      <div className="space-y-2">
        <Button
          className="h-11 w-full text-base"
          onClick={() => {
            mic.stop();
            onJoin();
          }}
          loading={joining}
          disabled={joining}
        >
          <Video /> {error ? "Try again" : "Join the room"}
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          pi (AI) is in this room and writes a transcript. It may speak if the
          host allows it, and says it is an AI first.
        </p>
      </div>
    </div>
  );
}

/** A control with its name under it, so nobody has to guess what a round button does. */
function Control({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="str-video__call-controls flex min-w-12 flex-col items-center gap-1">
      {children}
      <span className="text-[11px] leading-none text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

function Dock({
  onLeave,
  onError,
}: {
  onLeave: () => void;
  onError: (message: string) => void;
}) {
  const { useScreenShareState } = useCallStateHooks();
  const { isMute } = useScreenShareState();
  return (
    <div className="mx-auto flex w-fit max-w-full items-start justify-center gap-3 rounded-3xl border border-border bg-surface-muted/80 px-4 py-3 shadow-sm sm:gap-6">
      <Control label="Mic">
        <ToggleAudioPublishingButton />
      </Control>
      <Control label="Camera">
        <ToggleVideoPublishingButton />
      </Control>
      <Control label="Look">
        <BlurButton />
      </Control>
      <Control label="Sound">
        <NoiseButton />
      </Control>
      <Control label={isMute ? "Share" : "Stop"}>
        <ShareScreen onError={onError} />
      </Control>
      <Control label="Leave">
        <CancelCallButton onLeave={onLeave} />
      </Control>
    </div>
  );
}

/** Captions with translation (or the video service's own while the feature is off), and pi's
 *  private tips and notes for staff. One poll feeds both. */
function LiveView() {
  const state = useRoomLive();
  return (
    <>
      <LiveCaptions state={state} fallback={<Captions />} />
      <CopilotPanel state={state} />
    </>
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
    return <Lobby joining={joining} error={error} onJoin={() => void join()} />;
  }
  return (
    <StreamVideo client={live.client}>
      <StreamCall call={live.call}>
        <StreamTheme>
          <QualityProviders>
            <div className="space-y-3 [&_.str-video__participant-details]:text-white [&_.str-video__participant-details__name]:text-white">
              <RoomBar />
              {error && <Notice tone="danger">{error}</Notice>}
              <SharingBanner />
              <PiScreenBanner />
              <div className="relative h-[56dvh] min-h-72 overflow-hidden rounded-2xl border border-border sm:h-[62dvh]">
                <SpeakerLayout
                  participantsBarPosition="bottom"
                  VideoPlaceholder={Face}
                />
                <Companion />
              </div>
              <LiveView />
              <Dock onLeave={() => leave()} onError={setError} />
              <p className="text-center text-xs text-muted-foreground">
                pi (AI) is writing a transcript of this call. Your camera and
                screen stay off until you turn them on, and video is never
                recorded.
              </p>
              <EndWatch onClosed={() => leave("ended")} />
            </div>
          </QualityProviders>
        </StreamTheme>
      </StreamCall>
    </StreamVideo>
  );
}
