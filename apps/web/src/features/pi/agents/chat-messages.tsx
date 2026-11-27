"use client";

import { useState } from "react";
import { ChevronDown, Quote, RefreshCw, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { clock } from "../meeting-intel-service";
import { AgentAvatar } from "./agent-avatar";
import {
  ROLE_LABELS,
  type Agent,
  type ChatMessage,
  type ChatSource,
} from "./meeting-agents-service";

export function UserBubble({
  text,
  time,
  failed,
  onRetry,
}: {
  text: string;
  time?: string | null;
  failed?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-end motion-safe:animate-slide-in-right">
      <p
        className={cn(
          "max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-[14px] leading-relaxed break-words whitespace-pre-wrap text-primary-foreground shadow-sm",
          failed && "opacity-70",
        )}
      >
        {text}
      </p>
      {failed ? (
        <div className="mt-1.5 flex flex-wrap items-center justify-end gap-2 text-xs text-danger">
          <span role="alert">{failed}</span>
          {onRetry && (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              <RefreshCw /> Try again
            </Button>
          )}
        </div>
      ) : (
        time && (
          <span className="mt-1 text-[11px] text-muted-foreground">
            {formatTime(time)}
          </span>
        )
      )}
    </div>
  );
}

export function AssistantBubble({
  agent,
  message,
}: {
  agent: Agent;
  message: ChatMessage;
}) {
  const missing = !message.found;
  return (
    <div className="flex items-start gap-2.5 motion-safe:animate-fade-in">
      <AgentAvatar agent={agent} size="sm" className="mt-0.5" />
      <div className="min-w-0 max-w-[90%] space-y-2">
        <div
          className={cn(
            "rounded-2xl rounded-tl-md border px-3.5 py-2.5 text-[14px] leading-relaxed break-words whitespace-pre-wrap",
            missing
              ? "border-dashed border-border-strong bg-transparent text-muted-foreground"
              : "border-border bg-surface-muted text-foreground",
          )}
        >
          {missing && (
            <p className="mb-1 flex items-center gap-1.5 text-[13px] font-medium text-foreground-secondary">
              <SearchX className="size-3.5" aria-hidden="true" /> This was not
              said in the meeting
              {message.partial ? " (in the parts pi read)" : ""}
            </p>
          )}
          {message.text}
        </div>
        {message.partial && !missing && (
          <p className="px-1 text-xs text-muted-foreground">
            pi read the parts that matched, not every line.
          </p>
        )}
        {!missing && message.sources.length > 0 && (
          <Sources sources={message.sources} />
        )}
        {message.created_at && (
          <p className="px-1 text-[11px] text-muted-foreground">
            {formatTime(message.created_at)}
          </p>
        )}
      </div>
    </div>
  );
}

export function Sources({
  sources,
  large = false,
}: {
  sources: ChatSource[];
  /** 44px touch targets on a phone */
  large?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const expanded = sources.find((s) => s.ordinal === open);
  return (
    <section aria-label="From the meeting" className="px-1">
      <p className="mb-1.5 flex items-center gap-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
        <Quote className="size-3" aria-hidden="true" /> From the meeting
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {sources.map((s) => {
          const on = s.ordinal === open;
          const t = clock(s.start_ms);
          return (
            <li key={s.ordinal} className="max-w-full">
              <button
                type="button"
                aria-expanded={on}
                onClick={() => setOpen(on ? null : s.ordinal)}
                className={cn(
                  "flex min-h-8 max-w-full items-center gap-1.5 rounded-full border px-2.5 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  large && "max-sm:min-h-11",
                  on
                    ? "border-primary/40 bg-primary-soft text-primary-soft-foreground"
                    : "border-border bg-surface hover:bg-surface-muted",
                )}
              >
                <span className="shrink-0 font-semibold">
                  {ROLE_LABELS[s.role] ?? "Speaker"}
                  {t ? ` ${t}` : ""}
                </span>
                <span className="max-w-40 truncate text-muted-foreground sm:max-w-56">
                  {s.text}
                </span>
                <ChevronDown
                  className={cn(
                    "size-3 shrink-0 transition-transform motion-reduce:transition-none",
                    on && "rotate-180",
                  )}
                  aria-hidden="true"
                />
              </button>
            </li>
          );
        })}
      </ul>
      {expanded && (
        <blockquote className="mt-2 rounded-lg border-l-2 border-primary/50 bg-surface-muted px-3 py-2 text-[13px] break-words motion-safe:animate-fade-in">
          <span className="font-semibold">
            {expanded.speaker || ROLE_LABELS[expanded.role] || "Speaker"}
            {clock(expanded.start_ms) ? ` ${clock(expanded.start_ms)}` : ""}:
          </span>{" "}
          {expanded.text}
        </blockquote>
      )}
    </section>
  );
}

/** Three dots while pi writes the answer. Still (not bouncing) when motion is reduced. */
export function Typing({ agent }: { agent: Agent }) {
  return (
    <div className="flex items-start gap-2.5 motion-safe:animate-fade-in">
      <AgentAvatar agent={agent} size="sm" className="mt-0.5" />
      <div className="flex h-9 items-center gap-1 rounded-2xl rounded-tl-md border border-border bg-surface-muted px-3.5">
        <span className="sr-only">pi is reading the meeting</span>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            aria-hidden="true"
            style={{ animationDelay: `${i * 140}ms` }}
            className="size-1.5 rounded-full bg-muted-foreground/70 motion-safe:animate-bounce"
          />
        ))}
      </div>
    </div>
  );
}
