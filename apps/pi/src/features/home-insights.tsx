"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bot,
  Gauge,
  Languages,
  MessageCircle,
  Send,
  UserRound,
} from "lucide-react";

import { Badge, Card, Skeleton } from "@/components/ui";
import { get } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count } from "@/lib/format";
import { useBusinessKey } from "@/lib/session";
import type { Conversation, Page } from "@/lib/types";

export interface Insights {
  timezone: string;
  daily: { day: string; customers: number; pi: number; team: number }[];
  conversations: number;
  handled_by_pi: number;
  automation_rate: number | null;
  median_reply_seconds: number | null;
  topics: { intent: string; conversations: number }[];
  languages: { language: string; conversations: number }[];
}

export function useInsights() {
  const key = useBusinessKey();
  return useQuery({
    queryKey: key(["home", "insights"]),
    queryFn: () => get<Insights>("/home/insights"),
    refetchInterval: 60_000,
  });
}

const TOPIC: Record<string, string> = {
  requirement: "Service enquiries",
  quote: "Quotes",
  pricing: "Prices",
  order: "Orders",
  support: "Support questions",
  greeting: "Greetings",
  faq: "General questions",
  complaint: "Complaints",
  booking: "Bookings",
  payment: "Payments",
  handoff: "Asked for a person",
  customer_memory: "Their own details",
  sales_order: "Orders",
};

const LANGUAGE: Record<string, string> = {
  en: "English",
  ur: "Urdu",
  roman_ur: "Roman Urdu",
  hi: "Hindi",
  ar: "Arabic",
  unknown: "Not detected",
};

function topicLabel(intent: string) {
  return (
    TOPIC[intent] ??
    intent.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
  );
}

function plural(n: number, word: string) {
  return `${count(n)} ${word}${n === 1 ? "" : "s"}`;
}

function seconds(value: number | null) {
  if (value === null) return "—";
  if (value < 60) return `${Math.max(1, Math.round(value))}s`;
  return `${Math.round(value / 60)}m`;
}

