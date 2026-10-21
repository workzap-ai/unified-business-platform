"use client";

/**
 * Team board: everything the team has to do, for every customer, as a Kanban.
 * pi adds the work it finds (a proposal to price, a payment proof to check, a chat to
 * answer, paid work to start or deliver...) and closes it when it's done. Moving a
 * deal's "Start" card to In progress starts the work, and a "Deliver" card to Done
 * delivers it: pi tells the customer, as the deal page's buttons do.
 * API: app/modules/pi_saas/team_board_routes.py (/pi/team-board).
 */
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarClock,
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
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Switch,
  Textarea,
  cn,
} from "@/components/ui";
import { errorText, get, patch, post, put } from "@/lib/api";
import { piLink } from "@/lib/links";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

const LIVE_EVERY_MS = 20_000;

type Kind =
  | "price"
  | "approve"
  | "invoice"
  | "payment"
  | "request"
  | "reply"
  | "start"
  | "deliver"
  | "feedback"
  | "task";
type Column = "todo" | "doing" | "waiting" | "done";
type Priority = "low" | "normal" | "high" | "urgent";
/** "all", "me", "unassigned" or one member's user id. */
type Who = string;

export interface BoardCard {
  id: string;
  title: string;
  description: string;
  kind: Kind;
  auto: boolean;
  status: string;
  column: Column;
  customer: { id: string; name: string } | null;
  project: string | null;
  assignee: { id: string; name: string } | null;
  priority: Priority;
  due_at: string | null;
  overdue: boolean;
  created_at: string;
  updated_at: string;
  link: string | null;
}

interface Board {
  columns: Record<Column, BoardCard[]>;
  members: { id: string; name: string }[];
  counts: Record<string, number>;
  kinds: Record<string, number>;
  by_member?: Record<string, number>;
  me: string | null;
}

/** Team members' WhatsApp numbers for task alerts (team_alerts.py). */
interface TeamMembers {
  enabled: boolean;
  template_name: string;
  template_language: string;
  business_number: string | null;
  members: {
    id: string;
    name: string;
    whatsapp: string;
    window_open: boolean;
  }[];
}

const COLUMNS: Column[] = ["todo", "doing", "waiting", "done"];
const COLUMN_LABEL: Record<Column, string> = {
  todo: "To do",
  doing: "In progress",
  waiting: "Waiting",
  done: "Done (7 days)",
};
const COLUMN_STATUS: Record<Column, string> = {
  todo: "open",
  doing: "in_progress",
  waiting: "blocked",
  done: "done",
};
const KINDS: Kind[] = [
  "price",
  "approve",
  "invoice",
  "payment",
  "request",
  "reply",
  "start",
  "deliver",
  "feedback",
  "task",
];
const KIND: Record<
  Kind,
  {
    label: string;
    icon: LucideIcon;
    tone: "accent" | "success" | "warning" | "danger" | "info" | "neutral";
  }
> = {
  price: { label: "Price", icon: Tag, tone: "accent" },
  approve: { label: "Approve", icon: Stamp, tone: "info" },
  invoice: { label: "Send invoice", icon: Receipt, tone: "warning" },
  payment: { label: "Payment", icon: CreditCard, tone: "success" },
  request: { label: "pi asks", icon: MessageCircleQuestion, tone: "accent" },
  reply: { label: "Reply", icon: MessageCircle, tone: "danger" },
  start: { label: "Start", icon: Play, tone: "accent" },
  deliver: { label: "Deliver", icon: Truck, tone: "info" },
  feedback: { label: "Fix", icon: Wrench, tone: "warning" },
  task: { label: "Task", icon: CheckSquare, tone: "neutral" },
};
const PRIORITY_DOT: Record<Priority, string> = {
  urgent: "bg-danger",
  high: "bg-warning",
  normal: "bg-info",
  low: "bg-muted-foreground/40",
};

/** "in 3h", "2d late", "due now". */
function dueLabel(due: string) {
  const diff = new Date(due).getTime() - Date.now();
  if (Math.abs(diff) < 60_000) return "due now";
  const minutes = Math.round(Math.abs(diff) / 60_000);
  const span =
    minutes < 60
      ? `${minutes}m`
      : minutes < 60 * 48
        ? `${Math.round(minutes / 60)}h`
        : `${Math.round(minutes / 1440)}d`;
  return diff < 0 ? `${span} late` : `in ${span}`;
}

