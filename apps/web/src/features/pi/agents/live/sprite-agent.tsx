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

const src = (key: string, frame: Frame, cut = false) =>
  `/agents/${cut ? "cut" : "live"}/${key}/${frame}.webp`;

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
  cutout = false,
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
  /** the character with its background removed (transparent), for floating over other content */
  cutout?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const [frame, setFrame] = useState<Frame>("base");
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const loadKey = `${agentKey}:${cutout}`;
  const loaded = loadedKey === loadKey;
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
            img.src = src(agentKey, f, cutout);
          }),
      ),
    ).then(() => alive && setLoadedKey(loadKey));
    return () => {
      alive = false;
    };
  }, [agentKey, cutout, loadKey]);

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

  // The character is two layers: the head (with the mouth and eye frames) and the body. They move
  // apart from the neck, so it turns and nods, the shoulders breathe, and it leans in as it talks.
  const neck = NECK[agentKey] ?? 0.6;
  const talking = speaking && screen === "none";
  const head = reduced
    ? ""
    : screen === "looking"
      ? "motion-safe:animate-[agent-head-scan_2.6s_ease-in-out_infinite]"
      : screen === "missing"
        ? "motion-safe:animate-[agent-head-puzzled_2.8s_ease-in-out_infinite]"
        : screen === "seeing"
          ? "motion-safe:animate-[agent-head-nod_0.8s_ease-in-out_1]"
          : talking
            ? "motion-safe:animate-[agent-head-talk_1.1s_ease-in-out_infinite]"
            : listening
              ? "motion-safe:animate-[agent-head-listen_3.6s_ease-in-out_infinite]"
              : "motion-safe:animate-[agent-head-idle_5.2s_ease-in-out_infinite]";
  const body = reduced
    ? ""
    : screen === "looking"
      ? "motion-safe:animate-[agent-body-lean_2.6s_ease-in-out_infinite]"
      : talking
        ? "motion-safe:animate-[agent-body-talk_1.6s_ease-in-out_infinite]"
        : "motion-safe:animate-[agent-body-breathe_4.2s_ease-in-out_infinite]";
  // the two layers overlap at the neck and fade into each other, so there is no seam at rest
  const headMask = `linear-gradient(to bottom, #000 ${(neck - 0.02) * 100}%, transparent ${(neck + 0.06) * 100}%)`;
  const bodyMask = `linear-gradient(to bottom, transparent ${(neck - 0.1) * 100}%, #000 ${neck * 100}%)`;
  const imgClass = "absolute inset-0 size-full object-cover";

  return (
    <div
      role="img"
      aria-label={label ?? "Agent character"}
      className={cn(
        "relative select-none",
        !cutout && "overflow-hidden",
        className,
      )}
      style={{ width: size, height: size }}
    >
      <style>{KEYFRAMES}</style>
      <div className="absolute inset-0 scale-[1.04] origin-bottom">
        <div
          className={cn("absolute inset-0 origin-bottom", body)}
          style={{ maskImage: bodyMask, WebkitMaskImage: bodyMask }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- small static animation frames */}
          <img
            src={src(agentKey, "base", cutout)}
            alt=""
            width={512}
            height={512}
            draggable={false}
            decoding="async"
            className={imgClass}
          />
        </div>
        <div
          key={screen + String(listening) + String(talking)}
          className={cn("absolute inset-0", head)}
          style={{
            transformOrigin: `50% ${neck * 100}%`,
            maskImage: headMask,
            WebkitMaskImage: headMask,
          }}
        >
          {FRAMES.map((f) => (
            // eslint-disable-next-line @next/next/no-img-element -- small static animation frames
            <img
              key={f}
              src={src(agentKey, f, cutout)}
              alt=""
              width={512}
              height={512}
              draggable={false}
              decoding="async"
              className={cn(
                imgClass,
                f === "base" || f === frame ? "opacity-100" : "opacity-0",
              )}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

/** Where the neck is, as a fraction of the picture's height (the head and body layers split here). */
const NECK: Record<string, number> = {
  pi: 0.74,
  sales_coach: 0.6,
  negotiation_coach: 0.62,
  presentation_coach: 0.6,
  training_coach: 0.58,
  hustle_coach: 0.6,
  customer_success: 0.62,
  interviewer: 0.6,
};

const KEYFRAMES = `
@keyframes agent-head-idle {
  0%, 100% { transform: rotate(0deg) translateY(0); }
  30% { transform: rotate(1.6deg) translateY(-0.4%); }
  65% { transform: rotate(-1.4deg) translateY(0.2%); }
}
@keyframes agent-head-talk {
  0%, 100% { transform: rotate(0deg) translateY(0); }
  20% { transform: rotate(-2.2deg) translateY(0.8%); }
  45% { transform: rotate(1.8deg) translateY(-0.5%); }
  70% { transform: rotate(-1deg) translateY(0.6%); }
}
@keyframes agent-head-listen {
  0%, 100% { transform: rotate(3.5deg) translateY(0); }
  25% { transform: rotate(3.5deg) translateY(1.4%); }
  35% { transform: rotate(3.5deg) translateY(0); }
}
@keyframes agent-head-scan {
  0%, 100% { transform: translateX(-3%) rotate(-5deg); }
  50% { transform: translateX(3%) rotate(5deg); }
}
@keyframes agent-head-puzzled {
  0%, 100% { transform: rotate(0deg); }
  30% { transform: rotate(-7deg) translateX(-1%); }
  60% { transform: rotate(6deg) translateX(1%); }
}
@keyframes agent-head-nod {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  40% { transform: translateY(2.6%) rotate(1deg); }
}
@keyframes agent-body-breathe {
  0%, 100% { transform: scale(1, 1); }
  50% { transform: scale(1.012, 1.02); }
}
@keyframes agent-body-talk {
  0%, 100% { transform: scale(1, 1) rotate(0deg); }
  25% { transform: scale(1.01, 1.025) rotate(0.8deg); }
  60% { transform: scale(1.005, 1.01) rotate(-0.8deg); }
}
@keyframes agent-body-lean {
  0%, 100% { transform: translateX(-1.2%) rotate(-1.4deg); }
  50% { transform: translateX(1.2%) rotate(1.4deg); }
}`;
