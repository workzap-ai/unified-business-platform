"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Languages, Lightbulb, NotebookPen } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  meetingRoomService,
  type LiveLine,
  type LiveTip,
} from "../meeting-room-service";
import { toRomanUrdu } from "./roman-urdu";

/**
 * The live view of the call, read from the server by polling (the agent writes it): captions with a
 * translation people can switch on, and, for staff only, pi's tips and notes. Nothing here sends a
 * word anywhere. When the workspace has these features off, the call shows the video service's own
 * captions as before.
 */

const POLL_MS = 2000;
const IDLE_MS = 10000; // while both features are off: look now and then, a flag may be turned on
const MAX_BACKOFF_MS = 15000;
const KEEP_LINES = 60;
const MODE_KEY = "room-captions-mode";

export type LiveState = {
  lines: LiveLine[];
  tips: LiveTip[];
  live: boolean;
  copilot: boolean;
};

const EMPTY: LiveState = { lines: [], tips: [], live: false, copilot: false };

function merge<T extends { n: number; v: number }>(
  have: T[],
  fresh: T[],
  limit: number,
): T[] {
  if (fresh.length === 0) return have;
  const byNumber = new Map(have.map((x) => [x.n, x]));
  for (const item of fresh) {
    const old = byNumber.get(item.n);
    if (!old || item.v >= old.v) byNumber.set(item.n, item);
  }
  return [...byNumber.values()].sort((a, b) => a.n - b.n).slice(-limit);
}

/** Polls the live view while the call is open. Never throws; a failure only slows the polling. */
export function useRoomLive(): LiveState {
  const [state, setState] = useState<LiveState>(EMPTY);
  const after = useRef(0);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let wait = POLL_MS;

    const next = (ms: number) => {
      if (!stopped) timer = setTimeout(() => void poll(), ms);
    };
    async function poll() {
      const entry = meetingRoomService.entry();
      if (!entry || document.hidden) return next(POLL_MS);
      try {
        const view = await meetingRoomService.live(entry, after.current);
        if (stopped) return;
        wait = view.enabled.live || view.enabled.copilot ? POLL_MS : IDLE_MS;
        if (view.reset) {
          after.current = 0;
          setState({ ...EMPTY, ...view.enabled });
        } else {
          after.current = Math.max(after.current, view.seq);
          setState((s) => ({
            lines: merge(s.lines, view.lines, KEEP_LINES),
            tips: merge(s.tips, view.tips, 12),
            ...view.enabled,
          }));
        }
      } catch {
        wait = Math.min(MAX_BACKOFF_MS, wait * 2);
      }
      next(wait);
    }
    void poll();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return state;
}

type Mode = "both" | "original" | "translation";

function readMode(): Mode {
  try {
    const saved = window.localStorage.getItem(MODE_KEY);
    if (saved === "original" || saved === "translation") return saved;
  } catch {
    // a private window or blocked storage: the default is fine
  }
  return "both";
}

const MODES: Array<{ id: Mode; label: string }> = [
  { id: "both", label: "Both" },
  { id: "original", label: "As said" },
  { id: "translation", label: "Translated" },
];

function Who({ line }: { line: LiveLine }) {
  return (
    <span className="mr-1.5 inline-block rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
      {line.role === "pi" ? "pi (AI)" : line.name || "Speaker"}
    </span>
  );
}

function Original({ line }: { line: LiveLine }) {
  return <>{line.lang === "ur" ? toRomanUrdu(line.text) : line.text}</>;
}

/** Captions with translation. Shows `fallback` (the video service's captions) until the agent
 *  has written its first line, and always when the feature is off. */
