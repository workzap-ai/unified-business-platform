"use client";

import Link from "next/link";
import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Building2,
  GraduationCap,
  Plus,
  RefreshCw,
  Settings2,
  Sparkles,
  Trash2,
} from "lucide-react";

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
  Input,
  PageHeader,
  Skeleton,
  Textarea,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { errorText, get, patch, post } from "@/lib/api";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type Status = "open" | "with_team" | "resolved";

interface Department {
  key: string;
  name: string;
  description: string;
  open?: number;
  with_team?: number;
  resolved?: number;
}

interface Problem {
  index: number;
  conversation_id: string;
  customer_name: string;
  title: string;
  category: string;
  status: Status;
  summary: string;
  next_step: string;
  department: string;
  moved_by_team: boolean;
  last_message_at: string;
}

interface Board {
  departments: Department[];
  problems: Problem[];
  waiting_for_analysis: number;
  examples_learned: number;
  window_days: number;
  analysed?: number;
}

const STATUS: Record<
  Status,
  { label: string; tone: "warning" | "info" | "success"; bar: string }
> = {
  open: { label: "In progress", tone: "warning", bar: "bg-warning" },
  with_team: { label: "With your team", tone: "info", bar: "bg-info" },
  resolved: { label: "Sorted", tone: "success", bar: "bg-success" },
};

