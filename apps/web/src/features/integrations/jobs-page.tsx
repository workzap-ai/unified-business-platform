"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  CircleX,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";
import { humanize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
  Tooltip,
} from "@/components/ui/overlays";
import { RequirePermission } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { FilterBar, FilterSelect } from "@/components/app/filters";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { ConfirmDialog } from "@/components/app/forms";
import { EmptyState } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { integrationsService } from "./service";
import {
  IntegrationsFrame,
  StateBadge,
  When,
  useConnectionIndex,
  valueLabel,
} from "./components";
import { canJob, permissionReason } from "./lib";
import { WORK_STATUSES, type JobAction, type SyncJob } from "./types";

const PAGE_SIZE = 25;
const ACTIONS: { action: JobAction; label: string; icon: typeof Pause }[] = [
  { action: "pause", label: "Pause", icon: Pause },
  { action: "resume", label: "Resume", icon: Play },
  { action: "retry", label: "Retry", icon: RotateCcw },
  { action: "cancel", label: "Cancel", icon: CircleX },
];

export function JobsPage() {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Jobs />
    </RequirePermission>
  );
}

function Jobs() {
  const { can } = useSession();
  const canOperate = can("integrations.operate");
  const [state, setState, reset] = useUrlState({
    connection: "",
    status: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    connection_id: state.connection || undefined,
    status: state.status || undefined,
    page,
    pageSize: PAGE_SIZE,
  };
  const list = useScopedQuery(
    ["integrations", "jobs", params],
    () => integrationsService.jobs(params),
    {
      placeholderData: (previous) => previous,
    },
  );
  const all = useScopedQuery(["integrations", "jobs", "stats"], () =>
    integrationsService.jobs({ pageSize: 100 }),
  );
  const index = useConnectionIndex();
  const names = useMemo(
    () => new Map((index.data?.items ?? []).map((c) => [c.id, c.display_name])),
    [index.data],
  );
  const [cancelling, setCancelling] = useState<SyncJob | null>(null);
  const act = useScopedMutation(
    ({ job, action }: { job: SyncJob; action: JobAction }) =>
      integrationsService.jobAction(job.id, action),
    {
      invalidate: [["integrations"]],
      success: (j) =>
        `${humanize(j.entity)} sync is now ${valueLabel(j.status).toLowerCase()}`,
      onSuccess: () => setCancelling(null),
    },
  );
  const count = (status: string) =>
    (all.data?.items ?? []).filter((j) => j.status === status).length;

  const columns: Column<SyncJob>[] = [
    {
      key: "entity",
      header: "Job",
      cell: (j) => (
        <div className="min-w-0">
          <p className="font-medium">
            {humanize(j.entity)}{" "}
            <span className="font-normal text-muted-foreground">
              · {j.mode}
            </span>
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {j.direction === "none" ? "" : `${humanize(j.direction)} · `}
            <span className="md:hidden">
              {names.get(j.connection_id) ?? j.integration_key} ·{" "}
            </span>
            <When value={j.created_at} />
          </p>
        </div>
      ),
    },
    {
      key: "connection",
      header: "Connection",
      hideBelow: "md",
      cell: (j) => (
        <Link
          href={`/settings/integrations/connections/${j.connection_id}`}
          className="block max-w-48 truncate hover:underline"
        >
          {names.get(j.connection_id) ?? j.integration_key}
        </Link>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (j) => <StateBadge value={j.status} />,
    },
    {
      key: "stats",
      header: "Records",
      hideBelow: "lg",
      cell: (j) => (
        <Tooltip
          content={`Discovered ${j.stats.discovered} · created ${j.stats.created} · updated ${j.stats.updated} · skipped ${j.stats.skipped} · failed ${j.stats.failed} · conflicts ${j.stats.conflicts}`}
        >
          <span tabIndex={0} className="tabular text-xs whitespace-nowrap">
            {j.stats.created} new · {j.stats.updated} updated
            {j.stats.failed > 0 && (
              <span className="text-danger"> · {j.stats.failed} failed</span>
            )}
          </span>
        </Tooltip>
      ),
    },
    {
      key: "started",
      header: "Started",
      hideBelow: "xl",
      cell: (j) => <When value={j.started_at} empty="Not started" />,
    },
    {
      key: "finished",
      header: "Finished",
      hideBelow: "xl",
      cell: (j) => <When value={j.finished_at} empty="—" />,
    },
    {
      key: "error",
      header: "Last error",
      hideBelow: "lg",
      cell: (j) =>
        j.last_error ? (
          <span className="line-clamp-2 max-w-64 text-xs text-danger">
            {j.last_error}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (j) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="secondary"
              size="xs"
              aria-label={`Actions for ${j.entity} ${j.mode} sync`}
            >
              Actions
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-60">
            <DropdownMenuLabel className="normal-case">
              {canOperate
                ? `Status: ${valueLabel(j.status)}`
                : permissionReason("integrations.operate")}
            </DropdownMenuLabel>
            {ACTIONS.map(({ action, label, icon: Icon }) => {
              const valid = canJob(j.status, action);
              return (
                <DropdownMenuItem
                  key={action}
                  disabled={!valid || !canOperate}
                  destructive={action === "cancel"}
                  onSelect={() =>
                    action === "cancel"
                      ? setCancelling(j)
                      : act.mutate({ job: j, action })
                  }
                >
                  <Icon /> {label}
                  {!valid && (
                    <span className="ml-auto text-2xs text-muted-foreground">
                      Not from {valueLabel(j.status).toLowerCase()}
                    </span>
                  )}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];
  const active = [state.connection, state.status].filter(Boolean).length;

  return (
    <IntegrationsFrame
      title="Sync jobs"
      description="Record synchronisation between providers and this workspace. Only actions valid for a job's state are offered."
    >
      <MetricGrid className="mb-5">
        <MetricCard
          label="Running"
          icon={RefreshCw}
          value={count("running")}
          loading={all.isPending}
          detail={`${count("pending")} queued`}
        />
        <MetricCard
          label="Paused"
          icon={Pause}
          tone={count("paused") ? "warning" : "default"}
          value={count("paused")}
          loading={all.isPending}
        />
        <MetricCard
          label="Failed"
          icon={TriangleAlert}
          tone={count("failed") + count("dead_letter") ? "danger" : "default"}
          value={count("failed") + count("dead_letter")}
          loading={all.isPending}
          href="/settings/integrations/failures"
        />
        <MetricCard
          label="Succeeded"
          icon={Play}
          tone="success"
          value={count("succeeded")}
          loading={all.isPending}
        />
      </MetricGrid>
      <FilterBar activeCount={active} onClear={reset}>
        <FilterSelect
          label="Connection"
          value={state.connection}
          onChange={(connection) => setState({ connection })}
          options={(index.data?.items ?? []).map((c) => ({
            value: c.id,
            label: c.display_name,
          }))}
        />
        <FilterSelect
          label="Status"
          value={state.status}
          onChange={(status) => setState({ status })}
          options={WORK_STATUSES.map((s) => ({
            value: s,
            label: valueLabel(s),
          }))}
        />
      </FilterBar>
      <DataTable
        caption="Sync jobs"
        columns={columns}
        rows={list.data?.items}
        loading={list.isPending}
        error={list.error}
        onRetry={() => void list.refetch()}
        getRowId={(j) => j.id}
        empty={
          <EmptyState
            icon={RefreshCw}
            title={active ? "No jobs match these filters" : "No sync jobs yet"}
            description={
              active
                ? "Clear the filters to see all jobs."
                : "Jobs appear when a connection that supports sync runs, e.g. from its connection page."
            }
          />
        }
      />
      {list.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={list.data.total}
          onPage={(p) => setState({ page: String(p) })}
        />
      )}
      <ConfirmDialog
        open={cancelling !== null}
        onOpenChange={(open) => !open && setCancelling(null)}
        title={`Cancel the ${cancelling?.entity ?? ""} sync?`}
        consequences={[
          "Records already written stay; the rest are not synced.",
          "A cancelled job can't be resumed. Start a new sync instead.",
        ]}
        confirmLabel="Cancel job"
        destructive
        loading={act.isPending}
        onConfirm={() =>
          cancelling && act.mutate({ job: cancelling, action: "cancel" })
        }
      />
    </IntegrationsFrame>
  );
}