export function LiveCaptions({
  state,
  fallback,
}: {
  state: LiveState;
  fallback: ReactNode;
}) {
  // the room is drawn only in the browser (never on the server), so the saved choice is read here
  const [mode, setMode] = useState<Mode>(readMode);
  function choose(next: Mode) {
    setMode(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {
      // not remembered: it still applies now
    }
  }
  if (!state.live || state.lines.length === 0) return <>{fallback}</>;
  const lines = state.lines.slice(-3);
  return (
    <div
      aria-live="polite"
      className="space-y-1.5 rounded-xl border border-border bg-surface-muted px-3 py-2.5 text-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Languages className="size-3.5" /> Captions
        </span>
        <div
          role="group"
          aria-label="Caption language"
          className="flex gap-1 text-xs"
        >
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={mode === m.id}
              onClick={() => choose(m.id)}
              className={`rounded-full px-2 py-0.5 ${
                mode === m.id
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-surface"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
      {lines.map((line) => {
        const showOriginal = mode !== "translation" || !line.tr;
        const showTranslation = mode !== "original" && Boolean(line.tr);
        return (
          <div key={line.n} className="space-y-0.5 leading-snug">
            {showOriginal && (
              <p>
                <Who line={line} />
                <Original line={line} />
              </p>
            )}
            {showTranslation && (
              <p
                dir={line.tr_lang === "ur" ? "rtl" : "ltr"}
                lang={line.tr_lang}
                className={
                  showOriginal ? "pl-2 text-muted-foreground" : undefined
                }
              >
                {!showOriginal && <Who line={line} />}
                {line.tr}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

const NOTE_LABELS: Record<string, string> = {
  requirement_explicit: "Need",
  decision: "Decision",
  next_step: "Next step",
  action: "Action",
  question: "Question",
};

/** pi's private tips and notes for staff. Hidden from guests by the server; it is also visible if
 *  the staff member shares this window, so it says so. */
export function CopilotPanel({ state }: { state: LiveState }) {
  const [kept, setKept] = useState<Record<number, "busy" | "done" | "failed">>(
    {},
  );
  if (!state.copilot) return null;
  const entry = meetingRoomService.entry();
  const meetingId = entry?.kind === "staff" ? entry.meetingId : "";
  const items = [...state.tips].reverse().slice(0, 6);

  async function keep(n: number) {
    if (!meetingId) return;
    setKept((k) => ({ ...k, [n]: "busy" }));
    try {
      await meetingRoomService.keepNote(meetingId, n);
      setKept((k) => ({ ...k, [n]: "done" }));
    } catch {
      setKept((k) => ({ ...k, [n]: "failed" }));
    }
  }

  return (
    <section
      aria-label="pi copilot"
      className="space-y-2 rounded-xl border border-border bg-surface px-3 py-2.5 text-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-medium">
          <Lightbulb className="size-4 text-primary" /> pi copilot
        </h2>
        <span className="text-xs text-muted-foreground">
          Only you see this. Others can if you share this window.
        </span>
      </div>
      {items.length === 0 ? (
        <p className="text-muted-foreground">
          Tips and notes appear here as the customer speaks.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((tip) => (
            <li key={tip.n} className="flex items-start justify-between gap-2">
              <span className="min-w-0">
                {tip.kind === "note" ? (
                  <NotebookPen className="mr-1 inline size-3.5 text-muted-foreground" />
                ) : (
                  <Lightbulb className="mr-1 inline size-3.5 text-primary" />
                )}
                {tip.kind === "note" && tip.note_kind && (
                  <span className="mr-1 text-xs font-medium text-muted-foreground">
                    {NOTE_LABELS[tip.note_kind] ?? "Note"}:
                  </span>
                )}
                {tip.text}
              </span>
              {tip.kind === "note" && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={kept[tip.n] === "busy" || kept[tip.n] === "done"}
                  onClick={() => void keep(tip.n)}
                  aria-label={`Keep this note as a draft finding: ${tip.text}`}
                >
                  {kept[tip.n] === "done" ? (
                    <>
                      <Check /> Kept
                    </>
                  ) : kept[tip.n] === "failed" ? (
                    "Try again"
                  ) : (
                    "Keep"
                  )}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
