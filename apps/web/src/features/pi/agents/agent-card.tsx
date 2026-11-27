"use client";

import { MoreHorizontal, Pencil, Archive } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { AgentAvatar, stylesFor } from "./agent-avatar";
import type { Agent } from "./meeting-agents-service";

export const PI_BLURB =
  "pi's own personality: listens, asks one question at a time, always says it is an AI";

/** One agent in the gallery: avatar, what it looks for, and questions it answers well. */
export function AgentCard({
  agent,
  onEdit,
  onArchive,
}: {
  agent: Agent;
  onEdit: (a: Agent) => void;
  onArchive: (a: Agent) => void;
}) {
  const style = stylesFor(agent.color);
  const editable = agent.kind === "custom" && agent.can_edit;
  return (
    <li className="group relative">
      {/* a soft gradient glow that fades in around the card */}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute -inset-px rounded-[14px] bg-gradient-to-br opacity-0 blur-[3px] transition-opacity duration-200 group-focus-within:opacity-100 group-hover:opacity-100 motion-reduce:transition-none",
          style.glow,
        )}
      />
      <article
        aria-label={agent.name}
        className="relative flex h-full flex-col rounded-xl border border-border bg-surface p-4 shadow-sm transition-all duration-200 group-focus-within:-translate-y-0.5 group-focus-within:shadow-md group-hover:-translate-y-0.5 group-hover:shadow-md motion-reduce:transition-none motion-reduce:group-hover:translate-y-0"
      >
        <div className="flex items-start gap-3">
          <AgentAvatar agent={agent} size="lg" showAi />
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex items-center gap-2">
              <h2 className="line-clamp-2 text-[15px] leading-snug font-semibold break-words">
                {agent.name}
              </h2>
              {agent.is_default && (
                <span className="shrink-0 rounded-full bg-primary-soft px-1.5 py-px text-[10.5px] font-medium text-primary-soft-foreground">
                  Default
                </span>
              )}
            </div>
            <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">
              {agent.is_default ? PI_BLURB : agent.tagline}
            </p>
          </div>
          {editable && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="-mt-1 -mr-1.5 size-11 sm:size-9"
                  aria-label={`Options for ${agent.name}`}
                >
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem onSelect={() => onEdit(agent)}>
                  <Pencil /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem destructive onSelect={() => onArchive(agent)}>
                  <Archive /> Archive
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {agent.focus.length > 0 && (
          <div className="mt-4">
            <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
              Looks for
            </p>
            <ul className="mt-1.5 space-y-1">
              {agent.focus.slice(0, 3).map((f) => (
                <li
                  key={f}
                  className="flex items-start gap-2 text-[13px] text-foreground-secondary"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mt-[7px] size-1.5 shrink-0 rounded-full bg-gradient-to-br",
                      style.tile,
                    )}
                  />
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}

        {agent.sample_questions.length > 0 && (
          <ul
            aria-label="Questions it answers well"
            className="mt-auto flex flex-wrap gap-1.5 pt-4"
          >
            {agent.sample_questions.slice(0, 2).map((q) => (
              <li
                key={q}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs leading-snug",
                  style.chip,
                )}
              >
                {q}
              </li>
            ))}
          </ul>
        )}
      </article>
    </li>
  );
}
