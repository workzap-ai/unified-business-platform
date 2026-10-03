"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  AudioLines,
  CircleCheck,
  ClipboardList,
  ImageIcon,
  MessageCircle,
  Play,
  Sparkles,
  UserRound,
  Video,
} from "lucide-react";

import { errorText } from "@/lib/api";
import {
  customerFile,
  customerGet,
  customerPost,
  type CustomerConversationDetail,
  type CustomerIssues,
  type CustomerMessage,
} from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import {
  Badge,
  Button,
  Card,
  ErrorState,
  Skeleton,
  Spinner,
} from "@/components/ui";
import {
  Avatar,
  CATEGORY,
  Formatted,
  STATUS,
  ago,
  clock,
  dayLabel,
} from "./shared";

export function ConversationView({ id }: { id: string }) {
  const client = useQueryClient();
  const [tab, setTab] = useState<"chat" | "requests">("chat");
  const detail = useQuery({
    queryKey: ["pi-customer", "conversation", id],
    queryFn: () =>
      customerGet<CustomerConversationDetail>(`/conversations/${id}`),
    refetchInterval: 10_000,
  });
  const team = useMutation({
    mutationFn: () => customerPost(`/conversations/${id}/team`),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["pi-customer"] }),
  });

  if (detail.isPending)
    return (
      <div
        className="mx-auto w-full max-w-6xl space-y-4"
        role="status"
        aria-label="Loading"
      >
        <Skeleton className="h-20 w-full rounded-2xl" />
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Skeleton className="h-[60vh] rounded-2xl" />
          <Skeleton className="hidden h-80 rounded-2xl lg:block" />
        </div>
      </div>
    );
  if (detail.isError)
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <BackLink />
        <ErrorState
          message={errorText(detail.error)}
          onRetry={() => detail.refetch()}
        />
      </div>
    );

  const c = detail.data;
  const withTeam = c.with_team || team.isSuccess;
  return (
    <div className="mx-auto w-full max-w-6xl space-y-5">
      <BackLink />
      <Card className="p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-4">
          <Avatar name={c.business} size="lg" />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold sm:text-2xl">
              {c.business}
            </h1>
            <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
              <span>{c.business_phone}</span>
              <span aria-hidden>·</span>
              <span className="inline-flex items-center gap-1.5">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
                  <span className="relative inline-flex size-2 rounded-full bg-success" />
                </span>
                Live · last message {ago(c.last_message_at)}
              </span>
            </p>
          </div>
          <div className="flex w-full flex-wrap gap-2 sm:w-auto">
            {c.whatsapp_link && (
              <Button asChild className="flex-1 sm:flex-none">
                <a href={c.whatsapp_link} target="_blank" rel="noreferrer">
                  <MessageCircle className="size-4" aria-hidden />
                  Continue on WhatsApp
                </a>
              </Button>
            )}
            {withTeam ? (
              <span className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-info-soft px-3.5 py-2 text-sm font-medium text-info sm:flex-none">
                <UserRound className="size-4" aria-hidden />A person from the
                team will reply
              </span>
            ) : (
              <Button
                variant="secondary"
                className="flex-1 sm:flex-none"
                loading={team.isPending}
                onClick={() => team.mutate()}
              >
                <UserRound className="size-4" aria-hidden />
                Talk to a person
              </Button>
            )}
          </div>
        </div>
        {team.isError && (
          <div className="mt-3">
            <ErrorState message={errorText(team.error)} />
          </div>
        )}
      </Card>

      <div
        className="grid grid-cols-2 gap-1 rounded-xl bg-surface-muted p-1 lg:hidden"
        role="tablist"
        aria-label="Conversation sections"
      >
        {(
          [
            ["chat", "Chat", MessageCircle],
            ["requests", "Requests", ClipboardList],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium",
              tab === key
                ? "bg-surface text-foreground shadow-sm"
                : "text-muted-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className={cn(tab !== "chat" && "hidden lg:block")}>
          <Chat
            messages={c.messages}
            conversationId={id}
            business={c.business}
          />
        </div>
        <div
          className={cn(
            "lg:sticky lg:top-6",
            tab !== "requests" && "hidden lg:block",
          )}
        >
          <Requests detail={c} />
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/customer"
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" aria-hidden />
      All conversations
    </Link>
  );
}

/* ----------------------------------------------------------------- chat */

const SENDER: Record<CustomerMessage["from"], string> = {
  you: "You",
  assistant: "Pi assistant",
  team: "Team",
  business: "",
};

function Chat({
  messages,
  conversationId,
  business,
}: {
  messages: CustomerMessage[];
  conversationId: string;
  business: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const last = messages.at(-1)?.id;
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [last]);
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
        <h2 className="font-semibold">Conversation</h2>
        <span className="text-xs text-muted-foreground">
          {messages.length} {messages.length === 1 ? "message" : "messages"}
        </span>
      </div>
      <div
        ref={scroller}
        className="max-h-[68vh] min-h-72 overflow-y-auto bg-surface-muted/40 px-3 py-4 sm:px-5"
      >
        {messages.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No messages yet.
          </p>
        ) : (
          <ol className="space-y-2.5" aria-label="Messages">
            {messages.map((m, i) => {
              const prev = messages[i - 1];
              const newDay =
                !prev ||
                new Date(prev.at).toDateString() !==
                  new Date(m.at).toDateString();
              const grouped = prev && prev.from === m.from && !newDay;
              return (
                <Fragment key={m.id}>
                  {newDay && (
                    <li className="flex justify-center py-2" role="separator">
                      <span className="rounded-full bg-surface px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
                        {dayLabel(m.at)}
                      </span>
                    </li>
                  )}
                  <Bubble
                    message={m}
                    conversationId={conversationId}
                    business={business}
                    grouped={Boolean(grouped)}
                  />
                </Fragment>
              );
            })}
          </ol>
        )}
      </div>
    </Card>
  );
}

