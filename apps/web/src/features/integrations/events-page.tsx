"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Inbox, RotateCcw, ShieldAlert, ShieldCheck } from "lucide-react";
import { Tooltip } from "@/components/ui/overlays";
import { RequirePermission } from "@/components/app/page";
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
import { integrationsService } from "./service";
import {
  GatedButton,
  IntegrationsFrame,
  StateBadge,
  When,
  useConnectionIndex,
} from "./components";
import { RETRYABLE_EVENT } from "./lib";
import { EVENT_STATUSES, type InboundEvent } from "./types";

const PAGE_SIZE = 25;

export function EventsPage() {
  return (
    <RequirePermission permission="integrations.read" area="integrations">
      <Events />
    </RequirePermission>
  );
}

export function replayBlockedReason(e: InboundEvent) {
  if (!e.signature_verified)
    return "Signature wasn't verified; replaying an untrusted payload isn't allowed";
  if (!RETRYABLE_EVENT.includes(e.status) && e.status !== "processed")
    return "Still in progress";
  return null;
}

function Events() {
  const [state, setState, reset] = useUrlState({
    connection: "",
    status: "",
    type: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    connection_id: state.connection || undefined,
    status: state.status || undefined,
    event_type: state.type || undefined,
    page,
    pageSize: PAGE_SIZE,
  };
  const list = useScopedQuery(
    ["integrations", "events", params],
    () => integrationsService.events(params),
    {
      placeholderData: (previous) => previous,
    },
  );
  const index = useConnectionIndex();
  const names = useMemo(
    () => new Map((index.data?.items ?? []).map((c) => [c.id, c.display_name])),
    [index.data],
  );
  const [confirm, setConfirm] = useState<InboundEvent | null>(null);
  const replay = useScopedMutation(
    (id: string) => integrationsService.replayEvent(id),
    {
      invalidate: [["integrations"]],
      success: (e) => `Replayed: now ${e.status.replace("_", " ")}`,
      onSuccess: () => setConfirm(null),
    },
  );
  const typeOptions = useMemo(() => {
    const set = new Set((list.data?.items ?? []).map((e) => e.event_type));
    if (state.type) set.add(state.type);
    return [...set].sort().map((t) => ({ value: t, label: t }));
  }, [list.data, state.type]);

  const columns: Column<InboundEvent>[] = [
    {
      key: "event",
      header: "Event",
      cell: (e) => (
        <div className="min-w-0">
          <p className="truncate font-mono text-xs font-medium">
            {e.event_type}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            <span className="md:hidden">
              {names.get(e.connection_id) ?? e.integration_key} ·{" "}
            </span>
            <When value={e.received_at} />
          </p>
        </div>
      ),
    },
    {
      key: "connection",
      header: "Connection",
      hideBelow: "md",
      cell: (e) => (
        <Link
          href={`/settings/integrations/connections/${e.connection_id}`}
          className="block max-w-48 truncate hover:underline"
        >
          {names.get(e.connection_id) ?? e.integration_key}
        </Link>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (e) => <StateBadge value={e.status} />,
    },
    {
      key: "signature",
      header: "Signature",
      hideBelow: "sm",
      cell: (e) =>
        e.signature_verified ? (
          <span className="inline-flex items-center gap-1 text-xs text-success">
            <ShieldCheck className="size-3.5" aria-hidden="true" /> Verified
          </span>
        ) : (
          <Tooltip content="The provider signature didn't match. The payload was not processed.">
            <span
              tabIndex={0}
              className="inline-flex items-center gap-1 text-xs font-medium text-danger"
            >
              <ShieldAlert className="size-3.5" aria-hidden="true" /> Unverified
            </span>
          </Tooltip>
        ),
    },
    {
      key: "attempts",
      header: "Attempts",
      hideBelow: "lg",
      align: "right",
      cell: (e) => <span className="tabular">{e.attempt_count}</span>,
    },
    {
      key: "error",
      header: "Error",
      hideBelow: "lg",
      cell: (e) =>
        e.error_code ? (
          <code className="text-xs text-danger">{e.error_code}</code>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "provider",
      header: "Provider ID",
      hideBelow: "xl",
      cell: (e) => (
        <span className="block max-w-40 truncate font-mono text-xs text-muted-foreground">
          {e.provider_event_id ?? "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (e) =>
        RETRYABLE_EVENT.includes(e.status) ? (
          <GatedButton
            size="xs"
            variant="secondary"
            permission="integrations.operate"
            blockedReason={replayBlockedReason(e)}
            onClick={() => setConfirm(e)}
            aria-label={`Replay ${e.event_type}`}
          >
            <RotateCcw /> <span className="hidden sm:inline">Replay</span>
          </GatedButton>
        ) : null,
    },
  ];
  const active = [state.connection, state.status, state.type].filter(
    Boolean,
  ).length;

  return (
    <IntegrationsFrame
      title="Inbound events"
      description="Webhook events received from providers, with signature checks and processing status."
    >
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
          options={EVENT_STATUSES.map((s) => ({
            value: s,
            label: s.replace("_", " ").replace(/^\w/, (x) => x.toUpperCase()),
          }))}
        />
        <FilterSelect
          label="Event type"
          value={state.type}
          onChange={(type) => setState({ type })}
          options={typeOptions}
        />
      </FilterBar>
      <DataTable
        caption="Inbound events"
        columns={columns}
        rows={list.data?.items}
        loading={list.isPending}
        error={list.error}
        onRetry={() => void list.refetch()}
        getRowId={(e) => e.id}
        empty={
          <EmptyState
            icon={Inbox}
            title={
              active ? "No events match these filters" : "No inbound events yet"
            }
            description={
              active
                ? "Clear the filters to see all events."
                : "Events appear here when a connected provider sends a webhook to this environment."
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
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={`Replay ${confirm?.event_type ?? "event"}?`}
        description="The stored payload is processed again. Replays are idempotent, so records already created aren't duplicated."
        consequences={[
          "Handlers run again for this event and may send follow-up messages if they didn't before.",
        ]}
        confirmLabel="Replay event"
        loading={replay.isPending}
        onConfirm={() => confirm && replay.mutate(confirm.id)}
      />
    </IntegrationsFrame>
  );
}
