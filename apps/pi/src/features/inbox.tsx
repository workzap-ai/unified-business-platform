"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  FileText,
  ArrowLeft,
  Bot,
  Check,
  CheckCheck,
  Clock,
  Hand,
  Inbox as InboxIcon,
  MessageCircleQuestion,
  PanelRight,
  Search,
  Send,
  StickyNote,
  Tag,
  UserRound,
  X,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
  LoadingBlock,
  Notice,
  Select,
  Skeleton,
  Spinner,
  Textarea,
  cn,
} from "@/components/ui";
import { del, errorText, get, post } from "@/lib/api";
import product from "@/components/product.module.css";
import { dateTime, timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan, useSession } from "@/lib/session";
import type {
  Conversation,
  History,
  Message,
  Page,
  StaffRequest,
} from "@/lib/types";

type Filter =
  | "all"
  | "mine"
  | "unassigned"
  | "unread"
  | "human"
  | "approvals"
  | "questions";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "mine", label: "Mine" },
  { key: "unassigned", label: "Unassigned" },
  { key: "unread", label: "Unread" },
  { key: "human", label: "With a person" },
  { key: "approvals", label: "To approve" },
  { key: "questions", label: "Questions" },
];

function useUrl() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const set = React.useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, router, pathname],
  );
  return [params, set] as const;
}

