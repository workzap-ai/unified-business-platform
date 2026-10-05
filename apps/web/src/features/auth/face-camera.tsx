"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, RefreshCw, ScanFace } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FRAMES = 3;
const MAX_WIDTH = 640;
// Look at the camera, then move a little closer: the server checks the face grows.
const STEPS = [
  { at: 700, say: "Look at the camera" },
  { at: 1700, say: "Now move a little closer" },
  { at: 2600, say: "Hold still…" },
];

type Phase = "starting" | "ready" | "scanning" | "checking" | "done" | "error";

/**
 * Live camera face check. Shows a mirrored preview with an oval guide, then takes three
 * frames over about two and a half seconds while the person moves a little closer, and
 * hands them to `onFrames`. The frames go only to Owner OS's own server, which turns
 * them into a face code and throws the pictures away.
 */
export function FaceCamera({
  onFrames,
  action = "Scan my face",
  autoStart = false,
}: {
  /** Resolves when accepted; rejects with a message to show and offer a retry. */
  onFrames: (frames: string[]) => Promise<void>;
  action?: string;
  autoStart?: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<Phase>("starting");
  const [hint, setHint] = useState("Starting the camera…");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const stop = useCallback(() => {
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
        setHint("Fit your face inside the oval");
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

  const grab = useCallback((): string | null => {
    const v = video.current;
    if (!v || !v.videoWidth) return null;
    const scale = Math.min(1, MAX_WIDTH / v.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(v.videoWidth * scale);
    canvas.height = Math.round(v.videoHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height); // unmirrored, as the camera sees
    return canvas.toDataURL("image/jpeg", 0.88).split(",", 2)[1] ?? null;
  }, []);

  const scan = useCallback(async () => {
    setError(null);
    setPhase("scanning");
    setProgress(0);
    const frames: string[] = [];
    const started = performance.now();
    for (const [i, step] of STEPS.entries()) {
      setHint(step.say);
      const wait = step.at - (performance.now() - started);
      if (wait > 0) await new Promise((r) => setTimeout(r, wait));
      const frame = grab();
      if (!frame) {
        setPhase("error");
        setError("The camera stopped. Try again.");
        return;
      }
      frames.push(frame);
      setProgress(((i + 1) / FRAMES) * 100);
    }
    setPhase("checking");
    setHint("Checking it's you…");
    try {
      await onFrames(frames);
      setPhase("done");
      setHint("Done");
      stop();
    } catch (e) {
      setPhase("ready");
      setHint("Fit your face inside the oval");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [grab, onFrames, stop]);

  useEffect(() => {
    if (autoStart && phase === "ready" && !error) {
      const t = setTimeout(() => void scan(), 600);
      return () => clearTimeout(t);
    }
  }, [autoStart, phase, error, scan]);

  const busy = phase === "scanning" || phase === "checking";
  return (
    <div className="space-y-3">
      <div className="relative mx-auto aspect-[4/3] w-full max-w-sm overflow-hidden rounded-2xl bg-neutral-900">
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
            {/* The oval guide; the outside is dimmed so the face goes in the middle. */}
            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute top-1/2 left-1/2 h-[78%] w-[52%] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border-[3px] shadow-[0_0_0_999px_rgba(0,0,0,0.45)] transition-colors",
                busy ? "border-emerald-400" : "border-white/80",
                phase === "done" && "border-emerald-400",
              )}
            />
            {busy ? (
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-[24%] top-[11%] h-0.5 animate-[face-scan_1.4s_ease-in-out_infinite] bg-emerald-400 shadow-[0_0_12px_2px_rgba(52,211,153,0.8)]"
              />
            ) : null}
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-4 pt-6 pb-3 text-center text-sm font-medium text-white">
              <span role="status" aria-live="polite">
                {hint}
              </span>
              {busy ? (
                <div className="mx-auto mt-2 h-1 w-40 overflow-hidden rounded-full bg-white/25">
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
            <RefreshCw aria-hidden /> Try again
          </Button>
        ) : phase === "done" ? null : (
          <Button
            onClick={() => void scan()}
            disabled={phase === "starting"}
            loading={busy}
          >
            {error ? <RefreshCw aria-hidden /> : <ScanFace aria-hidden />}
            {error ? "Try again" : action}
          </Button>
        )}
      </div>
      <p className="flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
        <Camera className="size-3.5" aria-hidden /> Pictures are only used for
        this check and are not kept.
      </p>
    </div>
  );
}
