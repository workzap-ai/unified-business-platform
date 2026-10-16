"use client";

/**
 * A customer's Activity, made readable as in Owner OS: entries grouped by day (newest
 * first), a proposal's or order's status changes in a row merged into one plain line
 * ("Proposal QUO-000008 accepted", with drafted → approved → sent → accepted
 * underneath and every original entry one tap away), repeated lines folded, and
 * "Requirement captured" read as "New request". Nothing is hidden. Older entries load
 * page by page. GET /customers/{id}/activities.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import {
  Button,
  Card,
  CardSection,
  ErrorState,
  LoadingBlock,
} from "@/components/ui";
import { errorText, get } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useBusinessKey } from "@/lib/session";

type Activity = {
  id: string;
  kind: string;
  summary: string;
  ref_type: string | null;
  ref_id: string | null;
  actor_label: string;
  created_at: string;
};

type Page = {
  items: Activity[];
  total: number;
  page: number;
  page_size: number;
};

const QUOTE_WORD: Record<string, string> = {
  draft: "drafted",
  pending_approval: "waiting for approval",
  approved: "approved",
  sent: "sent",
  accepted: "accepted",
  rejected: "not accepted",
  expired: "expired",
  cancelled: "cancelled",
};
const ORDER_WORD: Record<string, string> = {
  draft: "drafted",
  confirmed: "confirmed",
  processing: "work started",
  shipped: "shipped",
  delivered: "delivered",
  cancelled: "cancelled",
};
const TRANSITION = /^(Quote|Order) (\S+): (\w+) → (\w+)$/;
const DRAFTED = /^(?:Quote (\S+) drafted|Draft order (\S+))$/;

type Step = {
  doc: "Quote" | "Order";
  number: string;
  from?: string;
  to: string;
};

/** A quote/order status line, read as data (null for anything else). */
function statusStep(a: Activity): Step | null {
  const moved = TRANSITION.exec(a.summary);
  if (moved)
    return {
      doc: moved[1] as Step["doc"],
      number: moved[2],
      from: moved[3],
      to: moved[4],
    };
  const drafted = DRAFTED.exec(a.summary);
  if (drafted)
    return drafted[1]
      ? { doc: "Quote", number: drafted[1], to: "draft" }
      : { doc: "Order", number: drafted[2], to: "draft" };
  return null;
}

function word(doc: Step["doc"], status: string): string {
  return (
    (doc === "Quote" ? QUOTE_WORD : ORDER_WORD)[status] ??
    status.replace(/_/g, " ")
  );
}

/** Plain words for one entry ("Order SO-1 work started", "New request: Logo"). */
function plainSummary(a: Activity): string {
  const step = statusStep(a);
  if (step) {
    const what = step.doc === "Quote" ? "Proposal" : "Order";
    return `${what} ${step.number} ${word(step.doc, step.to)}`;
  }
  return a.summary.replace(/^Requirement captured: /, "New request: ");
}

/** The calendar day of an entry in the viewer's time zone. */
function dayKey(at: string): string {
  const d = new Date(at);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

type Line = { id: string; entries: Activity[] };

/** Consecutive entries that read as one line: the same quote's or order's status
 * changes on one day, or the very same summary repeated. */
function mergeLines(items: Activity[]): Line[] {
  const lines: Line[] = [];
  for (const item of items) {
    const last = lines.at(-1);
    const prev = last?.entries.at(-1);
    if (last && prev && dayKey(prev.created_at) === dayKey(item.created_at)) {
      const a = statusStep(prev);
      const b = statusStep(item);
      const sameDoc = a && b && a.doc === b.doc && a.number === b.number;
      if (sameDoc || prev.summary === item.summary) {
        last.entries.push(item);
        continue;
      }
    }
    lines.push({ id: item.id, entries: [item] });
  }
  return lines;
}

/** drafted → approved → sent → accepted (oldest first). */
function statusPath(entries: Activity[]): string[] {
  const path: string[] = [];
  let doc: Step["doc"] = "Quote";
  for (const entry of [...entries].reverse()) {
    const step = statusStep(entry);
    if (!step) continue;
    doc = step.doc;
    if (!path.length && step.from) path.push(step.from);
    if (path.at(-1) !== step.to) path.push(step.to);
  }
  return path.map((status) => word(doc, status));
}

function dayLabel(at: string): string {
  const d = new Date(at);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(at) === dayKey(today.toISOString())) return "Today";
  if (dayKey(at) === dayKey(yesterday.toISOString())) return "Yesterday";
  return d.toLocaleDateString("en", {
    day: "numeric",
    month: "short",
    ...(d.getFullYear() === today.getFullYear() ? {} : { year: "numeric" }),
  });
}