function Bubble({
  message,
  conversationId,
  business,
  grouped,
}: {
  message: CustomerMessage;
  conversationId: string;
  business: string;
  grouped: boolean;
}) {
  const mine = message.from === "you";
  if (message.from === "business" && !message.has_media)
    return (
      <li className="flex justify-center py-1">
        <p className="max-w-[90%] rounded-xl bg-surface px-3 py-1.5 text-center text-xs text-muted-foreground shadow-sm">
          {message.body}
        </p>
      </li>
    );
  return (
    <li
      className={cn(
        "flex",
        mine ? "justify-end" : "justify-start",
        grouped && "-mt-1",
      )}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-[15px] shadow-sm sm:max-w-[75%]",
          mine
            ? "rounded-br-md bg-accent text-accent-foreground"
            : "rounded-bl-md bg-surface text-foreground",
        )}
      >
        {!mine && !grouped && (
          <p
            className={cn(
              "mb-0.5 flex items-center gap-1 text-xs font-semibold",
              message.from === "assistant" ? "text-accent" : "text-info",
            )}
          >
            {message.from === "assistant" && (
              <Sparkles className="size-3" aria-hidden />
            )}
            {SENDER[message.from] || business}
          </p>
        )}
        {message.has_media && (
          <MediaPart
            message={message}
            conversationId={conversationId}
            mine={mine}
          />
        )}
        {message.body && <Formatted text={message.body} />}
        <p className="mt-1 text-right text-[11px] opacity-70">
          {clock(message.at)}
        </p>
      </div>
    </li>
  );
}

