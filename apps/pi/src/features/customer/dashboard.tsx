"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Inbox, LogOut, Search } from "lucide-react";

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
  { key: "all", label: "All chats" },
  { key: "open", label: "In progress" },
  { key: "team", label: "With the team" },
  { key: "sorted", label: "Sorted" },
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

      <RequestsOverview items={items} businesses={businesses} />

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
                Your chats appear here when you message a business that uses pi
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
              <h2 className="font-semibold">Open requests by department</h2>
              <Badge tone={openRequests.length ? "warning" : "success"}>
                {openRequests.length || "None"}
              </Badge>
            </div>
            {openRequests.length === 0 ? (
              <p className="px-5 py-6 text-sm text-muted-foreground">
                Nothing waiting. Open a conversation to see what pi found in it.
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
                            {r.department_name
                              ? `${r.department_name} · ${r.conversation.business}`
                              : r.conversation.business}
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
            pi organises your requests when you open a conversation, and keeps
            them up to date as you chat.
          </p>
        </aside>
      </div>
    </div>
  );
}

/** Every request the customer raised, by where it stands: one bar, three parts. */
function RequestsOverview({
  items,
  businesses,
}: {
  items: CustomerConversationItem[];
  businesses: number;
}) {
  const totals = items.reduce(
    (t, c) => ({
      open: t.open + (c.issues_by_status?.open ?? 0),
      with_team: t.with_team + (c.issues_by_status?.with_team ?? 0),
      resolved: t.resolved + (c.issues_by_status?.resolved ?? 0),
    }),
    { open: 0, with_team: 0, resolved: 0 },
  );
  const total = totals.open + totals.with_team + totals.resolved;
  const parts = [
    {
      key: "open",
      label: "In progress",
      value: totals.open,
      bar: "bg-warning",
    },
    {
      key: "with_team",
      label: "With the team",
      value: totals.with_team,
      bar: "bg-info",
    },
    {
      key: "resolved",
      label: "Sorted",
      value: totals.resolved,
      bar: "bg-success",
    },
  ] as const;
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-semibold">Your requests</h2>
          <p className="text-xs text-muted-foreground">
            {total
              ? `${total} ${total === 1 ? "request" : "requests"} with ${businesses} ${businesses === 1 ? "business" : "businesses"}`
              : "Open a chat and pi lists what you asked for here."}
          </p>
        </div>
        {total > 0 && (
          <p className="text-sm font-medium">
            {Math.round((totals.resolved / total) * 100)}% sorted
          </p>
        )}
      </div>
      <div
        className="mt-3 flex h-3 overflow-hidden rounded-full bg-surface-muted"
        role="img"
        aria-label={parts.map((p) => `${p.label}: ${p.value}`).join(", ")}
      >
        {total > 0 &&
          parts.map((p) =>
            p.value ? (
              <span
                key={p.key}
                className={cn("h-full", p.bar)}
                style={{ width: `${(p.value / total) * 100}%` }}
              />
            ) : null,
          )}
      </div>
      <ul className="mt-3 grid grid-cols-3 gap-2">
        {parts.map((p) => (
          <li
            key={p.key}
            className="min-w-0 rounded-xl bg-surface-muted/60 px-2 py-2.5 text-center sm:px-3 sm:text-left"
          >
            <span className="block text-xl font-semibold tabular-nums">
              {p.value}
            </span>
            <span className="flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground sm:justify-start sm:text-xs">
              <span
                className={cn("size-2 shrink-0 rounded-full", p.bar)}
                aria-hidden
              />
              <span className="truncate">{p.label}</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
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
                  {i.department_name && (
                    <span className="shrink-0 text-muted-foreground">
                      · {i.department_name}
                    </span>
                  )}
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
