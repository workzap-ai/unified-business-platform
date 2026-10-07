"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  AudioLines,
  CircleCheck,
  ClipboardList,
  Hourglass,
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
  type CustomerIssue,
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
  STAGE,
  TURN,
  ago,
  clock,
  dayLabel,
  journeyPercent,
  nextStepLine,
  shortDay,
  turnOf,
  useLang,
  usePrefs,
} from "./shared";
import { ActivityTimeline, SolutionFlow, type TimelineEvent } from "./visuals";

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
  const openRequests = (c.issues?.issues ?? []).filter(
    (i) => turnOf(i) === "you",
  ).length;
  const whatsapp = c.whatsapp_link ? (
    <Button asChild className="min-h-12 flex-1 sm:min-h-10 sm:flex-none">
      <a href={c.whatsapp_link} target="_blank" rel="noreferrer">
        <MessageCircle className="size-4" aria-hidden />
        <span className="sm:hidden">WhatsApp</span>
        <span className="hidden sm:inline">Continue on WhatsApp</span>
      </a>
    </Button>
  ) : null;
  const person = withTeam ? (
    <span className="inline-flex min-h-12 flex-1 items-center justify-center gap-1.5 rounded-xl bg-info-soft px-3 text-sm font-medium text-info sm:min-h-10 sm:flex-none">
      <UserRound className="size-4 shrink-0" aria-hidden />
      <span className="sm:hidden">Team will reply</span>
      <span className="hidden sm:inline">
        A person from the team will reply
      </span>
    </span>
  ) : (
    <Button
      variant="secondary"
      className="min-h-12 flex-1 sm:min-h-10 sm:flex-none"
      loading={team.isPending}
      onClick={() => team.mutate()}
    >
      <UserRound className="size-4" aria-hidden />
      Talk to a person
    </Button>
  );

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 pb-28 sm:space-y-5 sm:pb-0">
      <BackLink />
      <Card className="p-4 sm:p-5">
        <div className="flex items-center gap-3 sm:gap-4">
          <span className="sm:hidden">
            <Avatar name={c.business} />
          </span>
          <span className="hidden sm:block">
            <Avatar name={c.business} size="lg" />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-semibold sm:text-2xl">
              {c.business}
            </h1>
            <p className="truncate text-sm text-muted-foreground">
              {c.business_phone}
            </p>
            <p className="mt-0.5 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
                <span className="relative inline-flex size-2 rounded-full bg-success" />
              </span>
              Live · last message {ago(c.last_message_at)}
            </p>
          </div>
          <div className="hidden shrink-0 gap-2 sm:flex">
            {whatsapp}
            {person}
          </div>
        </div>
        {team.isError && (
          <div className="mt-3">
            <ErrorState message={errorText(team.error)} />
          </div>
        )}
      </Card>

      <div className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-20 -mx-4 bg-background/95 px-4 py-2 backdrop-blur sm:top-[calc(4rem+env(safe-area-inset-top))] sm:mx-0 sm:px-0 lg:hidden">
        <div
          className="grid grid-cols-2 gap-1 rounded-xl bg-surface-muted p-1"
          role="tablist"
          aria-label="Conversation sections"
        >
          {(
            [
              ["chat", "Chat", MessageCircle, c.messages.length],
              ["requests", "Requests", ClipboardList, openRequests],
            ] as const
          ).map(([key, label, Icon, count]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => {
                setTab(key);
                if (key === "requests") window.scrollTo({ top: 0 });
              }}
              className={cn(
                "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors",
                tab === key
                  ? "bg-surface text-foreground shadow-sm"
                  : "text-muted-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
              {count > 0 && (
                <span
                  className={cn(
                    "rounded-full px-1.5 text-xs tabular-nums",
                    key === "requests"
                      ? "bg-warning-soft text-warning"
                      : "bg-surface-muted",
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className={cn("min-w-0", tab !== "chat" && "hidden lg:block")}>
          <Chat
            messages={c.messages}
            conversationId={id}
            business={c.business}
          />
        </div>
        <div
          className={cn(
            "min-w-0 lg:sticky lg:top-24",
            tab !== "requests" && "hidden lg:block",
          )}
        >
          <Requests detail={c} />
        </div>
      </div>

      {/* Phones: the two actions stay in reach of the thumb. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:hidden">
        <div className="flex gap-2">
          {whatsapp}
          {person}
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
  assistant: "pi assistant",
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
  const first = useRef(true);
  const last = messages.at(-1)?.id;
  useEffect(() => {
    const el = scroller.current;
    if (el && getComputedStyle(el).overflowY === "auto") {
      // Desktop: the chat scrolls inside its card.
      el.scrollTop = el.scrollHeight;
    } else {
      // Phones: the page scrolls. Open at the latest message, and follow new ones
      // only if the reader is already near the end.
      const page = document.documentElement;
      const nearEnd =
        window.innerHeight + window.scrollY >= page.scrollHeight - 240;
      if (first.current || nearEnd) window.scrollTo({ top: page.scrollHeight });
    }
    first.current = false;
  }, [last]);
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-5 sm:py-3.5">
        <h2 className="font-semibold">Conversation</h2>
        <span className="text-xs text-muted-foreground">
          {messages.length} {messages.length === 1 ? "message" : "messages"}
        </span>
      </div>
      <div
        ref={scroller}
        className="min-h-48 bg-surface-muted/40 px-3 py-4 sm:px-5 lg:max-h-[68vh] lg:min-h-72 lg:overflow-y-auto"
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

const STEPS = {
  en: [
    "Noted",
    "Understood",
    "Linked",
    "Solution ready",
    "Your decision",
    "Building",
    "Live",
  ],
  ur: [
    "Note hua",
    "Samjha gaya",
    "Juda hua",
    "Hal tayyar",
    "Aap ka faisla",
    "Ban raha",
    "Mukammal",
  ],
};

/** Seven fixed steps: done ones ticked, the current one coloured by whose turn it is. */
function JourneySteps({
  issue,
  lang,
}: {
  issue: CustomerIssue;
  lang: "en" | "ur";
}) {
  const done = issue.journey_steps;
  if (done === null) return null;
  const turn = turnOf(issue);
  const current = Math.min(done + 1, 7);
  const currentLabel = STEPS[lang][current - 1];
  return (
    <div className="mt-3">
      <ol
        className="flex items-center gap-1"
        aria-label={`${done} of 7 steps done. Now: ${currentLabel}`}
      >
        {STEPS[lang].map((label, i) => {
          const step = i + 1;
          const isDone = step <= done;
          const isNow = step === current && done < 7;
          return (
            <li key={label} className="flex flex-1 items-center gap-1">
              <span
                title={label}
                className={cn(
                  "flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold",
                  isDone && "border-accent bg-accent text-accent-foreground",
                  isNow &&
                    cn(
                      "size-6 ring-2 ring-offset-1 ring-offset-surface",
                      turn === "you"
                        ? "border-warning bg-warning text-foreground ring-warning/40"
                        : turn === "other"
                          ? "border-border-strong bg-surface-muted ring-border"
                          : "border-info bg-info text-white ring-info/40",
                    ),
                  !isDone &&
                    !isNow &&
                    "border-border bg-surface text-muted-foreground",
                )}
              >
                {isDone ? <CircleCheck className="size-3" aria-hidden /> : step}
              </span>
              {step < 7 && (
                <span
                  className={cn(
                    "h-0.5 flex-1 rounded-full",
                    step < done + 1 ? "bg-accent" : "bg-border",
                  )}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-1.5 text-xs text-muted-foreground">
        {done < 7
          ? `${lang === "ur" ? "Ab" : "Now"}: ${currentLabel} · ${TURN[turn][lang]}`
          : STEPS[lang][6]}
      </p>
    </div>
  );
}

function Requests({ detail }: { detail: CustomerConversationDetail }) {
  const client = useQueryClient();
  const lang = useLang();
  const issues = useQuery({
    queryKey: ["pi-customer", "issues", detail.id, detail.last_message_at],
    queryFn: () =>
      customerGet<CustomerIssues>(`/conversations/${detail.id}/issues`),
    initialData: detail.issues
      ? { available: true, at: detail.issues.at, issues: detail.issues.issues }
      : undefined,
    staleTime: Infinity,
  });
  const waiting = useMutation({
    mutationFn: (days: number) =>
      customerPost(`/conversations/${detail.id}/waiting`, { days }),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ["pi-customer"] }),
  });
  const list = issues.data?.issues ?? [];
  const links = issues.data?.links ?? detail.issues?.links ?? [];
  const prefs = usePrefs();
  const activity = useQuery({
    queryKey: ["pi-customer", "timeline", detail.id, detail.last_message_at],
    queryFn: () =>
      customerGet<TimelineEvent[]>(`/conversations/${detail.id}/timeline`),
  });
  const pct = journeyPercent(list);
  const yours = list.some((i) => i.ball_with === "client");
  const pausedUntil = detail.waiting_on_other_until;
  const paused = Boolean(pausedUntil && new Date(pausedUntil) > new Date());

  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="border-b border-border px-4 py-4 sm:px-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">
              {lang === "ur" ? "Aap ke requests" : "Your requests"}
            </h2>
            <Badge tone="accent">
              <Sparkles className="size-3" aria-hidden />
              {lang === "ur" ? "pi ne tarteeb di" : "Organised by pi"}
            </Badge>
          </div>
          {pct !== null && (
            <div className="mt-3">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>
                  {lang === "ur"
                    ? `${list.length} requests ka safar`
                    : `Journey across ${list.length} ${list.length === 1 ? "request" : "requests"}`}
                </span>
                <span className="tabular-nums">{pct}%</span>
              </div>
              <div
                className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-muted"
                role="progressbar"
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Journey progress"
              >
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}
          {(yours || paused) && (
            <div className="mt-3 rounded-xl bg-surface-muted/70 p-3 text-sm">
              {paused ? (
                <>
                  <p>
                    {lang === "ur"
                      ? `Aap kisi aur ka intezar kar rahe hain. ${shortDay(pausedUntil as string)} tak reminders band hain.`
                      : `You're waiting on someone else. No reminders until ${shortDay(pausedUntil as string)}.`}
                  </p>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="mt-2"
                    loading={waiting.isPending}
                    onClick={() => waiting.mutate(0)}
                  >
                    {lang === "ur"
                      ? "Main wapas aa gaya"
                      : "I'm ready to continue"}
                  </Button>
                </>
              ) : (
                <>
                  <p className="text-muted-foreground">
                    {lang === "ur"
                      ? "Boss, partner ya accountant ka intezar hai? pi 5 din reminder nahi bhejega."
                      : "Waiting on your boss, a partner or accountant? pi won't remind you for 5 days."}
                  </p>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="mt-2"
                    loading={waiting.isPending}
                    onClick={() => waiting.mutate(5)}
                  >
                    <Hourglass className="size-4" aria-hidden />
                    {lang === "ur"
                      ? "Kisi aur ka intezar hai"
                      : "I'm waiting on someone else"}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
        <div className="p-4">
          {issues.isPending ? (
            <div className="space-y-3 py-2">
              <Spinner label="pi is reading your conversation…" />
              <Skeleton className="h-20 w-full rounded-xl" />
              <Skeleton className="h-20 w-full rounded-xl" />
            </div>
          ) : issues.isError || !issues.data?.available ? (
            <p className="py-3 text-sm text-muted-foreground">
              pi can&apos;t organise your requests right now. Your full
              conversation is still here.
            </p>
          ) : list.length === 0 ? (
            <p className="py-3 text-sm text-muted-foreground">
              {lang === "ur"
                ? "Is chat mein abhi koi request nahi."
                : "No requests in this conversation yet."}
            </p>
          ) : (
            <ul className="space-y-3">
              {list.map((issue, i) => {
                const category = CATEGORY[issue.category];
                const stage = STAGE[issue.stage];
                const turn = turnOf(issue);
                const next = nextStepLine(issue, lang);
                const Icon = category.icon;
                return (
                  <li
                    key={i}
                    className={cn(
                      "rounded-xl border border-border border-l-4 bg-surface p-3.5",
                      stage.bar,
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex min-w-0 items-center gap-1.5 text-xs font-medium text-muted-foreground">
                        <Icon className="size-3.5 shrink-0" aria-hidden />
                        {category.label}
                        {issue.department_name && (
                          <span className="truncate">
                            · {issue.department_name}
                          </span>
                        )}
                      </span>
                      <Badge tone={stage.tone}>
                        <span
                          className={cn("size-2 rounded-full", stage.dot)}
                          aria-hidden
                        />
                        {stage[lang]}
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
                    {issue.original_words && (
                      <p className="mt-1.5 text-xs italic text-muted-foreground">
                        {lang === "ur" ? "Aap ke alfaaz: " : "Your words: "}“
                        {issue.original_words}”
                      </p>
                    )}
                    <JourneySteps issue={issue} lang={lang} />
                    <details className="group mt-2">
                      <summary className="cursor-pointer list-none text-xs font-medium text-accent">
                        {lang === "ur"
                          ? "Hum ise kaise hal karenge"
                          : "How we'd solve it"}
                      </summary>
                      <div className="mt-2">
                        <SolutionFlow
                          issue={issue}
                          issues={list}
                          links={links}
                          lang={lang}
                        />
                      </div>
                    </details>
                    {next && turn !== "done" && (
                      <p
                        className={cn(
                          "mt-2 rounded-lg px-3 py-2 text-[13px]",
                          turn === "you"
                            ? "bg-warning-soft/60"
                            : "bg-surface-muted",
                        )}
                      >
                        <span className="font-medium">
                          {turn === "you"
                            ? lang === "ur"
                              ? "Aap: "
                              : "You: "
                            : lang === "ur"
                              ? "Agla qadam: "
                              : "Next: "}
                        </span>
                        {next}
                        {issue.overdue && (
                          <span className="ml-1 font-medium text-danger">
                            {lang === "ur" ? "(der ho gayi)" : "(overdue)"}
                          </span>
                        )}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>

      <Card className="p-4 sm:p-5">
        <h2 className="mb-1 font-semibold">
          {lang === "ur" ? "Kya hua · naya pehle" : "Activity · newest first"}
        </h2>
        {activity.isPending ? (
          <Skeleton className="h-24 w-full rounded-xl" />
        ) : (
          <ActivityTimeline
            events={activity.data ?? []}
            lang={lang}
            lastSeen={prefs.data?.last_seen_at}
          />
        )}
      </Card>

      {detail.requests.length > 0 && (
        <Card>
          <div className="border-b border-border px-4 py-3.5 sm:px-5">
            <h2 className="font-semibold">
              {lang === "ur" ? "Team ne khola" : "Opened by the team"}
            </h2>
          </div>
          <ul className="divide-y divide-border">
            {detail.requests.map((r, i) => (
              <li
                key={i}
                className="flex items-start justify-between gap-3 px-4 py-3 text-sm sm:px-5"
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
                  {r.status === "resolved" ? TURN.done[lang] : TURN.us[lang]}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
