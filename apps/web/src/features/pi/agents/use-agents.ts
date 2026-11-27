"use client";

import { useScopedQuery } from "@/hooks/use-scoped";
import {
  ARCHIVED_AGENT,
  DEFAULT_AGENT_KEY,
  meetingAgentsService,
  PI_AGENT,
  type Agent,
} from "./meeting-agents-service";

export const AGENTS_KEY = ["pi", "meeting-agents"];

/** The agents this workspace can use (built-in first, then its own). One cached list for every screen. */
export function useAgents(enabled = true) {
  return useScopedQuery(
    AGENTS_KEY,
    async () => (await meetingAgentsService.list()).agents,
    { enabled, staleTime: 30_000 },
  );
}

/** The agent for a key; a missing key means pi, an unlisted one is an archived agent. */
export function agentFor(
  agents: Agent[] | undefined,
  key: string | null | undefined,
): Agent {
  const wanted = key || DEFAULT_AGENT_KEY;
  const found = agents?.find((a) => a.key === wanted);
  if (found) return found;
  if (wanted === DEFAULT_AGENT_KEY || !agents) return PI_AGENT;
  return ARCHIVED_AGENT;
}
