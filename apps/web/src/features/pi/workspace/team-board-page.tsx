"use client";

import { useMemo, useState, type DragEvent } from "react";
import Link from "next/link";
import {
  ArrowRightLeft,
  CheckSquare,
  CreditCard,
  Receipt,
  MessageCircle,
  MessageCircleQuestion,
  Play,
  Plus,
  Stamp,
  Tag,
  Truck,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, Badge } from "@/components/ui/display";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { FormField } from "@/components/app/forms";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ErrorState, InlineError } from "@/components/app/states";
import { PageSkeleton } from "@/components/app/page-skeleton";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { customersService } from "@/features/customers/service";
import { errorMessage } from "@/services/api-client";
import { formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  BOARD_COLUMNS,
  BOARD_KINDS,
  COLUMN_STATUS,
  PRIORITIES,
  teamBoardService,
  type BoardCard,
  type BoardColumn,
  type BoardFilter,
  type BoardKind,
  type Priority,
  type TeamBoard,
} from "../team-board-service";

const LIVE_EVERY_MS = 20_000;
const KEY = ["pi", "team-board"];

const COLUMN_LABEL: Record<BoardColumn, string> = {
  todo: "To do",
  doing: "In progress",
  waiting: "Waiting",
  done: "Done (7 days)",
};

const KIND: Record<
  BoardKind,
  {
    label: string;
    icon: LucideIcon;
    tone: "primary" | "warning" | "danger" | "info" | "pi" | "success";
  }
> = {
  price: { label: "Price", icon: Tag, tone: "primary" },
  approve: { label: "Approve", icon: Stamp, tone: "info" },
  invoice: { label: "Send invoice", icon: Receipt, tone: "warning" },
  payment: { label: "Payment", icon: CreditCard, tone: "success" },
  request: { label: "pi asks", icon: MessageCircleQuestion, tone: "pi" },
  reply: { label: "Reply", icon: MessageCircle, tone: "danger" },
  start: { label: "Start", icon: Play, tone: "primary" },
  deliver: { label: "Deliver", icon: Truck, tone: "info" },
  feedback: { label: "Fix", icon: Wrench, tone: "warning" },
  task: { label: "Task", icon: CheckSquare, tone: "primary" },
};

const PRIORITY_DOT: Record<Priority, string> = {
  urgent: "bg-danger",
  high: "bg-warning",
  normal: "bg-info",
  low: "bg-muted-foreground/40",
};

/** "in 3h", "2d late", "due now". */
export function dueLabel(due: string, now = Date.now()) {
  const diff = new Date(due).getTime() - now;
  const minutes = Math.round(Math.abs(diff) / 60_000);
  const span =
    minutes < 60
      ? `${Math.max(minutes, 1)}m`
      : minutes < 60 * 48
        ? `${Math.round(minutes / 60)}h`
        : `${Math.round(minutes / 1440)}d`;
  if (Math.abs(diff) < 60_000) return "due now";
  return diff < 0 ? `${span} late` : `in ${span}`;
}

export function TeamBoardPage() {
  return (
    <RequirePermission permission="pi.work.read" area="pi">
      <TeamBoardView />
    </RequirePermission>
  );
}

