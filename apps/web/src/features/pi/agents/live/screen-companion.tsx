"use client";

import { Check, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { SpriteAgent, LIVE_AGENTS, type ScreenState } from "./sprite-agent";

const WORDS: Record<Exclude<ScreenState, "none">, string> = {
  looking: "Looking at your screen…",
  seeing: "I can see your screen",
  missing: "I can't see your screen yet",
};

/**
 * The agent's character, background removed, standing at the corner of the shared screen while
 * someone shares. What it does shows what it sees: it scans from side to side while it looks,
 * nods once and shows a tick when it has understood the screen, and looks puzzled with an
 * "unseen" mark when the screen never reached it. It draws only the state it is told; it never
 * shows or sends anything that was on the screen.
 */
export function ScreenCompanion({
  agentKey,
  state,
  level = 0,
  speaking = false,
  className,
}: {
  agentKey: string;
  state: ScreenState;
  level?: number;
  speaking?: boolean;
  className?: string;
}) {
  if (state === "none" || !LIVE_AGENTS.has(agentKey)) return null;
  const tone =
    state === "seeing"
      ? "bg-emerald-500 text-white"
      : state === "looking"
        ? "bg-sky-500 text-white"
        : "bg-amber-500 text-white";
  const Icon = state === "seeing" ? Check : state === "looking" ? Eye : EyeOff;
  return (
    <div
      className={cn(
        "pointer-events-none absolute right-2 bottom-2 z-10 flex flex-col items-end motion-safe:animate-scale-in",
        className,
      )}
    >
      <div
        role="status"
        aria-live="polite"
        className={cn(
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
        {state === "looking" && (
          // a soft ring that pulses outwards while it looks
          <span
            aria-hidden="true"
            className="absolute inset-3 rounded-full bg-sky-400/30 motion-safe:animate-ping"
          />
        )}
        <SpriteAgent
          cutout
          agentKey={agentKey}
          level={level}
          speaking={speaking}
          screen={state}
          size={132}
          label="The agent looking at the shared screen"
          className="drop-shadow-[0_6px_10px_rgb(0_0_0/0.35)]"
        />
      </div>
    </div>
  );
}
