"use client";

import { useState } from "react";
import { ChevronsUpDown } from "lucide-react";
import { useScopedMutation } from "@/hooks/use-scoped";
import { AgentAvatar } from "./agent-avatar";
import { AgentChooser } from "./agent-chooser";
import { meetingAgentsService } from "./meeting-agents-service";
import { agentFor, useAgents } from "./use-agents";

/** The meeting's agent in its header: shows who is listening and, when allowed, changes it. */
export function MeetingAgentChip({
  meetingId,
  agentKey,
  canChange,
}: {
  meetingId: string;
  agentKey: string | null;
  canChange: boolean;
}) {
  const agents = useAgents();
  const [open, setOpen] = useState(false);
  const agent = agentFor(agents.data, agentKey);
  const set = useScopedMutation(
    (key: string) => meetingAgentsService.setMeetingAgent(meetingId, key),
    {
      invalidate: [["pi", "meeting-intel", meetingId]],
      success: "Agent changed",
    },
  );
  const body = (
    <>
      <AgentAvatar agent={agent} size="sm" className="-ml-0.5 scale-90" />
      <span className="truncate text-xs font-medium">{agent.name}</span>
      {canChange && (
        <ChevronsUpDown
          className="size-3 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      )}
    </>
  );
  const cls =
    "inline-flex min-h-8 max-w-56 items-center gap-1.5 rounded-full border border-border bg-surface py-0.5 pr-2.5 pl-1";
  if (!canChange)
    return (
      <span className={cls} title="The agent listening in this meeting">
        {body}
      </span>
    );
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={set.isPending}
        aria-label={`Meeting agent: ${agent.name}. Change agent`}
        className={`${cls} min-h-11 sm:min-h-8 transition-colors hover:bg-surface-muted disabled:opacity-60`}
      >
        {body}
      </button>
      <AgentChooser
        open={open}
        onOpenChange={setOpen}
        value={agentKey}
        title="Choose this meeting's agent"
        description="The agent decides what pi listens for in this meeting."
        onSelect={(a) => set.mutate(a.key)}
      />
    </>
  );
}
