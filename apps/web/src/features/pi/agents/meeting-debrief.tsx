"use client";

import { FileText, Play, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { ApiError, errorMessage } from "@/services/api-client";
import { AgentAvatar } from "./agent-avatar";
import {
  DebriefBlock,
  DebriefEmpty,
  DebriefSkeleton,
  LooksFor,
  RetryButton,
} from "./meeting-debrief-parts";
import { meetingAgentsService, type Debrief } from "./meeting-agents-service";
import { agentFor, useAgents } from "./use-agents";

const debriefKey = (id: string) => ["pi", "meeting-intel", id, "debrief"];

function failure(e: unknown): string {
  if (e instanceof ApiError && e.code === "MEETING_ASK_UNAVAILABLE")
    return "The debrief could not be written right now. Try again in a moment.";
  if (e instanceof ApiError && e.code === "TRANSCRIPT_EMPTY")
    return "This meeting has no transcript yet, so there is nothing to debrief.";
  return errorMessage(e, "Something went wrong. Try again.");
}

/**
 * The meeting agent's three starter questions, answered from the transcript. The saved debrief
 * loads on its own (no model call); the model runs only when a person presses the button.
 */
export function MeetingDebrief({
  meetingId,
  agentKey,
  hasTranscript,
}: {
  meetingId: string;
  /** the meeting's own agent; null means pi */
  agentKey: string | null;
  hasTranscript: boolean;
}) {
  const client = useQueryClient();
  const { scopeKey } = useSession();
  const agents = useAgents();
  const saved = useScopedQuery(
    debriefKey(meetingId),
    () => meetingAgentsService.getDebrief(meetingId),
    { enabled: hasTranscript, retry: false },
  );
  const run = useScopedMutation(
    () => meetingAgentsService.runDebrief(meetingId),
    {
      toastErrors: false,
      onSuccess: (d: Debrief) =>
        client.setQueryData([...scopeKey, ...debriefKey(meetingId)], d),
    },
  );

  const agent = agentFor(agents.data, saved.data?.agent_key || agentKey);
  const items = saved.data?.items ?? [];
  const running = run.isPending;
  const ran = items.length > 0;
  const loading = hasTranscript && saved.isPending;
  const error = run.isError
    ? failure(run.error)
    : saved.isError
      ? failure(saved.error)
      : "";
  const retry = () => (run.isError ? run.mutate(undefined) : saved.refetch());

  return (
    <section
      aria-labelledby="debrief-title"
      className="rounded-xl border border-border bg-surface p-4 shadow-sm"
    >
      <header className="flex flex-wrap items-center gap-3">
        <AgentAvatar agent={agent} size="md" />
        <div className="min-w-0 flex-1 basis-40">
          <h2
            id="debrief-title"
            className="text-[15px] font-semibold tracking-tight break-words"
          >
            {agent.name} debrief
          </h2>
          <p className="text-xs text-muted-foreground">
            What this agent looks for in this meeting
          </p>
        </div>
        <Button
          variant={ran ? "secondary" : "default"}
          size="sm"
          loading={running}
          disabled={!hasTranscript || running || loading}
          onClick={() => run.mutate(undefined)}
          className="min-h-11 max-sm:w-full sm:min-h-8"
        >
          {!running && (ran ? <RefreshCw /> : <Play />)}
          {running ? "Reading the meeting" : ran ? "Run again" : "Run debrief"}
        </Button>
      </header>

      <div className="mt-4" aria-live="polite" aria-busy={running || loading}>
        {!hasTranscript ? (
          <p className="flex items-center gap-2.5 rounded-lg bg-surface-muted px-3 py-3 text-[13px] text-muted-foreground">
            <FileText className="size-4 shrink-0" aria-hidden="true" />
            No transcript yet. Once the meeting has been transcribed, the
            debrief can run.
          </p>
        ) : running || loading ? (
          <DebriefSkeleton />
        ) : error ? (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-danger-soft px-3 py-3 text-[13px] text-danger"
          >
            <span className="min-w-0 break-words">{error}</span>
            <RetryButton onClick={retry} />
          </div>
        ) : ran ? (
          <ul className="divide-y divide-border">
            {items.map((item, i) => (
              <DebriefBlock key={`${i}-${item.question}`} item={item} />
            ))}
          </ul>
        ) : (
          <div className="space-y-4">
            {agent.focus.length > 0 && <LooksFor agent={agent} />}
            <DebriefEmpty agent={agent} />
          </div>
        )}
      </div>
    </section>
  );
}
