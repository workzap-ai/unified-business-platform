"use client";

import { createElement, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Briefcase,
  Flame,
  GraduationCap,
  Handshake,
  Headphones,
  Heart,
  Lightbulb,
  Mic,
  Presentation,
  Rocket,
  Search,
  Shield,
  Sparkles,
  Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PiAvatar } from "../room/pi-avatar";
import type { Agent, AgentColor, AgentIcon } from "./meeting-agents-service";

/** One lucide icon per icon key the server allows. Unknown keys fall back to sparkles. */
export const ICON_MAP: Record<AgentIcon, LucideIcon> = {
  sparkles: Sparkles,
  briefcase: Briefcase,
  handshake: Handshake,
  presentation: Presentation,
  "graduation-cap": GraduationCap,
  flame: Flame,
  headphones: Headphones,
  search: Search,
  heart: Heart,
  shield: Shield,
  rocket: Rocket,
  mic: Mic,
  target: Target,
  lightbulb: Lightbulb,
};

export function iconFor(key: string): LucideIcon {
  return ICON_MAP[key as AgentIcon] ?? Sparkles;
}

type Style = {
  /** the gradient tile, light and dark */
  tile: string;
  /** a soft glow behind a hovered card */
  glow: string;
  /** a selected swatch ring */
  ring: string;
  /** a quiet tinted chip */
  chip: string;
};

/** Soft two-stop gradients per colour key. Green follows the app's own primary tokens. */
export const COLOR_STYLES: Record<AgentColor, Style> = {
  green: {
    tile: "from-primary-soft to-primary/35 text-primary ring-primary/20",
    glow: "from-primary/40 to-emerald-300/30",
    ring: "ring-primary",
    chip: "bg-primary-soft text-primary-soft-foreground",
  },
  violet: {
    tile: "from-violet-100 to-violet-300/80 text-violet-700 ring-violet-300/50 dark:from-violet-950 dark:to-violet-700/50 dark:text-violet-200 dark:ring-violet-400/20",
    glow: "from-violet-400/40 to-fuchsia-300/30",
    ring: "ring-violet-500",
    chip: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200",
  },
  blue: {
    tile: "from-sky-100 to-blue-300/80 text-blue-700 ring-blue-300/50 dark:from-blue-950 dark:to-blue-700/50 dark:text-blue-200 dark:ring-blue-400/20",
    glow: "from-blue-400/40 to-sky-300/30",
    ring: "ring-blue-500",
    chip: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-200",
  },
  amber: {
    tile: "from-amber-100 to-amber-300/80 text-amber-800 ring-amber-300/50 dark:from-amber-950 dark:to-amber-700/50 dark:text-amber-200 dark:ring-amber-400/20",
    glow: "from-amber-400/40 to-orange-300/30",
    ring: "ring-amber-500",
    chip: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  },
  rose: {
    tile: "from-rose-100 to-rose-300/80 text-rose-700 ring-rose-300/50 dark:from-rose-950 dark:to-rose-700/50 dark:text-rose-200 dark:ring-rose-400/20",
    glow: "from-rose-400/40 to-pink-300/30",
    ring: "ring-rose-500",
    chip: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  },
  teal: {
    tile: "from-teal-100 to-teal-300/80 text-teal-700 ring-teal-300/50 dark:from-teal-950 dark:to-teal-700/50 dark:text-teal-200 dark:ring-teal-400/20",
    glow: "from-teal-400/40 to-cyan-300/30",
    ring: "ring-teal-500",
    chip: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-200",
  },
  indigo: {
    tile: "from-indigo-100 to-indigo-300/80 text-indigo-700 ring-indigo-300/50 dark:from-indigo-950 dark:to-indigo-700/50 dark:text-indigo-200 dark:ring-indigo-400/20",
    glow: "from-indigo-400/40 to-blue-300/30",
    ring: "ring-indigo-500",
    chip: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
  },
  slate: {
    tile: "from-slate-100 to-slate-300/80 text-slate-700 ring-slate-300/60 dark:from-slate-900 dark:to-slate-600/50 dark:text-slate-200 dark:ring-slate-400/20",
    glow: "from-slate-400/40 to-zinc-300/30",
    ring: "ring-slate-500",
    chip: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
  },
};

