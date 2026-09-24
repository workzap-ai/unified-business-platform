"use client";

import { useState } from "react";
import { Inbox, RotateCcw, ShieldCheck } from "lucide-react";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
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
import { FilterBar, FilterSelect } from "@/components/app/filters";
import { ConfirmDialog } from "@/components/app/forms";
import { EmptyState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { piService } from "../../service";
import type { WebhookEvent } from "../../types";
import { humanizeError, piKeys } from "../shared";
import { WhatsAppNav } from "./whatsapp-nav";

export function WhatsAppEventsPage() {
  return (
    <RequirePermission permission="pi.whatsapp.manage" area="WhatsApp settings">
      <Events />
    </RequirePermission>
  );
}

function Events() {
  const [state, set, reset] = useUrlState({ status: "", kind: "", page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const events = useScopedQuery(
    [...piKeys.events, state.status, state.kind, page],
    () =>
      piService.events({
        status: state.status || undefined,
        kind: state.kind || undefined,
        page,
      }),
  );
  const [target, setTarget] = useState<WebhookEvent | null>(null);
  const replay = useScopedMutation((id: string) => piService.replayEvent(id), {
    invalidate: [[...piKeys.events], [...piKeys.connection]],
    success: "Event reprocessed",
    onSuccess: () => setTarget(null),
  });

  const columns: Column<WebhookEvent>[] = [
    {
      key: "time",
      header: "Time",
      cell: (e) => (
        <time
          dateTime={e.created_at}
          title={formatDateTime(e.created_at)}
          className="whitespace-nowrap"
        >
          {relativeTime(e.created_at)}
        </time>
      ),
    },
    {
      key: "key",
      header: "Event key",
      cell: (e) => (
        <span
          className="block max-w-40 truncate font-mono text-xs text-muted-foreground"
          title={e.event_key}
        >
          {e.event_key}
        </span>
      ),
      hideBelow: "lg",
    },
    {
      key: "kind",
      header: "Kind",
      cell: (e) => <Badge tone="outline">{e.kind}</Badge>,
      hideBelow: "sm",
    },
    {
      key: "summary",
      header: "Summary",
      cell: (e) => (
        <div className="min-w-0">
          <p className="line-clamp-2">{e.summary}</p>
          {e.duplicate_count > 0 && (
            <Badge tone="neutral" className="mt-1">
              Deduplicated ×{e.duplicate_count}
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (e) => <StatusBadge status={e.status} />,
    },
    {
      key: "attempts",
      header: "Attempts",
      align: "right",
      cell: (e) => <span className="tabular">{e.attempts}</span>,
      hideBelow: "md",
    },
    {
      key: "error",
      header: "Error",
      cell: (e) =>
        e.error_code ? (
          <span className="text-xs text-danger" title={e.error_code}>
            {humanizeError(e.error_code)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
      hideBelow: "xl",
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (e) =>
        e.status === "failed" ? (
          <Button size="xs" variant="secondary" onClick={() => setTarget(e)}>
            <RotateCcw /> Replay
          </Button>
        ) : null,
    },
  ];

  const active = [state.status, state.kind].filter(Boolean).length;

  return (
    <PageShell>
      <PageHeader
        title="WhatsApp"
        description="Every webhook call from WhatsApp, as received and processed by PI."
      />
      <WhatsAppNav />
      <Notice tone="neutral" icon={ShieldCheck} className="mb-4">
        Every request is verified against Meta&apos;s signature before it&apos;s
        accepted. WhatsApp may deliver the same event more than once; PI keeps a
        single copy per event key, so a duplicate never produces a second reply
        or order.
      </Notice>
      <FilterBar activeCount={active} onClear={reset}>
        <FilterSelect
          label="Status"
          value={state.status}
          onChange={(status) => set({ status })}
          options={["received", "queued", "processed", "ignored", "failed"].map(
            (s) => ({ value: s, label: s[0]!.toUpperCase() + s.slice(1) }),
          )}
        />
        <FilterSelect
          label="Kind"
          value={state.kind}
          onChange={(kind) => set({ kind })}
          options={[
            { value: "message", label: "Message" },
            { value: "status", label: "Status update" },
            { value: "unknown", label: "Unknown" },
          ]}
        />
      </FilterBar>
      <DataTable
        columns={columns}
        rows={events.data?.items}
        error={events.error}
        onRetry={() => void events.refetch()}
        getRowId={(e) => e.id}
        loading={events.isPending}
        caption="Webhook events"
        rowClassName={(e) =>
          e.status === "failed" ? "bg-danger-soft/30" : undefined
        }
        empty={
          <EmptyState
            tone="pi"
            icon={Inbox}
            compact
            title={
              active ? "No events match these filters" : "No webhook events yet"
            }
            description={
              active
                ? "Try clearing a filter."
                : "Events appear here once WhatsApp starts delivering messages to PI."
            }
          />
        }
      />
      {events.data && (
        <Pagination
          page={events.data.page}
          pageSize={events.data.page_size}
          total={events.data.total}
          onPage={(p) => set({ page: String(p) }, { resetPage: false })}
        />
      )}
      <ConfirmDialog
        open={Boolean(target)}
        onOpenChange={(open) => !open && setTarget(null)}
        title="Replay this event?"
        description="PI processes the stored event again."
        consequences={[
          "Reprocessing is idempotent — duplicates never create duplicate replies or orders.",
          "If the original message was already answered, nothing is sent again.",
        ]}
        confirmLabel="Replay event"
        loading={replay.isPending}
        onConfirm={() => target && replay.mutate(target.id)}
      />
    </PageShell>
  );
}
