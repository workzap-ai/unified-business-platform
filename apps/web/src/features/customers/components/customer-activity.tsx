"use client";

import { useMemo } from "react";
import Link from "next/link";
import { isToday, isYesterday, isThisYear } from "date-fns";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/display";
import { ActivityTimeline, type TimelineEvent } from "@/components/app/record";
import { ErrorState } from "@/components/app/states";
import { useScopedInfiniteQuery } from "@/hooks/use-scoped";
import { formatDate, formatDateTime } from "@/lib/format";
import type { CustomerActivity } from "@/features/business/types";
import { customersService } from "../service";
import { activityToEvent, refHref } from "../lib";

/**
 * The customer's Activity tab, made readable: entries grouped by day (newest first),
 * a quote's or order's status changes in a row merged into one plain line ("Proposal
 * QUO-000008 accepted", with drafted → approved → sent → accepted underneath and every
 * original entry one tap away), repeated lines folded, and "Requirement captured"
 * read as "New request". Nothing is hidden. Older entries load page by page.
 */

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
export function statusStep(a: CustomerActivity): Step | null {
  const moved = TRANSITION.exec(a.summary);
  if (moved)
    return {
      doc: moved[1] as Step["doc"],
      number: moved[2]!,
      from: moved[3],
      to: moved[4]!,
    };
  const drafted = DRAFTED.exec(a.summary);
  if (drafted)
    return drafted[1]
      ? { doc: "Quote", number: drafted[1], to: "draft" }
      : { doc: "Order", number: drafted[2]!, to: "draft" };
  return null;
}

function word(doc: Step["doc"], status: string): string {
  return (
    (doc === "Quote" ? QUOTE_WORD : ORDER_WORD)[status] ??
    status.replace(/_/g, " ")
  );
}

/** Plain words for one entry ("Order SO-1: work started", "New request: Logo"). */
export function plainSummary(a: CustomerActivity): string {
  const step = statusStep(a);
  if (step) {
    const what = step.doc === "Quote" ? "Proposal" : "Order";
    return `${what} ${step.number} ${word(step.doc, step.to)}`;
  }
  return a.summary.replace(/^Requirement captured: /, "New request: ");
}

export type ActivityLine = {
  id: string;
  /** Newest first, like the list. */
  entries: CustomerActivity[];
};

function dayKey(at: string): string {
  return formatDate(at, "yyyy-MM-dd");
}

/** Consecutive entries that read as one line: the same quote's or order's status
 * changes on one day, or the very same summary repeated. */
export function mergeLines(items: CustomerActivity[]): ActivityLine[] {
  const lines: ActivityLine[] = [];
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
export function statusPath(entries: CustomerActivity[]): string[] {
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

function lineEvent(line: ActivityLine): TimelineEvent {
  const newest = line.entries[0]!;
  const base = activityToEvent(newest);
  const title = plainSummary(newest);
  if (line.entries.length === 1) return { ...base, title };
  const path = statusStep(newest) ? statusPath(line.entries) : [];
  const href = refHref(newest.ref_type, newest.ref_id);
  const actors = [...new Set(line.entries.map((e) => e.actor_label))];
  return {
    ...base,
    href: undefined,
    actor: actors.join(", "),
    title: href ? (
      <Link href={href} className="hover:underline">
        {title}
      </Link>
    ) : (
      title
    ),
    description: (
      <>
        {path.length > 1 && <span className="block">{path.join(" → ")}</span>}
        <details className="mt-0.5 text-xs">
          <summary className="cursor-pointer text-primary select-none">
            {path.length > 1
              ? `${line.entries.length} changes`
              : `${line.entries.length} times`}
          </summary>
          <ul className="mt-1 space-y-0.5">
            {line.entries.map((entry) => (
              <li key={entry.id} className="flex flex-wrap gap-x-2">
                <span className="text-foreground-secondary">
                  {entry.summary}
                </span>
                <time dateTime={entry.created_at}>
                  {formatDateTime(entry.created_at)}
                </time>
                <span>{entry.actor_label}</span>
              </li>
            ))}
          </ul>
        </details>
      </>
    ),
  };
}

function dayLabel(at: string): string {
  const date = new Date(at);
  if (isToday(date)) return "Today";
  if (isYesterday(date)) return "Yesterday";
  return formatDate(at, isThisYear(date) ? "d MMM" : "d MMM yyyy");
}

export function groupByDay(
  lines: ActivityLine[],
): { day: string; label: string; lines: ActivityLine[] }[] {
  const days: { day: string; label: string; lines: ActivityLine[] }[] = [];
  for (const line of lines) {
    const at = line.entries[0]!.created_at;
    const day = dayKey(at);
    const last = days.at(-1);
    if (last && last.day === day) last.lines.push(line);
    else days.push({ day, label: dayLabel(at), lines: [line] });
  }
  return days;
}

export function CustomerActivityTab({ customerId }: { customerId: string }) {
  const activities = useScopedInfiniteQuery(
    ["customers", "activities", customerId],
    (page: number) => customersService.activities(customerId, page),
    {
      initialPageParam: 1,
      getNextPageParam: (last) =>
        last.page * last.page_size < last.total ? last.page + 1 : undefined,
    },
  );
  const pages = activities.data?.pages;
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

  return (
    <Card className="max-w-3xl">
      <CardHeader
        title="Activity"
        description="Changes, notes, documents and conversations for this customer"
      />
      <CardBody>
        {activities.isError ? (
          <ErrorState
            error={activities.error}
            onRetry={() => void activities.refetch()}
            compact
          />
        ) : !days?.length ? (
          <ActivityTimeline
            events={days ? [] : undefined}
            loading={activities.isPending}
            empty="No activity recorded for this customer yet."
          />
        ) : (
          <div className="space-y-4">
            {days.map((group) => (
              <section key={group.day} aria-label={group.label}>
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {group.label}
                </h3>
                <ActivityTimeline events={group.lines.map(lineEvent)} />
              </section>
            ))}
            {activities.hasNextPage && (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                <span className="text-xs text-muted-foreground">
                  {pages!.reduce((n, p) => n + p.items.length, 0)} of {total}{" "}
                  entries
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={activities.isFetchingNextPage}
                  onClick={() => void activities.fetchNextPage()}
                >
                  {activities.isFetchingNextPage ? "Loading…" : "Show older"}
                </Button>
              </div>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