function useDebounced<T>(value: T, delay = 300): T {
  const [state, setState] = React.useState(value);
  React.useEffect(() => {
    const id = setTimeout(() => setState(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return state;
}

export function InboxPage() {
  const [params, setParams] = useUrl();
  const filter =
    (params.get("filter") as Filter) ||
    (params.get("mode") === "human" ? "human" : "all");
  const selected = params.get("conversation");
  const [search, setSearch] = React.useState(params.get("q") ?? "");
  const debounced = useDebounced(search);
  React.useEffect(() => {
    if ((params.get("q") ?? "") !== debounced)
      setParams({ q: debounced || null });
  }, [debounced, params, setParams]);

  return (
    <div className={cn("-mx-4 -mt-6 sm:-mx-6 md:mx-0 md:mt-0", product.inbox)}>
      <div className="grid h-[calc(100dvh-8.5rem)] grid-cols-1 overflow-hidden border-border bg-surface md:border lg:grid-cols-[22rem_1fr]">
        <section
          aria-label="Conversations"
          className={cn(
            "flex min-h-0 flex-col border-e border-border",
            selected && "hidden lg:flex",
          )}
        >
          <div className="space-y-3 border-b border-border p-3">
            <div className={product.inboxHeading}>
              <h1>Inbox</h1>
              <Link
                href="/problems"
                className="ms-auto inline-flex min-h-9 items-center rounded-full border border-border px-3 text-xs font-medium text-foreground-secondary hover:bg-surface-muted"
              >
                Problems
              </Link>
              <Link
                href="/inbox/handoffs"
                className="me-2 ms-1 inline-flex min-h-9 items-center rounded-full border border-border px-3 text-xs font-medium text-foreground-secondary hover:bg-surface-muted"
              >
                Handoffs
              </Link>
              <span>
                <InboxIcon size={17} aria-hidden />
              </span>
            </div>
            <div className="relative">
              <Search
                className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                aria-label="Search by name, phone or message"
                placeholder="Search name, phone or message"
                className="ps-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="-mx-3 overflow-x-auto px-3">
              <div
                className="flex w-max gap-1"
                role="tablist"
                aria-label="Filter conversations"
              >
                {FILTERS.map((f) => (
                  <button
                    key={f.key}
                    role="tab"
                    aria-selected={filter === f.key}
                    onClick={() =>
                      setParams({
                        filter: f.key === "all" ? null : f.key,
                        mode: null,
                      })
                    }
                    className={cn(
                      "h-9 whitespace-nowrap rounded-full border px-3 text-sm",
                      filter === f.key
                        ? "border-accent bg-accent-soft font-medium text-accent-soft-foreground"
                        : "border-border text-foreground-secondary hover:bg-surface-muted",
                    )}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {filter === "approvals" ? (
            <ApprovalList onOpen={(id) => setParams({ conversation: id })} />
          ) : filter === "questions" ? (
            <QuestionList onOpen={(id) => setParams({ conversation: id })} />
          ) : (
            <ConversationList
              filter={filter}
              search={debounced}
              selected={selected}
              onOpen={(id) => setParams({ conversation: id })}
            />
          )}
        </section>
        <section
          aria-label="Conversation"
          className={cn("min-h-0", !selected && "hidden lg:block")}
        >
          {selected ? (
            <Thread
              key={selected}
              id={selected}
              onBack={() => setParams({ conversation: null })}
            />
          ) : (
            <EmptyState
              icon={<InboxIcon className="size-6" aria-hidden />}
              title="Choose a conversation"
            >
              Messages from your customers appear here.
            </EmptyState>
          )}
        </section>
      </div>
    </div>
  );
}

function ConversationList({
  filter,
  search,
  selected,
  onOpen,
}: {
  filter: Filter;
  search: string;
  selected: string | null;
  onOpen: (id: string) => void;
}) {
  const key = useBusinessKey();
  const query = {
    search: search || undefined,
    assignment:
      filter === "mine" || filter === "unassigned" ? filter : undefined,
    unread: filter === "unread" ? true : undefined,
    mode: filter === "human" ? "human" : undefined,
    page_size: 25,
  };
  const list = useInfiniteQuery({
    queryKey: key(["conversations", query]),
    queryFn: ({ pageParam }) =>
      get<Page<Conversation>>("/pi/conversations", {
        ...query,
        page: pageParam,
      }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
    refetchInterval: 5_000, // new customer messages show up within seconds
  });
  if (list.isPending) {
    return (
      <div className="space-y-2 p-3">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  }
  if (list.isError)
    return (
      <div className="p-3">
        <ErrorState
          message={errorText(list.error)}
          onRetry={() => list.refetch()}
        />
      </div>
    );
  const items = list.data.pages.flatMap((p) => p.items);
  const total = list.data.pages[0]?.total ?? 0;
  if (!items.length) {
    return (
      <EmptyState
        icon={<InboxIcon className="size-6" aria-hidden />}
        title={search ? "No matches" : "No conversations yet"}
      >
        {search
          ? "Try a different name, number or word."
          : "When customers message your WhatsApp number, they appear here."}
      </EmptyState>
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <p className="px-3 pt-2 text-xs text-muted-foreground">
        {total} conversations
      </p>
      <ul>
        {items.map((c) => (
          <li key={c.id}>
            <button
              onClick={() => onOpen(c.id)}
              aria-current={selected === c.id ? "true" : undefined}
              className={cn(
                "flex w-full gap-3 border-b border-border px-3 py-3 text-start hover:bg-surface-muted",
                selected === c.id && "bg-accent-soft/60",
              )}
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-sm font-semibold">
                {c.customer_name.slice(0, 1).toUpperCase()}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "truncate",
                      c.unread_count ? "font-semibold" : "font-medium",
                    )}
                    data-user-text
                  >
                    {c.customer_name}
                  </span>
                  <span className="ms-auto shrink-0 text-xs text-muted-foreground">
                    {timeAgo(c.last_message_at)}
                  </span>
                </span>
                <span className="mt-0.5 flex items-center gap-2">
                  <span
                    className="truncate text-sm text-muted-foreground"
                    data-user-text
                  >
                    {c.last_message_preview || "No messages yet"}
                  </span>
                  {c.unread_count ? (
                    <span className="ms-auto flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-accent px-1.5 text-[11px] font-semibold text-accent-foreground">
                      <span className="sr-only">Unread messages: </span>
                      {c.unread_count}
                    </span>
                  ) : null}
                </span>
                <span className="mt-1 flex flex-wrap gap-1">
                  {c.mode === "human" ? (
                    <Badge tone="warning">
                      <Hand className="size-3" aria-hidden /> Person
                    </Badge>
                  ) : (
                    <Badge tone="accent">
                      <Bot className="size-3" aria-hidden /> pi
                    </Badge>
                  )}
                  {c.assigned_label ? <Badge>{c.assigned_label}</Badge> : null}
                  {c.status === "closed" ? <Badge>Closed</Badge> : null}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {list.hasNextPage ? (
        <div className="p-3">
          <Button
            variant="secondary"
            className="w-full"
            loading={list.isFetchingNextPage}
            onClick={() => list.fetchNextPage()}
          >
            Load more
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function ApprovalList({ onOpen }: { onOpen: (id: string) => void }) {
  const key = useBusinessKey();
  const approvals = useQuery({
    queryKey: key(["approvals"]),
    queryFn: () =>
      get<
        {
          message_id: string;
          conversation_id: string;
          body: string;
          created_at: string;
        }[]
      >("/pi/approvals"),
    refetchInterval: 20_000,
  });
  if (approvals.isPending)
    return (
      <div className="p-3">
        <LoadingBlock rows={2} />
      </div>
    );
  if (approvals.isError)
    return (
      <div className="p-3">
        <ErrorState
          message={errorText(approvals.error)}
          onRetry={() => approvals.refetch()}
        />
      </div>
    );
  if (!approvals.data.length) {
    return (
      <EmptyState
        icon={<Check className="size-6" aria-hidden />}
        title="Nothing to approve"
      >
        Replies pi drafts for your approval appear here.
      </EmptyState>
    );
  }
  return (
    <ul className="min-h-0 flex-1 overflow-y-auto">
      {approvals.data.map((a) => (
        <li key={a.message_id}>
          <button
            onClick={() => onOpen(a.conversation_id)}
            className="w-full border-b border-border px-3 py-3 text-start hover:bg-surface-muted"
          >
            <span className="text-xs text-muted-foreground">
              {timeAgo(a.created_at)}
            </span>
            <span className="mt-1 line-clamp-2 block text-sm" data-user-text>
              {a.body}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function QuestionList({ onOpen }: { onOpen: (id: string) => void }) {
  const key = useBusinessKey();
  const [answering, setAnswering] = React.useState<StaffRequest | null>(null);
  const questions = useQuery({
    queryKey: key(["questions"]),
    queryFn: () => get<StaffRequest[]>("/staff-requests"),
  });
  if (questions.isPending)
    return (
      <div className="p-3">
        <LoadingBlock rows={2} />
      </div>
    );
  if (questions.isError)
    return (
      <div className="p-3">
        <ErrorState
          message={errorText(questions.error)}
          onRetry={() => questions.refetch()}
        />
      </div>
    );
  if (!questions.data.length) {
    return (
      <EmptyState
        icon={<MessageCircleQuestion className="size-6" aria-hidden />}
        title="No open questions"
      >
        When pi doesn&apos;t know an answer, it asks you here.
      </EmptyState>
    );
  }
  return (
    <>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {questions.data.map((q) => (
          <li key={q.id} className="border-b border-border px-3 py-3">
            <p className="text-sm" data-user-text>
              {q.question}
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => setAnswering(q)}>
                Answer
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onOpen(q.conversation_id)}
              >
                Open chat
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <AnswerDialog request={answering} onClose={() => setAnswering(null)} />
    </>
  );
}

function AnswerDialog({
  request,
  onClose,
}: {
  request: StaffRequest | null;
  onClose: () => void;
}) {
  const [answer, setAnswer] = React.useState("");
  const [mode, setMode] = React.useState<"reply_once" | "reusable">(
    "reply_once",
  );
  const submit = useAction(
    () => post(`/staff-requests/${request?.id}/answer`, { answer, mode }),
    {
      invalidate: [["questions"], ["home"], ["conversations"]],
      success:
        mode === "reusable"
          ? "pi will reply to the customer and remember this answer"
          : "pi will reply to the customer using your answer",
      onSuccess: () => {
        setAnswer("");
        onClose();
      },
    },
  );
  return (
    <Dialog
      open={Boolean(request)}
      onOpenChange={(open) => (!open ? onClose() : null)}
    >
      <DialogContent
        title="Answer for pi"
        description={
          request?.question
            ? `${request.question} · pi writes the reply to the customer from your answer, in their language.`
            : undefined
        }
      >
        <div className="space-y-4">
          <Field label="Your answer" htmlFor="answer">
            <Textarea
              id="answer"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              maxLength={4000}
            />
          </Field>
          <fieldset className="space-y-2 text-sm">
            <legend className="mb-1 font-medium">Next time</legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="mode"
                checked={mode === "reply_once"}
                onChange={() => setMode("reply_once")}
              />
              Just reply this once
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="mode"
                checked={mode === "reusable"}
                onChange={() => setMode("reusable")}
              />
              Save it so pi can answer this itself
            </label>
          </fieldset>
          <Button
            className="w-full"
            disabled={!answer.trim()}
            loading={submit.isPending}
            onClick={() => submit.mutate(undefined)}
          >
            Send answer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function StatusIcon({ message }: { message: Message }) {
  if (message.direction !== "outbound") return null;
  const map: Record<string, [React.ReactNode, string]> = {
    queued: [<Clock key="q" className="size-3.5" aria-hidden />, "Sending"],
    processing: [<Clock key="p" className="size-3.5" aria-hidden />, "Sending"],
    sent: [<Check key="s" className="size-3.5" aria-hidden />, "Sent"],
    delivered: [
      <CheckCheck key="d" className="size-3.5" aria-hidden />,
      "Delivered",
    ],
    read: [
      <CheckCheck key="r" className="size-3.5 text-info" aria-hidden />,
      "Read",
    ],
    failed: [
      <XCircle key="f" className="size-3.5 text-danger" aria-hidden />,
      "Not delivered",
    ],
    skipped: [
      <XCircle
        key="k"
        className="size-3.5 text-muted-foreground"
        aria-hidden
      />,
      "Not sent",
    ],
    pending_approval: [
      <Hand key="a" className="size-3.5 text-warning" aria-hidden />,
      "Waiting for approval",
    ],
  };
  const [icon, label] = map[message.status] ?? [null, message.status];
  return (
    <span className="inline-flex items-center gap-1" title={label}>
      {icon}
      <span
        className={
          message.status === "failed" || message.status === "pending_approval"
            ? ""
            : "sr-only"
        }
      >
        {label}
      </span>
    </span>
  );
}

function senderLabel(message: Message): string {
  if (message.sender_type === "customer") return "Customer";
  if (message.sender_type === "ai") return "pi";
  if (message.sender_type === "human")
    return message.sent_by_label || "Your team";
  return "Notice";
}

function Thread({ id, onBack }: { id: string; onBack: () => void }) {
  const key = useBusinessKey();
  const can = useCan();
  const [panel, setPanel] = React.useState(false);
  const context = useQuery({
    queryKey: key(["context", id]),
    queryFn: () =>
      get<{
        conversation: Conversation;
        service_brief: Record<string, unknown> | null;
      }>(`/pi/conversations/${id}/context`),
    refetchInterval: 20_000,
  });
  const history = useInfiniteQuery({
    queryKey: key(["history", id]),
    queryFn: ({ pageParam }) =>
      get<History>(`/pi/conversations/${id}/history`, {
        limit: 40,
        before: pageParam?.before,
        before_id: pageParam?.before_id,
      }),
    initialPageParam: null as { before: string; before_id: string } | null,
    getNextPageParam: (last) =>
      last.has_more && last.before && last.before_id
        ? { before: last.before, before_id: last.before_id }
        : undefined,
    // Feels live: every 3 s while open, every second while a reply is still going
    // out. Polling pauses when the tab is in the background.
    refetchInterval: (query) =>
      query.state.data?.pages[0]?.items.some(
        (m) => m.status === "queued" || m.status === "processing",
      )
        ? 1_000
        : 3_000,
  });
  const markRead = useAction(
    () => post(`/pi/conversations/${id}/actions/read`),
    {
      invalidate: [["conversations"]],
      silentError: true,
    },
  );
  const conversation = context.data?.conversation;
  const unread = conversation?.unread_count ?? 0;
  React.useEffect(() => {
    if (unread > 0 && can("pi.inbox.reply")) markRead.mutate(undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, unread]);

  if (context.isPending || history.isPending)
    return (
      <div className="p-4">
        <LoadingBlock rows={4} label="Loading conversation" />
      </div>
    );
  if (context.isError)
    return (
      <div className="p-4">
        <ErrorState
          message={errorText(context.error)}
          onRetry={() => context.refetch()}
        />
      </div>
    );
  if (history.isError)
    return (
      <div className="p-4">
        <ErrorState
          message={errorText(history.error)}
          onRetry={() => history.refetch()}
        />
      </div>
    );
  const c = context.data.conversation;
  // Pages arrive newest-first; each page is oldest-first inside.
  const messages = [...history.data.pages].reverse().flatMap((p) => p.items);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[1fr_20rem]">
      <div className="flex min-h-0 flex-col">
        <header className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Back to conversations"
            onClick={onBack}
          >
            <ArrowLeft className="size-5 rtl:rotate-180" aria-hidden />
          </Button>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold" data-user-text>
              {c.customer_name}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {c.mode === "human"
                ? "A person is handling this"
                : "pi is handling this"}
              {c.assigned_label ? ` · ${c.assigned_label}` : ""}
            </p>
          </div>
          <OwnershipButtons conversation={c} />
          <Button
            variant="ghost"
            size="icon"
            className="xl:hidden"
            aria-label="Customer details"
            onClick={() => setPanel(true)}
          >
            <PanelRight className="size-5" aria-hidden />
          </Button>
        </header>
        <div
          className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-surface-muted px-3 py-4"
          aria-live="polite"
        >
          {history.hasNextPage ? (
            <div className="text-center">
              <Button
                variant="secondary"
                size="sm"
                loading={history.isFetchingNextPage}
                onClick={() => history.fetchNextPage()}
              >
                Load older messages
              </Button>
            </div>
          ) : null}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} conversationId={id} />
          ))}
          {!messages.length ? (
            <p className="text-center text-sm text-muted-foreground">
              No messages yet.
            </p>
          ) : null}
        </div>
        <Composer conversation={c} />
      </div>
      <aside
        className="hidden min-h-0 overflow-y-auto border-s border-border xl:block"
        aria-label="Customer details"
      >
        <CustomerPanel conversation={c} brief={context.data.service_brief} />
      </aside>
      <Dialog open={panel} onOpenChange={setPanel}>
        <DialogContent title="Customer details">
          <CustomerPanel conversation={c} brief={context.data.service_brief} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MessageBubble({
  message,
  conversationId,
}: {
  message: Message;
  conversationId: string;
}) {
  const can = useCan();
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(message.body);
  const approve = useAction(
    (body?: string) =>
      post(
        `/pi/conversations/${conversationId}/messages/${message.id}/approve`,
        body ? { body } : {},
      ),
    {
      invalidate: [["history", conversationId], ["approvals"], ["home"]],
      success: "Reply approved and sending",
    },
  );
  const reject = useAction(
    () =>
      post(`/pi/conversations/${conversationId}/messages/${message.id}/reject`),
    {
      invalidate: [["history", conversationId], ["approvals"], ["home"]],
      success: "Reply discarded",
    },
  );
  const inbound = message.direction === "inbound";
  const pending = message.status === "pending_approval";
  return (
    <div className={cn("flex", inbound ? "justify-start" : "justify-end")}>
      <div className="max-w-[85%] sm:max-w-[70%]">
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-[15px] shadow-sm",
            inbound
              ? "rounded-es-md bg-bubble-customer"
              : message.sender_type === "ai"
                ? "rounded-ee-md bg-bubble-pi"
                : "rounded-ee-md bg-bubble-team",
            pending && "border-2 border-dashed border-warning/60",
          )}
        >
          <p className="mb-0.5 text-xs font-medium text-muted-foreground">
            {senderLabel(message)}
          </p>
          {editing ? (
            <Textarea
              aria-label="Edit reply"
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={4000}
            />
          ) : (
            <>
              {message.card && (
                <a href={message.card.image} target="_blank" rel="noreferrer">
                  {/* eslint-disable-next-line @next/next/no-img-element -- signed external card */}
                  <img
                    src={message.card.image}
                    alt={
                      message.card.kind === "map"
                        ? "Problem map sent on WhatsApp"
                        : "Journey card sent on WhatsApp"
                    }
                    loading="lazy"
                    className="mb-1.5 block w-full max-w-[260px] rounded-xl border border-border"
                  />
                </a>
              )}
              {message.media?.file_kind === "document" &&
                typeof message.media.file_id === "string" && (
                  <a
                    href={`/api/v1/pi-app/customer-files/${message.media.file_id}/download`}
                    className="mb-1.5 flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5 text-sm font-medium text-primary hover:underline"
                  >
                    <FileText className="size-4 shrink-0" aria-hidden />
                    <span className="min-w-0 truncate">
                      {String(message.media.filename || "Document")}
                    </span>
                  </a>
                )}
              <p className="whitespace-pre-line" data-user-text>
                {message.body ||
                  (message.message_type !== "text"
                    ? `[${message.message_type}]`
                    : "")}
              </p>
            </>
          )}
          <p className="mt-1 flex items-center justify-end gap-1.5 text-[11px] text-muted-foreground">
            {dateTime(message.created_at)} <StatusIcon message={message} />
          </p>
        </div>
        {pending && can("pi.inbox.reply") ? (
          <div className="mt-2 flex flex-wrap justify-end gap-2">
            {editing ? (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(false);
                    setText(message.body);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  loading={approve.isPending}
                  disabled={!text.trim()}
                  onClick={() => approve.mutate(text)}
                >
                  Send edited reply
                </Button>
              </>
            ) : (
              <>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={reject.isPending}
                  onClick={() => reject.mutate(undefined)}
                >
                  Discard
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
                <Button
                  size="sm"
                  loading={approve.isPending}
                  onClick={() => approve.mutate(undefined)}
                >
                  Approve and send
                </Button>
              </>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function OwnershipButtons({ conversation }: { conversation: Conversation }) {
  const can = useCan();
  const takeover = useAction(
    () => post(`/pi/conversations/${conversation.id}/actions/takeover`),
    {
      invalidate: [["context", conversation.id], ["conversations"]],
      success: "You're handling this conversation. pi won't reply.",
    },
  );
  const resume = useAction(
    () => post(`/pi/conversations/${conversation.id}/actions/return-to-ai`),
    {
      invalidate: [["context", conversation.id], ["conversations"]],
      success: "pi is handling this conversation again",
    },
  );
  if (!can("pi.inbox.reply") || conversation.status !== "open") return null;
  return conversation.mode === "ai" ? (
    <Button
      size="sm"
      variant="secondary"
      loading={takeover.isPending}
      onClick={() => takeover.mutate(undefined)}
    >
      <Hand className="size-4" aria-hidden /> Take over
    </Button>
  ) : (
    <Button
      size="sm"
      variant="secondary"
      loading={resume.isPending}
      onClick={() => resume.mutate(undefined)}
    >
      <Bot className="size-4" aria-hidden /> Hand back to pi
    </Button>
  );
}

function Composer({ conversation }: { conversation: Conversation }) {
  const can = useCan();
  const key = useBusinessKey();
  const [text, setText] = React.useState("");
  const saved = useQuery({
    queryKey: key(["saved-replies"]),
    queryFn: () =>
      get<{ id: string; title: string; body: string }[]>("/pi/saved-replies"),
    enabled: can("pi.inbox.reply"),
    staleTime: 300_000,
  });
  const send = useAction(
    () => post(`/pi/conversations/${conversation.id}/messages`, { body: text }),
    {
      invalidate: [["history", conversation.id], ["conversations"]],
      onSuccess: () => setText(""),
    },
  );
  if (!can("pi.inbox.reply")) {
    return (
      <p className="border-t border-border px-4 py-3 text-sm text-muted-foreground">
        You can view this conversation but not reply.
      </p>
    );
  }
  if (conversation.status !== "open") {
    return (
      <p className="border-t border-border px-4 py-3 text-sm text-muted-foreground">
        This conversation is closed.
      </p>
    );
  }
  if (conversation.mode !== "human") {
    return (
      <p className="border-t border-border px-4 py-3 text-sm text-muted-foreground">
        pi is replying here. Take over to write to the customer yourself.
      </p>
    );
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) send.mutate(undefined);
      }}
      className="space-y-2 border-t border-border p-3"
    >
      {saved.data?.length ? (
        <Select
          aria-label="Insert a saved reply"
          value=""
          onChange={(e) => {
            const r = saved.data?.find((x) => x.id === e.target.value);
            if (r) setText(r.body);
          }}
          className="h-9 text-sm"
        >
          <option value="">Saved replies…</option>
          {saved.data.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
            </option>
          ))}
        </Select>
      ) : null}
      <div className="flex items-end gap-2">
        <label htmlFor="reply" className="sr-only">
          Reply to customer
        </label>
        <Textarea
          id="reply"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Write a reply…"
          rows={2}
          className="min-h-11 flex-1 resize-none"
          maxLength={4000}
        />
        <Button
          type="submit"
          size="icon"
          aria-label="Send reply"
          loading={send.isPending}
          disabled={!text.trim()}
        >
          {send.isPending ? null : <Send className="size-4" aria-hidden />}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        WhatsApp only allows free-text replies within 24 hours of the
        customer&apos;s last message.
      </p>
    </form>
  );
}

const PROJECT_STATUS: Record<string, string> = {
  collecting: "collecting details",
  awaiting_confirmation: "waiting for their yes",
  confirmed: "confirmed",
  with_team: "with the team",
};

function CustomerPanel({
  conversation,
  brief,
}: {
  conversation: Conversation;
  brief: Record<string, unknown> | null;
}) {
  const key = useBusinessKey();
  const can = useCan();
  const { data: session } = useSession();
  const [note, setNote] = React.useState("");
  const [tag, setTag] = React.useState("");
  const notes = useQuery({
    queryKey: key(["notes", conversation.id]),
    queryFn: () =>
      get<{ id: string; body: string; author: string; created_at: string }[]>(
        `/pi/conversations/${conversation.id}/notes`,
      ),
    enabled: can("pi.inbox.notes"),
  });
  const tags = useQuery({
    queryKey: key(["tags", conversation.id]),
    queryFn: () => get<string[]>(`/pi/conversations/${conversation.id}/tags`),
  });
  const team = useQuery({
    queryKey: key(["team"]),
    queryFn: () =>
      get<{
        members: {
          membership_id: string;
          user_id: string;
          display_name: string;
          status: string;
        }[];
      }>("/team"),
    enabled: can("pi.inbox.assign") && can("admin.members.read"),
  });
  const addNote = useAction(
    () => post(`/pi/conversations/${conversation.id}/notes`, { body: note }),
    {
      invalidate: [["notes", conversation.id]],
      onSuccess: () => setNote(""),
    },
  );
  const addTag = useAction(
    () => post(`/pi/conversations/${conversation.id}/tags`, { tag }),
    {
      invalidate: [["tags", conversation.id]],
      onSuccess: () => setTag(""),
    },
  );
  const removeTag = useAction(
    (value: string) =>
      del(
        `/pi/conversations/${conversation.id}/tags/${encodeURIComponent(value)}`,
      ),
    {
      invalidate: [["tags", conversation.id]],
    },
  );
  const assign = useAction(
    (userId: string | null) =>
      post(`/pi/conversations/${conversation.id}/assign`, { user_id: userId }),
    {
      invalidate: [["context", conversation.id], ["conversations"]],
      success: "Assignment updated",
    },
  );
  const requirements = (brief?.requirements ?? {}) as Record<string, string>;
  const filled = Object.entries(requirements).filter(([, v]) => v);
  const projects = Array.isArray(brief?.projects)
    ? (brief.projects as {
        title: string;
        details?: string;
        status?: string;
        missing?: string[];
      }[])
    : [];
  return (
    <div className="space-y-6 p-4">
      <div>
        <p className="font-semibold" data-user-text>
          {conversation.customer_name}
        </p>
        {conversation.customer_phone ? (
          <p className="text-sm text-muted-foreground">
            {conversation.customer_phone}
          </p>
        ) : null}
        <Link
          href={`/customers/${conversation.customer_id}`}
          className="mt-1 inline-flex items-center gap-1 text-sm text-accent underline"
        >
          <UserRound className="size-4" aria-hidden /> Full profile
        </Link>
      </div>
      {conversation.summary ? (
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Summary
          </h3>
          <p className="whitespace-pre-line text-sm" data-user-text>
            {conversation.summary}
          </p>
        </section>
      ) : null}
      {projects.length ? (
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Projects in this chat ({projects.length})
          </h3>
          <ul className="space-y-2 text-sm">
            {projects.map((p) => (
              <li key={p.title}>
                <p className="font-medium" data-user-text>
                  {p.title}{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    · {PROJECT_STATUS[p.status ?? ""] ?? "In progress"}
                  </span>
                </p>
                {p.details ? (
                  <p className="text-muted-foreground" data-user-text>
                    {p.details}
                  </p>
                ) : null}
                {p.missing?.length ? (
                  <p className="text-xs">
                    Still needed: {p.missing.join(", ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
          {brief?.meeting_requested ? (
            <p className="mt-2 text-xs font-medium text-accent">
              The customer asked for a meeting.
            </p>
          ) : null}
        </section>
      ) : null}
      {filled.length ? (
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            What they need
          </h3>
          <dl className="space-y-1 text-sm">
            {filled.map(([k, v]) => (
              <div key={k}>
                <dt className="text-muted-foreground">
                  {k.replaceAll("_", " ")}
                </dt>
                <dd data-user-text>{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-1 text-xs text-muted-foreground">
            Budgets and dates are what the customer said, not a commitment.
          </p>
        </section>
      ) : null}
      {can("pi.inbox.assign") ? (
        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Assigned to
          </h3>
          {team.data ? (
            <Select
              aria-label="Assign conversation"
              value=""
              onChange={(e) =>
                assign.mutate(e.target.value === "none" ? null : e.target.value)
              }
            >
              <option value="" disabled>
                {conversation.assigned_label ?? "Nobody yet"} — change
              </option>
              <option value="none">Nobody</option>
              {team.data.members
                .filter((m) => m.status === "active")
                .map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.user_id === session?.user.id
                      ? `${m.display_name} (me)`
                      : m.display_name}
                  </option>
                ))}
            </Select>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              loading={assign.isPending}
              onClick={() => assign.mutate(session?.user.id ?? null)}
            >
              Assign to me
            </Button>
          )}
        </section>
      ) : null}
      <section>
        <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Tag className="size-3.5" aria-hidden /> Tags
        </h3>
        <div className="flex flex-wrap gap-1">
          {(tags.data ?? []).map((t) => (
            <Badge key={t}>
              {t}
              {can("pi.inbox.reply") ? (
                <button
                  aria-label={`Remove tag ${t}`}
                  onClick={() => removeTag.mutate(t)}
                  className="ms-0.5"
                >
                  <X className="size-3" aria-hidden />
                </button>
              ) : null}
            </Badge>
          ))}
          {!tags.data?.length ? (
            <span className="text-sm text-muted-foreground">No tags</span>
          ) : null}
        </div>
        {can("pi.inbox.reply") ? (
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (tag.trim()) addTag.mutate(undefined);
            }}
          >
            <Input
              aria-label="New tag"
              placeholder="Add a tag"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              maxLength={40}
              className="h-9"
            />
            <Button
              size="sm"
              variant="secondary"
              type="submit"
              disabled={!tag.trim()}
            >
              Add
            </Button>
          </form>
        ) : null}
      </section>
      {can("pi.inbox.notes") ? (
        <section>
          <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <StickyNote className="size-3.5" aria-hidden /> Team notes
          </h3>
          <p className="mb-2 text-xs text-muted-foreground">
            Only your team sees these.
          </p>
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (note.trim()) addNote.mutate(undefined);
            }}
          >
            <Textarea
              aria-label="New note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              maxLength={4000}
            />
            <Button
              size="sm"
              variant="secondary"
              type="submit"
              disabled={!note.trim()}
              loading={addNote.isPending}
            >
              Add note
            </Button>
          </form>
          <ul className="mt-3 space-y-2">
            {notes.isPending ? <Spinner /> : null}
            {(notes.data ?? []).map((n) => (
              <li
                key={n.id}
                className="rounded-md bg-surface-muted p-2 text-sm"
              >
                <p className="whitespace-pre-line" data-user-text>
                  {n.body}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {n.author} · {timeAgo(n.created_at)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {conversation.mode === "human" && conversation.handoff_status ? (
        <Notice tone="info">
          pi handed this to your team. Hand it back when you&apos;re done.
        </Notice>
      ) : null}
    </div>
  );
}