/** An ISO time as the value of a datetime-local input (local time). */
function localInput(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (
    (parts[0]?.[0] ?? "?") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")
  ).toUpperCase();
}

export function TeamBoardPage() {
  const key = useBusinessKey();
  const can = useCan();
  const allowed = can("pi.work.read");
  const manage = can("pi.work.manage");
  const [who, setWho] = React.useState<Who>("all");
  const [kind, setKind] = React.useState<Kind | null>(null);
  const [tab, setTab] = React.useState<Column>("todo");
  const [creating, setCreating] = React.useState(false);
  const [team, setTeam] = React.useState(false);
  const [moving, setMoving] = React.useState<Record<string, Column>>({});
  const board = useQuery({
    queryKey: key(["team-board", who, kind]),
    queryFn: () => get<Board>("/pi/team-board", { who, kind }),
    enabled: allowed,
    refetchInterval: LIVE_EVERY_MS,
    placeholderData: (previous) => previous,
  });
  const update = useAction(
    ({
      id,
      ...change
    }: {
      id: string;
      status?: string;
      assignee_user_id?: string | null;
      due_at?: string | null;
    }) => patch<BoardCard>(`/pi/team-board/tasks/${id}`, change),
    { invalidate: [["team-board"]] },
  );

  const columns = React.useMemo(() => {
    const out: Record<Column, BoardCard[]> = {
      todo: [],
      doing: [],
      waiting: [],
      done: [],
    };
    for (const column of COLUMNS)
      for (const card of board.data?.columns[column] ?? [])
        out[moving[card.id] ?? column].push(card);
    return out;
  }, [board.data, moving]);

  // Late cards are pinned on top, so nothing overdue hides in a long column.
  const overdue = React.useMemo(
    () =>
      (["todo", "doing", "waiting"] as const)
        .flatMap((c) => columns[c])
        .filter((card) => card.overdue)
        .sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? "")),
    [columns],
  );
  const assign = (card: BoardCard, userId: string | null) =>
    update.mutate({ id: card.id, assignee_user_id: userId });
  const setDue = (card: BoardCard, due: string | null) =>
    update.mutate({ id: card.id, due_at: due });

  function move(card: BoardCard, to: Column) {
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

  if (!allowed) {
    return (
      <EmptyState title="No access to the team board">
        Ask your business owner to give you access to tasks.
      </EmptyState>
    );
  }
  const data = board.data;
  return (
    <div>
      <PageHeader
        title="Team board"
        description="Everything your team has to do, for every customer. pi adds the work it finds and closes it when it's done; moving a deal's card tells the customer."
        action={
          <>
            <LiveBadge
              fetching={board.isFetching}
              updatedAt={board.dataUpdatedAt}
            />
            <Button variant="secondary" onClick={() => setTeam(true)}>
              <Users className="size-4" aria-hidden /> Team
            </Button>
            {manage ? (
              <Button onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden /> New task
              </Button>
            ) : null}
          </>
        }
      />
      {board.isError && !data ? (
        <ErrorState
          message={errorText(board.error)}
          onRetry={() => board.refetch()}
        />
      ) : !data ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((c) => (
            <Skeleton key={c} className="h-64 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div
              role="group"
              aria-label="Whose cards"
              className="inline-flex items-center gap-0.5 rounded-xl border border-border bg-surface-muted p-0.5"
            >
              {(
                [
                  ["all", "All", data.counts.all],
                  ["me", "Mine", data.counts.mine],
                  ["unassigned", "Unassigned", data.counts.unassigned],
                ] as const
              ).map(([value, label, count]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={who === value}
                  onClick={() => setWho(value)}
                  className={cn(
                    "min-h-9 rounded-[10px] px-3 text-sm font-medium text-muted-foreground",
                    who === value && "bg-surface text-foreground shadow-sm",
                  )}
                >
                  {label}{" "}
                  <span className="tabular-nums opacity-70">{count ?? 0}</span>
                </button>
              ))}
            </div>
            <Select
              aria-label="Show one team member's cards"
              className={cn(
                "h-9 w-auto max-w-52 px-2 text-sm",
                data.members.some((m) => m.id === who) &&
                  "border-accent bg-accent-soft text-accent-soft-foreground",
              )}
              value={data.members.some((m) => m.id === who) ? who : ""}
              onChange={(e) => setWho(e.target.value || "all")}
            >
              <option value="">Any member</option>
              {data.members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({data.by_member?.[m.id] ?? 0})
                </option>
              ))}
            </Select>
            {KINDS.filter((k) => (data.kinds[k] ?? 0) > 0 || kind === k).map(
              (k) => {
                const meta = KIND[k];
                const active = kind === k;
                return (
                  <button
                    key={k}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setKind(active ? null : k)}
                    className={cn(
                      "inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-sm font-medium",
                      active
                        ? "border-accent bg-accent-soft text-accent-soft-foreground"
                        : "border-border text-muted-foreground",
                    )}
                  >
                    <meta.icon className="size-4" aria-hidden />
                    {meta.label}
                    <span className="tabular-nums opacity-70">
                      {data.kinds[k] ?? 0}
                    </span>
                  </button>
                );
              },
            )}
            {data.counts.overdue ? (
              <Badge tone="danger">{data.counts.overdue} late</Badge>
            ) : null}
          </div>

          {overdue.length > 0 ? (
            <section
              aria-label="Overdue"
              className="rounded-2xl border border-danger/30 bg-danger-soft/40 p-2"
            >
              <header className="flex items-center gap-1.5 px-2 pt-1 pb-2 text-danger">
                <AlertTriangle className="size-4" aria-hidden />
                <h2 className="text-sm font-semibold">Overdue</h2>
                <span className="text-xs tabular-nums">{overdue.length}</span>
              </header>
              <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {overdue.map((card) => (
                  <li key={card.id}>
                    <CardView
                      card={card}
                      column={card.column}
                      manage={manage}
                      members={data.members}
                      onMove={move}
                      onAssign={assign}
                      onDue={setDue}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <div
            role="tablist"
            aria-label="Columns"
            className="grid grid-cols-4 gap-1 rounded-xl border border-border bg-surface-muted p-0.5 sm:hidden"
          >
            {COLUMNS.map((column) => (
              <button
                key={column}
                type="button"
                role="tab"
                aria-selected={tab === column}
                onClick={() => setTab(column)}
                className={cn(
                  "min-w-0 rounded-[10px] px-1 py-1.5 text-xs font-medium text-muted-foreground",
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
            {COLUMNS.map((column) => (
              <BoardColumn
                key={column}
                column={column}
                cards={columns[column]}
                hidden={tab !== column}
                manage={manage}
                members={data.members}
                onDropCard={(id) => {
                  const card = COLUMNS.flatMap((c) => data.columns[c]).find(
                    (c) => c.id === id,
                  );
                  if (card) move(card, column);
                }}
                onMove={move}
                onAssign={assign}
                onDue={setDue}
              />
            ))}
          </div>
        </div>
      )}
      {creating && data ? (
        <NewTaskDialog
          members={data.members}
          onClose={() => setCreating(false)}
        />
      ) : null}
      {team ? (
        <TeamDialog
          manage={manage}
          counts={data?.by_member ?? {}}
          onClose={() => setTeam(false)}
        />
      ) : null}
    </div>
  );
}

function BoardColumn({
  column,
  cards,
  hidden,
  manage,
  members,
  onDropCard,
  onMove,
  onAssign,
  onDue,
}: {
  column: Column;
  cards: BoardCard[];
  hidden: boolean;
  manage: boolean;
  members: Board["members"];
  onDropCard: (id: string) => void;
  onMove: (card: BoardCard, to: Column) => void;
  onAssign: (card: BoardCard, userId: string | null) => void;
  onDue: (card: BoardCard, due: string | null) => void;
}) {
  const [over, setOver] = React.useState(false);
  return (
    <section
      aria-label={COLUMN_LABEL[column]}
      className={cn(
        "min-w-0 flex-col rounded-2xl border border-border bg-surface-muted/50 p-2 transition-colors",
        hidden ? "hidden sm:flex" : "flex",
        over && "border-accent bg-accent-soft/40",
      )}
      onDragOver={(e) => {
        if (!manage) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const id = e.dataTransfer.getData("text/plain");
        if (id) onDropCard(id);
      }}
    >
      <header className="flex items-center justify-between px-2 pt-1 pb-2">
        <h2 className="text-sm font-semibold">{COLUMN_LABEL[column]}</h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {cards.length}
        </span>
      </header>
      <ul className="flex min-h-24 flex-col gap-2">
        {cards.map((card) => (
          <li key={card.id}>
            <CardView
              card={card}
              column={column}
              manage={manage}
              members={members}
              onMove={onMove}
              onAssign={onAssign}
              onDue={onDue}
            />
          </li>
        ))}
        {cards.length === 0 ? (
          <li className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
            {column === "done"
              ? "Nothing finished this week yet"
              : "Nothing here"}
          </li>
        ) : null}
      </ul>
    </section>
  );
}

function CardView({
  card,
  column,
  manage,
  members,
  onMove,
  onAssign,
  onDue,
}: {
  card: BoardCard;
  column: Column;
  manage: boolean;
  members: Board["members"];
  onMove: (card: BoardCard, to: Column) => void;
  onAssign: (card: BoardCard, userId: string | null) => void;
  onDue: (card: BoardCard, due: string | null) => void;
}) {
  const meta = KIND[card.kind] ?? KIND.task;
  const done = column === "done";
  const [editingDue, setEditingDue] = React.useState(false);
  const [due, setDueValue] = React.useState(localInput(card.due_at));
  const dueChip = cn(
    "ms-auto shrink-0 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
    card.overdue
      ? "bg-danger-soft text-danger"
      : "bg-surface-muted text-muted-foreground",
  );
  const link = piLink(card.link);
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
        "rounded-xl border border-border bg-surface p-3 shadow-sm",
        manage && "cursor-grab active:cursor-grabbing",
        done && "opacity-70",
      )}
    >
      <div className="flex items-center gap-1.5">
        <Badge tone={meta.tone}>
          <meta.icon className="size-3.5" aria-hidden /> {meta.label}
        </Badge>
        <span
          className={cn(
            "size-2 shrink-0 rounded-full",
            PRIORITY_DOT[card.priority],
          )}
          title={`${card.priority} priority`}
          aria-label={`${card.priority} priority`}
        />
        {!done && manage ? (
          <button
            type="button"
            className={cn(
              dueChip,
              "min-h-7 hover:ring-1 hover:ring-border-strong",
            )}
            title={
              card.due_at
                ? `Due ${new Date(card.due_at).toLocaleString()}. Change`
                : "Set a due time"
            }
            aria-label={`Due time for ${card.title}`}
            aria-expanded={editingDue}
            onClick={() => {
              setDueValue(localInput(card.due_at));
              setEditingDue((v) => !v);
            }}
          >
            {card.due_at ? (
              dueLabel(card.due_at)
            ) : (
              <CalendarClock className="size-4" aria-hidden />
            )}
          </button>
        ) : card.due_at && !done ? (
          <span
            className={dueChip}
            title={new Date(card.due_at).toLocaleString()}
          >
            {dueLabel(card.due_at)}
          </span>
        ) : null}
      </div>
      {editingDue ? (
        <form
          className="mt-2 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onDue(card, due ? new Date(due).toISOString() : null);
            setEditingDue(false);
          }}
        >
          <Input
            type="datetime-local"
            aria-label={`Due time for ${card.title}`}
            className="h-9 min-w-0 flex-1 px-2 text-[13px]"
            value={due}
            onChange={(e) => setDueValue(e.target.value)}
          />
          <Button type="submit" size="sm">
            Save
          </Button>
          {card.due_at ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                onDue(card, null);
                setEditingDue(false);
              }}
            >
              Clear
            </Button>
          ) : null}
        </form>
      ) : null}
      <h3 className="mt-2 text-sm font-medium leading-snug break-words">
        {link ? (
          <Link href={link} className="hover:underline">
            {card.title}
          </Link>
        ) : (
          card.title
        )}
      </h3>
      {subtitle ? (
        <p className="mt-0.5 truncate text-[13px] text-muted-foreground">
          {subtitle}
        </p>
      ) : null}
      <div className="mt-2.5 flex items-center gap-2">
        <span
          aria-hidden
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
            card.assignee
              ? "bg-accent-soft text-accent-soft-foreground"
              : "border border-dashed border-border",
          )}
        >
          {card.assignee ? initials(card.assignee.name) : ""}
        </span>
        {manage ? (
          <>
            <Select
              aria-label={`Assign ${card.title}`}
              className="h-9 min-w-0 flex-1 px-2 text-[13px]"
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
              !members.some((m) => m.id === card.assignee?.id) ? (
                <option value={card.assignee.id}>{card.assignee.name}</option>
              ) : null}
            </Select>
            <Select
              aria-label={`Move ${card.title} to`}
              className="h-9 w-auto shrink-0 px-2 text-[13px]"
              value=""
              onChange={(e) => {
                if (e.target.value) onMove(card, e.target.value as Column);
              }}
            >
              <option value="">Move to…</option>
              {COLUMNS.filter((c) => c !== column).map((c) => (
                <option key={c} value={c}>
                  {COLUMN_LABEL[c]}
                </option>
              ))}
            </Select>
          </>
        ) : (
          <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">
            {card.assignee?.name ?? "Unassigned"}
          </span>
        )}
      </div>
    </article>
  );
}

