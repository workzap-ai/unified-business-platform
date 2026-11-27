"use client";

import { Crosshair, FileSearch, RefreshCw, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import { AgentAvatar, stylesFor } from "./agent-avatar";
import { Sources } from "./chat-messages";
import type { Agent, DebriefItem } from "./meeting-agents-service";

/** One starter question and its answer, with the lines it came from. */
export function DebriefBlock({ item }: { item: DebriefItem }) {
  const missing = !item.found;
  return (
    <li className="space-y-1.5 py-3.5 first:pt-0 last:pb-0 motion-safe:animate-fade-in">
      <p className="text-xs font-medium text-muted-foreground">
        {item.question}
      </p>
      {missing ? (
        <p className="flex items-start gap-1.5 text-[14px] leading-relaxed text-muted-foreground">
          <SearchX className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span className="break-words">
            Not said in this meeting
            {item.partial ? " (in the parts pi read)" : ""}
          </span>
        </p>
      ) : (
        <p className="text-[14px] leading-relaxed break-words whitespace-pre-wrap text-foreground">
          {item.answer}
        </p>
      )}
      {item.partial && !missing && (
        <p className="text-xs text-muted-foreground">
          pi read the parts that matched, not every line.
        </p>
      )}
      {!missing && item.sources.length > 0 && (
        <Sources sources={item.sources} large />
      )}
    </li>
  );
}

export function DebriefSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-3 w-2/5" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      ))}
    </div>
  );
}

/** The topics this agent listens for, shown before the first run. */
export function LooksFor({ agent }: { agent: Agent }) {
  const chip = stylesFor(agent.color).chip;
  return (
    <section aria-label="Looks for">
      <p className="mb-2 flex items-center gap-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
        <Crosshair className="size-3" aria-hidden="true" /> Looks for
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {agent.focus.map((f) => (
          <li
            key={f}
            className={cn(
              "max-w-full rounded-full px-2.5 py-1 text-xs break-words",
              chip,
            )}
          >
            {f}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A small picture and one line, shown before anything has been run. */
export function DebriefEmpty({ agent }: { agent: Agent }) {
  return (
    <div className="flex flex-col items-center gap-3 py-2 text-center">
      <div className="relative" aria-hidden="true">
        <AgentAvatar agent={agent} size="lg" />
        <span className="absolute -right-3 -bottom-2 grid size-7 place-items-center rounded-full bg-surface text-muted-foreground shadow-sm ring-1 ring-border motion-safe:animate-scale-in">
          <FileSearch className="size-3.5" />
        </span>
      </div>
      <p className="max-w-xs text-[13px] leading-relaxed text-muted-foreground">
        {agent.name} will ask this meeting its three starter questions and show
        the lines each answer came from. Press Run debrief to start.
      </p>
    </div>
  );
}

export function RetryButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={onClick}
      className="min-h-11 sm:min-h-8"
    >
      <RefreshCw /> Try again
    </Button>
  );
}
