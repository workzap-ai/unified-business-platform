"use client";

import { useState } from "react";
import { Lock, ScrollText } from "lucide-react";
import { formatDateTime, humanize, relativeTime } from "@/lib/format";
import { Badge } from "@/components/ui/display";
import { Dialog, DialogHeader, SheetContent } from "@/components/ui/overlays";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { FilterBar, FilterSelect, SearchInput } from "@/components/app/filters";
import { PropertyList } from "@/components/app/record";
import { EmptyState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { adminService, type AuditEvent } from "./service";
import { flattenDetails } from "./lib";

const PAGE_SIZE = 50;

function ActorCell({ e }: { e: AuditEvent }) {
  const system = e.actor_type === "system";
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="truncate font-medium">{e.actor_label}</span>
      {system && (
        <Badge tone={e.actor_label === "PI" ? "pi" : "neutral"}>
          {e.actor_label === "PI" ? "PI" : "System"}
        </Badge>
      )}
      {e.actor_type === "anonymous" && <Badge tone="outline">Anonymous</Badge>}
    </span>
  );
}

export function AuditPage() {
  return (
    <RequirePermission permission="audit.read" area="the audit log">
      <AuditContent />
    </RequirePermission>
  );
}

function AuditContent() {
  const [state, setState, reset] = useUrlState({
    action: "",
    outcome: "",
    entity: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const query = useScopedQuery(["admin", "audit", state], () =>
    adminService.audit({
      page,
      pageSize: PAGE_SIZE,
      action: state.action || undefined,
      entityType: state.entity || undefined,
      outcome: state.outcome || undefined,
    }),
  );
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [seenEntities, setSeenEntities] = useState<string[]>([]);
  const rows = query.data?.items;

  // Entity types come from loaded rows; remember them so the filter keeps its options
  // after it narrows the list (state derived from previous renders).
  const fresh = [
    ...(rows ?? []).map((r) => r.entity_type),
    state.entity,
  ].filter(
    (t): t is string => Boolean(t) && !seenEntities.includes(t as string),
  );
  if (fresh.length) setSeenEntities([...new Set([...seenEntities, ...fresh])]);
  const entityOptions = [...new Set([...seenEntities, ...fresh])]
    .sort()
    .map((t) => ({ value: t, label: humanize(t) }));

  const active = [state.action, state.outcome, state.entity].filter(
    Boolean,
  ).length;

  const columns: Column<AuditEvent>[] = [
    {
      key: "time",
      header: "Time",
      cell: (e) => (
        <time
          dateTime={e.created_at}
          title={formatDateTime(e.created_at)}
          className="whitespace-nowrap text-muted-foreground"
        >
          {relativeTime(e.created_at)}
        </time>
      ),
    },
    { key: "actor", header: "Actor", cell: (e) => <ActorCell e={e} /> },
    {
      key: "action",
      header: "Action",
      cell: (e) => <span className="font-mono text-xs">{e.action}</span>,
    },
    {
      key: "entity",
      header: "Entity",
      hideBelow: "md",
      cell: (e) =>
        e.entity_type ? (
          <span className="block max-w-56 truncate">
            {humanize(e.entity_type)}
            {e.entity_id && (
              <span className="ml-1 font-mono text-xs text-muted-foreground">
                {e.entity_id}
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "outcome",
      header: "Outcome",
      cell: (e) => <StatusBadge status={e.outcome} />,
    },
    {
      key: "request",
      header: "Request ID",
      hideBelow: "lg",
      cell: (e) =>
        e.request_id ? (
          <span
            className="block max-w-28 truncate font-mono text-xs text-muted-foreground"
            title={e.request_id}
          >
            {e.request_id}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Audit log"
        description="Who did what, when, in this environment. Entries can't be edited or deleted."
      />
      <FilterBar activeCount={active} onClear={reset}>
        <SearchInput
          value={state.action}
          onChange={(v) => setState({ action: v.trim() })}
          placeholder="Action starts with, e.g. order."
          className="w-full shrink-0 md:w-72"
        />
        <FilterSelect
          label="Outcome"
          value={state.outcome}
          onChange={(v) => setState({ outcome: v })}
          options={[
            { value: "success", label: "Success" },
            { value: "denied", label: "Denied" },
            { value: "failure", label: "Failure" },
          ]}
        />
        <FilterSelect
          label="Entity"
          value={state.entity}
          onChange={(v) => setState({ entity: v })}
          options={entityOptions}
        />
      </FilterBar>
      <DataTable
        caption="Audit events"
        columns={columns}
        rows={rows}
        getRowId={(e) => e.id}
        onRowClick={setSelected}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        empty={
          <EmptyState
            compact
            icon={ScrollText}
            title={
              active ? "No events match these filters" : "No audit events yet"
            }
            description={
              active
                ? "Try a broader action prefix or clear filters."
                : "Sign-ins, changes and PI actions are recorded here as they happen."
            }
          />
        }
      />
      {query.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data.total}
          onPage={(p) => setState({ page: String(p) })}
        />
      )}

      <Dialog
        open={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
      >
        {selected && <AuditDetail e={selected} />}
      </Dialog>
    </PageShell>
  );
}

function AuditDetail({ e }: { e: AuditEvent }) {
  const details = flattenDetails(e.details);
  return (
    <SheetContent width="md">
      <DialogHeader
        title={<span className="font-mono text-[14px]">{e.action}</span>}
        description={`${formatDateTime(e.created_at)} · ${relativeTime(e.created_at)}`}
      />
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
        <PropertyList
          items={[
            { label: "Outcome", value: <StatusBadge status={e.outcome} /> },
            { label: "Actor", value: <ActorCell e={e} /> },
            { label: "Actor type", value: humanize(e.actor_type) },
            {
              label: "Entity type",
              value: e.entity_type ? humanize(e.entity_type) : null,
            },
            {
              label: "Entity ID",
              value: e.entity_id ? (
                <span className="font-mono text-xs">{e.entity_id}</span>
              ) : null,
            },
            {
              label: "Request ID",
              value: e.request_id ? (
                <span className="font-mono text-xs break-all">
                  {e.request_id}
                </span>
              ) : null,
            },
            {
              label: "Environment",
              value: e.environment_id ? (
                <span className="font-mono text-xs">{e.environment_id}</span>
              ) : (
                "Workspace-wide"
              ),
            },
            {
              label: "Event ID",
              value: <span className="font-mono text-xs">{e.id}</span>,
            },
          ]}
        />
        <section>
          <h3 className="mb-1 text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
            Details
          </h3>
          {details.length ? (
            <PropertyList
              items={details.map((d) => ({
                label: humanize(d.key),
                value: <span className="break-words">{d.value}</span>,
              }))}
            />
          ) : (
            <p className="text-[13px] text-muted-foreground">
              No additional details were recorded.
            </p>
          )}
        </section>
        <Notice tone="neutral" icon={Lock}>
          Secrets such as passwords, access tokens and API keys are never
          recorded in the audit log.
        </Notice>
      </div>
    </SheetContent>
  );
}
