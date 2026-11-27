"use client";

import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { cn } from "@/lib/utils";
import type { VoiceShape } from "./voice-shape";

/**
 * A living agent character. Each character is the same 3D portrait in five frames (rest, a blink and
 * three mouth shapes), aligned to each other, in /agents/live/<key>/. The mouth follows the voice
 * level, the eyes blink on their own, the body breathes and sways a little, and while pi looks at a
 * shared screen the head scans; it nods once when it has understood it. Nothing here makes a sound
 * or reads anything: it only draws what it is told (`level`, `speaking`, `listening`, `screen`).
 */

export type ScreenState = "none" | "looking" | "seeing" | "missing";
type Frame = "base" | "blink" | "m1" | "m2" | "m3" | "wide" | "round";
const FRAMES: Frame[] = ["base", "blink", "m1", "m2", "m3", "wide", "round"];

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

/**
 * The mouth shape for a voice. How loud sets how far the jaw opens; how bright (`tone`) picks the
 * lips: bright and not loud is the wide "ee", dark and not loud is the round "oo", and the loudest
 * is the open "ah". A small hysteresis stops it flickering at a boundary.
 */
export function mouthFor(level: number, tone: number, current: Frame): Frame {
  const up = current === "base" ? 0.1 : 0.06;
  if (level < up) return "base";
  if (level >= 0.58) return "m3";
  if (level < 0.5) {
    if (tone > (current === "wide" ? 0.5 : 0.62)) return "wide";
    if (tone < (current === "round" ? 0.42 : 0.3)) return "round";
  }
  return level < 0.3 ? "m1" : "m2";
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
  voice,
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
  /** the agent's real voice (level and tone); when it is listening, the mouth follows it */
  voice?: RefObject<VoiceShape>;
}) {
  const reduced = usePrefersReducedMotion();
  const [frame, setFrame] = useState<Frame>("base");
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const loadKey = agentKey;
  const loaded = loadedKey === loadKey;
  const live = useRef({ level, speaking, screen, listening });
  useEffect(() => {
    live.current = { level, speaking, screen, listening };
  });
  const headRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

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
    ).then(() => alive && setLoadedKey(loadKey));
    return () => {
      alive = false;
    };
  }, [agentKey, loadKey]);

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
      const { level: given, speaking: sp } = live.current;
      const v = voice?.current;
      const lv = v?.active ? v.level : given;
      const tone = v?.active ? v.tone : 0.5;
      // a fast attack and a slower release, like a real mouth
      smooth += (lv - smooth) * (lv > smooth ? 0.6 : 0.25);
      let target: Frame = mouthFor(
        smooth,
        tone,
        shown === "blink" ? "base" : shown,
      );
      if (sp && smooth < 0.06 && !v?.active) {
        // speaking with no level to follow: a gentle natural talk cycle, never frozen
        if (now >= fakeAt) {
          const cycle: Frame[] = [
            "m1",
            "wide",
            "m2",
            "round",
            "m1",
            "m3",
            "wide",
            "base",
            "round",
            "m2",
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
        nextBlink =
          now + (Math.random() < 0.22 ? 280 : 2400 + Math.random() * 3200);
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
  }, [loaded, voice]);

  // The character is two layers: the head (with the mouth and eye frames) and the body. They move
  // apart from the neck. The movement is not a loop: it is slow noise, with a nod now and then,
  // and what it does depends on what the agent is doing (talking, listening, looking at a screen).
  const neck = NECK[agentKey] ?? 0.6;

  useEffect(() => {
    const h = headRef.current;
    const b = bodyRef.current;
    if (reduced || !loaded || !h || !b) return;
    let raf = 0;
    let last = performance.now();
    let smoothLv = 0;
    let impulse = 0;
    let nextImpulse = last + 2500;
    let prevScreen: ScreenState = "none";
    const pos = { roll: 0, yaw: 0, pitch: 0, broll: 0 };
    const hop = { roll: 0, yaw: 0, pitch: 0, until: 0 };
    let lastNod = 0;
    let prevLv = 0;
    // a smooth, never-repeating wobble: two sines with unrelated speeds
    const wob = (t: number, f: number, p: number) =>
      Math.sin(t * f + p) * 0.6 + Math.sin(t * f * 2.31 + p * 1.7) * 0.4;
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = now / 1000;
      const m = live.current;
      const isTalking = m.speaking && m.screen === "none";
      smoothLv += (m.level - smoothLv) * (m.level > smoothLv ? 0.35 : 0.12);
      const e = Math.min(1, smoothLv * 1.7);
      if (m.screen !== prevScreen) {
        if (m.screen === "seeing") impulse = 1.7; // understood: a clear nod
        if (m.screen === "missing") impulse = 1.2;
        prevScreen = m.screen;
      }
      // a nod on the stress of a word: the voice rises quickly after a quieter moment
      if (isTalking && m.level - prevLv > 0.2 && now - lastNod > 900) {
        impulse = Math.max(impulse, 0.55 + Math.min(0.4, e * 0.4));
        lastNod = now;
      }
      prevLv = m.level;
      if (now > nextImpulse) {
        impulse = Math.max(impulse, isTalking ? 0.6 : 0.5);
        nextImpulse =
          now +
          (isTalking
            ? 3500 + Math.random() * 3500
            : m.listening
              ? 3500 + Math.random() * 3500
              : 6000 + Math.random() * 6000);
      }
      impulse *= Math.exp(-dt * 4.5);

      // What the research on natural head motion agrees on: the head turns about the base of the
      // neck (a ball in a socket) and does not slide sideways; it stays joined to the shoulders,
      // which answer it a little; movement is small and slow (fast jitter reads as fake); and in
      // speech the head follows the voice, nodding as the voice rises into a stressed word.
      let tRoll = wob(t, 0.29, 1) * 0.6;
      let tYaw = wob(t, 0.19, 4) * 1.2;
      let tPitch = wob(t, 0.33, 3) * 0.25;
      if (isTalking) {
        tRoll += wob(t, 0.5, 7) * (0.4 + e * 1.1);
        tYaw += wob(t, 0.38, 8) * (0.8 + e * 1.6);
        tPitch += e * 0.4;
      } else if (m.listening && m.screen === "none") {
        tRoll += 1.8; // the head a little to one side, as people hold it when they listen
        tYaw += 1.5;
      }
      if (m.screen === "looking") {
        // the gaze goes from place to place and rests there, like eyes reading a screen
        if (now > hop.until) {
          hop.roll = (Math.random() * 2 - 1) * 1.2;
          hop.yaw = (Math.random() * 2 - 1) * 4.5;
          hop.pitch = Math.random() * 1.2 - 0.3;
          hop.until = now + 800 + Math.random() * 1100;
        }
        tRoll += hop.roll;
        tYaw += hop.yaw;
        tPitch += hop.pitch;
      } else if (m.screen === "missing") {
        tRoll += wob(t, 0.45, 10) * 3.5;
        tYaw += wob(t, 0.35, 11) * 2.5;
      }
      tPitch += impulse * 1.1;
      tRoll += impulse * (m.screen === "missing" ? 2.5 : 0.3);

      const kHead = 1 - Math.exp(-dt * 5);
      const kBody = 1 - Math.exp(-dt * 3);
      pos.roll += (tRoll - pos.roll) * kHead;
      pos.yaw += (tYaw - pos.yaw) * kHead;
      pos.pitch += (tPitch - pos.pitch) * kHead;
      // the shoulders answer the head: they lean the other way a little, never on their own
      const tBodyRoll = -pos.roll * 0.3 + wob(t, 0.17, 5) * 0.15;
      pos.broll += (tBodyRoll - pos.broll) * kBody;
      const breath = 0.5 + 0.5 * Math.sin(t * 1.45 + wob(t, 0.2, 12) * 0.6);
      const talkLift = isTalking ? e * 0.008 : 0;
      h.style.transform = `perspective(700px) translateY(${pos.pitch.toFixed(3)}%) rotateY(${pos.yaw.toFixed(3)}deg) rotate(${pos.roll.toFixed(3)}deg) scaleY(${(1 - pos.pitch * 0.004).toFixed(4)})`;
      b.style.transform = `rotate(${pos.broll.toFixed(3)}deg) scale(${(1 + breath * 0.005).toFixed(4)}, ${(1 + breath * 0.012 + talkLift).toFixed(4)})`;
      raf = requestAnimationFrame(tick);
    };
    const onVisibility = () => {
      cancelAnimationFrame(raf);
      last = performance.now();
      if (!document.hidden) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduced, loaded]);
  // the two layers overlap at the neck and fade into each other, so there is no seam at rest
  const headMask = `linear-gradient(to bottom, #000 ${(neck - 0.02) * 100}%, transparent ${(neck + 0.06) * 100}%)`;
  const bodyMask = `linear-gradient(to bottom, transparent ${(neck - 0.1) * 100}%, #000 ${neck * 100}%)`;
  const imgClass = "absolute inset-0 size-full object-cover";

  return (
    <div
      role="img"
      aria-label={label ?? "Agent character"}
      className={cn("relative overflow-hidden select-none", className)}
      style={{ width: size, height: size }}
    >
      {/* with a background, it stays still behind the moving head, so its corners never tilt */}
      {/* eslint-disable-next-line @next/next/no-img-element -- small static animation frames */}
      <img
        src={src(agentKey, "base")}
        alt=""
        width={512}
        height={512}
        draggable={false}
        className={imgClass}
      />
      <div className="absolute inset-0 scale-[1.04] origin-bottom">
        <div
          ref={bodyRef}
          className="absolute inset-0 origin-bottom"
          style={{ maskImage: bodyMask, WebkitMaskImage: bodyMask }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- small static animation frames */}
          <img
            src={src(agentKey, "base")}
            alt=""
            width={512}
            height={512}
            draggable={false}
            decoding="async"
            className={imgClass}
          />
        </div>
        <div
          ref={headRef}
          className="absolute inset-0"
          style={{
            transformOrigin: `50% ${(neck + 0.05) * 100}%`,
            maskImage: headMask,
            WebkitMaskImage: headMask,
          }}
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
