"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * A living agent character. Each character is the same 3D portrait in five frames (rest, a blink and
 * three mouth shapes), aligned to each other, in /agents/live/<key>/. The mouth follows the voice
 * level, the eyes blink on their own, the body breathes and sways a little, and while pi looks at a
 * shared screen the head scans; it nods once when it has understood it. Nothing here makes a sound
 * or reads anything: it only draws what it is told (`level`, `speaking`, `listening`, `screen`).
 */

export type ScreenState = "none" | "looking" | "seeing" | "missing";
type Frame = "base" | "blink" | "m1" | "m2" | "m3";
const FRAMES: Frame[] = ["base", "blink", "m1", "m2", "m3"];

/** Agents that have a living character (every built-in one, pi's robot included). */
export const LIVE_AGENTS = new Set([
  "pi",
  "sales_coach",
  "negotiation_coach",
  "presentation_coach",
  "training_coach",
  "hustle_coach",
  "customer_success",
  "interviewer",
]);

const src = (key: string, frame: Frame) => `/agents/live/${key}/${frame}.webp`;

/** The mouth frame for a voice level; a small hysteresis stops it flickering at a boundary. */
export function mouthFor(level: number, current: Frame): Frame {
  const up = current === "base" ? 0.1 : 0.06;
  if (level < up) return "base";
  const m = level < 0.32 ? "m1" : level < 0.62 ? "m2" : "m3";
  return m;
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(q.matches);
    on();
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function SpriteAgent({
  agentKey,
  level = 0,
  speaking = false,
  listening = false,
  screen = "none",
  size = 220,
  className,
  label,
}: {
  agentKey: string;
  /** the voice level, 0 to 1 */
  level?: number;
  speaking?: boolean;
  listening?: boolean;
  screen?: ScreenState;
  size?: number;
  className?: string;
  label?: string;
}) {
  const reduced = usePrefersReducedMotion();
  const [frame, setFrame] = useState<Frame>("base");
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const loaded = loadedKey === agentKey;
  const live = useRef({ level, speaking });
  useEffect(() => {
    live.current = { level, speaking };
  });

  // the frames are fetched together, so a swap never shows a gap
  useEffect(() => {
    let alive = true;
    Promise.all(
      FRAMES.map(
        (f) =>
          new Promise<void>((resolve) => {
            const img = new Image();
            img.onload = img.onerror = () => resolve();
            img.src = src(agentKey, f);
          }),
      ),
    ).then(() => alive && setLoadedKey(agentKey));
    return () => {
      alive = false;
    };
  }, [agentKey]);

  // mouth and blink, one loop; paused while the tab is hidden
  useEffect(() => {
    if (!loaded) return;
    let raf = 0;
    let smooth = 0;
    let shown: Frame = "base";
    let heldUntil = 0;
    let nextBlink = performance.now() + 1500 + Math.random() * 2500;
    let blinkUntil = 0;
    let fakeAt = 0;
    let fakeStep = 0;
    const set = (f: Frame, now: number, hold = 70) => {
      if (f === shown) return;
      shown = f;
      heldUntil = now + hold;
      setFrame(f);
    };
    const tick = (now: number) => {
      const { level: lv, speaking: sp } = live.current;
      // a fast attack and a slower release, like a real mouth
      smooth += (lv - smooth) * (lv > smooth ? 0.6 : 0.25);
      let target: Frame = mouthFor(smooth, shown === "blink" ? "base" : shown);
      if (sp && smooth < 0.06) {
        // speaking with no level to follow: a gentle natural talk cycle, never frozen
        if (now >= fakeAt) {
          const cycle: Frame[] = [
            "m1",
            "m2",
            "m1",
            "m3",
            "m1",
            "base",
            "m2",
            "m1",
          ];
          fakeStep = (fakeStep + 1) % cycle.length;
          fakeAt = now + 90 + Math.random() * 90;
          target = cycle[fakeStep];
        } else {
          target = shown === "blink" ? "base" : shown;
        }
      }
      if (now < blinkUntil) {
        target = "blink";
      } else if (now >= nextBlink && target === "base") {
        blinkUntil = now + 120;
        nextBlink = now + 2500 + Math.random() * 2600;
        target = "blink";
      }
      if (target !== shown && (now >= heldUntil || target === "blink")) {
        set(target, now, target === "blink" ? 120 : 70);
      }
      raf = requestAnimationFrame(tick);
    };
    const onVisibility = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [loaded]);

  const motion = reduced
    ? ""
    : screen === "looking"
      ? "motion-safe:animate-[agent-scan_2.4s_ease-in-out_infinite]"
      : screen === "seeing"
        ? "motion-safe:animate-[agent-nod_0.7s_ease-in-out_1]"
        : listening
          ? "motion-safe:animate-[agent-listen_3.2s_ease-in-out_infinite]"
          : "motion-safe:animate-[agent-breathe_4.4s_ease-in-out_infinite]";

  return (
    <div
      role="img"
      aria-label={label ?? "Agent character"}
      className={cn("relative select-none overflow-hidden", className)}
      style={{ width: size, height: size }}
    >
      <style>{KEYFRAMES}</style>
      <div
        key={screen + String(listening)}
        className={cn("absolute inset-0 origin-[50%_85%]", motion)}
      >
        {FRAMES.map((f) => (
          // eslint-disable-next-line @next/next/no-img-element -- small static animation frames
          <img
            key={f}
            src={src(agentKey, f)}
            alt=""
            width={512}
            height={512}
            draggable={false}
            decoding="async"
            className={cn(
              "absolute inset-0 size-full object-cover",
              f === "base"
                ? "opacity-100"
                : f === frame
                  ? "opacity-100"
                  : "opacity-0",
            )}
          />
        ))}
      </div>
    </div>
  );
}

const KEYFRAMES = `
@keyframes agent-breathe {
  0%, 100% { transform: translateY(0) scale(1) rotate(0deg); }
  50% { transform: translateY(-0.6%) scale(1.012) rotate(0.5deg); }
}
@keyframes agent-listen {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  20% { transform: translateY(1.6%) rotate(0.8deg); }
  40% { transform: translateY(0) rotate(0deg); }
}
@keyframes agent-scan {
  0%, 100% { transform: translateX(-2.2%) rotate(-1.2deg); }
  50% { transform: translateX(2.2%) rotate(1.2deg); }
}
@keyframes agent-nod {
  0% { transform: translateY(0); }
  40% { transform: translateY(2.4%); }
  100% { transform: translateY(0); }
}`;
