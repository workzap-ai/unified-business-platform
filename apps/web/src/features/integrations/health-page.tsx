"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  Activity,
  Ban,
  CircleAlert,
  PlugZap,
  TriangleAlert,
} from "lucide-react";
import { formatDateTime } from "@/lib/format";
import { RequirePermission } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { integrationsService } from "./service";
import {
  CircuitBadge,
  IntegrationsFrame,
  StateBadge,
  When,
  useDefinitions,
} from "./components";
import { formatLatency } from "./lib";
import type { HealthRow } from "./types";

export function HealthPage() {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Health />
    </RequirePermission>
  );
}

function Health() {
  const health = useScopedQuery(["integrations", "health"], () =>
    integrationsService.health(),
  );
  const definitions = useDefinitions();
  const names = useMemo(
    () => new Map((definitions.data ?? []).map((d) => [d.key, d.name])),
    [definitions.data],
  );
  const s = health.data?.summary;

  const columns: Column<HealthRow>[] = [
    {
      key: "name",
      header: "Connection",
      cell: (r) => (
        <div className="min-w-0">
          <Link
            href={`/settings/integrations/connections/${r.id}`}
            className="block truncate font-medium hover:underline"
          >
            {r.display_name}
          </Link>
          <p className="truncate text-xs text-muted-foreground">
            {names.get(r.integration_key) ?? r.integration_key}
          </p>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      hideBelow: "sm",
      cell: (r) => <StateBadge value={r.status} />,
    },
    {
      key: "health",
      header: "Health",
      cell: (r) => <StateBadge value={r.health} />,
    },
    {
      key: "circuit",
      header: "Circuit",
      hideBelow: "md",
      cell: (r) => <CircuitBadge value={r.circuit_state} />,
    },
    {
      key: "latency",
      header: "Latency",
      hideBelow: "md",
      align: "right",
      cell: (r) => (
        <span className="tabular">{formatLatency(r.latency_ms)}</span>
      ),
    },
    {
      key: "rate",
      header: "Rate limited until",
      hideBelow: "lg",
      cell: (r) =>
        r.rate_limited_until ? (
          <span className="text-xs text-warning">
            {formatDateTime(r.rate_limited_until)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "webhook",
      header: "Webhooks",
      hideBelow: "lg",
      cell: (r) => <StateBadge value={r.webhook_state} />,
    },
    {
      key: "sync",
      header: "Sync",
      hideBelow: "lg",
      cell: (r) => <StateBadge value={r.sync_state} />,
    },
    {
      key: "success",
      header: "Last success",
      hideBelow: "xl",
      cell: (r) => <When value={r.last_success_at} />,
    },
    {
      key: "failure",
      header: "Last failure",
      hideBelow: "xl",
      cell: (r) => <When value={r.last_failure_at} empty="None" />,
    },
  ];

  return (
    <IntegrationsFrame
      title="Health"
      description="Current health of every connection in this environment."
    >
      <MetricGrid className="mb-4">
        <MetricCard
          label="Connected"
          icon={PlugZap}
          tone="success"
          value={s?.connected ?? 0}
          loading={health.isPending}
        />
        <MetricCard
          label="Degraded"
          icon={TriangleAlert}
          tone={s?.degraded ? "warning" : "default"}
          value={s?.degraded ?? 0}
          loading={health.isPending}
        />
        <MetricCard
          label="Failing"
          icon={CircleAlert}
          tone={s?.failing ? "danger" : "default"}
          value={s?.failing ?? 0}
          loading={health.isPending}
        />
        <MetricCard
          label="Disabled"
          icon={Ban}
          value={s?.disabled ?? 0}
          loading={health.isPending}
        />
      </MetricGrid>
      <Notice tone="neutral" icon={Activity} className="mb-4">
        Computed from recorded calls and the most recent test. Opening this page
        never calls providers or changes data.
      </Notice>
      <DataTable
        caption="Connection health"
        columns={columns}
        rows={health.data?.connections}
        loading={health.isPending}
        error={health.error}
        onRetry={() => void health.refetch()}
        getRowId={(r) => r.id}
        rowHref={(r) => `/settings/integrations/connections/${r.id}`}
        loadingRows={4}
        empty={
          <EmptyState
            icon={Activity}
            title="Nothing to monitor yet"
            description="Connect an integration and its health appears here."
          />
        }
      />
    </IntegrationsFrame>
  );
}
