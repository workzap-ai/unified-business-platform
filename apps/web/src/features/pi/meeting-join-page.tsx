"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Lock, Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, Skeleton } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Notice } from "@/components/app/states";
import { ApiError } from "@/services/api-client";
import { meetingJoinService } from "./meeting-join-service";
import { MeetingVoiceJoin } from "./meeting-voice-join";

/**
 * The page a meeting link opens (`/join/<token>`), with no sign-in. The person sees what is
 * recorded and who can read it, gives an optional name and agrees; their browser then records
 * their own microphone and sends it, a minute at a time, to the meeting. The sound is turned into
 * text on the server and not kept; this page never shows the transcript or the other people.
 * Backend: apps/api/app/modules/pi_meetings/guest_routes.py.
 */

const PART_MS = 60_000;
const MIN_PART_MS = 1_000;
const TRIES = 3;
/** Answers a retry will not change: the link, the guest or the meeting is gone, or the part is bad. */
const FINAL_STATUSES = [403, 404, 409, 413, 422];
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

type Phase = "ready" | "starting" | "recording" | "finishing" | "ended";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

function clock(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function startError(e: unknown): string {
  const name = e instanceof DOMException ? e.name : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "The browser did not allow the microphone. Allow it for this page and try again.";
  if (name === "NotFoundError")
    return "No microphone was found on this device.";
  if (e instanceof ApiError && e.status === 404)
    return "This link is not open any more.";
  if (e instanceof ApiError && e.code === "MEETING_FULL")
    return "This meeting link is full.";
  return "Could not start. Check the microphone and try again.";
}

export function MeetingJoinPage({ token }: { token: string }) {
  const look = useQuery({
    queryKey: ["meeting-join", token],
    queryFn: () => meetingJoinService.look(token),
    retry: false,
    staleTime: Infinity,
  });
  const [phase, setPhase] = useState<Phase>("ready");
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [sent, setSent] = useState(0);
  const [missed, setMissed] = useState(0);
  const [error, setError] = useState("");
  const [stopped, setStopped] = useState("");

  const run = useRef({
    guest: "",
    stream: null as MediaStream | null,
    recorder: null as MediaRecorder | null,
    mime: undefined as string | undefined,
    t0: 0,
    stopping: false,
    queue: Promise.resolve(),
    seq: 0,
    sent: 0,
    missed: 0,
    partTimer: 0 as unknown as ReturnType<typeof setTimeout>,
    tick: 0 as unknown as ReturnType<typeof setInterval>,
  });

  function release() {
    const r = run.current;
    clearTimeout(r.partTimer);
    clearInterval(r.tick);
    r.stream?.getTracks().forEach((t) => t.stop());
    r.stream = null;
    r.recorder = null;
  }
  useEffect(() => release, []);

  // leaving the page ends the recording; a part already sent is kept
  useEffect(() => {
    if (phase !== "recording") return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [phase]);

  async function send(seq: number, audio: Blob, durationMs: number) {
    const r = run.current;
    for (let attempt = 1; attempt <= TRIES; attempt++) {
      try {
        // the same number on a retry: the server keeps one copy of each part
        await meetingJoinService.sendPart(r.guest, { seq, durationMs, audio });
        r.sent += 1;
        setSent(r.sent);
        return;
      } catch (e) {
        if (e instanceof ApiError && e.code === "MEETING_PART_ANALYSED") {
          // the host's analysis already holds that minute: nothing was lost, nothing more to send
          r.sent += 1;
          setSent(r.sent);
          return;
        }
        if (e instanceof ApiError && FINAL_STATUSES.includes(e.status)) {
          if (e.status === 404) {
            // the host closed the meeting, removed this person or stopped the link
            r.stopping = true;
            clearTimeout(r.partTimer);
            setStopped(
              "The host has closed the meeting or the link. Nothing more is being recorded.",
            );
            if (r.recorder && r.recorder.state !== "inactive")
              r.recorder.stop();
            release();
            setPhase("ended");
          }
          break;
        }
        // 429 (a part came too soon, or the last one is still being read) and network errors wait
        // and retry: waiting longer each time
        if (attempt < TRIES) await sleep(4000 * attempt);
      }
    }
    r.missed += 1;
    setMissed(r.missed);
  }

  function startPart() {
    const r = run.current;
    if (!r.stream || r.stopping) return;
    const startedAt = performance.now();
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(r.stream, {
      mimeType: r.mime,
      audioBitsPerSecond: 32_000,
    });
    r.recorder = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    recorder.onstop = () => {
      const durationMs = performance.now() - startedAt;
      if (durationMs < MIN_PART_MS || chunks.length === 0) return;
      const audio = new Blob(chunks, { type: recorder.mimeType || r.mime });
      // one at a time, in order, so a slow connection never reorders the minutes
      const seq = r.seq++;
      r.queue = r.queue.then(() => send(seq, audio, durationMs));
    };
    recorder.start();
    r.partTimer = setTimeout(() => {
      if (r.stopping) return;
      recorder.stop();
      startPart();
    }, PART_MS);
  }

  async function start() {
    const r = run.current;
    setError("");
    setPhase("starting");
    r.stopping = false;
    r.queue = Promise.resolve();
    r.seq = 0;
    r.sent = 0;
    r.missed = 0;
    setSent(0);
    setMissed(0);
    r.mime = pickMime();
    try {
      r.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      // join only once the microphone is open, so no one is counted in who never recorded
      const joined = await meetingJoinService.join(token, {
        name: name.trim(),
        consent: agreed,
      });
      r.guest = joined.guest_token;
      r.t0 = performance.now();
      r.tick = setInterval(() => setElapsed(performance.now() - r.t0), 500);
      startPart();
      setPhase("recording");
    } catch (e) {
      release();
      setError(startError(e));
      setPhase("ready");
    }
  }

  async function stop() {
    const r = run.current;
    if (phase !== "recording") return;
    setPhase("finishing");
    r.stopping = true;
    clearTimeout(r.partTimer);
    const recorder = r.recorder;
    if (recorder && recorder.state !== "inactive") {
      await new Promise<void>((resolve) => {
        recorder.addEventListener("stop", () => resolve(), { once: true });
        recorder.stop();
      });
    }
    release();
    await r.queue; // every part has been sent (or given up on)
    // tell the server this person has left, so the link's token sends nothing more
    await meetingJoinService.leave(r.guest).catch(() => undefined);
    setPhase("ended");
  }

  if (look.isPending)
    return (
      <Shell>
        <Skeleton className="h-40 w-full" />
      </Shell>
    );
  if (look.isError)
    return (
      <Shell>
        <Notice tone="warning" title="This link is not open">
          The meeting may have ended, the link may have expired, or the host
          closed it. Ask the host for a new link.
        </Notice>
      </Shell>
    );

  // the host set pi to talk with whoever opens this link: a different page, with its own consent
  if (look.data.pi_voice)
    return (
      <Shell>
        <MeetingVoiceJoin token={token} title={look.data.title} />
      </Shell>
    );

  return (
    <Shell>
      <Card>
        <CardBody className="space-y-4">
          <div>
            <p className="text-xs text-muted-foreground">You are joining</p>
            <h1 className="text-lg font-semibold">{look.data.title}</h1>
          </div>

          {phase === "ended" ? (
            <div className="space-y-2" role="status">
              <p className="flex items-center gap-2 text-sm font-medium">
                <CheckCircle2 className="size-4 text-success" aria-hidden />
                {stopped
                  ? "Recording stopped"
                  : "Thank you, you can close this page"}
              </p>
              <p className="text-xs text-muted-foreground">
                {stopped ||
                  `${sent} minute${sent === 1 ? "" : "s"} of your voice ${sent === 1 ? "was" : "were"} added to the meeting.`}
                {missed > 0 && ` ${missed} could not be sent.`}
              </p>
            </div>
          ) : phase === "recording" || phase === "finishing" ? (
            <div className="space-y-3" role="status">
              <p className="flex items-center gap-2 text-sm font-medium">
                <span className="size-2 animate-pulse rounded-full bg-danger" />
                {phase === "finishing"
                  ? "Sending the last part…"
                  : "Recording your microphone"}
                <span className="tabular-nums text-muted-foreground">
                  {clock(elapsed)}
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                {sent} part{sent === 1 ? "" : "s"} sent
                {missed > 0 ? `, ${missed} could not be sent` : ""}. Keep this
                page open while you talk.
              </p>
              <Button
                variant="secondary"
                onClick={() => void stop()}
                disabled={phase === "finishing"}
              >
                <Square /> Stop and leave
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-1.5 rounded-lg border border-border bg-surface-muted p-3 text-xs">
                <p className="flex items-center gap-1.5 font-medium">
                  <Lock className="size-3.5" aria-hidden /> Before you join
                </p>
                <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
                  <li>
                    Your microphone is recorded and turned into text for this
                    meeting. The sound is sent to a speech-to-text service to do
                    this.
                  </li>
                  <li>
                    The sound itself is not kept. Phone, card and ID numbers are
                    taken out of the text.
                  </li>
                  <li>
                    The host&apos;s team can read what you say. pi may summarise
                    it, and after their review points from it can be saved to
                    the customer&apos;s record. You will not see the text or the
                    other people.
                  </li>
                  <li>
                    You can stop at any time. Only the host can delete what you
                    already said.
                  </li>
                </ul>
              </div>
              <div>
                <Label htmlFor="join-name">Your name (optional)</Label>
                <Input
                  id="join-name"
                  value={name}
                  maxLength={60}
                  disabled={phase === "starting"}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="So the transcript says who spoke"
                />
              </div>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-primary"
                  checked={agreed}
                  disabled={phase === "starting"}
                  onChange={(e) => setAgreed(e.target.checked)}
                />
                <span>
                  I agree that my voice is recorded and turned into text for
                  this meeting.
                </span>
              </label>
              {error && <Notice tone="danger">{error}</Notice>}
              <Button
                disabled={!agreed || phase === "starting"}
                loading={phase === "starting"}
                onClick={() => void start()}
              >
                <Mic /> Join and start recording
              </Button>
            </div>
          )}
        </CardBody>
      </Card>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col justify-center gap-4 px-4 py-8">
      {children}
    </main>
  );
}
