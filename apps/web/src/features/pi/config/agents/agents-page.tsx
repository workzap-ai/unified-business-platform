"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowRight, Bot, Plus, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatNumber, formatPercent, relativeTime } from "@/lib/format";
import { errorMessage } from "@/services/api-client";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/display";
import { Switch } from "@/components/ui/controls";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { Agent, AgentKey } from "../../types";
import {
  AGENT_ORDER,
  CardsSkeleton,
  MODEL_ALIASES,
  Stat,
  formatLatency,
  piKeys,
} from "../shared";

export function AgentsPage() {
  return (
    <RequirePermission permission="pi.agents.manage" area="PI agents">
      <Agents />
    </RequirePermission>
  );
}

function sortAgents(agents: Agent[]) {
  return [...agents].sort(
    (a, b) => AGENT_ORDER.indexOf(a.key) - AGENT_ORDER.indexOf(b.key),
  );
}

function Agents() {
  const agents = useScopedQuery(piKeys.agents, () => piService.agents());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const toggle = useScopedMutation(
    (input: { id: string; enabled: boolean }) =>
      piService.setAgentEnabled(input.id, input.enabled),
    {
      invalidate: [[...piKeys.agents]],
      success: (a) => `${a.name} ${a.enabled ? "enabled" : "disabled"}`,
    },
  );

  function onToggle(agent: Agent, enabled: boolean) {
    setErrors((e) => ({ ...e, [agent.id]: "" }));
    toggle.mutate(
      { id: agent.id, enabled },
      {
        onError: (error) =>
          setErrors((e) => ({ ...e, [agent.id]: errorMessage(error) })),
      },
    );
  }

  const list = agents.data ? sortAgents(agents.data) : undefined;

  return (
    <PageShell>
      <PageHeader
        title="Agents"
        description="PI works through six fixed roles. Configure their instructions, model and tools; every change is versioned."
        actions={
          <Button asChild>
            <Link href="/pi/agents/new">
              <Plus /> New configuration
            </Link>
          </Button>
        }
      />

      {agents.isError ? (
        <Card>
          <ErrorState
            error={agents.error}
            onRetry={() => void agents.refetch()}
          />
        </Card>
      ) : !list ? (
        <>
          <CardsSkeleton count={1} itemClassName="h-32" className="mb-4 md:grid-cols-1 xl:grid-cols-1" />
          <CardsSkeleton />
        </>
      ) : list.length === 0 ? (
        <Card>
          <EmptyState
            tone="pi"
            icon={Bot}
            title="No agents provisioned yet"
            description="PI's system agents are created when PI is installed in this environment."
          />
        </Card>
      ) : (
        <>
          <RoutingDiagram agents={list} />
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {list.map((agent) => (
              <li key={agent.id}>
                <AgentCard
                  agent={agent}
                  pending={
                    toggle.isPending && toggle.variables?.id === agent.id
                  }
                  error={errors[agent.id]}
                  onToggle={(enabled) => onToggle(agent, enabled)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </PageShell>
  );
}

function AgentCard({
  agent,
  pending,
  error,
  onToggle,
}: {
  agent: Agent;
  pending: boolean;
  error?: string;
  onToggle: (enabled: boolean) => void;
}) {
  const alias = MODEL_ALIASES.find((m) => m.value === agent.model_alias);
  const switchId = `agent-enabled-${agent.id}`;
  return (
    <Card
      className={cn(
        "flex h-full flex-col p-4 transition-colors",
        !agent.enabled && "bg-surface-muted/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/pi/agents/${agent.id}`}
              className="text-[14px] font-semibold hover:underline"
            >
              {agent.name}
            </Link>
            <Badge tone="outline" className="font-mono">
              v{agent.current_version}
            </Badge>
          </div>
          <p className="mt-0.5 text-[13px] text-muted-foreground">
            {agent.role}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor={switchId} className="sr-only">
            {agent.enabled ? `Disable ${agent.name}` : `Enable ${agent.name}`}
          </label>
          <span className="text-xs text-muted-foreground" aria-hidden="true">
            {agent.enabled ? "On" : "Off"}
          </span>
          <Switch
            id={switchId}
            checked={agent.enabled}
            disabled={pending}
            onCheckedChange={onToggle}
          />
        </div>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs font-medium text-danger">
          {error}
        </p>
      )}
      <dl className="mt-4 grid grid-cols-3 gap-x-3 gap-y-3">
        <Stat label="Model" value={alias?.label ?? agent.model_alias} />
        <Stat label="Tools" value={formatNumber(agent.tools.length)} />
        <Stat label="Runs (7d)" value={formatNumber(agent.runs_7d)} />
        <Stat
          label="Success"
          value={agent.runs_7d ? formatPercent(agent.success_rate, 1) : "—"}
          tone={
            agent.runs_7d && agent.success_rate < 0.9 ? "warning" : undefined
          }
        />
        <Stat label="Avg latency" value={formatLatency(agent.avg_latency_ms)} />
        <Stat
          label="Last run"
          value={agent.last_run_at ? relativeTime(agent.last_run_at) : "Never"}
        />
      </dl>
      <div className="mt-auto flex items-center gap-3 border-t border-border pt-3 text-xs font-medium">
        <Link
          href={`/pi/agents/${agent.id}`}
          className="text-primary hover:underline"
        >
          Details
        </Link>
        <Link
          href={`/pi/agents/${agent.id}/versions`}
          className="text-muted-foreground hover:text-foreground"
        >
          Versions
        </Link>
        <Link
          href={`/pi/agents/${agent.id}/tools`}
          className="text-muted-foreground hover:text-foreground"
        >
          Tools
        </Link>
      </div>
    </Card>
  );
}

/** Router → specialists → Handoff, drawn with plain boxes so it stays accessible. */
function RoutingDiagram({ agents }: { agents: Agent[] }) {
  const byKey = new Map(agents.map((a) => [a.key, a]));
  const node = (key: AgentKey, emphasis = false) => {
    const agent = byKey.get(key);
    if (!agent) return null;
    return (
      <div
        className={cn(
          "rounded-lg border px-3 py-2 text-center text-[13px] font-medium",
          emphasis
            ? "border-pi/30 bg-pi-soft text-pi-soft-foreground"
            : "border-border bg-surface",
          !agent.enabled && "border-dashed text-muted-foreground",
        )}
      >
        {agent.name}
        {!agent.enabled && (
          <span className="block text-2xs font-normal">Disabled</span>
        )}
      </div>
    );
  };
  const arrow = (
    <span className="flex shrink-0 items-center justify-center text-border-strong">
      <ArrowDown className="size-4 md:hidden" aria-hidden="true" />
      <ArrowRight className="hidden size-4 md:block" aria-hidden="true" />
    </span>
  );
  return (
    <Card className="mb-4 p-4">
      <h2 className="text-[13.5px] font-semibold">How a message is routed</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Every inbound message goes to the Router, which loads customer context
        and hands it to one specialist. Anything a person should decide goes to
        Handoff.
      </p>
      <div
        className="mt-4 flex flex-col items-stretch gap-2 md:flex-row md:items-center"
        role="list"
        aria-label="Routing order: Router, Customer and Memory, then Support, Requirement or Sales and Order, then Handoff"
      >
        <div role="listitem" className="md:w-32">
          {node("router", true)}
        </div>
        {arrow}
        <div role="listitem" className="md:w-40">
          {node("customer_memory")}
        </div>
        {arrow}
        <div
          role="listitem"
          className="flex flex-col gap-1.5 rounded-xl border border-dashed border-border p-2 md:flex-1"
        >
          <span className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
            One specialist
          </span>
          <div className="grid gap-1.5 sm:grid-cols-3">
            {node("support")}
            {node("requirement")}
            {node("sales_order")}
          </div>
        </div>
        {arrow}
        <div role="listitem" className="md:w-32">
          <div className="flex items-center justify-center gap-1.5">
            <UserCheck className="size-4 text-warning" aria-hidden="true" />
            <div className="flex-1">{node("handoff")}</div>
          </div>
        </div>
      </div>
    </Card>
  );
}
