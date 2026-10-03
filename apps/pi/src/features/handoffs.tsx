"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleX,
  Hand,
  MessageSquare,
  RotateCcw,
  UserRound,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardSection,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  LoadingBlock,
  Notice,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count, dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan, useSession } from "@/lib/session";

type Status = "open" | "assigned" | "in_progress" | "resolved" | "closed";
type Action = "assign" | "start" | "resolve" | "close" | "reopen";

interface Handoff {
  id: string;
  conversation_id: string;
  customer_id: string;
  customer_name: string;
  status: Status;
  reason: string;
  priority: string;
  summary: string;
  assigned_label: string | null;
  created_by_label: string;
  created_at: string;
  assigned_at: string | null;
  resolved_at: string | null;
  resolution_note: string;
}

interface TeamView {
  members: {
    membership_id: string;
    user_id: string;
    email: string;
    display_name: string;
    status: string;
    roles: string[];
  }[];
}

const FILTERS: { status: Status | ""; label: string }[] = [
  { status: "", label: "All" },
  { status: "open", label: "Open" },
  { status: "assigned", label: "Assigned" },
  { status: "in_progress", label: "In progress" },
  { status: "resolved", label: "Resolved" },
  { status: "closed", label: "Closed" },
];

const STATUS_META: Record<
  Status,
  {
    label: string;
    tone: "neutral" | "accent" | "success" | "warning" | "danger" | "info";
  }
> = {
  open: { label: "Open", tone: "warning" },
  assigned: { label: "Assigned", tone: "info" },
  in_progress: { label: "In progress", tone: "accent" },
  resolved: { label: "Resolved", tone: "success" },
  closed: { label: "Closed", tone: "neutral" },
};

const REASON_LABEL: Record<string, string> = {
  customer_request: "Customer asked for a person",
  low_confidence: "pi wasn't sure of the answer",
  provider_failure: "AI was unavailable",
  policy: "Needs your approval",
  tool_failure: "An action didn't work",
  complaint: "Complaint",
  sensitive: "Sensitive topic",
  manual: "Handed over by your team",
};

// Mirrors the server's handoff state machine (pi/service.py HANDOFF_STATES).
const NEXT: Record<Status, Action[]> = {
  open: ["assign", "start", "close"],
  assigned: ["assign", "start", "close"],
  in_progress: ["assign", "resolve"],
  resolved: ["close", "reopen"],
  closed: ["reopen"],
};

const ACTION_META: Record<
  Action,
  { label: string; icon: typeof UserRound; help: string }
> = {
  assign: {
    label: "Assign",
    icon: UserRoundCheck,
    help: "Give this conversation to someone on your team.",
  },
  start: {
    label: "Take over",
    icon: UserRound,
    help: "pi stops replying and you (or the person chosen) handle the chat.",
  },
  resolve: {
    label: "Resolve",
    icon: CheckCircle2,
    help: "Say what was done so the team has a record.",
  },
  close: {
    label: "Close",
    icon: CircleX,
    help: "Dismiss this handover. You can reopen it later.",
  },
  reopen: {
    label: "Reopen",
    icon: RotateCcw,
    help: "Put this handover back in the open queue.",
  },
};

