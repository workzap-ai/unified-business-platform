"use client";

import { useSyncExternalStore } from "react";
import { Bot, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate, formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../service";
import type { Conversation, ConversationMode } from "../types";
import { piKeys } from "./lib";

/** Media query subscription for layout decisions that CSS alone can't make. */
export function useMediaQuery(query: string, serverValue = true) {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}

/** Display names for agents and tools (configurable in PI); falls back to built-in labels. */
export function usePiNames() {
  const agents = useScopedQuery(piKeys.agents, () => piService.agents(), { staleTime: 5 * 60_000, retry: false });
  const tools = useScopedQuery(piKeys.tools, () => piService.tools(), { staleTime: 5 * 60_000, retry: false });
  const agentNames = new Map((agents.data ?? []).map((a) => [a.key as string, a.name]));
  const toolNames = new Map((tools.data ?? []).map((t) => [t.key, t.name]));
  return { agentNames, toolNames };
}

export function ModeIndicator({ mode, withLabel = false, className }: { mode: ConversationMode; withLabel?: boolean; className?: string }) {
  const ai = mode === "ai";
  const label = ai ? "PI is replying" : "Team is replying";
  const Icon = ai ? Bot : UserRound;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full text-[11px] font-medium",
        ai ? "text-pi" : "text-info",
        withLabel && (ai ? "bg-pi-soft px-1.5 py-0.5 text-pi-soft-foreground" : "bg-info-soft px-1.5 py-0.5"),
        className,
      )}
      title={label}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {withLabel ? <span>{ai ? "AI" : "Human"}</span> : <span className="sr-only">{label}</span>}
    </span>
  );
}

export function senderPrefix(sender: Conversation["last_sender"]) {
  if (sender === "ai") return "PI: ";
  if (sender === "human") return "You: ";
  return "";
}

/** Compact relative time for dense lists: now, 5m, 3h, Mon, 12 Sep. */
export function shortTime(value: string) {
  const date = new Date(value);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (Number.isNaN(diff)) return "—";
  if (diff < 60) return "now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  if (diff < 6 * 86400) return formatDate(date, "EEE");
  return formatDate(date, "d MMM");
}

export function TimeAgo({ value, className }: { value: string; className?: string }) {
  return (
    <time dateTime={value} title={formatDateTime(value)} className={cn("tabular shrink-0", className)}>
      {shortTime(value)}
    </time>
  );
}

/** Tooltip wrapper for disabled controls: disabled buttons don't receive pointer or focus events. */
export function DisabledHint({ content, children }: { content: string; children: React.ReactNode }) {
  return (
    <Tooltip content={content}>
      <span tabIndex={0} className="inline-flex rounded-md focus-visible:outline-2 focus-visible:outline-ring" aria-label={content}>
        {children}
      </span>
    </Tooltip>
  );
}

export function PriorityBadge({ priority, showNormal = false }: { priority: "normal" | "high" | "urgent"; showNormal?: boolean }) {
  if (priority === "urgent") return <Badge tone="danger" dot>Urgent</Badge>;
  if (priority === "high") return <Badge tone="warning" dot>High</Badge>;
  return showNormal ? <span className="text-xs text-muted-foreground">Normal</span> : null;
}

export function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h3 className={cn("text-2xs font-semibold tracking-wide text-muted-foreground uppercase", className)}>{children}</h3>;
}
