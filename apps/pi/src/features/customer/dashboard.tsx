"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  ChevronRight,
  CircleCheck,
  Inbox,
  ListChecks,
  LogOut,
  Search,
  UserRound,
} from "lucide-react";

import { errorText } from "@/lib/api";
import {
  customerGet,
  customerPost,
  type CustomerConversationItem,
  type CustomerMe,
} from "@/lib/customer-api";
import { cn } from "@/lib/cn";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { Avatar, CATEGORY, LIST, ME, STATUS, ago } from "./shared";

type Filter = "all" | "open" | "team" | "sorted";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "open", label: "Open requests" },
  { key: "team", label: "With a team" },
  { key: "sorted", label: "All sorted" },
];

function matches(c: CustomerConversationItem, filter: Filter) {
  if (filter === "open") return c.issues_open > 0;
  if (filter === "team") return c.with_team;
  if (filter === "sorted") return c.issues_total > 0 && c.issues_open === 0;
  return true;
}

export function Dashboard({ me }: { me: CustomerMe }) {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const list = useQuery({
    queryKey: LIST,
    queryFn: () => customerGet<CustomerConversationItem[]>("/conversations"),
    refetchInterval: 20_000,
  });
  const signOut = useMutation({
    mutationFn: () => customerPost("/sign-out"),
    onSettled: () => {
      client.setQueryData(ME, null);
      client.removeQueries({ queryKey: ["pi-customer"] });
    },
  });

  const items = useMemo(() => list.data ?? [], [list.data]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(
      (c) =>
        matches(c, filter) &&
        (!q ||
          c.business.toLowerCase().includes(q) ||
          c.preview.toLowerCase().includes(q) ||
          c.issues_preview.some((i) => i.title.toLowerCase().includes(q))),
    );
  }, [items, query, filter]);
  const openRequests = items.flatMap((c) =>
    c.issues_preview
      .filter((i) => i.status !== "resolved")
      .map((i) => ({ ...i, conversation: c })),
  );
  const businesses = new Set(items.map((c) => c.business)).size;
  const sorted = items.reduce(
    (n, c) => n + (c.issues_total - c.issues_open),
    0,
  );

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-muted-foreground">
            Signed in as <span className="font-medium">{me.phone}</span>
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Your conversations
          </h1>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="min-h-11 shrink-0 sm:min-h-10"
          aria-label="Sign out"
          onClick={() => signOut.mutate()}
          loading={signOut.isPending}
        >
          <LogOut className="size-4" aria-hidden />
          <span className="hidden sm:inline">Sign out</span>
        </Button>
      </header>

      <div className="grid grid-cols-4 gap-2 sm:gap-3">
        <Stat
          icon={Building2}
          label="Businesses"
          value={businesses}
          tone="accent"
        />
        <Stat
          icon={ListChecks}
          label="Open requests"
          value={openRequests.length}
          tone="warning"
        />
        <Stat
          icon={UserRound}
          label="With a team"
          value={items.filter((c) => c.with_team).length}
          tone="info"
        />
        <Stat icon={CircleCheck} label="Sorted" value={sorted} tone="success" />
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section aria-label="Conversations" className="min-w-0 space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative flex-1">
              <span className="sr-only">Search conversations</span>
              <Search
                className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search businesses or requests"
                className="h-12 w-full rounded-xl border border-border-strong bg-surface pl-10 pr-3.5 text-base placeholder:text-muted-foreground/70 focus-visible:outline-2 focus-visible:outline-ring sm:h-11 sm:text-[15px]"
              />
            </label>
          </div>
          <div
            className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden"
            role="tablist"
            aria-label="Filter conversations"
          >
            {FILTERS.map((f) => {
              const count = items.filter((c) => matches(c, f.key)).length;
              return (
                <button
                  key={f.key}
                  type="button"
                  role="tab"
                  aria-selected={filter === f.key}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    "inline-flex min-h-10 shrink-0 snap-start items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors sm:min-h-9",
                    filter === f.key
                      ? "border-accent bg-accent text-accent-foreground"
                      : "border-border bg-surface text-foreground-secondary hover:bg-surface-muted",
                  )}
                >
                  {f.label}
                  <span
                    className={cn(
                      "rounded-full px-1.5 text-xs tabular-nums",
                      filter === f.key
                        ? "bg-accent-foreground/20"
                        : "bg-surface-muted",
                    )}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {list.isPending ? (
            <div className="space-y-3" role="status" aria-label="Loading">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-28 w-full rounded-2xl" />
              ))}
            </div>
          ) : list.isError ? (
            <ErrorState
              message={errorText(list.error)}
              onRetry={() => list.refetch()}
            />
          ) : items.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Inbox className="size-6" aria-hidden />}
                title="No conversations yet"
              >
                Your chats appear here when you message a business that uses Pi
                on WhatsApp.
              </EmptyState>
            </Card>
          ) : shown.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Search className="size-6" aria-hidden />}
                title="Nothing matches"
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setQuery("");
                      setFilter("all");
                    }}
                  >
                    Show everything
                  </Button>
                }
              >
                Try another search or filter.
              </EmptyState>
            </Card>
          ) : (
            <ul className="space-y-3">
              {shown.map((c) => (
                <li key={c.id}>
                  <ConversationCard c={c} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="space-y-4 lg:sticky lg:top-6">
          <Card>
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="font-semibold">Open requests</h2>
              <Badge tone={openRequests.length ? "warning" : "success"}>
                {openRequests.length || "None"}
              </Badge>
            </div>
            {openRequests.length === 0 ? (
              <p className="px-5 py-6 text-sm text-muted-foreground">
                Nothing waiting. Open a conversation to see what Pi found in it.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {openRequests.slice(0, 8).map((r, i) => {
                  const Icon = CATEGORY[r.category].icon;
                  return (
                    <li key={i}>
                      <Link
                        href={`/customer/c/${r.conversation.id}`}
                        className="flex min-h-14 items-start gap-3 px-4 py-3.5 hover:bg-surface-muted active:bg-surface-muted sm:px-5"
                      >
                        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-foreground-secondary">
                          <Icon className="size-4" aria-hidden />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">
                            {r.title}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {r.conversation.business}
                          </span>
                        </span>
                        <span className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                          <span
                            className={cn(
                              "size-2 rounded-full",
                              STATUS[r.status].dot,
                            )}
                            aria-hidden
                          />
                          {STATUS[r.status].label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <p className="hidden px-1 text-xs text-muted-foreground sm:block">
            Pi organises your requests when you open a conversation, and keeps
            them up to date as you chat.
          </p>
        </aside>
      </div>
    </div>
  );
}

const STAT_TONES = {
  accent: "bg-accent-soft text-accent-soft-foreground",
  warning: "bg-warning-soft text-warning",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
};

function Stat({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Inbox;
  label: string;
  value: number;
  tone: keyof typeof STAT_TONES;
}) {
  return (
    <div className="flex min-w-0 flex-col items-center gap-1.5 rounded-2xl border border-border bg-surface px-1.5 py-3 text-center shadow-sm sm:flex-row sm:gap-3 sm:p-4 sm:text-left">
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-lg sm:size-10 sm:rounded-xl",
          STAT_TONES[tone],
        )}
      >
        <Icon className="size-4 sm:size-5" aria-hidden />
      </span>
      <span className="min-w-0">
        <span className="block text-xl font-semibold leading-none tabular-nums sm:text-2xl">
          {value}
        </span>
        <span className="mt-1 block text-[11px] leading-tight text-muted-foreground sm:text-xs">
          {label}
        </span>
      </span>
    </div>
  );
}

function ConversationCard({ c }: { c: CustomerConversationItem }) {
  return (
    <Link
      href={`/customer/c/${c.id}`}
      className="group block rounded-2xl border border-border bg-surface p-4 shadow-sm transition-all hover:border-accent/40 hover:shadow-md focus-visible:outline-2 focus-visible:outline-ring active:scale-[0.99] active:bg-surface-muted/60 sm:p-5 sm:hover:-translate-y-0.5"
    >
      <div className="flex items-start gap-3 sm:gap-4">
        <Avatar name={c.business} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <p className="truncate text-[15px] font-semibold">{c.business}</p>
            <span className="shrink-0 text-xs text-muted-foreground">
              {ago(c.last_message_at)}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
            {c.preview || "Conversation"}
          </p>
          {c.issues_preview.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {c.issues_preview.map((i, n) => (
                <li
                  key={n}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface-muted/60 px-2.5 py-1 text-xs"
                >
                  <span
                    className={cn(
                      "size-1.5 shrink-0 rounded-full",
                      STATUS[i.status].dot,
                    )}
                    aria-hidden
                  />
                  <span className="truncate">{i.title}</span>
                  <span className="sr-only">({STATUS[i.status].label})</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {c.with_team && <Badge tone="info">With the team</Badge>}
            {c.issues_open > 0 && (
              <Badge tone="warning">
                {c.issues_open} open{" "}
                {c.issues_open === 1 ? "request" : "requests"}
              </Badge>
            )}
            {c.issues_total > 0 && c.issues_open === 0 && (
              <Badge tone="success">All sorted</Badge>
            )}
            {c.status === "closed" && <Badge>Closed</Badge>}
            <span className="ml-auto hidden items-center gap-1 text-xs font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100 sm:inline-flex">
              Open
              <ChevronRight className="size-3.5" aria-hidden />
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