function reasonLabel(reason: string) {
  return (
    REASON_LABEL[reason] ??
    reason.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  if (priority === "urgent") return <Badge tone="danger">Urgent</Badge>;
  if (priority === "high") return <Badge tone="warning">High priority</Badge>;
  return null;
}

function ActionDialog({
  handoff,
  onClose,
}: {
  handoff: Handoff;
  onClose: () => void;
}) {
  const can = useCan();
  const key = useBusinessKey();
  const session = useSession();
  const actions = NEXT[handoff.status] ?? [];
  const [action, setAction] = React.useState<Action>(actions[0] ?? "close");
  const [assignee, setAssignee] = React.useState("");
  const [note, setNote] = React.useState("");
  const team = useQuery({
    queryKey: key(["team"]),
    queryFn: () => get<TeamView>("/team"),
    enabled: can("admin.members.read"),
  });
  const members = (team.data?.members ?? []).filter(
    (m) => m.status === "active",
  );
  const me = session.data?.user.id;
  const run = useAction(
    (body: { action: Action; assignee?: string; note?: string }) =>
      post<Handoff>(`/pi/handoffs/${handoff.id}/actions`, body),
    {
      success: (h) =>
        `${h.customer_name}: ${STATUS_META[h.status]?.label.toLowerCase() ?? "updated"}`,
      invalidate: [["handoffs"]],
      onSuccess: onClose,
    },
  );
  const needsPerson = action === "assign" || action === "start";
  const noteRequired = action === "resolve";
  const invalid = noteRequired && !note.trim();

  return (
    <DialogContent
      title={`Handover: ${handoff.customer_name}`}
      description={reasonLabel(handoff.reason)}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (invalid) return;
          run.mutate({
            action,
            ...(needsPerson && assignee ? { assignee } : {}),
            ...(note.trim() ? { note: note.trim() } : {}),
          });
        }}
      >
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">
            What do you want to do?
          </legend>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {actions.map((a) => {
              const Icon = ACTION_META[a].icon;
              return (
                <button
                  key={a}
                  type="button"
                  aria-pressed={action === a}
                  onClick={() => setAction(a)}
                  className={cn(
                    "flex min-h-11 items-center gap-2 rounded-xl border px-3.5 text-start text-sm font-medium transition-colors",
                    action === a
                      ? "border-accent bg-accent-soft text-accent-soft-foreground"
                      : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                  )}
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  {ACTION_META[a].label}
                </button>
              );
            })}
          </div>
          <p className="text-[13px] text-muted-foreground">
            {ACTION_META[action].help}
          </p>
        </fieldset>

        {needsPerson ? (
          <Field
            label="Team member"
            htmlFor="handoff-assignee"
            hint={
              team.isError
                ? "Couldn't load your team, so this goes to you."
                : "Leave as 'Me' to take it yourself."
            }
          >
            <Select
              id="handoff-assignee"
              className="text-base sm:text-[15px]"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
            >
              <option value="">Me</option>
              {members
                .filter((m) => m.user_id !== me)
                .map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.display_name || m.email}
                  </option>
                ))}
            </Select>
          </Field>
        ) : null}

        {action !== "assign" ? (
          <Field
            label={noteRequired ? "What was done?" : "Note"}
            htmlFor="handoff-note"
            optional={!noteRequired}
            hint={
              noteRequired
                ? "Required. A short summary for your team."
                : undefined
            }
          >
            <Textarea
              id="handoff-note"
              className="text-base sm:text-[15px]"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={
                noteRequired ? "e.g. Refunded the order and apologised" : ""
              }
            />
          </Field>
        ) : null}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            loading={run.isPending}
            disabled={invalid}
            variant={action === "close" ? "danger" : "primary"}
          >
            {ACTION_META[action].label}
          </Button>
        </div>
      </form>
    </DialogContent>
  );
}

function HandoffCard({
  handoff,
  canManage,
  onAct,
}: {
  handoff: Handoff;
  canManage: boolean;
  onAct: () => void;
}) {
  const meta = STATUS_META[handoff.status] ?? {
    label: handoff.status,
    tone: "neutral" as const,
  };
  return (
    <li>
      <Card className="min-w-0">
        <CardSection className="space-y-3 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold">
                {handoff.customer_name}
              </h2>
              <p className="text-sm text-foreground-secondary">
                {reasonLabel(handoff.reason)}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <PriorityBadge priority={handoff.priority} />
              <Badge tone={meta.tone}>{meta.label}</Badge>
            </div>
          </div>
          {handoff.summary ? (
            <p className="line-clamp-3 break-words text-sm text-foreground">
              {handoff.summary}
            </p>
          ) : null}
          {handoff.resolution_note ? (
            <p className="break-words rounded-xl bg-success-soft px-3 py-2 text-sm text-foreground">
              <span className="font-medium">Resolution: </span>
              {handoff.resolution_note}
            </p>
          ) : null}
          <p className="text-[13px] text-muted-foreground">
            <time
              dateTime={handoff.created_at}
              title={dateTime(handoff.created_at)}
            >
              {timeAgo(handoff.created_at)}
            </time>
            {" · "}
            {handoff.assigned_label
              ? `With ${handoff.assigned_label}`
              : "Not assigned"}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button asChild variant="secondary" size="sm" className="min-h-11">
              <Link
                href={`/inbox?conversation=${encodeURIComponent(handoff.conversation_id)}`}
              >
                <MessageSquare className="size-4" aria-hidden />
                Open conversation
              </Link>
            </Button>
            {canManage && NEXT[handoff.status]?.length ? (
              <Button size="sm" className="min-h-11" onClick={onAct}>
                Update
              </Button>
            ) : null}
          </div>
        </CardSection>
      </Card>
    </li>
  );
}

