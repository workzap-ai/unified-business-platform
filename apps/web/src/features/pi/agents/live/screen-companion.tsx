"use client";

import { useEffect, useState } from "react";
import { Check, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RefObject } from "react";
import type { VoiceShape } from "./voice-shape";
import { SpriteAgent, LIVE_AGENTS, type ScreenState } from "./sprite-agent";

const WORDS: Record<Exclude<ScreenState, "none">, string> = {
  looking: "Looking at your screen…",
  seeing: "I can see your screen",
  missing: "I can't see your screen yet",
};

/**
 * The agent's character, in its own coloured rounded tile, at the corner of the shared screen while
 * someone shares. What it does shows what it sees: it scans from side to side while it looks,
 * nods once and shows a tick when it has understood the screen, and looks puzzled with an
 * "unseen" mark when the screen never reached it. It draws only the state it is told; it never
 * shows or sends anything that was on the screen.
 */
export function ScreenCompanion({
  agentKey,
  state,
  level = 0,
  voice,
  speaking = false,
  className,
}: {
  agentKey: string;
  state: ScreenState;
  level?: number;
  voice?: RefObject<VoiceShape>;
  speaking?: boolean;
  className?: string;
}) {
  if (state === "none" || !LIVE_AGENTS.has(agentKey)) return null;
  return (
    <Standing
      key={state}
      agentKey={agentKey}
      state={state}
      level={level}
      voice={voice}
      speaking={speaking}
      className={className}
    />
  );
}

const SETTLE_MS = 6000; // after it has understood the screen it steps aside

function Standing({
  agentKey,
  state,
  level,
  voice,
  speaking,
  className,
}: {
  agentKey: string;
  state: Exclude<ScreenState, "none">;
  level: number;
  voice?: RefObject<VoiceShape>;
  speaking: boolean;
  className?: string;
}) {
  // this component is keyed by `state`, so "settled" starts again at every change
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    if (state !== "seeing") return;
    const t = window.setTimeout(() => setSettled(true), SETTLE_MS);
    return () => window.clearTimeout(t);
  }, [state]);
  // it keeps out of the way of what is shared once it has understood, and returns when it speaks
  const small = state === "seeing" && settled && !speaking;
  const tone =
    state === "seeing"
      ? "bg-emerald-500 text-white"
      : state === "looking"
        ? "bg-sky-500 text-white"
        : "bg-amber-500 text-white";
  const Icon = state === "seeing" ? Check : state === "looking" ? Eye : EyeOff;
  return (
    <>
      <ScreenScan state={state} />
      <div
        className={cn(
          "pointer-events-none absolute right-5 bottom-5 z-10 flex flex-col items-end transition-[transform] duration-500 motion-safe:animate-scale-in",
          small && "origin-bottom-right scale-[0.45]",
          className,
        )}
      >
        <div
          role="status"
          aria-live="polite"
          className={cn(
            small && "opacity-0",
            "mb-1 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium shadow-md",
            tone,
          )}
        >
          <Icon
            aria-hidden="true"
            className={cn(
              "size-3.5",
              state === "looking" && "motion-safe:animate-pulse",
            )}
          />
          {WORDS[state]}
        </div>
        <div className="relative">
          <SpriteAgent
            agentKey={agentKey}
            level={level}
            voice={voice}
            speaking={speaking}
            screen={state}
            size={168}
            label="The agent looking at the shared screen"
            className="rounded-3xl shadow-xl ring-2 ring-white/70"
          />
        </div>
      </div>
    </>
  );
}

/** What the agent is doing, drawn on the shared screen itself: a scan line and corner brackets. */
function ScreenScan({ state }: { state: Exclude<ScreenState, "none"> }) {
  const color =
    state === "seeing"
      ? "border-emerald-400"
      : state === "looking"
        ? "border-sky-400"
        : "border-amber-400";
  const corner = cn("absolute size-6 border-2", color);
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-2 z-[9] overflow-hidden rounded-xl",
        state === "seeing" &&
          "motion-safe:animate-[agent-frame_2.4s_ease-out_forwards]",
        state === "missing" && "border-2 border-dashed border-amber-400/70",
      )}
    >
      <style>{SCAN_CSS}</style>
      {state !== "missing" && (
        <>
          <span
            className={cn(
              corner,
              "top-0 left-0 rounded-tl-lg border-r-0 border-b-0",
            )}
          />
          <span
            className={cn(
              corner,
              "top-0 right-0 rounded-tr-lg border-b-0 border-l-0",
            )}
          />
          <span
            className={cn(
              corner,
              "bottom-0 left-0 rounded-bl-lg border-t-0 border-r-0",
            )}
          />
          <span
            className={cn(
              corner,
              "right-0 bottom-0 rounded-br-lg border-t-0 border-l-0",
            )}
          />
        </>
      )}
      {state === "looking" && (
        <span className="absolute inset-x-0 h-16 bg-gradient-to-b from-transparent via-sky-400/25 to-sky-400/60 motion-safe:animate-[agent-sweep_2.2s_linear_infinite]" />
      )}
    </div>
  );
}

const SCAN_CSS = `
@keyframes agent-sweep {
  0% { top: -4rem; }
  100% { top: 100%; }
}
@keyframes agent-frame {
  0% { opacity: 1; transform: scale(1.02); }
  60% { opacity: 1; transform: scale(1); }
  100% { opacity: 0.35; transform: scale(1); }
}`;
