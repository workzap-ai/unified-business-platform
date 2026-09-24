"use client";

import Link from "next/link";
import { AlertTriangle, ArrowLeft, Wrench } from "lucide-react";
import { formatNumber, relativeTime } from "@/lib/format";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
  SectionHeader,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "../../service";
import type { ToolDefinition } from "../../types";
import { CapabilityBadge, MUTATION_WARNING, piKeys } from "../shared";
import { AgentToolsCard } from "./agent-detail-page";

export function AgentToolsPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="pi.agents.manage" area="PI agents">
      <AgentTools id={id} />
    </RequirePermission>
  );
}

function AgentTools({ id }: { id: string }) {
  const agent = useScopedQuery(piKeys.agent(id), () => piService.agent(id));
  const tools = useScopedQuery(piKeys.tools, () => piService.tools());
  useBreadcrumbs(
    agent.data
      ? [
          { label: agent.data.name, href: `/pi/agents/${agent.data.id}` },
          { label: "Tools" },
        ]
      : [],
  );

  if (agent.isError) {
    return (
      <PageShell>
        <Card>
          <ErrorState
            error={agent.error}
            onRetry={() => void agent.refetch()}
          />
        </Card>
      </PageShell>
    );
  }
  const assigned = new Set(agent.data?.tools ?? []);

  const columns: Column<ToolDefinition>[] = [
    {
      key: "name",
      header: "Tool",
      cell: (t) => (
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5 font-medium">
            {t.name}
            {assigned.has(t.key) && <Badge tone="pi">This agent</Badge>}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t.description}
          </p>
          {t.capability === "mutation" && (
            <p className="mt-1 flex items-center gap-1 text-xs font-medium text-warning">
              <AlertTriangle className="size-3.5" aria-hidden="true" />
              {MUTATION_WARNING}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "capability",
      header: "Capability",
      cell: (t) => <CapabilityBadge capability={t.capability} />,
    },
    {
      key: "permission",
      header: "Permission",
      cell: (t) => <span className="font-mono text-xs">{t.permission}</span>,
      hideBelow: "lg",
    },
    {
      key: "confirmation",
      header: "Confirmation",
      cell: (t) =>
        t.requires_confirmation ? (
          <Badge tone="warning">Required</Badge>
        ) : (
          <span className="text-muted-foreground">No</span>
        ),
      hideBelow: "md",
    },
    {
      key: "status",
      header: "Workspace",
      cell: (t) => (
        <StatusBadge
          status={t.enabled ? "active" : "disabled"}
          label={t.enabled ? "On" : "Off"}
        />
      ),
      hideBelow: "sm",
    },
    {
      key: "calls",
      header: "Calls (7d)",
      align: "right",
      cell: (t) => <span className="tabular">{formatNumber(t.calls_7d)}</span>,
      hideBelow: "md",
    },
    {
      key: "failures",
      header: "Failures (7d)",
      align: "right",
      cell: (t) => (
        <span
          className={
            t.failures_7d ? "tabular font-medium text-danger" : "tabular"
          }
        >
          {formatNumber(t.failures_7d)}
        </span>
      ),
      hideBelow: "md",
    },
    {
      key: "last",
      header: "Last called",
      cell: (t) =>
        t.last_called_at ? relativeTime(t.last_called_at) : "Never",
      hideBelow: "xl",
    },
  ];

  return (
    <PageShell>
      <Link
        href={`/pi/agents/${agent.data?.id ?? id}`}
        className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        {agent.data?.name ?? "Agent"}
      </Link>
      <PageHeader
        title="Tools"
        description="Choose which tools this agent may call. Workspace-wide tool switches live in PI settings."
        actions={
          <Link
            href="/pi/settings/tool-permissions"
            className="text-[13px] font-medium text-primary hover:underline"
          >
            Tool permissions
          </Link>
        }
      />
      {agent.data ? (
        <AgentToolsCard agent={agent.data} />
      ) : (
        <Skeleton className="h-72 rounded-xl" />
      )}

      <SectionHeader
        className="mt-6"
        title="Tool catalog"
        description="All tools PI can use in this workspace, with 7-day activity"
      />
      <DataTable
        columns={columns}
        rows={tools.data}
        getRowId={(t) => t.key}
        loading={tools.isPending}
        error={tools.error}
        onRetry={() => void tools.refetch()}
        caption="Tool catalog"
        rowClassName={(t) =>
          t.capability === "mutation" ? "bg-warning-soft/30" : undefined
        }
        empty={
          <EmptyState
            tone="pi"
            icon={Wrench}
            title="No tools registered"
            description="PI's tools are provisioned with the product."
            compact
          />
        }
      />
    </PageShell>
  );
}