/** A tiny trend line for a KPI tile (decorative; the number is the value). */
function Sparkline({
  values,
  className,
}: {
  values: number[];
  className?: string;
}) {
  const max = Math.max(1, ...values);
  const step = 100 / Math.max(1, values.length - 1);
  const points = values
    .map((v, i) => `${i * step},${30 - (v / max) * 26}`)
    .join(" ");
  return (
    <svg
      viewBox="0 0 100 32"
      preserveAspectRatio="none"
      aria-hidden
      className={cn("h-8 w-full", className)}
    >
      <polyline
        points={`0,32 ${points} 100,32`}
        fill="currentColor"
        opacity="0.12"
        stroke="none"
      />
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  hint,
  trend,
  progress,
  tone = "accent",
}: {
  icon: typeof Send;
  label: string;
  value: string;
  hint: string;
  trend?: number[];
  progress?: number;
  tone?: "accent" | "info" | "success" | "warning";
}) {
  const tones = {
    accent: "bg-accent-soft text-accent",
    info: "bg-info-soft text-info",
    success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning",
  };
  const line = {
    accent: "text-accent",
    info: "text-info",
    success: "text-success",
    warning: "text-warning",
  };
  return (
    <Card className="flex h-full flex-col gap-3 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-xl",
            tones[tone],
          )}
        >
          <Icon className="size-4" aria-hidden />
        </span>
      </div>
      <div className="flex-1">
        <p className="text-3xl font-semibold tracking-tight tabular-nums">
          {value}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
      </div>
      <div className="h-8">
        {trend ? (
          <Sparkline values={trend} className={line[tone]} />
        ) : progress !== undefined ? (
          <div className="flex h-full items-end">
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-surface-muted"
              role="progressbar"
              aria-valuenow={Math.round(progress * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={label}
            >
              <div
                className="h-full rounded-full bg-success"
                style={{ width: `${progress * 100}%` }}
              />
            </div>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export function InsightKpis({ data }: { data: Insights }) {
  const rate = data.automation_rate;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi
        icon={MessageCircle}
        label="Customer messages"
        value={count(data.daily.reduce((n, d) => n + d.customers, 0))}
        hint={plural(data.conversations, "conversation")}
        trend={data.daily.map((d) => d.customers)}
      />
      <Kpi
        icon={Send}
        label="Replies by pi"
        value={count(data.daily.reduce((n, d) => n + d.pi, 0))}
        hint="delivered on WhatsApp"
        trend={data.daily.map((d) => d.pi)}
        tone="info"
      />
      <Kpi
        icon={Bot}
        label="Handled by pi"
        value={rate === null ? "—" : `${Math.round(rate * 100)}%`}
        hint={
          data.conversations
            ? `${count(data.handled_by_pi)} of ${count(data.conversations)} without your team`
            : "no conversations yet"
        }
        tone="success"
        progress={rate ?? 0}
      />
      <Kpi
        icon={Gauge}
        label="Reply time"
        value={seconds(data.median_reply_seconds)}
        hint="typical time to pi's reply"
        tone="warning"
      />
    </div>
  );
}

const SERIES = [
  { key: "customers", label: "Customers", bar: "bg-border-strong" },
  { key: "pi", label: "pi", bar: "bg-accent" },
  { key: "team", label: "Your team", bar: "bg-info" },
] as const;

export function ActivityChart({ data }: { data: Insights }) {
  const max = Math.max(
    1,
    ...data.daily.flatMap((d) => [d.customers, d.pi, d.team]),
  );
  const total = data.daily.reduce((n, d) => n + d.customers + d.pi + d.team, 0);
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Messages this week</h2>
          <p className="text-xs text-muted-foreground">
            Per day, in your timezone ({data.timezone})
          </p>
        </div>
        <ul className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {SERIES.map((s) => (
            <li key={s.key} className="inline-flex items-center gap-1.5">
              <span className={cn("size-2.5 rounded-sm", s.bar)} aria-hidden />
              {s.label}
            </li>
          ))}
        </ul>
      </div>
      {total === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No messages this week yet. They&apos;ll show up here as customers
          write.
        </p>
      ) : (
        <ol
          className="mt-5 grid h-48 grid-cols-7 items-end gap-1.5 sm:gap-3"
          aria-label="Messages per day"
        >
          {data.daily.map((d) => {
            const day = new Date(`${d.day}T00:00:00`);
            const label = day.toLocaleDateString([], { weekday: "short" });
            return (
              <li
                key={d.day}
                className="flex h-full min-w-0 flex-col items-center gap-2"
              >
                <div
                  className="flex w-full flex-1 items-end justify-center gap-0.5 sm:gap-1"
                  role="img"
                  aria-label={`${label}: ${d.customers} from customers, ${d.pi} from pi, ${d.team} from your team`}
                >
                  {SERIES.map((s) => (
                    <span
                      key={s.key}
                      title={`${s.label}: ${d[s.key]}`}
                      className={cn(
                        "w-full max-w-4 rounded-t-md transition-all",
                        s.bar,
                        d[s.key] === 0 && "opacity-30",
                      )}
                      style={{
                        height: `${Math.max(3, (d[s.key] / max) * 100)}%`,
                      }}
                    />
                  ))}
                </div>
                <span className="text-[11px] text-muted-foreground">
                  {label}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

export function TopicsCard({ data }: { data: Insights }) {
  const max = Math.max(1, ...data.topics.map((t) => t.conversations));
  return (
    <Card className="p-4 sm:p-5">
      <h2 className="font-semibold">What customers ask about</h2>
      <p className="text-xs text-muted-foreground">Conversations this week</p>
      {data.topics.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Nothing yet this week.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {data.topics.map((t) => (
            <li key={t.intent}>
              <div className="flex justify-between gap-2 text-sm">
                <span className="truncate">{topicLabel(t.intent)}</span>
                <span className="tabular-nums text-muted-foreground">
                  {t.conversations}
                </span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(t.conversations / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      {data.languages.length > 0 && (
        <div className="mt-5 border-t border-border pt-4">
          <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Languages className="size-3.5" aria-hidden />
            Languages your customers use
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.languages.map((l) => (
              <Badge key={l.language}>
                {LANGUAGE[l.language] ?? l.language} · {l.conversations}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function ago(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export function RecentConversations() {
  const key = useBusinessKey();
  const list = useQuery({
    queryKey: key(["conversations", "home-recent"]),
    queryFn: () =>
      get<Page<Conversation>>("/pi/conversations", { page: 1, page_size: 5 }),
    refetchInterval: 15_000,
  });
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3.5 sm:px-5">
        <h2 className="font-semibold">Latest conversations</h2>
        <Link
          href="/inbox"
          className="inline-flex items-center gap-1 text-sm font-medium text-accent"
        >
          See all
          <ArrowRight className="size-3.5 rtl:rotate-180" aria-hidden />
        </Link>
      </div>
      {list.isPending ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : !list.data?.items.length ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">
          Conversations show up here as soon as a customer writes.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {list.data.items.map((c) => (
            <li key={c.id}>
              <Link
                href={`/inbox?conversation=${c.id}`}
                className="flex min-h-16 items-center gap-3 px-4 py-3 hover:bg-surface-muted active:bg-surface-muted sm:px-5"
              >
                <span
                  aria-hidden
                  className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-soft-foreground"
                >
                  {(c.customer_name || "?").charAt(0).toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {c.customer_name || c.customer_phone || "Customer"}
                    </span>
                    {c.unread_count > 0 && (
                      <span className="rounded-full bg-accent px-1.5 text-[11px] font-semibold text-accent-foreground">
                        {c.unread_count}
                      </span>
                    )}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {c.last_message_preview}
                  </span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-1">
                  <span className="text-xs text-muted-foreground">
                    {ago(c.last_message_at)}
                  </span>
                  {c.mode === "human" ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-info">
                      <UserRound className="size-3" aria-hidden />
                      Team
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-accent">
                      <Bot className="size-3" aria-hidden />
                      pi
                    </span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function InsightsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-36 rounded-2xl" />
      ))}
    </div>
  );
}