function NewTaskDialog({
  members,
  onClose,
}: {
  members: Board["members"];
  onClose: () => void;
}) {
  const key = useBusinessKey();
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [customerId, setCustomerId] = React.useState("");
  const [assignee, setAssignee] = React.useState("");
  const [priority, setPriority] = React.useState<Priority>("normal");
  const [due, setDue] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const customers = useQuery({
    queryKey: key(["customers", "board-picker", search]),
    queryFn: () =>
      get<{ items: { id: string; name: string | null }[] }>("/pi/customers", {
        search: search || undefined,
        page: 1,
        page_size: 20,
      }),
    placeholderData: (previous) => previous,
  });
  const create = useAction(
    () =>
      post<BoardCard>("/pi/team-board/tasks", {
        title: title.trim(),
        description: description.trim(),
        customer_id: customerId || null,
        assignee_user_id: assignee || null,
        priority,
        due_at: due ? new Date(due).toISOString() : null,
      }),
    {
      invalidate: [["team-board"]],
      success: "Task added to the board",
      onSuccess: onClose,
    },
  );
  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !create.isPending && onClose()}
    >
      <DialogContent
        title="New task"
        description="A card for something the team has to do."
      >
        <form
          noValidate
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!title.trim()) {
              setError("Give the task a title");
              return;
            }
            setError(null);
            create.mutate(undefined);
          }}
        >
          <Field label="Title" htmlFor="task-title" error={error}>
            <Input
              id="task-title"
              autoComplete="off"
              maxLength={200}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>
          <Field label="Details" htmlFor="task-details" optional>
            <Textarea
              id="task-details"
              rows={3}
              maxLength={4000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          <Field label="Customer" htmlFor="task-customer" optional>
            <div className="space-y-2">
              <Input
                aria-label="Search customers"
                placeholder="Search customers"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Select
                id="task-customer"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
              >
                <option value="">No customer</option>
                {(customers.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name || "Unnamed customer"}
                  </option>
                ))}
              </Select>
            </div>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Assign to" htmlFor="task-assignee" optional>
              <Select
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
              </Select>
            </Field>
            <Field label="Priority" htmlFor="task-priority">
              <Select
                id="task-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </Select>
            </Field>
          </div>
          <Field label="Due" htmlFor="task-due" optional>
            <Input
              id="task-due"
              type="datetime-local"
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
          </Field>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
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
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The team and their WhatsApp numbers: pi tells each person on WhatsApp when a card
 * is given to them or due within the hour (team_alerts.py). */
