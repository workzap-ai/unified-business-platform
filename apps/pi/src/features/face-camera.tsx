"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CameraOff, RefreshCw, ScanFace } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";

/** What the server sees in a small preview frame (no recognition, nothing stored). */
export interface FaceProbe {
  faces: number;
  size?: number; // face width as a share of the picture width (0-1)
  x?: number; // distance from the centre, -0.5..0.5
  y?: number;
}

const PROBE_EVERY_MS = 280;
const NEAR = 0.24; // smaller than this: "move closer"
const FAR = 0.62; // bigger than this: "move back"
const OFF_CENTRE = 0.16;
const STEP_B = 1.1; // the face must grow this much for the 2nd picture…
const STEP_C = 1.18; // …and this much for the 3rd (the server needs at least 1.08)
const GIVE_UP_MS = 20_000;

type Phase =
  "starting" | "ready" | "align" | "closer" | "checking" | "done" | "error";
type Tone = "idle" | "adjust" | "good";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Live camera face check, like a banking app's: the screen watches the camera in real
 * time and guides the person ("move closer", "move back", "centre your face"), then
 * takes three pictures by itself as they bring the phone a little closer, and hands
 * them to `onFrames`. Small preview frames go to `probe` (pi's own server) only to
 * find the face; nothing is kept.
 */
export function FaceCamera({
  onFrames,
  probe,
  action = "Start face check",
  autoStart = false,
}: {
  /** Resolves when accepted; rejects with a message to show and offer a retry. */
  onFrames: (frames: string[]) => Promise<void>;
  probe: (frame: string) => Promise<FaceProbe>;
  action?: string;
  autoStart?: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const run = useRef(0); // bumps to cancel a running check
  const [phase, setPhase] = useState<Phase>("starting");
  const [hint, setHint] = useState("Starting the camera…");
  const [tone, setTone] = useState<Tone>("idle");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const stop = useCallback(() => {
    run.current += 1;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setPhase("error");
        setError(
          "This browser can't open the camera. Try Chrome, Edge or Safari.",
        );
        return;
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: "user",
            width: { ideal: 640 },
            height: { ideal: 480 },
          },
          audio: false,
        });
        if (cancelled) {
          media.getTracks().forEach((t) => t.stop());
          return;
        }
        stream.current = media;
        if (video.current) {
          video.current.srcObject = media;
          await video.current.play().catch(() => undefined);
        }
        setPhase("ready");
        setHint("Hold the phone at eye level, about an arm's length away");
      } catch (e) {
        setPhase("error");
        setError(
          e instanceof DOMException && e.name === "NotAllowedError"
            ? "Camera access was blocked. Allow the camera for this site and try again."
            : "We couldn't open the camera. Check that no other app is using it.",
        );
      }
    }
    void start();
    return () => {
      cancelled = true;
      stop();
    };
  }, [stop]);

  const grab = useCallback((width: number, quality: number): string | null => {
    const v = video.current;
    if (!v || !v.videoWidth) return null;
    const scale = Math.min(1, width / v.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(v.videoWidth * scale);
    canvas.height = Math.round(v.videoHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height); // as the camera sees it
    return canvas.toDataURL("image/jpeg", quality).split(",", 2)[1] ?? null;
  }, []);

  /** Advice for the current frame, or null when the face is well placed. */
  function advice(seen: FaceProbe, mode: "align" | "closer"): string | null {
    if (!seen.faces) return "Look at the camera";
    if (seen.faces > 1) return "Only you should be in the picture";
    const size = seen.size ?? 0;
    if (size > FAR + (mode === "closer" ? 0.25 : 0))
      return "Too close: move back a little";
    if (mode === "align" && size < NEAR) return "Move a little closer";
    if (
      Math.abs(seen.x ?? 0) > OFF_CENTRE ||
      Math.abs(seen.y ?? 0) > OFF_CENTRE + 0.06
    )
      return "Keep your face in the middle of the oval";
    return null;
  }

  const check = useCallback(async () => {
    const id = ++run.current;
    const alive = () => run.current === id;
    setError(null);
    setProgress(0);
    setPhase("align");
    setTone("idle");
    setHint("Look at the camera");
    const frames: string[] = [];
    let base = 0;
    let steady = 0;
    const started = performance.now();
    try {
      while (alive()) {
        if (performance.now() - started > GIVE_UP_MS) {
          throw new Error(
            frames.length
              ? "Bring the phone a little closer to your face while it checks."
              : "We couldn't see your face clearly. Find more light and try again.",
          );
        }
        const small = grab(320, 0.6);
        if (!small) throw new Error("The camera stopped. Try again.");
        const seen = await probe(small);
        if (!alive()) return;
        const mode = frames.length ? "closer" : "align";
        const fix = advice(seen, mode);
        if (fix) {
          steady = 0;
          setTone("adjust");
          setHint(fix);
        } else if (!frames.length) {
          // Well placed: two good looks in a row, then the first picture.
          steady += 1;
          setTone("good");
          setHint("Hold still…");
          if (steady >= 2) {
            const full = grab(640, 0.88);
            if (!full) throw new Error("The camera stopped. Try again.");
            frames.push(full);
            base = seen.size ?? 0;
            setProgress(34);
            setPhase("closer");
            setHint("Now bring the phone a little closer");
          }
        } else {
          const grown = (seen.size ?? 0) / (base || 1);
          setTone("good");
          const need = frames.length === 1 ? STEP_B : STEP_C;
          if (grown >= need) {
            const full = grab(640, 0.88);
            if (!full) throw new Error("The camera stopped. Try again.");
            frames.push(full);
            setProgress(frames.length === 2 ? 67 : 100);
            if (frames.length === 3) break;
          } else {
            setHint("A little closer…");
          }
        }
        await sleep(PROBE_EVERY_MS);
      }
      if (!alive()) return;
      setPhase("checking");
      setTone("good");
      setHint("Checking it's you…");
      await onFrames(frames);
      setPhase("done");
      setHint("Done");
      stop();
    } catch (e) {
      if (!alive()) return;
      setPhase("ready");
      setTone("idle");
      setProgress(0);
      setHint("Hold the phone at eye level, about an arm's length away");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [grab, onFrames, probe, stop]);

  useEffect(() => {
    if (autoStart && phase === "ready" && !error) {
      const t = setTimeout(() => void check(), 500);
      return () => clearTimeout(t);
    }
  }, [autoStart, phase, error, check]);

  const busy = phase === "align" || phase === "closer" || phase === "checking";
  return (
    <div className="space-y-3">
      <div className="relative mx-auto aspect-[3/4] w-full max-w-xs overflow-hidden rounded-3xl bg-neutral-900 sm:aspect-[4/3] sm:max-w-sm">
        {phase === "error" ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-white/80">
            <CameraOff className="size-8" aria-hidden />
            {error}
          </div>
        ) : (
          <>
            <video
              ref={video}
              muted
              playsInline
              aria-label="Camera preview"
              className="h-full w-full -scale-x-100 object-cover"
            />
            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute top-[46%] left-1/2 h-[66%] w-[62%] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border-4 shadow-[0_0_0_999px_rgba(0,0,0,0.5)] transition-colors duration-300 sm:w-[48%]",
                tone === "good" && "border-emerald-400",
                tone === "adjust" && "border-amber-300",
                tone === "idle" && "border-white/85",
              )}
            />
            {busy ? (
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-[22%] top-[14%] h-0.5 animate-[face-scan_1.6s_ease-in-out_infinite] bg-emerald-400 shadow-[0_0_12px_2px_rgba(52,211,153,0.8)]"
              />
            ) : null}
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent px-4 pt-8 pb-4 text-center text-[15px] font-semibold text-white">
              <span role="status" aria-live="polite">
                {hint}
              </span>
              {busy ? (
                <div className="mx-auto mt-2 h-1.5 w-44 overflow-hidden rounded-full bg-white/25">
                  <div
                    className="h-full bg-emerald-400 transition-[width] duration-500"
                    style={{
                      width: `${phase === "checking" ? 100 : progress}%`,
                    }}
                  />
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>
      {error && phase !== "error" ? (
        <p role="alert" className="text-center text-sm text-danger">
          {error}
        </p>
      ) : null}
      <div className="flex justify-center">
        {phase === "error" ? (
          <Button variant="secondary" onClick={() => window.location.reload()}>
            <RefreshCw className="size-4" aria-hidden /> Try again
          </Button>
        ) : phase === "done" ? null : (
          <Button
            onClick={() => void check()}
            disabled={phase === "starting"}
            loading={busy}
          >
            {error ? (
              <RefreshCw className="size-4" aria-hidden />
            ) : (
              <ScanFace className="size-4" aria-hidden />
            )}
            {error ? "Try again" : action}
          </Button>
        )}
      </div>
      <p className="text-center text-xs text-muted-foreground">
        Good light on your face helps. Pictures are only used for this check and
        are not kept.
      </p>
    </div>
  );
}