export function HandoffsPage() {
  const can = useCan();
  const key = useBusinessKey();
  const canView = can("pi.read");
  const canManage = can("pi.handoffs.manage");
  const [status, setStatus] = React.useState<Status | "">("open");
  const [active, setActive] = React.useState<Handoff | null>(null);
  // One list for all statuses so the filter chips can show counts.
  const handoffs = useQuery({
    queryKey: key(["handoffs"]),
    queryFn: () => get<Handoff[]>("/pi/handoffs"),
    enabled: canView,
    refetchInterval: 30_000,
  });
  const counts = new Map<string, number>();
  for (const h of handoffs.data ?? [])
    counts.set(h.status, (counts.get(h.status) ?? 0) + 1);
  const rows = (handoffs.data ?? []).filter(
    (h) => !status || h.status === status,
  );

  return (
    <div className="min-w-0">
      <PageHeader
        title="Handovers"
        description="Conversations pi passed to your team. Pick one up, sort it out and mark it resolved."
        action={
          <Button asChild variant="secondary">
            <Link href="/inbox">Back to inbox</Link>
          </Button>
        }
      />
      {!canView ? (
        <Notice tone="warning" title="No access">
          Ask your business owner for access to conversations.
        </Notice>
      ) : (
        <>
          <div
            role="group"
            aria-label="Filter by status"
            className="-mx-4 mb-5 overflow-x-auto px-4 sm:mx-0 sm:px-0"
          >
            <div className="flex w-max gap-2">
              {FILTERS.map((f) => {
                const n = f.status
                  ? (counts.get(f.status) ?? 0)
                  : (handoffs.data?.length ?? 0);
                const on = status === f.status;
                return (
                  <button
                    key={f.label}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setStatus(f.status)}
                    className={cn(
                      "inline-flex min-h-11 items-center gap-2 whitespace-nowrap rounded-full border px-4 text-sm font-medium transition-colors",
                      on
                        ? "border-accent bg-accent-soft text-accent-soft-foreground"
                        : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                    )}
                  >
                    {f.label}
                    {handoffs.data ? (
                      <span
                        className={cn(
                          "rounded-full px-1.5 text-xs",
                          on ? "bg-surface" : "bg-surface-muted",
                        )}
                      >
                        {count(n)}
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>

          {handoffs.isLoading ? (
            <LoadingBlock rows={4} label="Loading handovers" />
          ) : handoffs.isError ? (
            <ErrorState
              message={errorText(handoffs.error)}
              onRetry={() => void handoffs.refetch()}
            />
          ) : rows.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Hand className="size-5" aria-hidden />}
                title={
                  status === "open" ? "Nothing waiting" : "No handovers here"
                }
              >
                {status === "open"
                  ? "pi is handling every conversation on its own right now."
                  : "When pi needs a person, the conversation shows up here."}
              </EmptyState>
            </Card>
          ) : (
            <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {rows.map((h) => (
                <HandoffCard
                  key={h.id}
                  handoff={h}
                  canManage={canManage}
                  onAct={() => setActive(h)}
                />
              ))}
            </ul>
          )}
          {handoffs.data?.length === 100 ? (
            <p className="mt-4 text-center text-[13px] text-muted-foreground">
              Showing the latest 100 handovers.
            </p>
          ) : null}
        </>
      )}

      <Dialog
        open={active !== null}
        onOpenChange={(open) => {
          if (!open) setActive(null);
        }}
      >
        {active ? (
          <ActionDialog
            key={active.id}
            handoff={active}
            onClose={() => setActive(null)}
          />
        ) : null}
      </Dialog>
    </div>
  );
}