function MediaPart({
  message,
  conversationId,
  mine,
}: {
  message: CustomerMessage;
  conversationId: string;
  mine: boolean;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "failed">("idle");
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  async function load() {
    setState("loading");
    try {
      const blob = await customerFile(
        `/conversations/${conversationId}/messages/${message.id}/media`,
      );
      setUrl(URL.createObjectURL(blob));
      setState("idle");
    } catch {
      setState("failed");
    }
  }
  const kind = message.type;
  const Icon =
    kind === "audio" ? AudioLines : kind === "video" ? Video : ImageIcon;
  const label =
    kind === "audio" ? "Voice note" : kind === "video" ? "Video" : "Photo";
  return (
    <div className="mb-1.5 space-y-1.5">
      {url ? (
        kind === "audio" ? (
          <audio controls autoPlay src={url} className="h-10 w-64 max-w-full" />
        ) : kind === "video" ? (
          <video controls src={url} className="max-h-72 w-full rounded-xl" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- a private blob URL
          <img
            src={url}
            alt="Your photo"
            className="max-h-72 w-full rounded-xl object-contain"
          />
        )
      ) : (
        <button
          type="button"
          onClick={load}
          disabled={state === "loading"}
          className={cn(
            "flex w-60 max-w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm",
            mine ? "bg-accent-foreground/15" : "bg-surface-muted",
          )}
        >
          <span
            className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-full",
              mine ? "bg-accent-foreground/20" : "bg-surface",
            )}
          >
            {state === "loading" ? (
              <Spinner label="" />
            ) : (
              <Play className="size-4" aria-hidden />
            )}
          </span>
          <span className="flex-1">
            <span className="flex items-center gap-1.5 font-medium">
              <Icon className="size-4" aria-hidden />
              {label}
            </span>
            <span className="text-xs opacity-75">
              {state === "failed" ? "No longer available" : "Tap to open"}
            </span>
          </span>
        </button>
      )}
      {message.transcript && (
        <p className="text-[13px] italic opacity-85">“{message.transcript}”</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- requests */

function Requests({ detail }: { detail: CustomerConversationDetail }) {
  const issues = useQuery({
    queryKey: ["pi-customer", "issues", detail.id, detail.last_message_at],
    queryFn: () =>
      customerGet<CustomerIssues>(`/conversations/${detail.id}/issues`),
    initialData: detail.issues
      ? { available: true, at: detail.issues.at, issues: detail.issues.issues }
      : undefined,
    staleTime: Infinity,
  });
  const list = issues.data?.issues ?? [];
  const done = list.filter((i) => i.status === "resolved").length;
  const pct = list.length ? Math.round((done / list.length) * 100) : 0;

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">Your requests</h2>
            <Badge tone="accent">
              <Sparkles className="size-3" aria-hidden />
              Organised by Pi
            </Badge>
          </div>
          {list.length > 0 && (
            <div className="mt-3">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>
                  {done} of {list.length} sorted
                </span>
                <span className="tabular-nums">{pct}%</span>
              </div>
              <div
                className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-muted"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Requests sorted"
              >
                <div
                  className="h-full rounded-full bg-success transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}
        </div>
        <div className="p-4">
          {issues.isPending ? (
            <div className="space-y-3 py-2">
              <Spinner label="Pi is reading your conversation…" />
              <Skeleton className="h-20 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
            </div>
          ) : issues.isError || !issues.data?.available ? (
            <p className="py-3 text-sm text-muted-foreground">
              Pi can&apos;t organise your requests right now. Your full
              conversation is still here.
            </p>
          ) : list.length === 0 ? (
            <p className="py-3 text-sm text-muted-foreground">
              No requests in this conversation yet.
            </p>
          ) : (
            <ul className="space-y-3">
              {list.map((issue, i) => {
                const category = CATEGORY[issue.category];
                const status = STATUS[issue.status];
                const Icon = category.icon;
                return (
                  <li
                    key={i}
                    className={cn(
                      "rounded-xl border border-border border-l-4 bg-surface p-3.5",
                      status.bar,
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                        <Icon className="size-3.5" aria-hidden />
                        {category.label}
                      </span>
                      <Badge tone={status.tone}>
                        {issue.status === "resolved" && (
                          <CircleCheck className="size-3" aria-hidden />
                        )}
                        {status.label}
                      </Badge>
                    </div>
                    <p className="mt-1.5 font-semibold leading-snug">
                      {issue.title}
                    </p>
                    {issue.summary && (
                      <p className="mt-1 text-sm text-foreground-secondary">
                        {issue.summary}
                      </p>
                    )}
                    {issue.next_step && issue.status !== "resolved" && (
                      <p className="mt-2 rounded-lg bg-surface-muted px-3 py-2 text-[13px]">
                        <span className="font-medium">Next: </span>
                        {issue.next_step}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>

      {detail.requests.length > 0 && (
        <Card>
          <div className="border-b border-border px-5 py-3.5">
            <h2 className="font-semibold">Opened by the team</h2>
          </div>
          <ul className="divide-y divide-border">
            {detail.requests.map((r, i) => (
              <li
                key={i}
                className="flex items-start justify-between gap-3 px-5 py-3 text-sm"
              >
                <span className="min-w-0">
                  <span className="block font-medium">{r.title}</span>
                  {r.note && (
                    <span className="block text-xs text-muted-foreground">
                      {r.note}
                    </span>
                  )}
                  <span className="block text-xs text-muted-foreground">
                    {ago(r.at)}
                  </span>
                </span>
                <Badge tone={r.status === "resolved" ? "success" : "info"}>
                  {r.status === "resolved" ? "Done" : "With the team"}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
