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
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { ApiError } from "@/services/api-client";
import { clock, meetingIntelService } from "../meeting-intel-service";

/**
 * Records a meeting in the browser and sends it for transcription as it goes.
 *
 * The recording is cut into self-contained parts of a few minutes. Each part goes to the server
 * on its own and is transcribed there, so a long meeting never meets an upload limit, a dropped
 * connection costs one part and not the meeting, and a retry replaces a part instead of
 * duplicating it. By default the audio is not stored: only the redacted words are kept. When the
 * person chooses to save the recording and the workspace has a storage bucket connected, the audio
 * goes with each part and the shared screen is recorded as video parts, all in that bucket.
 *
 * Backend: apps/api/app/modules/pi_meetings/recording_routes.py and media_routes.py.
 */

const PART_MS = 4 * 60_000;
const VIDEO_PART_MS = 2 * 60_000;
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
const VIDEO_MIMES = [
  "video/webm;codecs=vp9,opus",
  "video/webm;codecs=vp8,opus",
  "video/webm",
  "video/mp4",
];

type Phase = "idle" | "starting" | "recording" | "finishing";
type Source = "mic" | "mic+tab";
type Part = {
  index: number;
  offsetMs: number;
  durationMs: number;
  audio: Blob;
};
type VideoPart = {
  index: number;
  offsetMs: number;
  durationMs: number;
  video: Blob;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

function pickVideoMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return VIDEO_MIMES.find((m) => MediaRecorder.isTypeSupported(m));
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
  const [mapped, setMapped] = useState(0);
  const [saveRecording, setSaveRecording] = useState(false);
  const [videoSent, setVideoSent] = useState(0);
  const [videoSkipped, setVideoSkipped] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // saving a recording needs a storage bucket connected in Settings -> Integrations
  const storage = useScopedQuery(
    ["pi", "meeting-intel", "storage"],
    () => meetingIntelService.storageConnected(),
    { staleTime: 60_000 },
  );
  // with a bucket the audio and the shared screen's video are saved there; without one only the
  // audio is saved, in the platform's database, and video is not offered
  const hasBucket = storage.data?.storage === true;

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
    analysis: Promise.resolve(),
    keep: false,
    videoStream: null as MediaStream | null,
    videoRecorder: null as MediaRecorder | null,
    videoMime: undefined as string | undefined,
    videoIndex: 0,
    videoSent: 0,
    videoSkipped: 0,
    videoQueue: Promise.resolve(),
    videoTimer: 0 as unknown as ReturnType<typeof setTimeout>,
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

  // Ending the meeting closes the transcript and then writes the summary and the requirement list,
  // so they are saved even if nobody presses "Analyse". One mutation, so it finishes even after the
  // page has moved on to the review screen.
  const complete = useScopedMutation(
    async (v: { duration_ms: number; parts: number; skipped: number }) => {
      const done = await meetingIntelService.completeRecording(id, v);
      const analysed = await meetingIntelService.analyse(id).catch(() => null);
      return { done, analysed };
    },
    {
      invalidate: [
        ["pi", "meeting-intel", id],
        ["pi", "meeting-intel"],
      ],
      success: ({ done, analysed }) => {
        const gaps =
          done.skipped > 0
            ? ` ${done.skipped} part${done.skipped === 1 ? "" : "s"} could not be transcribed.`
            : "";
        if (analysed === null)
          return `Transcript saved. The summary could not be written: press “Analyse with pi”.${gaps}`;
        return analysed.insights === 0
          ? `Transcript and summary saved: nothing worth noting.${gaps}`
          : `Transcript, summary and ${analysed.insights} finding${analysed.insights === 1 ? "" : "s"} saved for review.${gaps}`;
      },
      toastErrors: false,
      onSuccess: () => setPhase("idle"),
    },
  );

  const release = useCallback(() => {
    const r = run.current;
    clearTimeout(r.partTimer);
    clearTimeout(r.videoTimer);
    clearInterval(r.tick);
    r.inputs.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    r.stream?.getTracks().forEach((t) => t.stop());
    void r.ctx?.close().catch(() => undefined);
    void r.wake?.release().catch(() => undefined);
    r.inputs = [];
    r.stream = null;
    r.videoStream = null;
    r.ctx = null;
    r.recorder = null;
    r.videoRecorder = null;
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
          const saved = await meetingIntelService.uploadPart(id, {
            ...part,
            keep: run.current.keep,
          });
          if (run.current.keep && !saved.saved)
            setNotice(
              "Some audio could not be saved to storage. The transcript is safe.",
            );
          run.current.parts += 1;
          setSent(run.current.parts);
          // map what was just said while the meeting goes on; best effort, one at a time, and the
          // recording never waits for it (the full analysis at the end covers everything anyway)
          run.current.analysis = run.current.analysis.then(() =>
            meetingIntelService
              .analysePart(id, part.index)
              .then((r) => setMapped((m) => m + r.insights))
              .catch(() => undefined),
          );
          return;
        } catch (e) {
          if (e instanceof ApiError && e.code === "MEETING_PART_ANALYSED") {
            // a retry of a part the server already stored and analysed: nothing was lost
            run.current.parts += 1;
            setSent(run.current.parts);
            return;
          }
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

  const sendVideo = useCallback(
    async (part: VideoPart) => {
      for (let attempt = 1; attempt <= TRIES; attempt++) {
        try {
          await meetingIntelService.uploadVideo(id, part);
          run.current.videoSent += 1;
          setVideoSent(run.current.videoSent);
          return;
        } catch (e) {
          if (e instanceof ApiError && FINAL_STATUSES.includes(e.status)) break;
          if (attempt < TRIES) await sleep(2000 * attempt);
        }
      }
      run.current.videoSkipped += 1;
      setVideoSkipped(run.current.videoSkipped);
      setNotice(
        "Some video could not be saved to storage. The transcript is safe.",
      );
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

  function startVideoPart() {
    const r = run.current;
    const stream = r.videoStream;
    if (!stream || r.stopping) return;
    // the person pressed the browser's "Stop sharing": the audio and transcript carry on
    if (stream.getVideoTracks().every((t) => t.readyState === "ended")) return;
    const index = r.videoIndex++;
    const startedAt = performance.now();
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream, {
      mimeType: r.videoMime,
      videoBitsPerSecond: 700_000,
      audioBitsPerSecond: 48_000,
    });
    r.videoRecorder = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    recorder.onstop = () => {
      const durationMs = performance.now() - startedAt;
      if (durationMs < MIN_PART_MS || chunks.length === 0) return;
      const part: VideoPart = {
        index,
        offsetMs: startedAt - r.t0,
        durationMs,
        video: new Blob(chunks, { type: recorder.mimeType || r.videoMime }),
      };
      r.videoQueue = r.videoQueue.then(() => sendVideo(part));
    };
    recorder.start();
    r.videoTimer = setTimeout(() => {
      if (r.stopping) return;
      recorder.stop();
      startVideoPart();
    }, VIDEO_PART_MS);
  }

  async function start() {
    const r = run.current;
    setError("");
    setNotice("");
    setSent(0);
    setSkipped(0);
    setMapped(0);
    setVideoSent(0);
    setVideoSkipped(0);
    setPhase("starting");
    r.index = 0;
    r.parts = 0;
    r.skipped = 0;
    r.stopping = false;
    r.queue = Promise.resolve();
    r.analysis = Promise.resolve();
    r.keep = saveRecording;
    r.videoIndex = 0;
    r.videoSent = 0;
    r.videoSkipped = 0;
    r.videoQueue = Promise.resolve();
    r.mime = pickMime();
    r.videoMime = pickVideoMime();
    let sharedVideo: MediaStreamTrack[] = [];
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
        // the picture is kept only when the recording is being saved; otherwise it is dropped now
        if (r.keep && hasBucket) sharedVideo = shared.getVideoTracks();
        else shared.getVideoTracks().forEach((t) => t.stop());
        if (audio.length === 0) throw new Error("NO_TAB_AUDIO");
        r.ctx.createMediaStreamSource(new MediaStream(audio)).connect(mixed);
      }
      r.stream = mixed.stream;
      if (sharedVideo.length > 0)
        r.videoStream = new MediaStream([
          ...sharedVideo,
          ...mixed.stream.getAudioTracks(),
        ]);
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
      startVideoPart();
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
    clearTimeout(r.videoTimer);
    const total = performance.now() - r.t0;
    const recorder = r.recorder;
    if (recorder && recorder.state !== "inactive") {
      await new Promise<void>((resolve) => {
        recorder.addEventListener("stop", () => resolve(), { once: true });
        recorder.stop();
      });
    }
    const videoRecorder = r.videoRecorder;
    if (videoRecorder && videoRecorder.state !== "inactive") {
      await new Promise<void>((resolve) => {
        videoRecorder.addEventListener("stop", () => resolve(), { once: true });
        videoRecorder.stop();
      });
    }
    release();
    await r.queue; // every part has been sent (or given up on)
    await r.videoQueue; // and every video part
    await r.analysis; // and every live analysis has finished before the transcript is closed
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
            pi writes down what is said while you record and maps the problems
            and requirements as the meeting goes on. A call, a pause or a bad
            minute does not stop it. The words are kept with phone, card and ID
            numbers removed. The audio and video are not kept unless you choose
            to save the recording below. Consent was recorded when this meeting
            was created.
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
                {mapped > 0 &&
                  `, ${mapped} requirement${mapped === 1 ? "" : "s"} mapped`}
                {videoSent + videoSkipped > 0 &&
                  `, video ${videoSent} saved${videoSkipped > 0 ? `, ${videoSkipped} not saved` : ""}`}
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

        {(phase === "idle" || phase === "starting") && (
          <div className="text-xs">
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5 size-4 accent-primary"
                checked={saveRecording}
                disabled={busy}
                onChange={(e) => setSaveRecording(e.target.checked)}
              />
              <span>
                <span className="font-medium">
                  Save the recording so it can be played back later
                </span>
                <span className="block text-muted-foreground">
                  {hasBucket
                    ? "The audio is saved, and for an online meeting the shared screen is saved as video, in your own storage. "
                    : "The audio is saved. To save video as well, connect a storage bucket in Settings → Integrations. "}
                  It is kept for a year unless your workspace sets another time.
                </span>
              </span>
            </label>
          </div>
        )}

        {notice && <Notice tone="warning">{notice}</Notice>}
        {error && <Notice tone="danger">{error}</Notice>}
      </CardBody>
    </Card>
  );
}