function TeamBoardView() {
  const { can } = useSession();
  const manage = can("pi.work.manage");
  const [filter, setFilter] = useState<BoardFilter>({ who: "all", kind: null });
  const [tab, setTab] = useState<BoardColumn>("todo");
  const [creating, setCreating] = useState(false);
  // Cards being moved show in their new column straight away.
  const [moving, setMoving] = useState<Record<string, BoardColumn>>({});
  const query = useScopedQuery(
    [...KEY, filter.who, filter.kind],
    () => teamBoardService.get(filter),
    { refetchInterval: LIVE_EVERY_MS },
  );
  const update = useScopedMutation(teamBoardService.update, {
    invalidate: [KEY],
    error: "That card couldn't be changed. Please try again.",
  });
  const data = query.data;

  const columns = useMemo(() => {
    const out: Record<BoardColumn, BoardCard[]> = {
      todo: [],
      doing: [],
      waiting: [],
      done: [],
    };
    if (!data) return out;
    for (const column of BOARD_COLUMNS)
      for (const card of data.columns[column])
        out[moving[card.id] ?? column].push(card);
    return out;
  }, [data, moving]);

  function move(card: BoardCard, to: BoardColumn) {
    if (!manage || (moving[card.id] ?? card.column) === to) return;
    setMoving((m) => ({ ...m, [card.id]: to }));
    update.mutate(
      { id: card.id, status: COLUMN_STATUS[to] },
      {
        onSettled: () =>
          setMoving((m) => {
            const next = { ...m };
            delete next[card.id];
            return next;
          }),
      },
    );
  }

  function assign(card: BoardCard, userId: string | null) {
    update.mutate({ id: card.id, assignee_user_id: userId });
  }

  return (
    <PageShell>
      <PageHeader
        title="Team board"
        description="Everything your team has to do, for every customer. pi adds the work it finds and closes it when it's done; moving a deal's card tells the customer."
        actions={
          <>
            <LiveBadge
              fetching={query.isFetching}
              updatedAt={query.dataUpdatedAt}
            />
            {manage && (
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus aria-hidden="true" /> New task
              </Button>
            )}
          </>
        }
      />
      {query.isError && !data ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !data ? (
        <PageSkeleton variant="dashboard" />
      ) : (
        <div className="space-y-4">
          <Filters data={data} filter={filter} onChange={setFilter} />
          <div
            role="tablist"
            aria-label="Columns"
            className="grid grid-cols-4 gap-1 rounded-md border border-border bg-surface-muted p-0.5 sm:hidden"
          >
            {BOARD_COLUMNS.map((column) => (
              <button
                key={column}
                type="button"
                role="tab"
                aria-selected={tab === column}
                onClick={() => setTab(column)}
                className={cn(
                  "min-w-0 rounded-[5px] px-1 py-1.5 text-xs font-medium text-muted-foreground",
                  tab === column && "bg-surface text-foreground shadow-sm",
                )}
              >
                <span className="block truncate">
                  {column === "done" ? "Done" : COLUMN_LABEL[column]}
                </span>
                <span className="tabular-nums">{columns[column].length}</span>
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {BOARD_COLUMNS.map((column) => (
              <Column
                key={column}
                column={column}
                cards={columns[column]}
                hidden={tab !== column}
                manage={manage}
                members={data.members}
                onDropCard={(id) => {
                  const card = BOARD_COLUMNS.flatMap(
                    (c) => data.columns[c],
                  ).find((c) => c.id === id);
                  if (card) move(card, column);
                }}
                onMove={move}
                onAssign={assign}
              />
            ))}
          </div>
        </div>
      )}
      {creating && data && (
        <NewTaskDialog
          members={data.members}
          onClose={() => setCreating(false)}
        />
      )}
    </PageShell>
  );
}

function Filters({
  data,
  filter,
  onChange,
}: {
  data: TeamBoard;
  filter: BoardFilter;
  onChange: (next: BoardFilter) => void;
}) {
  const who: { key: BoardFilter["who"]; label: string; count?: number }[] = [
    { key: "all", label: "All", count: data.counts.all },
    { key: "me", label: "Mine", count: data.counts.mine },
    { key: "unassigned", label: "Unassigned", count: data.counts.unassigned },
  ];
  const kinds = BOARD_KINDS.filter(
    (k) => (data.kinds[k] ?? 0) > 0 || filter.kind === k,
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div
        role="group"
        aria-label="Whose cards"
        className="inline-flex h-8 items-center gap-0.5 rounded-md border border-border bg-surface-muted p-0.5"
      >
        {who.map((w) => (
          <button
            key={w.key}
            type="button"
            aria-pressed={filter.who === w.key}
            onClick={() => onChange({ ...filter, who: w.key })}
            className={cn(
              "inline-flex h-6.5 items-center gap-1 rounded-[5px] px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground",
              filter.who === w.key && "bg-surface text-foreground shadow-sm",
            )}
          >
            {w.label}
            <span className="tabular-nums opacity-70">{w.count ?? 0}</span>
          </button>
        ))}
      </div>
      {kinds.map((k) => {
        const meta = KIND[k];
        const active = filter.kind === k;
        return (
          <button
            key={k}
            type="button"
            aria-pressed={active}
            onClick={() => onChange({ ...filter, kind: active ? null : k })}
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors",
              active
                ? "border-primary bg-primary-soft text-primary-soft-foreground"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            <meta.icon className="size-3.5" aria-hidden="true" />
            {meta.label}
            <span className="tabular-nums opacity-70">
              {data.kinds[k] ?? 0}
            </span>
          </button>
        );
      })}
      {data.counts.overdue ? (
        <Badge tone="danger" dot>
          {data.counts.overdue} late
        </Badge>
      ) : null}
    </div>
  );
}

function Column({
  column,
  cards,
  hidden,
  manage,
  members,
  onDropCard,
  onMove,
  onAssign,
}: {
  column: BoardColumn;
  cards: BoardCard[];
  hidden: boolean;
  manage: boolean;
  members: TeamBoard["members"];
  onDropCard: (id: string) => void;
  onMove: (card: BoardCard, to: BoardColumn) => void;
  onAssign: (card: BoardCard, userId: string | null) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <section
      aria-label={COLUMN_LABEL[column]}
      className={cn(
        "min-w-0 flex-col rounded-lg border border-border bg-surface-muted/50 p-2 transition-colors",
        hidden ? "hidden sm:flex" : "flex",
        over && "border-primary bg-primary-soft/40",
      )}
      onDragOver={(e) => {
        if (!manage) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => {
        e.preventDefault();
        setOver(false);
        const id = e.dataTransfer.getData("text/plain");
        if (id) onDropCard(id);
      }}
    >
      <header className="flex items-center justify-between px-1.5 pt-0.5 pb-2">
        <h2 className="text-[13px] font-semibold">{COLUMN_LABEL[column]}</h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {cards.length}
        </span>
      </header>
      <ul className="flex min-h-24 flex-col gap-2">
        {cards.map((card) => (
          <li key={card.id}>
            <BoardCardView
              card={card}
              column={column}
              manage={manage}
              members={members}
              onMove={onMove}
              onAssign={onAssign}
            />
          </li>
        ))}
        {cards.length === 0 && (
          <li className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            {column === "done"
              ? "Nothing finished this week yet"
              : "Nothing here"}
          </li>
        )}
      </ul>
    </section>
  );
}

function BoardCardView({
  card,
  column,
  manage,
  members,
  onMove,
  onAssign,
}: {
  card: BoardCard;
  column: BoardColumn;
  manage: boolean;
  members: TeamBoard["members"];
  onMove: (card: BoardCard, to: BoardColumn) => void;
  onAssign: (card: BoardCard, userId: string | null) => void;
}) {
  const meta = KIND[card.kind];
  const done = column === "done";
  const subtitle = [card.customer?.name, card.project]
    .filter(Boolean)
    .join(" · ");
  return (
    <article
      draggable={manage}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", card.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      className={cn(
        "rounded-md border border-border bg-surface p-2.5 shadow-xs",
        manage && "cursor-grab active:cursor-grabbing",
        done && "opacity-70",
      )}
    >
      <div className="flex items-center gap-1.5">
        <Badge tone={meta.tone}>
          <meta.icon aria-hidden="true" /> {meta.label}
        </Badge>
        <span
          className={cn(
            "size-2 shrink-0 rounded-full",
            PRIORITY_DOT[card.priority],
          )}
          title={`${card.priority} priority`}
          aria-label={`${card.priority} priority`}
        />
        {card.due_at && !done && (
          <span
            className={cn(
              "ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-medium tabular-nums",
              card.overdue
                ? "bg-danger-soft text-danger"
                : "bg-surface-muted text-muted-foreground",
            )}
            title={new Date(card.due_at).toLocaleString()}
          >
            {dueLabel(card.due_at)}
          </span>
        )}
      </div>
      <h3 className="mt-1.5 text-[13px] leading-snug font-medium break-words">
        {card.link ? (
          <Link href={card.link} className="hover:underline">
            {card.title}
          </Link>
        ) : (
          card.title
        )}
      </h3>
      {subtitle && (
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {subtitle}
        </p>
      )}
      <div className="mt-2 flex items-center gap-1.5">
        {card.assignee ? (
          <Avatar name={card.assignee.name} size="xs" />
        ) : (
          <span className="size-5 shrink-0 rounded-full border border-dashed border-border" />
        )}
        {manage ? (
          <NativeSelect
            aria-label={`Assign ${card.title}`}
            className="h-7 min-w-0 flex-1 truncate border-transparent bg-transparent px-1 text-xs shadow-none"
            value={card.assignee?.id ?? ""}
            onChange={(e) => onAssign(card, e.target.value || null)}
          >
            <option value="">Unassigned</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
            {card.assignee &&
              !members.some((m) => m.id === card.assignee?.id) && (
                <option value={card.assignee.id}>{card.assignee.name}</option>
              )}
          </NativeSelect>
        ) : (
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            {card.assignee?.name ?? "Unassigned"}
          </span>
        )}
        {manage && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Move ${card.title} to…`}
              >
                <ArrowRightLeft />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Move to…</DropdownMenuLabel>
              {BOARD_COLUMNS.filter((c) => c !== column).map((c) => (
                <DropdownMenuItem key={c} onSelect={() => onMove(card, c)}>
                  {COLUMN_LABEL[c]}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </article>
  );
}

function NewTaskDialog({
  members,
  onClose,
}: {
  members: TeamBoard["members"];
  onClose: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [search, setSearch] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState<Priority>("normal");
  const [due, setDue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const customers = useScopedQuery(["customers", "board-picker", search], () =>
    customersService.list({ page: 1, pageSize: 20, search }),
  );
  const create = useScopedMutation(teamBoardService.create, {
    invalidate: [KEY],
    success: "Task added to the board",
    toastErrors: false,
  });
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent size="sm">
        <DialogHeader
          title="New task"
          description="A card for something the team has to do."
        />
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!title.trim()) {
              setError("Give the task a title");
              return;
            }
            setError(null);
            try {
              await create.mutateAsync({
                title: title.trim(),
                description: description.trim(),
                customer_id: customerId || null,
                assignee_user_id: assignee || null,
                priority,
                due_at: due ? new Date(due).toISOString() : null,
              });
              onClose();
            } catch (err) {
              setError(errorMessage(err, "The task could not be added."));
            }
          }}
        >
          <DialogBody className="space-y-4">
            <FormField label="Title" htmlFor="task-title" required>
              <Input
                id="task-title"
                autoComplete="off"
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </FormField>
            <FormField label="Details" htmlFor="task-details" optional>
              <Textarea
                id="task-details"
                rows={3}
                maxLength={4000}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </FormField>
            <FormField label="Customer" htmlFor="task-customer" optional>
              <div className="space-y-1.5">
                <Input
                  aria-label="Search customers"
                  placeholder="Search customers"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <NativeSelect
                  id="task-customer"
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                >
                  <option value="">No customer</option>
                  {(customers.data?.items ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Assign to" htmlFor="task-assignee" optional>
                <NativeSelect
                  id="task-assignee"
                  value={assignee}
                  onChange={(e) => setAssignee(e.target.value)}
                >
                  <option value="">Unassigned</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
              <FormField label="Priority" htmlFor="task-priority">
                <NativeSelect
                  id="task-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority)}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p[0]!.toUpperCase() + p.slice(1)}
                    </option>
                  ))}
                </NativeSelect>
              </FormField>
            </div>
            <FormField label="Due" htmlFor="task-due" optional>
              <Input
                id="task-due"
                type="datetime-local"
                value={due}
                onChange={(e) => setDue(e.target.value)}
              />
            </FormField>
            {error && <InlineError message={error} />}
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Add task
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LiveBadge({
  fetching,
  updatedAt,
}: {
  fetching: boolean;
  updatedAt: number;
}) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground"
      title={`Refreshes every ${LIVE_EVERY_MS / 1000} seconds while open`}
    >
      <span className="relative flex size-2">
        <span
          className={cn(
            "absolute inline-flex size-full rounded-full bg-success opacity-60",
            fetching ? "animate-ping" : "motion-safe:animate-pulse",
          )}
        />
        <span className="relative inline-flex size-2 rounded-full bg-success" />
      </span>
      Live ·{" "}
      {fetching || !updatedAt ? "updating…" : formatTime(new Date(updatedAt))}
    </span>
  );
}
