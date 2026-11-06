"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Lock, Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/display";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/controls";
import { Notice } from "@/components/app/states";
import { ApiError } from "@/services/api-client";
import { meetingJoinService } from "./meeting-join-service";

/**
 * The link page when the host has set pi to talk (`pi_voice`). The person talks with pi, an AI
 * assistant: pi says so first, asks one question at a time, and listens. This page opens the
 * microphone, notices when the person has finished a sentence (a simple volume check, no model),
 * sends that one clip, and says pi's reply aloud with the browser's own speech. The sound is turned
 * into text on the server and not kept. While pi speaks the microphone is not listened to, so pi
 * never answers itself; "Stop" ends the conversation at any moment, and if the host mutes pi
 * the page says so and ends. Backend: apps/api/app/modules/pi_meetings/voice_routes.py.
 *
 * Limits of this first version: pi's voice is the browser's built-in one (quality and Urdu support
 * depend on the device), one person talks with pi at a time, and a headset avoids pi's voice being
 * picked up by the microphone.
 */

const POLL_MS = 60;
const SPEECH_RMS = 0.02; // louder than this counts as speaking
const MIN_SPEECH_MS = 400;
const END_SILENCE_MS = 1_200;
const MAX_CLIP_MS = 40_000;
const IDLE_RESET_MS = 25_000; // nobody spoke: start a fresh clip so it stays small
const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

type Phase = "ready" | "starting" | "talking" | "ended";
type Mood = "speaking" | "listening" | "thinking";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function pickMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
}

/** The browser says the words aloud and resolves when it has finished (or cannot speak). */
function say(words: string): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      resolve();
      return;
    }
    const utter = new SpeechSynthesisUtterance(words);
    // Urdu script gets an Urdu voice if there is one; otherwise the device's default is used
    utter.lang = /[؀-ۿ]/.test(words) ? "ur-PK" : "en-GB";
    const guard = setTimeout(resolve, 30_000);
    const done = () => {
      clearTimeout(guard);
      resolve();
    };
    utter.onend = done;
    utter.onerror = done;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  });
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

