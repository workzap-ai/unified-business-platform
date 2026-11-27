"use client";

import { useEffect, useState } from "react";
import { useCallStateHooks } from "@stream-io/video-react-sdk";
import { Eye, EyeOff, ScanEye } from "lucide-react";

/**
 * Whether pi can see the screen someone shares. The room agent writes a small state on the call
 * (`pi_screen`: none, looking or seeing; never what was seen) and every browser in the room gets it
 * at once. A person who shares can tell at a glance if pi really has their screen: pi's face grows
 * an eye, the bar says so, and if the screen never reached pi after a few seconds, a plain notice
 * says that instead of leaving them to guess.
 */

export type PiScreen = "none" | "looking" | "seeing" | "missing";

const MISSING_AFTER_S = 8; // a share pi has not received for this long is reported as not received

export function usePiScreen(): { state: PiScreen; sharing: boolean } {
  const { useCallCustomData, useHasOngoingScreenShare } = useCallStateHooks();
  const custom = useCallCustomData() as Record<string, unknown> | undefined;
  const sharing = useHasOngoingScreenShare();
  const told = custom?.pi_screen;
  const known: PiScreen =
    told === "looking" || told === "seeing" ? told : "none";
  const [waited, setWaited] = useState(false);
  useEffect(() => {
    if (!sharing || known !== "none") return;
    const t = setTimeout(() => setWaited(true), MISSING_AFTER_S * 1000);
    return () => {
      clearTimeout(t);
      setWaited(false); // a new share, or pi got it: the wait starts again
    };
  }, [sharing, known]);
  if (!sharing) return { state: "none", sharing };
  if (known === "none" && waited) return { state: "missing", sharing };
  return { state: known, sharing };
}

/** Which agent is in this meeting (the room agent writes `pi_agent` on the call); pi when unknown. */
export function usePiAgent(): string {
  const { useCallCustomData } = useCallStateHooks();
  const custom = useCallCustomData() as Record<string, unknown> | undefined;
  const told = custom?.pi_agent;
  return typeof told === "string" && /^[a-z0-9_-]{1,40}$/i.test(told)
    ? told
    : "pi";
}

/** The small eye on pi's own tile while a screen is shared. */
export function PiEye({ state }: { state: PiScreen }) {
  if (state === "none") return null;
  const label =
    state === "seeing"
      ? "pi can see the shared screen"
      : state === "looking"
        ? "pi is looking at the shared screen"
        : "pi has not received the shared screen";
  const tone =
    state === "seeing"
      ? "bg-emerald-500 text-white"
      : state === "looking"
        ? "bg-sky-500 text-white"
        : "bg-amber-500 text-white";
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={`absolute -right-2 -top-2 flex size-9 items-center justify-center rounded-full shadow-md ring-2 ring-surface ${tone}`}
    >
      {state === "looking" && (
        <span
          aria-hidden
          className="absolute inset-0 rounded-full bg-sky-400/50 motion-safe:animate-ping"
        />
      )}
      {state === "seeing" && (
        <span
          aria-hidden
          className="absolute inset-0 rounded-full bg-emerald-400/40 motion-safe:animate-pulse"
        />
      )}
      {state === "missing" ? (
        <EyeOff className="relative size-5" aria-hidden />
      ) : state === "looking" ? (
        <ScanEye className="relative size-5" aria-hidden />
      ) : (
        <Eye className="relative size-5" aria-hidden />
      )}
    </span>
  );
}

/** A line under the room bar while a screen is shared: what pi sees of it, in plain words. */
export function PiScreenBanner() {
  const { state, sharing } = usePiScreen();
  if (!sharing) return null;
  const copy: Record<PiScreen, { text: string; box: string }> = {
    none: {
      text: "A screen is being shared. pi is getting it ready…",
      box: "border-border bg-surface-muted text-muted-foreground",
    },
    looking: {
      text: "pi is looking at the shared screen…",
      box: "border-sky-300/60 bg-sky-500/10 text-sky-800 dark:text-sky-200",
    },
    seeing: {
      text: "pi can see the shared screen. It tells what kind of page it is, never reads names or numbers.",
      box: "border-emerald-300/60 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200",
    },
    missing: {
      text: "pi has not received the shared screen yet. Ask “pi, can you see my screen?”, or stop sharing and share again.",
      box: "border-amber-300/70 bg-amber-500/10 text-amber-900 dark:text-amber-200",
    },
  };
  const { text, box } = copy[state];
  return (
    <p
      role="status"
      aria-live="polite"
      className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${box}`}
    >
      <PiEyeInline state={state} />
      {text}
    </p>
  );
}

function PiEyeInline({ state }: { state: PiScreen }) {
  const Icon =
    state === "missing" ? EyeOff : state === "looking" ? ScanEye : Eye;
  return (
    <Icon
      aria-hidden
      className={`size-4 shrink-0 ${state === "looking" ? "motion-safe:animate-pulse" : ""}`}
    />
  );
}