function ago(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `${Math.max(1, Math.floor(s / 60))}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function ProblemsPage() {
  const key = useBusinessKey();
  const can = useCan();
  const client = useQueryClient();
  const [department, setDepartment] = React.useState<string>("all");
  const [status, setStatus] = React.useState<Status | "all">("all");
  const [manage, setManage] = React.useState(false);
  const board = useQuery({
    queryKey: key(["problems"]),
    queryFn: () => get<Board>("/problems"),
    refetchInterval: 60_000,
  });
  const refresh = useAction(() => post<Board>("/problems/refresh"), {
    success: (b) =>
      b.analysed
        ? `pi sorted ${b.analysed} ${b.analysed === 1 ? "chat" : "chats"}`
        : "Everything is already sorted",
    onSuccess: (b) => client.setQueryData(key(["problems"]), b),
  });
  const move = useAction(
    (args: { problem: Problem; department: string }) =>
      post<Board>("/problems/move", {
        conversation_id: args.problem.conversation_id,
        index: args.problem.index,
        department: args.department,
      }),
    {
      success: "Moved. pi will sort problems like this the same way.",
      onSuccess: (b) => client.setQueryData(key(["problems"]), b),
    },
  );

  const data = board.data;
  const names = new Map(data?.departments.map((d) => [d.key, d.name]) ?? []);
  const shown = (data?.problems ?? []).filter(
    (p) =>
      (department === "all" || p.department === department) &&
      (status === "all" || p.status === status),
  );
  const totals = (data?.problems ?? []).reduce(
    (t, p) => ({ ...t, [p.status]: t[p.status] + 1 }),
    { open: 0, with_team: 0, resolved: 0 } as Record<Status, number>,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Problems"
        description="Every customer problem pi found in your chats, sorted into your departments. Move one and pi learns your way."
        action={
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            {can("pi.settings.manage") && (
              <Button
                variant="secondary"
                className="flex-1 sm:flex-none"
                onClick={() => setManage(true)}
                disabled={!data}
              >
                <Settings2 className="size-4" aria-hidden />
                Departments
              </Button>
            )}
            <Button
              className="flex-1 sm:flex-none"
              loading={refresh.isPending}
              onClick={() => refresh.mutate(undefined)}
            >
              <RefreshCw className="size-4" aria-hidden />
              Sort new chats
              {data && data.waiting_for_analysis > 0 && (
                <span className="rounded-full bg-accent-foreground/20 px-1.5 text-xs">
                  {data.waiting_for_analysis}
                </span>
              )}
            </Button>
          </div>
        }
      />

      {board.isPending ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
      ) : board.isError ? (
        <ErrorState
          message={errorText(board.error)}
          onRetry={() => board.refetch()}
        />
      ) : data ? (
        <>
          <Card className="p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 className="font-semibold">Last {data.window_days} days</h2>
                <p className="text-xs text-muted-foreground">
                  {data.problems.length} problems from your customers
                  {data.waiting_for_analysis > 0 &&
                    ` · ${data.waiting_for_analysis} new ${data.waiting_for_analysis === 1 ? "chat" : "chats"} not sorted yet`}
                </p>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent-soft-foreground">
                <GraduationCap className="size-3.5" aria-hidden />
                pi learned from {data.examples_learned} of your moves
              </span>
            </div>
            <StatusBar counts={totals} />
          </Card>

          <section aria-labelledby="departments" className="space-y-3">
            <h2 id="departments" className="text-base font-semibold">
              Departments
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <DepartmentCard
                name="All departments"
                description="Every problem"
                counts={totals}
                active={department === "all"}
                onClick={() => setDepartment("all")}
              />
              {data.departments.map((d) => (
                <DepartmentCard
                  key={d.key}
                  name={d.name}
                  description={d.description}
                  counts={{
                    open: d.open ?? 0,
                    with_team: d.with_team ?? 0,
                    resolved: d.resolved ?? 0,
                  }}
                  active={department === d.key}
                  onClick={() => setDepartment(d.key)}
                />
              ))}
            </div>
          </section>

          <section aria-labelledby="problem-list" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="problem-list" className="text-base font-semibold">
                {department === "all" ? "All problems" : names.get(department)}
                <span className="ms-2 text-sm font-normal text-muted-foreground">
                  {shown.length}
                </span>
              </h2>
              <div
                className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0"
                role="tablist"
                aria-label="Filter by status"
              >
                {(["all", "open", "with_team", "resolved"] as const).map(
                  (s) => (
                    <button
                      key={s}
                      type="button"
                      role="tab"
                      aria-selected={status === s}
                      onClick={() => setStatus(s)}
                      className={cn(
                        "min-h-10 shrink-0 rounded-full border px-3.5 text-sm font-medium",
                        status === s
                          ? "border-accent bg-accent text-accent-foreground"
                          : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                      )}
                    >
                      {s === "all" ? "All" : STATUS[s].label}
                    </button>
                  ),
                )}
              </div>
            </div>
            {shown.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<Sparkles className="size-6" aria-hidden />}
                  title={
                    data.problems.length
                      ? "Nothing here"
                      : "No problems sorted yet"
                  }
                  action={
                    data.waiting_for_analysis > 0 ? (
                      <Button
                        loading={refresh.isPending}
                        onClick={() => refresh.mutate(undefined)}
                      >
                        Sort new chats
                      </Button>
                    ) : undefined
                  }
                >
                  {data.problems.length
                    ? "Try another department or status."
                    : "When customers write on WhatsApp, pi lists each separate problem here and puts it in the right department."}
                </EmptyState>
              </Card>
            ) : (
              <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {shown.map((p) => (
                  <li
                    key={`${p.conversation_id}-${p.index}`}
                    className="min-w-0"
                  >
                    <ProblemCard
                      problem={p}
                      departments={data.departments}
                      canMove={can("pi.handoffs.manage")}
                      moving={move.isPending}
                      onMove={(d) => move.mutate({ problem: p, department: d })}
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
          {manage && (
            <DepartmentsDialog
              departments={data.departments}
              onClose={() => setManage(false)}
            />
          )}
        </>
      ) : null}
    </div>
  );
}

function StatusBar({ counts }: { counts: Record<Status, number> }) {
  const total = counts.open + counts.with_team + counts.resolved;
  return (
    <div className="mt-3">
      <div
        className="flex h-2.5 overflow-hidden rounded-full bg-surface-muted"
        role="img"
        aria-label={(Object.keys(STATUS) as Status[])
          .map((s) => `${STATUS[s].label}: ${counts[s]}`)
          .join(", ")}
      >
        {total > 0 &&
          (Object.keys(STATUS) as Status[]).map((s) =>
            counts[s] ? (
              <span
                key={s}
                className={cn("h-full", STATUS[s].bar)}
                style={{ width: `${(counts[s] / total) * 100}%` }}
              />
            ) : null,
          )}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {(Object.keys(STATUS) as Status[]).map((s) => (
          <li key={s} className="inline-flex items-center gap-1.5">
            <span
              className={cn("size-2 rounded-full", STATUS[s].bar)}
              aria-hidden
            />
            {STATUS[s].label} · {counts[s]}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DepartmentCard({
  name,
  description,
  counts,
  active,
  onClick,
}: {
  name: string;
  description: string;
  counts: Record<Status, number>;
  active: boolean;
  onClick: () => void;
}) {
  const total = counts.open + counts.with_team + counts.resolved;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex h-full min-w-0 flex-col rounded-2xl border bg-surface p-4 text-left shadow-sm transition-colors",
        active
          ? "border-accent ring-1 ring-accent"
          : "border-border hover:border-accent/40",
      )}
    >
      <span className="flex items-center gap-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Building2 className="size-4" aria-hidden />
        </span>
        <span className="min-w-0 flex-1 truncate font-semibold">{name}</span>
        <span className="text-lg font-semibold tabular-nums">{total}</span>
      </span>
      <span className="mt-1 line-clamp-2 text-xs text-muted-foreground">
        {description}
      </span>
      <span className="mt-auto flex gap-3 pt-3 text-xs">
        <span className="text-warning">{counts.open} in progress</span>
        <span className="text-info">{counts.with_team} team</span>
        <span className="text-success">{counts.resolved} sorted</span>
      </span>
    </button>
  );
}

function ProblemCard({
  problem,
  departments,
  canMove,
  moving,
  onMove,
}: {
  problem: Problem;
  departments: Department[];
  canMove: boolean;
  moving: boolean;
  onMove: (department: string) => void;
}) {
  const status = STATUS[problem.status] ?? STATUS.open;
  return (
    <Card className="h-full">
      <CardSection className="space-y-2 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="min-w-0 truncate text-sm font-medium">
            {problem.customer_name}
            <span className="ms-2 text-xs font-normal text-muted-foreground">
              {ago(problem.last_message_at)}
            </span>
          </span>
          <Badge tone={status.tone}>{status.label}</Badge>
        </div>
        <p className="font-semibold leading-snug">{problem.title}</p>
        {problem.summary && (
          <p className="text-sm text-foreground-secondary">{problem.summary}</p>
        )}
        {problem.next_step && problem.status !== "resolved" && (
          <p className="rounded-lg bg-surface-muted px-3 py-2 text-[13px]">
            <span className="font-medium">Next: </span>
            {problem.next_step}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {canMove ? (
            <label className="flex min-w-0 flex-1 items-center gap-2 text-xs text-muted-foreground">
              Department
              <select
                value={problem.department}
                disabled={moving}
                onChange={(e) => onMove(e.target.value)}
                className="h-10 min-w-0 flex-1 rounded-lg border border-border-strong bg-surface px-2 text-base text-foreground sm:h-9 sm:text-sm"
              >
                {departments.map((d) => (
                  <option key={d.key} value={d.key}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <Badge>
              {departments.find((d) => d.key === problem.department)?.name}
            </Badge>
          )}
          {problem.moved_by_team && (
            <Badge tone="accent">
              <GraduationCap className="size-3" aria-hidden />
              Set by your team
            </Badge>
          )}
          <Button asChild variant="ghost" size="sm" className="ms-auto">
            <Link href={`/inbox?conversation=${problem.conversation_id}`}>
              Open chat
              <ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
          </Button>
        </div>
      </CardSection>
    </Card>
  );
}

function slug(name: string) {
  const s = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
  return s.length >= 2 ? s : `dept_${Date.now().toString(36)}`;
}

function DepartmentsDialog({
  departments,
  onClose,
}: {
  departments: Department[];
  onClose: () => void;
}) {
  const [rows, setRows] = React.useState(
    departments.map(({ key: k, name, description }) => ({
      key: k,
      name,
      description,
    })),
  );
  const save = useAction(
    () =>
      patch("/pi/settings/handoff_rules", {
        value: {
          departments: rows.map((r) => ({
            key: r.key || slug(r.name),
            name: r.name.trim(),
            description: r.description.trim(),
          })),
        },
      }),
    {
      success: "Departments saved. pi uses them for new problems.",
      invalidate: [["problems"], ["settings"]],
      onSuccess: onClose,
    },
  );
  const valid =
    rows.length > 0 &&
    rows.every((r) => r.name.trim().length > 0 && r.description.length <= 300);
  return (
    <Dialog open onOpenChange={(open) => !open && !save.isPending && onClose()}>
      <DialogContent
        title="Your departments"
        description="pi puts every customer problem in one of these. Describe what each one handles so pi chooses well."
      >
        <ul className="max-h-[60vh] space-y-3 overflow-y-auto pe-1">
          {rows.map((r, i) => (
            <li
              key={i}
              className="space-y-2 rounded-xl border border-border p-3"
            >
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Field label="Name" htmlFor={`dept-name-${i}`}>
                    <Input
                      id={`dept-name-${i}`}
                      value={r.name}
                      maxLength={60}
                      className="text-base sm:text-[15px]"
                      onChange={(e) =>
                        setRows(
                          rows.map((x, j) =>
                            j === i ? { ...x, name: e.target.value } : x,
                          ),
                        )
                      }
                    />
                  </Field>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${r.name || "department"}`}
                  disabled={rows.length <= 1}
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </div>
              <Field label="What it handles" htmlFor={`dept-desc-${i}`}>
                <Textarea
                  id={`dept-desc-${i}`}
                  rows={2}
                  maxLength={300}
                  value={r.description}
                  className="text-base sm:text-[15px]"
                  onChange={(e) =>
                    setRows(
                      rows.map((x, j) =>
                        j === i ? { ...x, description: e.target.value } : x,
                      ),
                    )
                  }
                />
              </Field>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap justify-between gap-2">
          <Button
            variant="secondary"
            disabled={rows.length >= 20}
            onClick={() =>
              setRows([...rows, { key: "", name: "", description: "" }])
            }
          >
            <Plus className="size-4" aria-hidden />
            Add department
          </Button>
          <Button
            loading={save.isPending}
            disabled={!valid}
            onClick={() => save.mutate(undefined)}
          >
            Save departments
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
