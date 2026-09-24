"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRightLeft,
  Bot,
  CircleDot,
  CreditCard,
  FilePlus2,
  MessageSquare,
  Pencil,
  ShoppingCart,
  StickyNote,
  UserCheck,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDateTime, relativeTime } from "@/lib/format";
import { Avatar, Card, CardHeader, Skeleton } from "@/components/ui/display";
import { Tooltip } from "@/components/ui/overlays";

export function RecordHeader({
  title,
  subtitle,
  status,
  identifier,
  avatar,
  icon: Icon,
  meta,
  actions,
  loading = false,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  status?: React.ReactNode;
  identifier?: React.ReactNode;
  avatar?: string;
  icon?: LucideIcon;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="mb-5 flex items-center gap-3">
        <Skeleton className="size-12 rounded-xl" />
        <div className="space-y-2">
          <Skeleton className="h-5 w-56" />
          <Skeleton className="h-3.5 w-36" />
        </div>
      </div>
    );
  }
  return (
    <header className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="flex min-w-0 items-start gap-3.5">
        {avatar ? (
          <Avatar
            name={avatar}
            size="xl"
            square
            className="size-12 text-base"
          />
        ) : Icon ? (
          <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-border bg-surface-muted text-muted-foreground">
            <Icon className="size-5.5" aria-hidden="true" />
          </div>
        ) : null}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="min-w-0 truncate text-xl font-semibold tracking-tight">
              {title}
            </h1>
            {status}
            {identifier && (
              <span className="rounded-md bg-surface-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                {identifier}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="mt-0.5 text-[13.5px] text-muted-foreground">
              {subtitle}
            </p>
          )}
          {meta && (
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
              {meta}
            </div>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      )}
    </header>
  );
}

export function PropertyList({
  items,
  className,
  columns = 1,
}: {
  items: { label: string; value: React.ReactNode; hint?: string }[];
  className?: string;
  columns?: 1 | 2;
}) {
  return (
    <dl
      className={cn(
        "grid gap-x-6",
        columns === 2 ? "sm:grid-cols-2" : "",
        className,
      )}
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-start justify-between gap-4 border-b border-border py-2.5 last:border-0 sm:[&:nth-last-child(2)]:border-0"
        >
          <dt className="shrink-0 text-[13px] text-muted-foreground">
            {item.hint ? (
              <Tooltip content={item.hint}>
                <span className="cursor-help underline decoration-dotted underline-offset-2">
                  {item.label}
                </span>
              </Tooltip>
            ) : (
              item.label
            )}
          </dt>
          <dd className="min-w-0 text-right text-[13px] font-medium break-words">
            {item.value ?? <span className="text-muted-foreground">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export type TimelineEvent = {
  id: string;
  kind: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actor?: string;
  at: string;
  href?: string;
};

const EVENT_ICONS: Record<string, { icon: LucideIcon; className: string }> = {
  created: { icon: FilePlus2, className: "bg-primary-soft text-primary" },
  updated: {
    icon: Pencil,
    className: "bg-surface-muted text-muted-foreground",
  },
  note: { icon: StickyNote, className: "bg-warning-soft text-warning" },
  order: { icon: ShoppingCart, className: "bg-info-soft text-info" },
  quote: { icon: FilePlus2, className: "bg-info-soft text-info" },
  invoice: {
    icon: CreditCard,
    className: "bg-surface-muted text-foreground-secondary",
  },
  payment: { icon: CreditCard, className: "bg-success-soft text-success" },
  conversation: { icon: MessageSquare, className: "bg-pi-soft text-pi" },
  handoff: { icon: UserCheck, className: "bg-warning-soft text-warning" },
  ai: { icon: Bot, className: "bg-pi-soft text-pi" },
  status: {
    icon: ArrowRightLeft,
    className: "bg-surface-muted text-foreground-secondary",
  },
  lead: { icon: Zap, className: "bg-primary-soft text-primary" },
  system: {
    icon: CircleDot,
    className: "bg-surface-muted text-muted-foreground",
  },
};

export function ActivityTimeline({
  events,
  loading = false,
  empty = "No activity yet.",
  className,
}: {
  events: TimelineEvent[] | undefined;
  loading?: boolean;
  empty?: React.ReactNode;
  className?: string;
}) {
  if (loading || !events) {
    return (
      <ul className={cn("space-y-4", className)}>
        {Array.from({ length: 4 }, (_, i) => (
          <li key={i} className="flex gap-3">
            <Skeleton className="size-7 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </li>
        ))}
      </ul>
    );
  }
  if (!events.length)
    return (
      <p
        className={cn(
          "py-6 text-center text-[13px] text-muted-foreground",
          className,
        )}
      >
        {empty}
      </p>
    );
  return (
    <ol className={cn("relative", className)}>
      {events.map((event, index) => {
        const style = EVENT_ICONS[event.kind] ?? EVENT_ICONS.system!;
        const Icon = style.icon;
        const content = (
          <>
            <p className="text-[13px] leading-snug font-medium">
              {event.title}
            </p>
            {event.description && (
              <p className="mt-0.5 text-[13px] text-muted-foreground">
                {event.description}
              </p>
            )}
            <p className="mt-0.5 text-xs text-muted-foreground">
              {event.actor && <span>{event.actor} · </span>}
              <time dateTime={event.at} title={formatDateTime(event.at)}>
                {relativeTime(event.at)}
              </time>
            </p>
          </>
        );
        return (
          <li key={event.id} className="relative flex gap-3 pb-4 last:pb-0">
            {index < events.length - 1 && (
              <span
                className="absolute top-7 bottom-0 left-3.5 w-px bg-border"
                aria-hidden="true"
              />
            )}
            <span
              className={cn(
                "relative z-[1] flex size-7 shrink-0 items-center justify-center rounded-full",
                style.className,
              )}
            >
              <Icon className="size-3.5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              {event.href ? (
                <Link
                  href={event.href}
                  className="block rounded hover:underline"
                >
                  {content}
                </Link>
              ) : (
                content
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function RelatedList<T>({
  title,
  items,
  loading,
  render,
  empty,
  action,
  getKey,
  viewAllHref,
}: {
  title: string;
  items: T[] | undefined;
  loading?: boolean;
  render: (item: T) => React.ReactNode;
  getKey: (item: T) => string;
  empty: string;
  action?: React.ReactNode;
  viewAllHref?: string;
}) {
  return (
    <Card>
      <CardHeader
        title={title}
        actions={
          <>
            {action}
            {viewAllHref && (
              <Link
                href={viewAllHref}
                className="text-xs font-medium text-primary hover:underline"
              >
                View all
              </Link>
            )}
          </>
        }
      />
      <div className="px-2 pb-2">
        {loading || !items ? (
          <div className="space-y-2 px-2 pb-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-9" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className="px-2 pt-1 pb-3 text-[13px] text-muted-foreground">
            {empty}
          </p>
        ) : (
          <ul>
            {items.map((item) => (
              <li key={getKey(item)}>{render(item)}</li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
