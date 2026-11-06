"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Notice } from "@/components/app/states";
import { useScopedMutation } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { clock, meetingIntelService } from "../meeting-intel-service";

/**
 * Records a meeting in the browser and sends it for transcription as it goes.
 *
 * The recording is cut into self-contained parts of a few minutes. Each part goes to the server
 * on its own and is transcribed there, so a long meeting never meets an upload limit, a dropped
 * connection costs one part and not the meeting, and a retry replaces a part instead of
 * duplicating it. The audio is not stored anywhere: only the redacted words are kept.
 *
 * Backend: apps/api/app/modules/pi_meetings/recording_routes.py.
 */

const PART_MS = 4 * 60_000;
const MIN_PART_MS = 1_000;
const TRIES = 3;
/** Answers that will not change on a retry: skip the part (or stop) instead of sending it again. */
const FINAL_STATUSES = [403, 404, 409, 413, 422];
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

type Phase = "idle" | "starting" | "recording" | "finishing";
type Source = "mic" | "mic+tab";
type Part = {
  index: number;
  offsetMs: number;
  durationMs: number;
  audio: Blob;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

function startError(e: unknown): string {
  const name = e instanceof DOMException ? e.name : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "The browser did not allow the microphone. Allow it for this site and try again.";
  if (name === "NotFoundError")
    return "No microphone was found on this device.";
  if (e instanceof Error && e.message === "NO_TAB_AUDIO")
    return "No audio was shared. Choose a tab or screen and tick “Share audio”, or record the microphone only.";
  return "Recording could not start. Check the microphone and try again.";
}

export function MeetingRecorder({ id }: { id: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [source, setSource] = useState<Source>("mic");
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [sent, setSent] = useState(0);
  const [skipped, setSkipped] = useState(0);
  const [error, setError] = useState("");

  const run = useRef({
    stream: null as MediaStream | null,
    inputs: [] as MediaStream[],
    ctx: null as AudioContext | null,
    recorder: null as MediaRecorder | null,
    mime: undefined as string | undefined,
    t0: 0,
    index: 0,
    parts: 0,
    skipped: 0,
    stopping: false,
    queue: Promise.resolve(),
    partTimer: 0 as unknown as ReturnType<typeof setTimeout>,
    tick: 0 as unknown as ReturnType<typeof setInterval>,
    wake: null as { release: () => Promise<void> } | null,
  });

  // Sharing a call tab needs getDisplayMedia (not on phones); read after hydration, never on the server.
  const canShareTab = useSyncExternalStore(
    () => () => undefined,
    () => !!navigator.mediaDevices?.getDisplayMedia,
    () => false,
  );

  const complete = useScopedMutation(
    (v: { duration_ms: number; parts: number; skipped: number }) =>
      meetingIntelService.completeRecording(id, v),
    {
      invalidate: [
        ["pi", "meeting-intel", id],
        ["pi", "meeting-intel"],
      ],
      success: (r) =>
        r.skipped > 0
          ? `Transcript ready. ${r.skipped} part${r.skipped === 1 ? "" : "s"} could not be transcribed.`
          : "Transcript ready",
      toastErrors: false,
      onSuccess: () => setPhase("idle"),
    },
  );

  const release = useCallback(() => {
    const r = run.current;
    clearTimeout(r.partTimer);
    clearInterval(r.tick);
    r.inputs.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    r.stream?.getTracks().forEach((t) => t.stop());
    void r.ctx?.close().catch(() => undefined);
    void r.wake?.release().catch(() => undefined);
    r.inputs = [];
    r.stream = null;
    r.ctx = null;
    r.recorder = null;
    r.wake = null;
    setLevel(0);
  }, []);

  // leaving the page ends the recording; a part already sent is kept
  useEffect(() => {
    if (phase !== "recording") return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [phase]);
  useEffect(() => release, [release]);

  const send = useCallback(
    async (part: Part) => {
      for (let attempt = 1; attempt <= TRIES; attempt++) {
        try {
          await meetingIntelService.uploadPart(id, part);
          run.current.parts += 1;
          setSent(run.current.parts);
          return;
        } catch (e) {
          if (e instanceof ApiError && FINAL_STATUSES.includes(e.status)) {
            if (e.status !== 422) {
              // consent, meeting or permission problem: nothing more can be sent
              setError(
                e.status === 409
                  ? "This meeting has already been reviewed. Start a new one."
                  : "This recording can no longer be saved to the meeting.",
              );
            }
            break;
          }
          if (attempt < TRIES) await sleep(1500 * attempt);
        }
      }
      run.current.skipped += 1;
      setSkipped(run.current.skipped);
    },
    [id],
  );

  function startPart() {
    const r = run.current;
    if (!r.stream || r.stopping) return;
    const index = r.index++;
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
      const part: Part = {
        index,
        offsetMs: startedAt - r.t0,
        durationMs,
        audio: new Blob(chunks, { type: recorder.mimeType || r.mime }),
      };
      r.queue = r.queue.then(() => send(part));
    };
    recorder.start();
    r.partTimer = setTimeout(() => {
      if (r.stopping) return;
      recorder.stop(); // ends this part; the next one starts at once on the same stream
      startPart();
    }, PART_MS);
  }

  async function start() {
    const r = run.current;
    setError("");
    setSent(0);
    setSkipped(0);
    setPhase("starting");
    r.index = 0;
    r.parts = 0;
    r.skipped = 0;
    r.stopping = false;
    r.queue = Promise.resolve();
    r.mime = pickMime();
    try {
      const mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      r.inputs = [mic];
      r.ctx = new AudioContext();
      const mixed = r.ctx.createMediaStreamDestination();
      r.ctx.createMediaStreamSource(mic).connect(mixed);
      if (source === "mic+tab") {
        // an online call: the other side is heard through the shared tab or screen audio
        const shared = await navigator.mediaDevices.getDisplayMedia({
          video: true,
          audio: true,
        });
        r.inputs.push(shared);
        const audio = shared.getAudioTracks();
        shared.getVideoTracks().forEach((t) => t.stop());
        if (audio.length === 0) throw new Error("NO_TAB_AUDIO");
        r.ctx.createMediaStreamSource(new MediaStream(audio)).connect(mixed);
      }
      r.stream = mixed.stream;
      const meter = r.ctx.createAnalyser();
      meter.fftSize = 512;
      r.ctx.createMediaStreamSource(mixed.stream).connect(meter);
      const samples = new Uint8Array(meter.fftSize);
      r.t0 = performance.now();
      r.tick = setInterval(() => {
        setElapsed(performance.now() - r.t0);
        meter.getByteTimeDomainData(samples);
        let peak = 0;
        for (const v of samples) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(Math.min(1, peak / 64));
      }, 250);
      try {
        // keeps the screen on so the browser does not pause the recording
        r.wake =
          (await (
            navigator as Navigator & {
              wakeLock?: {
                request: (
                  t: "screen",
                ) => Promise<{ release: () => Promise<void> }>;
              };
            }
          ).wakeLock?.request("screen")) ?? null;
      } catch {
        r.wake = null; // not essential
      }
      startPart();
      setPhase("recording");
    } catch (e) {
      release();
      setError(startError(e));
      setPhase("idle");
    }
  }

  async function stop() {
    const r = run.current;
    if (phase !== "recording") return;
    setPhase("finishing");
    r.stopping = true;
    clearTimeout(r.partTimer);
    const total = performance.now() - r.t0;
    const recorder = r.recorder;
    if (recorder && recorder.state !== "inactive") {
      await new Promise<void>((resolve) => {
        recorder.addEventListener("stop", () => resolve(), { once: true });
        recorder.stop();
      });
    }
    release();
    await r.queue; // every part has been sent (or given up on)
    if (r.parts === 0) {
      setError(
        r.skipped > 0
          ? "The recording could not be transcribed. Check your connection and try again."
          : "Nothing was recorded.",
      );
      setPhase("idle");
      return;
    }
    complete.mutate(
      { duration_ms: Math.round(total), parts: r.parts, skipped: r.skipped },
      {
        onError: (e) => {
          setError(
            e instanceof ApiError && e.code === "TRANSCRIPT_EMPTY"
              ? "No speech was found in the recording."
              : "The transcript could not be finished. Try recording again.",
          );
          setPhase("idle");
        },
      },
    );
  }

  const busy = phase === "starting" || phase === "finishing";
  return (
    <Card>
      <CardBody className="space-y-4">
        <div>
          <h2 className="text-sm font-semibold">Record this meeting</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            pi writes down what is said while you record. The audio is not
            stored: only the words are kept, with phone, card and ID numbers
            removed. Consent was recorded when this meeting was created.
          </p>
        </div>

        {phase === "idle" || phase === "starting" ? (
          <div className="flex flex-wrap items-end gap-3">
            {canShareTab && (
              <div className="min-w-56">
                <Label htmlFor="record-source">What to record</Label>
                <NativeSelect
                  id="record-source"
                  value={source}
                  onChange={(e) => setSource(e.target.value as Source)}
                  disabled={busy}
                >
                  <option value="mic">Microphone (in person or phone)</option>
                  <option value="mic+tab">
                    Microphone and a call tab or screen (online meeting)
                  </option>
                </NativeSelect>
              </div>
            )}
            <Button loading={phase === "starting"} onClick={() => void start()}>
              <Mic /> Start recording
            </Button>
          </div>
        ) : (
          <div className="space-y-3" role="status" aria-live="polite">
            <div className="flex flex-wrap items-center gap-4">
              <span className="flex items-center gap-2 text-sm font-medium">
                <span
                  className="size-2.5 animate-pulse rounded-full bg-danger"
                  aria-hidden="true"
                />
                {phase === "finishing" ? "Finishing…" : "Recording"}
                <span className="tabular text-muted-foreground">
                  {clock(elapsed) || "0:00"}
                </span>
              </span>
              <div
                className="h-2 w-40 overflow-hidden rounded-full bg-surface-sunken"
                aria-hidden="true"
              >
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-200"
                  style={{ width: `${Math.round(level * 100)}%` }}
                />
              </div>
              <span className="text-xs text-muted-foreground">
                {sent} part{sent === 1 ? "" : "s"} transcribed
                {skipped > 0 && `, ${skipped} skipped`}
              </span>
            </div>
            <Button
              variant="danger"
              loading={phase === "finishing"}
              onClick={() => void stop()}
            >
              <Square /> Stop and transcribe
            </Button>
          </div>
        )}

        {error && <Notice tone="danger">{error}</Notice>}
      </CardBody>
    </Card>
  );
}