function TeamDialog({
  manage,
  counts,
  onClose,
}: {
  manage: boolean;
  counts: Record<string, number>;
  onClose: () => void;
}) {
  const key = useBusinessKey();
  const query = useQuery({
    queryKey: key(["team-board", "members"]),
    queryFn: () => get<TeamMembers>("/pi/team-board/members"),
  });
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        title="Team"
        description="pi messages a person on WhatsApp, from your business number, when a card is given to them and when it's due within the hour."
      >
        {query.isError && !query.data ? (
          <ErrorState
            message={errorText(query.error)}
            onRetry={() => query.refetch()}
          />
        ) : !query.data ? (
          <Skeleton className="h-48 w-full" />
        ) : (
          <TeamForm
            key={JSON.stringify(query.data)}
            team={query.data}
            manage={manage}
            counts={counts}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function TeamForm({
  team,
  manage,
  counts,
  onClose,
}: {
  team: TeamMembers;
  manage: boolean;
  counts: Record<string, number>;
  onClose: () => void;
}) {
  const [enabled, setEnabled] = React.useState(team.enabled);
  const [numbers, setNumbers] = React.useState<Record<string, string>>(() =>
    Object.fromEntries(team.members.map((m) => [m.id, m.whatsapp])),
  );
  const [templateName, setTemplateName] = React.useState(team.template_name);
  const [templateLanguage, setTemplateLanguage] = React.useState(
    team.template_language,
  );
  const changed = team.members.some(
    (m) => (numbers[m.id] ?? "") !== m.whatsapp,
  );
  const save = useAction(
    () =>
      put<TeamMembers>("/pi/team-board/members", {
        enabled,
        numbers: Object.fromEntries(
          team.members
            .filter((m) => (numbers[m.id] ?? "") !== m.whatsapp)
            .map((m) => [m.id, numbers[m.id] ?? ""]),
        ),
        template_name: templateName.trim(),
        template_language: templateLanguage.trim(),
      }),
    { invalidate: [["team-board"]], success: "Team saved" },
  );
  const test = useAction(
    (userId: string) =>
      post<{
        delivery: "sent" | "template" | "no_window";
        business_number: string | null;
      }>(`/pi/team-board/members/${userId}/test`),
    {
      success: (r) =>
        r.delivery === "sent"
          ? "Test message sent on WhatsApp"
          : r.delivery === "template"
            ? "Test sent with your template"
            : `Their WhatsApp chat isn't open. Ask them to send "hi" to ${r.business_number ?? "your business number"} first, or add a template.`,
    },
  );
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border p-3">
        <label htmlFor="team-alerts" className="text-sm">
          <span className="block font-medium">WhatsApp alerts</span>
          <span className="text-[13px] text-muted-foreground">
            Only people with a number below get them.
          </span>
        </label>
        <Switch
          id="team-alerts"
          label="WhatsApp alerts"
          checked={enabled}
          onCheckedChange={setEnabled}
          disabled={!manage}
        />
      </div>
      <ul className="divide-y divide-border rounded-xl border border-border">
        {team.members.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-2 p-3">
            <span
              aria-hidden
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-soft-foreground"
            >
              {initials(m.name)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">
                {m.name}
              </span>
              <span className="text-[13px] text-muted-foreground">
                {counts[m.id] ?? 0} open ·{" "}
                {m.whatsapp
                  ? m.window_open
                    ? "chat open"
                    : "chat closed"
                  : "no number"}
              </span>
            </span>
            {manage ? (
              <div className="flex w-full items-center gap-2 sm:w-auto">
                <Input
                  aria-label={`${m.name}'s WhatsApp number`}
                  inputMode="tel"
                  autoComplete="off"
                  placeholder="+92 300 1234567"
                  className="h-10 min-w-0 flex-1 text-sm sm:w-48"
                  value={numbers[m.id] ?? ""}
                  onChange={(e) =>
                    setNumbers((n) => ({ ...n, [m.id]: e.target.value }))
                  }
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={!m.whatsapp || !enabled || changed}
                  loading={test.isPending && test.variables === m.id}
                  onClick={() => test.mutate(m.id)}
                >
                  Test
                </Button>
              </div>
            ) : (
              <span className="text-[13px] text-muted-foreground tabular-nums">
                {m.whatsapp
                  ? m.whatsapp === "saved"
                    ? "Saved"
                    : `+${m.whatsapp}`
                  : ""}
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="text-[13px] text-muted-foreground">
        WhatsApp lets pi write freely only to someone who messaged{" "}
        {team.business_number ?? "your business number"} in the last 24 hours.
        Otherwise pi uses your approved template, if you add one, or the person
        only gets the notification in the app.
      </p>
      {manage ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Template name" htmlFor="team-template" optional>
            <Input
              id="team-template"
              autoComplete="off"
              placeholder="task_assigned"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
            />
          </Field>
          <Field
            label="Template language"
            htmlFor="team-template-language"
            optional
            hint="Body variables: {{1}} name, {{2}} task, {{3}} due."
          >
            <Input
              id="team-template-language"
              autoComplete="off"
              placeholder="en"
              value={templateLanguage}
              onChange={(e) => setTemplateLanguage(e.target.value)}
            />
          </Field>
        </div>
      ) : null}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="secondary" onClick={onClose}>
          {manage ? "Cancel" : "Close"}
        </Button>
        {manage ? (
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        ) : null}
      </div>
    </form>
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
      className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-medium text-muted-foreground"
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
      {fetching || !updatedAt
        ? "updating…"
        : new Date(updatedAt).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
    </span>
  );
}