export function MeetingVoiceJoin({
  token,
  title,
}: {
  token: string;
  title: string;
}) {
  const [phase, setPhase] = useState<Phase>("ready");
  const [mood, setMood] = useState<Mood>("thinking");
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [caption, setCaption] = useState("");
  const [ending, setEnding] = useState("");
  const run = useRef({
    guest: "",
    stream: null as MediaStream | null,
    ctx: null as AudioContext | null,
    stop: false,
    mime: undefined as string | undefined,
  });

  function release() {
    const r = run.current;
    r.stop = true;
    r.stream?.getTracks().forEach((t) => t.stop());
    r.stream = null;
    void r.ctx?.close().catch(() => undefined);
    r.ctx = null;
    if (typeof window !== "undefined" && "speechSynthesis" in window)
      window.speechSynthesis.cancel();
  }
  useEffect(() => release, []);

  /** Listen until the person has said one thing; null when the conversation was stopped. */
  async function listen(): Promise<{ audio: Blob; durationMs: number } | null> {
    const r = run.current;
    const stream = r.stream;
    const ctx = r.ctx;
    if (!stream || !ctx) return null;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    try {
      for (;;) {
        const recorder = new MediaRecorder(stream, {
          mimeType: r.mime,
          audioBitsPerSecond: 32_000,
        });
        const chunks: Blob[] = [];
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data);
        };
        const startedAt = performance.now();
        recorder.start();
        let speechMs = 0;
        let lastLoud = 0;
        let spoke = false;
        for (;;) {
          await sleep(POLL_MS);
          if (r.stop) {
            if (recorder.state !== "inactive") recorder.stop();
            return null;
          }
          analyser.getFloatTimeDomainData(samples);
          let sum = 0;
          for (const v of samples) sum += v * v;
          const now = performance.now();
          if (Math.sqrt(sum / samples.length) > SPEECH_RMS) {
            speechMs += POLL_MS;
            lastLoud = now;
            if (speechMs >= MIN_SPEECH_MS) spoke = true;
          }
          const finished =
            spoke &&
            now - lastLoud > END_SILENCE_MS &&
            now - startedAt > MIN_SPEECH_MS;
          const tooLong = now - startedAt > MAX_CLIP_MS;
          const idle = !spoke && now - startedAt > IDLE_RESET_MS;
          if (finished || tooLong || idle) {
            await new Promise<void>((resolve) => {
              recorder.addEventListener("stop", () => resolve(), {
                once: true,
              });
              recorder.stop();
            });
            if (idle) break; // a fresh clip: nothing was said
            return {
              audio: new Blob(chunks, { type: recorder.mimeType || r.mime }),
              durationMs: performance.now() - startedAt,
            };
          }
        }
      }
    } finally {
      source.disconnect();
    }
  }

  async function conversation() {
    const r = run.current;
    let failures = 0;
    setMood("thinking");
    let turn = await meetingJoinService.piTurn(r.guest);
    for (;;) {
      if (r.stop) return;
      if (turn.reply) {
        setCaption(turn.reply);
        setMood("speaking");
        await say(turn.reply);
        if (turn.done) {
          setEnding("Thank you. That is all pi needed.");
          return;
        }
      }
      if (r.stop) return;
      setMood("listening");
      const clip = await listen();
      if (!clip || r.stop) return;
      setMood("thinking");
      try {
        turn = await meetingJoinService.piTurn(r.guest, clip);
        failures = 0;
      } catch (e) {
        if (
          e instanceof ApiError &&
          (e.code === "PI_NOT_SPEAKING" || e.status === 404)
        ) {
          setEnding(
            "The host has stopped pi from talking, or closed the meeting. Nothing more is being recorded.",
          );
          return;
        }
        failures += 1;
        if (failures >= 3) {
          setEnding(
            "pi could not answer just now, so the conversation has stopped.",
          );
          return;
        }
        // a failed turn is simply asked again: say it once more
        turn = { heard: false, reply: "", done: false };
        await sleep(1500 * failures);
      }
    }
  }

  async function start() {
    const r = run.current;
    setError("");
    setEnding("");
    setPhase("starting");
    r.stop = false;
    r.mime = pickMime();
    try {
      r.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      r.ctx = new AudioContext();
      const joined = await meetingJoinService.join(token, {
        name: name.trim(),
        consent: agreed,
      });
      r.guest = joined.guest_token;
      setPhase("talking");
    } catch (e) {
      release();
      setError(startError(e));
      setPhase("ready");
      return;
    }
    try {
      await conversation();
    } catch (e) {
      if (!run.current.stop)
        setEnding(
          e instanceof ApiError && e.code === "PI_NOT_SPEAKING"
            ? "The host has stopped pi from talking. Nothing more is being recorded."
            : "pi could not start the conversation. You can close this page.",
        );
    }
    await finish();
  }

  async function finish() {
    const r = run.current;
    release();
    if (r.guest) await meetingJoinService.leave(r.guest).catch(() => undefined);
    setPhase("ended");
  }

  return (
    <Card>
      <CardBody className="space-y-4">
        <div>
          <p className="text-xs text-muted-foreground">
            You are talking with pi
          </p>
          <h1 className="text-lg font-semibold">{title}</h1>
        </div>
        {phase === "ended" ? (
          <div className="space-y-2" role="status">
            <p className="flex items-center gap-2 text-sm font-medium">
              <CheckCircle2 className="size-4 text-success" aria-hidden />
              {ending
                ? "The conversation has ended"
                : "Thank you, you can close this page"}
            </p>
            {ending && (
              <p className="text-xs text-muted-foreground">{ending}</p>
            )}
          </div>
        ) : phase === "talking" ? (
          <div className="space-y-3" role="status">
            <p className="flex items-center gap-2 text-sm font-medium">
              <span
                className={`size-2 rounded-full ${mood === "listening" ? "animate-pulse bg-danger" : "bg-primary"}`}
              />
              {mood === "speaking"
                ? "pi is speaking"
                : mood === "listening"
                  ? "pi is listening: speak, then pause"
                  : "pi is thinking…"}
            </p>
            {caption && (
              <p className="rounded-lg bg-surface-muted p-3 text-sm break-words">
                {caption}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Keep this page open. A headset stops pi hearing its own voice.
            </p>
            <Button variant="secondary" onClick={() => void finish()}>
              <Square /> Stop and leave
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5 rounded-lg border border-border bg-surface-muted p-3 text-xs">
              <p className="flex items-center gap-1.5 font-medium">
                <Lock className="size-3.5" aria-hidden /> Before you start
              </p>
              <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
                <li>
                  You will talk with pi, an <strong>AI assistant</strong> from
                  Workzap, not a person. It asks about your business and
                  listens.
                </li>
                <li>
                  Your microphone is turned into text by a speech-to-text
                  service. The sound is not kept. Phone, card and ID numbers are
                  taken out of the text. Please do not say any.
                </li>
                <li>
                  The host&apos;s team can read the conversation. pi may
                  summarise it, and after their review points from it can be
                  saved to your customer record.
                </li>
                <li>
                  pi will not quote a price or ask for payment. You can stop at
                  any time.
                </li>
              </ul>
            </div>
            <div>
              <Label htmlFor="voice-name">Your name (optional)</Label>
              <Input
                id="voice-name"
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
                I understand I am talking with an AI, and I agree that my voice
                is recorded and turned into text.
              </span>
            </label>
            {error && <Notice tone="danger">{error}</Notice>}
            <Button
              disabled={!agreed || phase === "starting"}
              loading={phase === "starting"}
              onClick={() => void start()}
            >
              <Mic /> Start talking with pi
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
