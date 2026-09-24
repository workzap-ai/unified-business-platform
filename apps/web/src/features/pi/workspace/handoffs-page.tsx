"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  CheckCircle2,
  CircleX,
  Inbox,
  MessageSquare,
  MoreHorizontal,
  PauseCircle,
  RotateCcw,
  SearchX,
  UserCheck,
  UserRound,
  UserRoundCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Avatar, Badge } from "@/components/ui/display";
import { Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { PageHeader, PageShell } from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { FilterBar, SearchInput } from "@/components/app/filters";
import { ConfirmDialog, FormField } from "@/components/app/forms";
import { EmptyState, Notice } from "@/components/app/states";
import { StatusBadge, statusLabel } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { HANDOFF_FLOW, piService } from "../service";
import type { Handoff, HandoffStatus } from "../types";
import { HANDOFF_REASON_LABELS, inboxHref, piKeys, slugForStatus } from "./lib";
import { PriorityBadge } from "./parts";

type Action = "assign" | "start" | "resolve" | "close" | "reopen";

const TABS: { status?: HandoffStatus; label: string }[] = [
  { label: "All" },
  { status: "open", label: "Open" },
  { status: "assigned", label: "Assigned" },
  { status: "in_progress", label: "In progress" },
  { status: "resolved", label: "Resolved" },
  { status: "closed", label: "Closed" },
];

const ACTION_META: Record<Action, { label: string; icon: typeof UserCheck }> = {
  assign: { label: "Assign to me", icon: UserRoundCheck },
  start: { label: "Start (take over)", icon: UserRound },
  resolve: { label: "Resolve…", icon: CheckCircle2 },
  close: { label: "Close", icon: CircleX },
  reopen: { label: "Reopen", icon: RotateCcw },
};

const EMPTY_COPY: Record<string, { title: string; description: string }> = {
  all: {
    title: "No handoffs yet",
    description:
      "When PI needs a person, for a complaint, an approval or low confidence, the conversation appears here.",
  },
  open: {
    title: "Nothing waiting",
    description:
      "No open handoffs. PI is handling every conversation on its own right now.",
  },
  assigned: {
    title: "No assigned handoffs",
    description:
      "Handoffs assigned to a team member but not started appear here.",
  },
  in_progress: {
    title: "No handoffs in progress",
    description:
      "When someone takes over a conversation, it shows here until it's resolved.",
  },
  resolved: {
    title: "No resolved handoffs",
    description: "Resolved handoffs stay here until they're closed.",
  },
  closed: {
    title: "No closed handoffs",
    description: "Closed handoffs are kept here for reference.",
  },
};

export function HandoffsPage({ status }: { status?: HandoffStatus }) {
  const { canAny } = useSession();
  const canManage = canAny("pi.handoffs.manage", "pi.inbox.reply");
  const [url, setUrl] = useUrlState({ search: "" });
  const query = useScopedQuery<Handoff[]>(
    piKeys.handoffs(),
    () => piService.handoffs(),
    { refetchInterval: 30_000 },
  );
  const [pending, setPending] = useState<{
    handoff: Handoff;
    action: "start" | "close" | "resolve";
  } | null>(null);

  const update = useScopedMutation(
    ({ id, action, note }: { id: string; action: Action; note?: string }) =>
      piService.updateHandoff(
        id,
        action,
        note !== undefined ? { note } : undefined,
      ),
    {
      invalidate: [[...piKeys.all], ["navigation"]],
      success: (h) =>
        `Handoff for ${h.customer_name} is now ${statusLabel(h.status).toLowerCase()}`,
      error: "Couldn't update the handoff.",
      onSuccess: () => setPending(null),
    },
  );

  const all = query.data;
  const counts = new Map<string, number>();
  for (const h of all ?? [])
    counts.set(h.status, (counts.get(h.status) ?? 0) + 1);
  const term = url.search.trim().toLowerCase();
  const rows = all
    ?.filter((h) => !status || h.status === status)
    .filter(
      (h) =>
        !term ||
        h.customer_name.toLowerCase().includes(term) ||
        h.summary.toLowerCase().includes(term),
    );

  function trigger(handoff: Handoff, action: Action) {
    if (action === "start" || action === "close" || action === "resolve")
      setPending({ handoff, action });
    else update.mutate({ id: handoff.id, action });
  }

  const columns: Column<Handoff>[] = [
    {
      key: "customer",
      header: "Customer",
      cell: (h) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar name={h.customer_name} size="sm" />
          <div className="min-w-0">
            <p className="truncate font-medium">{h.customer_name}</p>
            <p className="truncate text-xs text-muted-foreground md:hidden">
              {HANDOFF_REASON_LABELS[h.reason]}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "reason",
      header: "Reason",
      hideBelow: "md",
      cell: (h) => (
        <span className="whitespace-nowrap">
          {HANDOFF_REASON_LABELS[h.reason]}
        </span>
      ),
    },
    {
      key: "priority",
      header: "Priority",
      hideBelow: "sm",
      cell: (h) => <PriorityBadge priority={h.priority} showNormal />,
    },
    {
      key: "summary",
      header: "Summary",
      hideBelow: "lg",
      cell: (h) => (
        <p
          className="max-w-80 truncate text-muted-foreground"
          title={h.summary}
        >
          {h.summary || "—"}
        </p>
      ),
    },
    {
      key: "assignee",
      header: "Assignee",
      hideBelow: "md",
      cell: (h) =>
        h.assigned_label ? (
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <Avatar name={h.assigned_label} size="xs" /> {h.assigned_label}
          </span>
        ) : (
          <span className="text-muted-foreground">Unassigned</span>
        ),
    },
    {
      key: "age",
      header: "Age",
      hideBelow: "sm",
      cell: (h) => (
        <time
          dateTime={h.created_at}
          title={formatDateTime(h.created_at)}
          className="tabular whitespace-nowrap text-muted-foreground"
        >
          {relativeTime(h.created_at)}
        </time>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (h) => (
        <div className="flex flex-wrap items-center gap-1">
          <StatusBadge status={h.status} />
          {h.status === "in_progress" && (
            <Badge
              tone="info"
              title="A team member is replying; PI's automatic replies are paused"
            >
              <UserRound /> Human
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      cell: (h) => (
        <div className="flex items-center justify-end gap-1" data-no-row-click>
          <Button variant="ghost" size="icon-xs" asChild>
            <Link
              href={inboxHref(h.conversation_id)}
              aria-label={`Open conversation with ${h.customer_name}`}
            >
              <MessageSquare />
            </Link>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Actions for handoff with ${h.customer_name}`}
              >
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-52">
              <DropdownMenuItem asChild>
                <Link href={inboxHref(h.conversation_id)}>
                  <Inbox /> Open conversation
                </Link>
              </DropdownMenuItem>
              {canManage && HANDOFF_FLOW[h.status].length > 0 && (
                <DropdownMenuSeparator />
              )}
              {canManage &&
                HANDOFF_FLOW[h.status].map((action) => {
                  const meta = ACTION_META[action];
                  return (
                    <DropdownMenuItem
                      key={action}
                      onSelect={() => trigger(h, action)}
                      destructive={action === "close"}
                    >
                      <meta.icon /> {meta.label}
                    </DropdownMenuItem>
                  );
                })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  const empty = EMPTY_COPY[status ?? "all"]!;

  return (
    <PageShell>
      <PageHeader
        title="Handoffs"
        description="Conversations PI passed to your team. While a handoff is in progress, PI stops automatic replies in that conversation."
      />

      {!canManage && (
        <Notice tone="neutral" className="mb-4" icon={PauseCircle}>
          You can view handoffs. Assigning, starting or resolving them requires
          handoff or inbox reply permission.
        </Notice>
      )}

      <nav
        aria-label="Handoff status"
        className="scrollbar-thin mb-3 flex items-center gap-1 overflow-x-auto"
      >
        {TABS.map((tab) => {
          const active = tab.status === status;
          const count = tab.status
            ? (counts.get(tab.status) ?? 0)
            : (all?.length ?? 0);
          return (
            <Link
              key={tab.label}
              href={
                tab.status
                  ? `/pi/handoffs/${slugForStatus(tab.status)}`
                  : "/pi/handoffs"
              }
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors",
                active
                  ? "bg-foreground text-background"
                  : "text-foreground-secondary hover:bg-surface-muted",
              )}
            >
              {tab.label}
              {all && (
                <span
                  className={cn(
                    "tabular text-xs",
                    active ? "text-background/70" : "text-muted-foreground",
                  )}
                >
                  {count}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <FilterBar>
        <SearchInput
          value={url.search}
          onChange={(search) => setUrl({ search })}
          placeholder="Search customer or summary"
          className="w-full md:w-72"
        />
      </FilterBar>

      <DataTable
        caption="Handoff queue"
        columns={columns}
        rows={rows}
        getRowId={(h) => h.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(h) => inboxHref(h.conversation_id)}
        rowClassName={(h) =>
          h.priority === "urgent" && ["open", "assigned"].includes(h.status)
            ? "bg-danger-soft/40"
            : undefined
        }
        empty={
          term ? (
            <EmptyState
              compact
              icon={SearchX}
              title="No handoffs match"
              description="Try a different customer name or clear the search."
              action={
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setUrl({ search: "" })}
                >
                  Clear search
                </Button>
              }
            />
          ) : (
            <EmptyState
              compact
              tone="pi"
              icon={UserCheck}
              title={empty.title}
              description={empty.description}
            />
          )
        }
      />

      {pending && pending.action === "resolve" && (
        <ResolveDialog
          handoff={pending.handoff}
          loading={update.isPending}
          onCancel={() => setPending(null)}
          onResolve={(note) =>
            update.mutate({ id: pending.handoff.id, action: "resolve", note })
          }
        />
      )}
      <ConfirmDialog
        open={pending?.action === "start"}
        onOpenChange={(o) => !o && setPending(null)}
        title="Start this handoff?"
        description={
          pending
            ? `You'll take over the conversation with ${pending.handoff.customer_name}.`
            : undefined
        }
        consequences={[
          "PI stops sending automatic replies in this conversation.",
          "The handoff moves to In progress and is assigned to you if unassigned.",
          "Return the conversation to PI from the inbox when you're done.",
        ]}
        confirmLabel="Start and take over"
        loading={update.isPending}
        onConfirm={() =>
          pending && update.mutate({ id: pending.handoff.id, action: "start" })
        }
      />
      <ConfirmDialog
        open={pending?.action === "close"}
        onOpenChange={(o) => !o && setPending(null)}
        title="Close this handoff?"
        description={
          pending
            ? `The handoff for ${pending.handoff.customer_name} leaves the active queue.`
            : undefined
        }
        consequences={[
          "It no longer counts as an open handoff.",
          "You can reopen it later if the customer still needs help.",
        ]}
        confirmLabel="Close handoff"
        destructive
        loading={update.isPending}
        onConfirm={() =>
          pending && update.mutate({ id: pending.handoff.id, action: "close" })
        }
      />
    </PageShell>
  );
}

const resolveSchema = z.object({
  note: z
    .string()
    .trim()
    .min(3, "Add a short resolution note.")
    .max(1000, "Keep the note under 1,000 characters."),
});

function ResolveDialog({
  handoff,
  loading,
  onCancel,
  onResolve,
}: {
  handoff: Handoff;
  loading: boolean;
  onCancel: () => void;
  onResolve: (note: string) => void;
}) {
  const form = useForm<z.infer<typeof resolveSchema>>({
    resolver: zodResolver(resolveSchema),
    defaultValues: { note: "" },
  });
  const error = form.formState.errors.note;
  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent size="md">
        <form
          onSubmit={form.handleSubmit((v) => onResolve(v.note))}
          noValidate
          className="flex min-h-0 flex-col"
        >
          <DialogHeader
            title="Resolve handoff"
            description={`Record how the request from ${handoff.customer_name} was settled.`}
          />
          <DialogBody className="space-y-3">
            {handoff.summary && (
              <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px] text-foreground-secondary">
                {handoff.summary}
              </p>
            )}
            <FormField
              label="Resolution note"
              htmlFor="resolution-note"
              required
              error={error}
              help="Visible to your team on the handoff record."
            >
              <Textarea
                id="resolution-note"
                rows={4}
                maxLength={1000}
                placeholder="e.g. Sent a replacement mug; customer confirmed."
                aria-invalid={Boolean(error)}
                aria-describedby={
                  error ? "resolution-note-error" : "resolution-note-help"
                }
                {...form.register("note")}
              />
            </FormField>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onCancel}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" loading={loading}>
              <CheckCircle2 /> Resolve
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
