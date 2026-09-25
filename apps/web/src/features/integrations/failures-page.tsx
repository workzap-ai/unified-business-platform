"use client";

import { useMemo } from "react";
import Link from "next/link";
import { CircleCheck, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/display";
import { RequirePermission } from "@/components/app/page";
import { FilterBar, FilterSelect } from "@/components/app/filters";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { EmptyState, Notice } from "@/components/app/states";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { integrationsService } from "./service";
import {
  GatedButton,
  IntegrationsFrame,
  StateBadge,
  When,
  useConnectionIndex,
} from "./components";
import type { Failure } from "./types";

const PAGE_SIZE = 100;
const KIND_LABELS: Record<Failure["kind"], string> = {
  delivery: "Webhook delivery",
  event: "Inbound event",
  job: "Sync job",
};

export function FailuresPage() {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Failures />
    </RequirePermission>
  );
}

function retryFailure(f: Failure): Promise<{ status: string }> {
  if (f.kind === "delivery") return integrationsService.retryDelivery(f.id);
  if (f.kind === "event") return integrationsService.replayEvent(f.id);
  return integrationsService.jobAction(f.id, "retry");
}

function sourceHref(f: Failure) {
  if (f.kind === "delivery") return "/settings/integrations/webhooks";
  if (f.kind === "event")
    return `/settings/integrations/events${f.connection_id ? `?connection=${f.connection_id}` : ""}`;
  return `/settings/integrations/jobs${f.connection_id ? `?connection=${f.connection_id}` : ""}`;
}

function Failures() {
  const [state, setState, reset] = useUrlState({ kind: "", page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const list = useScopedQuery(["integrations", "failures", { page }], () =>
    integrationsService.failures({ page, pageSize: PAGE_SIZE }),
  );
  const index = useConnectionIndex();
  const names = useMemo(
    () => new Map((index.data?.items ?? []).map((c) => [c.id, c.display_name])),
    [index.data],
  );
  const retry = useScopedMutation((f: Failure) => retryFailure(f), {
    invalidate: [["integrations"]],
    success: (r) =>
      ["succeeded", "processed"].includes(r.status)
        ? "Retried successfully"
        : `Retry queued: ${String(r.status).replace("_", " ")}`,
  });
  // The contract has no kind filter; filter the loaded page client-side.
  const rows = list.data?.items.filter(
    (f) => !state.kind || f.kind === state.kind,
  );

  const columns: Column<Failure>[] = [
    {
      key: "summary",
      header: "Failure",
      cell: (f) => (
        <div className="min-w-0">
          <p className="line-clamp-2 text-[13px] font-medium break-words">
            {f.summary}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span className="sm:hidden">{KIND_LABELS[f.kind]} ·</span>
            <When value={f.occurred_at} />
            {f.connection_id && (
              <Link
                href={`/settings/integrations/connections/${f.connection_id}`}
                className="hover:underline"
              >
                {names.get(f.connection_id) ?? f.integration_key}
              </Link>
            )}
          </p>
        </div>
      ),
    },
    {
      key: "kind",
      header: "Kind",
      hideBelow: "sm",
      cell: (f) => <Badge tone="outline">{KIND_LABELS[f.kind]}</Badge>,
    },
    {
      key: "status",
      header: "Status",
      hideBelow: "md",
      cell: (f) => <StateBadge value={f.status} />,
    },
    {
      key: "code",
      header: "Error code",
      hideBelow: "lg",
      cell: (f) =>
        f.error_code ? (
          <code className="text-xs text-danger">{f.error_code}</code>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "attempts",
      header: "Attempts",
      hideBelow: "lg",
      align: "right",
      cell: (f) => <span className="tabular">{f.attempt_count}</span>,
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (f) => (
        <div className="flex items-center justify-end gap-1.5">
          <Link
            href={sourceHref(f)}
            className="hidden text-xs font-medium text-primary hover:underline xl:inline"
          >
            View source
          </Link>
          <GatedButton
            size="xs"
            variant="secondary"
            permission="integrations.operate"
            blockedReason={
              f.can_retry
                ? null
                : f.kind === "event"
                  ? "Unverified or non-retryable event"
                  : f.kind === "delivery"
                    ? "The subscription is disabled or deleted"
                    : "This job can't be retried"
            }
            loading={retry.isPending && retry.variables?.id === f.id}
            onClick={() => retry.mutate(f)}
            aria-label={`Retry ${KIND_LABELS[f.kind].toLowerCase()}`}
          >
            <RotateCcw /> <span className="hidden sm:inline">Retry</span>
          </GatedButton>
        </div>
      ),
    },
  ];

  return (
    <IntegrationsFrame
      title="Failures"
      description="Dead-letter view: inbound events, webhook deliveries and sync jobs that failed. Retry once the cause is fixed."
    >
      <FilterBar activeCount={state.kind ? 1 : 0} onClear={reset}>
        <FilterSelect
          label="Kind"
          value={state.kind}
          onChange={(kind) => setState({ kind })}
          options={(Object.keys(KIND_LABELS) as Failure["kind"][]).map((k) => ({
            value: k,
            label: KIND_LABELS[k],
            count: list.data?.items.filter((f) => f.kind === k).length,
          }))}
        />
      </FilterBar>
      {list.data && list.data.total > list.data.items.length && state.kind && (
        <Notice tone="neutral" className="mb-3">
          The kind filter applies to the {list.data.items.length} failures on
          this page.
        </Notice>
      )}
      <DataTable
        caption="Integration failures"
        columns={columns}
        rows={rows}
        loading={list.isPending}
        error={list.error}
        onRetry={() => void list.refetch()}
        getRowId={(f) => `${f.kind}-${f.id}`}
        empty={
          <EmptyState
            icon={CircleCheck}
            title={state.kind ? "No failures of this kind" : "No failures"}
            description="Everything that failed has been retried or resolved."
          />
        }
      />
      {list.data && list.data.total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={list.data.total}
          onPage={(p) => setState({ page: String(p) })}
        />
      )}
    </IntegrationsFrame>
  );
}