export function stylesFor(color: string): Style {
  return COLOR_STYLES[color as AgentColor] ?? COLOR_STYLES.green;
}

const SIZES = {
  sm: { box: "size-7 rounded-lg", icon: "size-3.5", badge: "hidden" },
  md: { box: "size-10 rounded-xl", icon: "size-5", badge: "hidden" },
  lg: { box: "size-14 rounded-2xl", icon: "size-7", badge: "text-[9px]" },
  xl: {
    box: "size-[72px] rounded-[22px]",
    icon: "size-9",
    badge: "text-[10px]",
  },
} as const;

export type AvatarSize = keyof typeof SIZES;

/**
 * Built-in agents that have a character portrait in /agents (square, 384 px, WebP). pi itself keeps
 * its brand face (never redrawn); a custom agent keeps its gradient tile and icon. A portrait that
 * fails to load falls back to the tile, so an avatar is never blank.
 */
const PORTRAITS = new Set([
  "sales_coach",
  "negotiation_coach",
  "presentation_coach",
  "training_coach",
  "hustle_coach",
  "customer_success",
  "interviewer",
]);
const PI_FACE: Record<AvatarSize, number> = { sm: 22, md: 30, lg: 44, xl: 58 };

export function AgentAvatar({
  agent,
  icon,
  color,
  size = "md",
  showAi = false,
  className,
}: {
  agent?: Pick<Agent, "icon" | "color" | "is_default"> & { key?: string };
  icon?: string;
  color?: string;
  size?: AvatarSize;
  /** a small "AI" badge: pi (the default) says it is an AI wherever it appears large */
  showAi?: boolean;
  className?: string;
}) {
  const glyph = iconFor(icon ?? agent?.icon ?? "sparkles");
  const style = stylesFor(color ?? agent?.color ?? "green");
  const s = SIZES[size];
  const ai = showAi && agent?.is_default && size !== "sm" && size !== "md";
  const [broken, setBroken] = useState(false);
  const portrait =
    !broken && agent?.key && PORTRAITS.has(agent.key)
      ? `/agents/${agent.key}.webp`
      : null;
  return (
    <span
      aria-hidden="true"
      className={cn("relative inline-flex shrink-0", className)}
    >
      <span
        className={cn(
          "grid place-items-center overflow-hidden bg-gradient-to-br shadow-sm ring-1 ring-inset",
          s.box,
          style.tile,
        )}
      >
        {portrait ? (
          // eslint-disable-next-line @next/next/no-img-element -- a small static portrait
          <img
            src={portrait}
            alt=""
            width={384}
            height={384}
            loading="lazy"
            decoding="async"
            draggable={false}
            onError={() => setBroken(true)}
            className="size-full object-cover"
          />
        ) : agent?.is_default ? (
          <PiAvatar expression="rest" size={PI_FACE[size]} decorative />
        ) : (
          createElement(glyph, { className: s.icon, strokeWidth: 1.9 })
        )}
      </span>
      {ai && (
        <span
          className={cn(
            "absolute -right-1 -bottom-1 rounded-full bg-foreground px-1 py-px leading-3 font-bold tracking-wide text-background ring-2 ring-surface",
            s.badge,
          )}
        >
          AI
        </span>
      )}
    </span>
  );
}

/** An illustration-style cluster of three tiles, for empty states. */
export function AgentCluster({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("relative h-24 w-36 select-none", className)}
    >
      <AgentAvatar
        icon="target"
        color="amber"
        size="lg"
        className="absolute top-1 left-0 -rotate-6 motion-safe:animate-fade-in"
      />
      <AgentAvatar
        icon="sparkles"
        color="green"
        size="xl"
        className="absolute top-3 left-[34px] z-10 motion-safe:animate-scale-in"
      />
      <AgentAvatar
        icon="headphones"
        color="violet"
        size="lg"
        className="absolute right-0 bottom-0 rotate-6 motion-safe:animate-fade-in"
      />
    </div>
  );
}