function groupByDay(lines: Line[]) {
  const days: { day: string; label: string; lines: Line[] }[] = [];
  for (const line of lines) {
    const at = line.entries[0].created_at;
    const day = dayKey(at);
    const last = days.at(-1);
    if (last && last.day === day) last.lines.push(line);
    else days.push({ day, label: dayLabel(at), lines: [line] });
  }
  return days;
}

/** Where an entry leads in the pi app (a deal or a chat); null when nowhere. */
function refHref(a: Activity): string | null {
  if (!a.ref_id) return null;
  if (a.ref_type === "lead") return `/deals/${a.ref_id}`;
  if (a.ref_type === "conversation")
    return `/inbox?conversation=${encodeURIComponent(a.ref_id)}`;
  return null;
}

const DOT: Record<string, string> = {
  note: "bg-info",
  status: "bg-accent",
  document: "bg-warning",
  conversation: "bg-success",
};

export function CustomerActivity({ id }: { id: string }) {
  const key = useBusinessKey();
  const query = useInfiniteQuery({
    queryKey: key(["customer-activity", id]),
    queryFn: ({ pageParam }) =>
      get<Page>(`/customers/${id}/activities`, {
        page: pageParam,
        page_size: 25,
      }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  });
  const pages = query.data?.pages;
  const days = useMemo(() => {
    if (!pages) return undefined;
    // A new entry can shift offset pages: never show one twice.
    const seen = new Set<string>();
    const items = pages
      .flatMap((p) => p.items)
      .filter((a) => !seen.has(a.id) && seen.add(a.id));
    return groupByDay(mergeLines(items));
  }, [pages]);
  const total = pages?.at(-1)?.total ?? 0;
  const shown = pages?.reduce((n, p) => n + p.items.length, 0) ?? 0;

  return (
    <Card>
      <CardSection className="space-y-4">
        <div className="flex items-center gap-2">
          <History className="size-5 text-accent" aria-hidden />
          <div className="min-w-0">
            <h2 className="font-semibold">Activity</h2>
            <p className="text-xs text-muted-foreground">
              Changes, notes, documents and conversations for this customer
            </p>
          </div>
        </div>
        {query.isPending ? (
          <LoadingBlock rows={3} label="Loading activity" />
        ) : query.isError ? (
          <ErrorState
            message={errorText(query.error)}
            onRetry={() => query.refetch()}
          />
        ) : !days?.length ? (
          <p className="text-sm text-muted-foreground">
            No activity recorded for this customer yet.
          </p>
        ) : (
          <div className="space-y-4">
            {days.map((group) => (
              <section key={group.day} aria-label={group.label}>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {group.label}
                </h3>
                <ol className="space-y-2.5">
                  {group.lines.map((line) => (
                    <ActivityLine key={line.id} line={line} />
                  ))}
                </ol>
              </section>
            ))}
            {query.hasNextPage ? (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                <span className="text-xs text-muted-foreground">
                  {shown} of {total} entries
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={query.isFetchingNextPage}
                  onClick={() => void query.fetchNextPage()}
                >
                  Show older
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </CardSection>
    </Card>
  );
}

function ActivityLine({ line }: { line: Line }) {
  const newest = line.entries[0];
  const title = plainSummary(newest);
  const href = refHref(newest);
  const path =
    line.entries.length > 1 && statusStep(newest)
      ? statusPath(line.entries)
      : [];
  const actors = [...new Set(line.entries.map((e) => e.actor_label))];
  return (
    <li className="flex gap-3">
      <span
        className={`mt-1.5 size-2 shrink-0 rounded-full ${DOT[newest.kind] ?? "bg-border-strong"}`}
        aria-hidden
      />
      <div className="min-w-0 flex-1 text-sm">
        <p className="break-words font-medium" data-user-text>
          {href ? (
            <Link href={href} className="hover:underline">
              {title}
            </Link>
          ) : (
            title
          )}
        </p>
        {path.length > 1 ? (
          <p className="text-xs text-muted-foreground">{path.join(" → ")}</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          {actors.join(", ")} ·{" "}
          <time dateTime={newest.created_at}>
            {dateTime(newest.created_at)}
          </time>
        </p>
        {line.entries.length > 1 ? (
          <details className="mt-0.5 text-xs">
            <summary className="cursor-pointer select-none py-1 text-accent">
              {path.length > 1
                ? `${line.entries.length} changes`
                : `${line.entries.length} times`}
            </summary>
            <ul className="mt-1 space-y-0.5 text-muted-foreground">
              {line.entries.map((entry) => (
                <li key={entry.id} className="flex flex-wrap gap-x-2">
                  <span className="text-foreground-secondary" data-user-text>
                    {entry.summary}
                  </span>
                  <time dateTime={entry.created_at}>
                    {dateTime(entry.created_at)}
                  </time>
                  <span>{entry.actor_label}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </li>
  );
}
