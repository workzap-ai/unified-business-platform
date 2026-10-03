"use client";

import * as React from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  Gauge,
  MessageCircle,
  MessagesSquare,
  Send,
  Timer,
  UserRound,
} from "lucide-react";

import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingBlock,
  Notice,
  PageHeader,
  Skeleton,
  Spinner,
} from "@/components/ui";
import { errorText, get } from "@/lib/api";
import { cn } from "@/lib/cn";
import { count } from "@/lib/format";
import { useBusinessKey, useCan, useSession } from "@/lib/session";

/* ------------------------------------------------------------------ */
/* Types (mirrors PiAnalytics in apps/web/src/features/pi/types.ts)    */
/* ------------------------------------------------------------------ */

type AnalyticsRange = 7 | 30 | 90;
type HandoffReason =
  | "customer_request"
  | "low_confidence"
  | "provider_failure"
  | "policy"
  | "tool_failure"
  | "complaint"
  | "sensitive"
  | "manual";
type AgentKey =
  | "router"
  | "customer_memory"
  | "support"
  | "requirement"
  | "sales_order"
  | "handoff";
type ProviderName = "openai" | "gemini" | "groq";

export type PiAnalytics = {
  range: AnalyticsRange;
  currency_note: string;
  conversations: { day: string; started: number; resolved: number }[];
  messages: {
    day: string;
    inbound: number;
    outbound_ai: number;
    outbound_human: number;
  }[];
  latency: { day: string; p50: number; p95: number }[];
  runs_by_agent: { agent: AgentKey; runs: number; failures: number }[];
  intents: { intent: string; count: number }[];
  tools: { tool: string; success: number; failed: number; denied: number }[];
  handoffs_by_reason: { reason: HandoffReason; count: number }[];
  handoffs_by_day: { day: string; opened: number; resolved: number }[];
  fallbacks: { day: string; count: number }[];
  fallback_pairs: {
    from: ProviderName;
    to: ProviderName | "handoff";
    count: number;
    top_reason: string;
  }[];
  provider_usage: {
    day: string;
    openai: number;
    gemini: number;
    groq: number;
  }[];
  tokens: { day: string; input: number; output: number }[];
  cost_estimate: { day: string; amount: number }[] | null;
  totals: {
    conversations: number;
    messages: number;
    ai_responses: number;
    runs: number;
    tool_calls: number;
    handoffs: number;
    fallbacks: number;
    failure_rate: number;
    input_tokens: number;
    output_tokens: number;
    cost_estimate_usd: number | null;
  };
};

/* ------------------------------------------------------------------ */
/* Labels and formatting                                               */
/* ------------------------------------------------------------------ */

const RANGES: AnalyticsRange[] = [7, 30, 90];

const REASON: Record<string, string> = {
  customer_request: "Customer asked for a person",
  low_confidence: "Pi wasn't sure",
  provider_failure: "AI unavailable",
  policy: "Business rule",
  tool_failure: "A tool failed",
  complaint: "Complaint",
  sensitive: "Sensitive topic",
  manual: "Sent by your team",
};

const INTENT: Record<string, string> = {
  requirement: "Service enquiries",
  quote: "Quotes",
  pricing: "Prices",
  order: "Orders",
  sales_order: "Orders",
  support: "Support questions",
  greeting: "Greetings",
  faq: "General questions",
  complaint: "Complaints",
  booking: "Bookings",
  payment: "Payments",
  handoff: "Asked for a person",
  customer_memory: "Their own details",
  unknown: "Not sure yet",
};

const AGENT: Record<string, string> = {
  router: "Reading each message",
  customer_memory: "Remembering customers",
  support: "Answering questions",
  requirement: "Service enquiries",
  sales_order: "Taking orders",
  handoff: "Handing to your team",
};

const PROVIDER: Record<string, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
  groq: "Groq",
  handoff: "your team",
};

function humanize(value: string) {
  return value
    .replace(/[._-]+/g, " ")
    .trim()
    .replace(/^\w/, (c) => c.toUpperCase());
}

function label(map: Record<string, string>, key: string) {
  return map[key] ?? humanize(key);
}

function percent(value: number | null) {
  if (value === null) return "—";
  const pct = value * 100;
  if (pct > 0 && pct < 1) return "<1%";
  return `${Math.round(pct)}%`;
}

/** Latency arrives in milliseconds. */
function duration(ms: number | null) {
  if (ms === null || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function sum(values: number[]) {
  return values.reduce((n, v) => n + v, 0);
}

function asDate(day: string) {
  return new Date(`${day}T00:00:00Z`);
}

function shortDay(day: string, weekday: boolean) {
  return asDate(day).toLocaleDateString(
    [],
    weekday
      ? { weekday: "short", timeZone: "UTC" }
      : { day: "numeric", month: "short", timeZone: "UTC" },
  );
}

function longDay(day: string) {
  return asDate(day).toLocaleDateString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

/** Every calendar day in the range (UTC, like the API), plus any day the API returned. */
function dayAxis(range: number, data: PiAnalytics): string[] {
  const now = new Date();
  const keys = new Set<string>();
  for (let i = range - 1; i >= 0; i--) {
    const d = new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i),
    );
    keys.add(d.toISOString().slice(0, 10));
  }
  for (const list of [
    data.conversations,
    data.messages,
    data.latency,
    data.provider_usage,
    data.tokens,
    data.fallbacks,
  ]) {
    for (const row of list) keys.add(row.day);
  }
  return [...keys].sort();
}

type Values = Record<string, number>;
type DayRow = { day: string; values: Values };

/** Fill a sparse per-day list onto the full axis with zeros. */
function onAxis<T extends { day: string }>(
  axis: string[],
  rows: T[],
  pick: (row: T) => Values,
  keys: string[],
): DayRow[] {
  const byDay = new Map(rows.map((r) => [r.day, r]));
  return axis.map((day) => {
    const row = byDay.get(day);
    return {
      day,
      values: row
        ? pick(row)
        : Object.fromEntries(keys.map((k) => [k, 0] as const)),
    };
  });
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export function AnalyticsPage() {
  const session = useSession();
  const can = useCan();
  const key = useBusinessKey();
  const [range, setRange] = React.useState<AnalyticsRange>(30);
  const allowed = can("pi.analytics.read");

  const query = useQuery({
    queryKey: key(["analytics", range]),
    queryFn: () => get<PiAnalytics>("/pi/analytics", { range }),
    enabled: allowed,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  const header = (
    <PageHeader
      title="Analytics"
      description="How Pi is doing with your customers: conversations, replies, speed and when your team stepped in."
      action={
        allowed ? <RangeControl value={range} onChange={setRange} /> : null
      }
    />
  );

  if (session.isPending) {
    return (
      <div className="min-w-0">
        {header}
        <LoadingBlock rows={4} label="Loading analytics" />
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="min-w-0">
        {header}
        <Notice title="Analytics isn't available on your account">
          Ask the business owner or an admin to give you access to analytics.
        </Notice>
      </div>
    );
  }

  return (
    <div className="min-w-0">
      {header}
      <div
        role="tabpanel"
        id="analytics-panel"
        aria-labelledby={`analytics-range-${range}`}
        aria-busy={query.isFetching}
        className="min-w-0"
      >
        {query.isPending ? (
          <AnalyticsSkeleton />
        ) : query.isError && !query.data ? (
          <ErrorState
            message={errorText(query.error)}
            onRetry={() => void query.refetch()}
          />
        ) : query.data ? (
          <div
            className={cn(
              "min-w-0 transition-opacity",
              query.isPlaceholderData && "opacity-60",
            )}
          >
            {query.isPlaceholderData ? (
              <div className="mb-3 flex justify-end">
                <Spinner label="Updating" />
              </div>
            ) : null}
            <AnalyticsBody data={query.data} range={range} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RangeControl({
  value,
  onChange,
}: {
  value: AnalyticsRange;
  onChange: (range: AnalyticsRange) => void;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  function onKeyDown(event: React.KeyboardEvent, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % RANGES.length;
    else if (event.key === "ArrowLeft")
      next = (index - 1 + RANGES.length) % RANGES.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = RANGES.length - 1;
    else return;
    event.preventDefault();
    onChange(RANGES[next]);
    refs.current[next]?.focus();
  }
  return (
    <div
      role="tablist"
      aria-label="Time range"
      className="inline-flex rounded-xl border border-border bg-surface-muted p-1"
    >
      {RANGES.map((r, i) => {
        const selected = r === value;
        return (
          <button
            key={r}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={`analytics-range-${r}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls="analytics-panel"
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(r)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              "min-h-11 min-w-[4.5rem] rounded-lg px-3 text-sm font-medium transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
              selected
                ? "bg-surface text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {r} days
          </button>
        );
      })}
    </div>
  );
}

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6" aria-hidden>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-2xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-72 rounded-2xl" />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Body                                                                */
/* ------------------------------------------------------------------ */

function AnalyticsBody({
  data,
  range,
}: {
  data: PiAnalytics;
  range: AnalyticsRange;
}) {
  const axis = React.useMemo(() => dayAxis(range, data), [range, data]);
  const t = data.totals;
  const empty =
    t.conversations === 0 &&
    t.messages === 0 &&
    t.runs === 0 &&
    t.handoffs === 0;

  if (empty) {
    return (
      <Card>
        <EmptyState
          icon={<BarChart3 className="size-5" aria-hidden />}
          title={`Nothing to show for the last ${range} days`}
        >
          Once customers message you on WhatsApp, you&apos;ll see how many
          conversations Pi handled, how fast it replied and when your team
          stepped in.
        </EmptyState>
      </Card>
    );
  }

  const conversations = onAxis(
    axis,
    data.conversations,
    (r) => ({ started: r.started, resolved: r.resolved }),
    ["started", "resolved"],
  );
  const messages = onAxis(
    axis,
    data.messages,
    (r) => ({
      inbound: r.inbound,
      ai: r.outbound_ai,
      team: r.outbound_human,
    }),
    ["inbound", "ai", "team"],
  );
  const providers = onAxis(
    axis,
    data.provider_usage,
    (r) => ({ openai: r.openai, gemini: r.gemini, groq: r.groq }),
    ["openai", "gemini", "groq"],
  );
  const tokens = onAxis(
    axis,
    data.tokens,
    (r) => ({ input: r.input, output: r.output }),
    ["input", "output"],
  );
  const latencyByDay = new Map(
    data.latency.filter((l) => l.p50 > 0 || l.p95 > 0).map((l) => [l.day, l]),
  );
  const latency = axis.map((day) => ({
    day,
    p50: latencyByDay.get(day)?.p50 ?? null,
    p95: latencyByDay.get(day)?.p95 ?? null,
  }));

  const p50 = median([...latencyByDay.values()].map((l) => l.p50));
  const p95 = median([...latencyByDay.values()].map((l) => l.p95));
  const handledRate =
    t.conversations > 0
      ? Math.min(1, Math.max(0, 1 - t.handoffs / t.conversations))
      : null;

  return (
    <div className="space-y-6">
      <section aria-labelledby="analytics-kpis">
        <h2 id="analytics-kpis" className="sr-only">
          Key numbers
        </h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi
            icon={MessagesSquare}
            label="Conversations"
            value={count(t.conversations)}
            hint={`started in the last ${range} days`}
            trend={conversations.map((d) => d.values.started)}
          />
          <Kpi
            icon={MessageCircle}
            label="Messages"
            value={count(t.messages)}
            hint="from customers, Pi and your team"
            trend={messages.map(
              (d) => d.values.inbound + d.values.ai + d.values.team,
            )}
            tone="info"
          />
          <Kpi
            icon={Send}
            label="Replies by Pi"
            value={count(t.ai_responses)}
            hint={
              t.messages
                ? `${percent(t.ai_responses / t.messages)} of all messages`
                : "no messages yet"
            }
            trend={messages.map((d) => d.values.ai)}
          />
          <Kpi
            icon={Bot}
            label="Handled without your team"
            value={percent(handledRate)}
            hint={
              t.conversations
                ? `${count(Math.max(0, t.conversations - t.handoffs))} of ${count(t.conversations)} conversations`
                : "no conversations yet"
            }
            progress={handledRate ?? undefined}
            tone="success"
          />
          <Kpi
            icon={Gauge}
            label="Typical reply time"
            value={duration(p50)}
            hint="half of Pi's replies are faster"
            tone="warning"
          />
          <Kpi
            icon={Timer}
            label="Slowest replies"
            value={duration(p95)}
            hint="95% of replies are faster than this"
            tone="warning"
          />
          <Kpi
            icon={UserRound}
            label="Handed to your team"
            value={count(t.handoffs)}
            hint={
              t.handoffs === 1
                ? "conversation"
                : "conversations needed a person"
            }
            tone="info"
          />
          <Kpi
            icon={AlertTriangle}
            label="Failed AI runs"
            value={t.runs ? percent(t.failure_rate) : "—"}
            hint={t.runs ? `of ${count(t.runs)} AI runs` : "no AI runs yet"}
            tone={t.failure_rate > 0.05 ? "danger" : "success"}
            progress={t.runs ? t.failure_rate : undefined}
          />
        </div>
      </section>

      <section aria-labelledby="analytics-charts">
        <h2 id="analytics-charts" className="sr-only">
          Charts
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartCard
            title="Conversations"
            description="Started each day, and how many of those are now resolved"
            legend={CONVERSATION_SERIES}
          >
            <DayBars
              name="Conversations per day"
              rows={conversations}
              series={CONVERSATION_SERIES}
              mode="overlay"
              emptyText="No conversations in this period."
            />
          </ChartCard>

          <ChartCard
            title="Messages"
            description="Per day, by who sent them"
            legend={MESSAGE_SERIES}
          >
            <DayBars
              name="Messages per day"
              rows={messages}
              series={MESSAGE_SERIES}
              mode="stacked"
              emptyText="No messages in this period."
            />
          </ChartCard>

          <ChartCard
            title="Reply speed"
            description="How long Pi took to answer, per day"
            legend={LATENCY_SERIES}
          >
            <LatencyChart rows={latency} />
          </ChartCard>

          <ChartCard
            title="Why conversations went to your team"
            description={`${count(t.handoffs)} handed over in this period`}
          >
            <HBars
              name="Handoffs by reason"
              emptyText="Pi didn't hand any conversation to your team."
              items={[...data.handoffs_by_reason]
                .sort((a, b) => b.count - a.count)
                .map((h) => ({
                  key: h.reason,
                  label: label(REASON, h.reason),
                  segments: [{ value: h.count, bar: "bg-info", label: "" }],
                }))}
            />
          </ChartCard>

          <ChartCard
            title="What customers ask about"
            description="Most common topics Pi recognised"
          >
            <HBars
              name="Top topics"
              emptyText="No topics recognised yet."
              items={[...data.intents]
                .sort((a, b) => b.count - a.count)
                .slice(0, 8)
                .map((i) => ({
                  key: i.intent,
                  label: label(INTENT, i.intent),
                  segments: [{ value: i.count, bar: "bg-accent", label: "" }],
                }))}
            />
          </ChartCard>

          <ChartCard
            title="Pi's work by area"
            description="AI runs for each part of Pi, and how many failed"
            legend={AGENT_SERIES}
          >
            <HBars
              name="Runs by area"
              emptyText="No AI runs in this period."
              items={[...data.runs_by_agent]
                .filter((a) => a.runs > 0)
                .sort((a, b) => b.runs - a.runs)
                .map((a) => ({
                  key: a.agent,
                  label: label(AGENT, a.agent),
                  segments: [
                    {
                      value: Math.max(0, a.runs - a.failures),
                      bar: "bg-accent",
                      label: "worked",
                    },
                    { value: a.failures, bar: "bg-danger", label: "failed" },
                  ],
                }))}
            />
          </ChartCard>

          <ChartCard
            title="Tools Pi used"
            description={`${count(t.tool_calls)} actions like looking up orders or saving details`}
            legend={TOOL_SERIES}
          >
            <HBars
              name="Tool activity"
              emptyText="Pi didn't use any tools in this period."
              items={[...data.tools]
                .sort(
                  (a, b) =>
                    b.success +
                    b.failed +
                    b.denied -
                    (a.success + a.failed + a.denied),
                )
                .slice(0, 8)
                .map((tool) => ({
                  key: tool.tool,
                  label: humanize(tool.tool),
                  segments: [
                    { value: tool.success, bar: "bg-success", label: "worked" },
                    { value: tool.failed, bar: "bg-danger", label: "failed" },
                    {
                      value: tool.denied,
                      bar: "bg-warning",
                      label: "not allowed",
                    },
                  ],
                }))}
            />
          </ChartCard>

          <ChartCard
            title="AI providers"
            description="Which AI answered each day"
            legend={PROVIDER_SERIES}
          >
            <DayBars
              name="AI provider use per day"
              rows={providers}
              series={PROVIDER_SERIES}
              mode="stacked"
              emptyText="No AI use recorded in this period."
            />
            <BackupAi data={data} />
          </ChartCard>

          <ChartCard
            title="AI usage (tokens)"
            description={`${count(t.input_tokens + t.output_tokens)} tokens: what Pi read and what it wrote`}
            legend={TOKEN_SERIES}
            className="lg:col-span-2"
          >
            <DayBars
              name="Tokens per day"
              rows={tokens}
              series={TOKEN_SERIES}
              mode="stacked"
              emptyText="No AI usage recorded in this period."
            />
          </ChartCard>
        </div>
      </section>

      <p className="text-xs text-muted-foreground">
        Days follow UTC. &ldquo;Resolved&rdquo; shows the current state of
        conversations started on each day, so recent days can still change.
      </p>
    </div>
  );
}

function BackupAi({ data }: { data: PiAnalytics }) {
  const total = data.totals.fallbacks;
  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-medium">Backup AI used</h4>
        <Badge tone={total ? "warning" : "success"}>
          {total ? `${count(total)} times` : "Not needed"}
        </Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        When one AI is busy or down, Pi switches to another so customers still
        get a reply.
      </p>
      {data.fallback_pairs.length > 0 ? (
        <ul className="mt-3 space-y-1.5 text-sm">
          {[...data.fallback_pairs]
            .sort((a, b) => b.count - a.count)
            .map((p) => (
              <li
                key={`${p.from}-${p.to}`}
                className="flex min-w-0 justify-between gap-3"
              >
                <span className="min-w-0 truncate">
                  {label(PROVIDER, p.from)} → {label(PROVIDER, p.to)}
                </span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {count(p.count)}
                </span>
              </li>
            ))}
        </ul>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Building blocks                                                     */
/* ------------------------------------------------------------------ */

type Tone = "accent" | "info" | "success" | "warning" | "danger";

const TONE_ICON: Record<Tone, string> = {
  accent: "bg-accent-soft text-accent",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};
const TONE_TEXT: Record<Tone, string> = {
  accent: "text-accent",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};
const TONE_BAR: Record<Tone, string> = {
  accent: "bg-accent",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

/** A tiny decorative trend line for a KPI tile; the number is the value. */
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
  label: title,
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
  tone?: Tone;
}) {
  return (
    <Card className="flex h-full min-w-0 flex-col gap-3 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 text-sm text-muted-foreground">{title}</h3>
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-xl",
            TONE_ICON[tone],
          )}
        >
          <Icon className="size-4" aria-hidden />
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-2xl font-semibold tracking-tight tabular-nums sm:text-3xl">
          {value}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
      </div>
      <div className="h-8">
        {trend && trend.some((v) => v > 0) ? (
          <Sparkline values={trend} className={TONE_TEXT[tone]} />
        ) : progress !== undefined ? (
          <div className="flex h-full items-end">
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-surface-muted"
              role="progressbar"
              aria-valuenow={Math.round(progress * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={title}
            >
              <div
                className={cn("h-full rounded-full", TONE_BAR[tone])}
                style={{ width: `${Math.min(1, progress) * 100}%` }}
              />
            </div>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

type Series = { key: string; label: string; bar: string };

const CONVERSATION_SERIES: Series[] = [
  { key: "started", label: "Started", bar: "bg-accent-soft" },
  { key: "resolved", label: "Resolved", bar: "bg-accent" },
];
const MESSAGE_SERIES: Series[] = [
  { key: "inbound", label: "Customers", bar: "bg-border-strong" },
  { key: "ai", label: "Pi", bar: "bg-accent" },
  { key: "team", label: "Your team", bar: "bg-info" },
];
const PROVIDER_SERIES: Series[] = [
  { key: "openai", label: "OpenAI", bar: "bg-accent" },
  { key: "gemini", label: "Gemini", bar: "bg-info" },
  { key: "groq", label: "Groq", bar: "bg-warning" },
];
const TOKEN_SERIES: Series[] = [
  { key: "input", label: "Read by Pi", bar: "bg-info" },
  { key: "output", label: "Written by Pi", bar: "bg-accent" },
];
const LATENCY_SERIES: Series[] = [
  { key: "p50", label: "Typical", bar: "bg-accent" },
  { key: "p95", label: "Slowest 5%", bar: "bg-warning" },
];
const AGENT_SERIES: Series[] = [
  { key: "worked", label: "Worked", bar: "bg-accent" },
  { key: "failed", label: "Failed", bar: "bg-danger" },
];
const TOOL_SERIES: Series[] = [
  { key: "success", label: "Worked", bar: "bg-success" },
  { key: "failed", label: "Failed", bar: "bg-danger" },
  { key: "denied", label: "Not allowed", bar: "bg-warning" },
];

function ChartCard({
  title,
  description,
  legend,
  className,
  children,
}: {
  title: string;
  description?: string;
  legend?: Series[];
  className?: string;
  children: React.ReactNode;
}) {
  const id = React.useId();
  return (
    <Card
      className={cn("min-w-0 overflow-hidden p-4 sm:p-5", className)}
      role="region"
      aria-labelledby={id}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h3 id={id} className="font-semibold">
            {title}
          </h3>
          {description ? (
            <p className="text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {legend ? (
          <ul
            className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground"
            aria-label="Legend"
          >
            {legend.map((s) => (
              <li key={s.key} className="inline-flex items-center gap-1.5">
                <span
                  className={cn("size-2.5 rounded-sm", s.bar)}
                  aria-hidden
                />
                {s.label}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="min-w-0">{children}</div>
    </Card>
  );
}

function labelStride(n: number) {
  if (n <= 8) return 1;
  if (n <= 31) return 7;
  return 15;
}

/** Day labels under a chart; only some are shown on long ranges so they stay readable. */
function DayAxis({ days }: { days: string[] }) {
  const stride = labelStride(days.length);
  const weekday = days.length <= 8;
  return (
    <div
      className="relative mt-2 h-4 text-[11px] text-muted-foreground"
      aria-hidden
    >
      {days.map((day, i) => {
        // Anchor labels to the newest day, so "today" is always labelled.
        if ((days.length - 1 - i) % stride !== 0) return null;
        const pos = ((i + 0.5) / days.length) * 100;
        const align =
          pos < 12
            ? "translate-x-0"
            : pos > 88
              ? "-translate-x-full"
              : "-translate-x-1/2";
        return (
          <span
            key={day}
            className={cn("absolute top-0 whitespace-nowrap", align)}
            style={{ left: pos < 12 ? 0 : pos > 88 ? "100%" : `${pos}%` }}
          >
            {shortDay(day, weekday)}
          </span>
        );
      })}
    </div>
  );
}

function busiest(rows: { day: string; total: number }[]) {
  return rows.reduce<{ day: string; total: number } | null>(
    (best, r) => (r.total > (best?.total ?? 0) ? r : best),
    null,
  );
}

/**
 * Per-day columns drawn with divs. `stacked` piles the series; `overlay` draws the
 * second series inside the first (e.g. resolved within started).
 */
function DayBars({
  name,
  rows,
  series,
  mode,
  emptyText,
}: {
  name: string;
  rows: DayRow[];
  series: Series[];
  mode: "stacked" | "overlay";
  emptyText: string;
}) {
  const totals = rows.map((r) =>
    mode === "overlay"
      ? Math.max(...series.map((s) => r.values[s.key] ?? 0))
      : sum(series.map((s) => r.values[s.key] ?? 0)),
  );
  const max = Math.max(1, ...totals);
  const grand = sum(totals);
  const dense = rows.length > 14;

  if (grand === 0) {
    return (
      <p className="py-14 text-center text-sm text-muted-foreground">
        {emptyText}
      </p>
    );
  }

  const describe = (r: DayRow) =>
    `${longDay(r.day)}: ${series
      .map((s) => `${count(r.values[s.key] ?? 0)} ${s.label.toLowerCase()}`)
      .join(", ")}`;
  const peak = busiest(rows.map((r, i) => ({ day: r.day, total: totals[i] })));

  return (
    <div className="mt-4 min-w-0">
      <div className="flex items-baseline justify-between text-[11px] text-muted-foreground">
        <span aria-hidden>Peak {count(max)}</span>
      </div>
      <div className="mt-1 overflow-hidden">
        <ol
          aria-label={name}
          className={cn(
            "flex h-40 items-end border-b border-border",
            dense ? "gap-px" : "gap-1.5 sm:gap-2",
          )}
        >
          {rows.map((r, i) => {
            const total = totals[i];
            const height = total ? Math.max(2, (total / max) * 100) : 0;
            return (
              <li
                key={r.day}
                className="flex h-full min-w-0 flex-1 items-end justify-center"
              >
                <span
                  role="img"
                  aria-label={describe(r)}
                  title={describe(r)}
                  className={cn(
                    "flex w-full flex-col-reverse overflow-hidden",
                    dense ? "rounded-t-[2px]" : "max-w-8 rounded-t-md",
                    total === 0 && "h-0.5 bg-surface-muted",
                    mode === "overlay" && total > 0 && series[0].bar,
                  )}
                  style={total ? { height: `${height}%` } : undefined}
                >
                  {total === 0
                    ? null
                    : mode === "overlay"
                      ? series.slice(1).map((s) => (
                          <span
                            key={s.key}
                            className={cn("block w-full shrink-0", s.bar)}
                            style={{
                              height: `${((r.values[s.key] ?? 0) / total) * 100}%`,
                            }}
                          />
                        ))
                      : series.map((s) => (
                          <span
                            key={s.key}
                            className={cn("block w-full shrink-0", s.bar)}
                            style={{
                              height: `${((r.values[s.key] ?? 0) / total) * 100}%`,
                            }}
                          />
                        ))}
                </span>
              </li>
            );
          })}
        </ol>
        <DayAxis days={rows.map((r) => r.day)} />
      </div>
      <ul className="sr-only">
        {series.map((s) => (
          <li key={s.key}>
            {s.label}: {count(sum(rows.map((r) => r.values[s.key] ?? 0)))} in
            total
          </li>
        ))}
        {peak ? (
          <li>
            Busiest day: {longDay(peak.day)} with {count(peak.total)}
          </li>
        ) : null}
      </ul>
    </div>
  );
}

function LatencyChart({
  rows,
}: {
  rows: { day: string; p50: number | null; p95: number | null }[];
}) {
  const known = rows.filter((r) => r.p50 !== null || r.p95 !== null);
  if (known.length === 0) {
    return (
      <p className="py-14 text-center text-sm text-muted-foreground">
        No replies timed in this period.
      </p>
    );
  }
  const max = Math.max(
    1,
    ...known.map((r) => Math.max(r.p50 ?? 0, r.p95 ?? 0)),
  );
  const n = rows.length;
  const x = (i: number) => (n === 1 ? 50 : ((i + 0.5) / n) * 100);
  const y = (v: number) => 58 - (v / max) * 54;
  const line = (keyName: "p50" | "p95") =>
    rows
      .map((r, i) => (r[keyName] === null ? null : `${x(i)},${y(r[keyName])}`))
      .filter(Boolean)
      .join(" ");
  const p50 = median(known.map((r) => r.p50 ?? 0));
  const p95 = median(known.map((r) => r.p95 ?? 0));
  const slowest = known.reduce((a, b) => ((b.p95 ?? 0) > (a.p95 ?? 0) ? b : a));
  const summary = `Reply speed per day. Typical ${duration(p50)}, slowest 5% ${duration(p95)}. Slowest day ${longDay(slowest.day)} at ${duration(slowest.p95)}.`;

  return (
    <div className="mt-4 min-w-0">
      <div className="text-[11px] text-muted-foreground" aria-hidden>
        Up to {duration(max)}
      </div>
      <div className="relative mt-1 h-40 overflow-hidden border-b border-border">
        <svg
          viewBox="0 0 100 60"
          preserveAspectRatio="none"
          role="img"
          aria-label={summary}
          className="absolute inset-0 h-full w-full"
        >
          {[0.25, 0.5, 0.75].map((f) => (
            <line
              key={f}
              x1="0"
              x2="100"
              y1={y(max * f)}
              y2={y(max * f)}
              className="text-border"
              stroke="currentColor"
              strokeDasharray="2 2"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {known.length === 1 ? null : (
            <>
              <polyline
                points={line("p95")}
                fill="none"
                className="text-warning"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
              <polyline
                points={line("p50")}
                fill="none"
                className="text-accent"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            </>
          )}
        </svg>
        {/* Point markers in HTML so they stay round with a stretched SVG. */}
        {n <= 31
          ? rows.flatMap((r, i) =>
              (["p95", "p50"] as const).map((k) =>
                r[k] === null ? null : (
                  <span
                    key={`${r.day}-${k}`}
                    aria-hidden
                    title={`${longDay(r.day)}: ${k === "p50" ? "typical" : "slowest 5%"} ${duration(r[k])}`}
                    className={cn(
                      "absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface",
                      k === "p50" ? "bg-accent" : "bg-warning",
                    )}
                    style={{
                      left: `${x(i)}%`,
                      top: `${(y(r[k]) / 60) * 100}%`,
                    }}
                  />
                ),
              ),
            )
          : null}
      </div>
      <DayAxis days={rows.map((r) => r.day)} />
      <ul className="sr-only">
        {known.map((r) => (
          <li key={r.day}>
            {longDay(r.day)}: typical {duration(r.p50)}, slowest 5%{" "}
            {duration(r.p95)}
          </li>
        ))}
      </ul>
    </div>
  );
}

type HBarItem = {
  key: string;
  label: string;
  segments: { value: number; bar: string; label: string }[];
};

/** Horizontal bars; extra segments split a bar (e.g. worked / failed). */
function HBars({
  name,
  items,
  emptyText,
}: {
  name: string;
  items: HBarItem[];
  emptyText: string;
}) {
  const totals = items.map((it) => sum(it.segments.map((s) => s.value)));
  const max = Math.max(1, ...totals);
  const visible = items.filter((_, i) => totals[i] > 0);
  if (visible.length === 0) {
    return (
      <p className="py-14 text-center text-sm text-muted-foreground">
        {emptyText}
      </p>
    );
  }
  return (
    <ul className="mt-4 space-y-3" aria-label={name}>
      {items.map((it, i) => {
        const total = totals[i];
        if (total === 0) return null;
        const detail = it.segments
          .filter((s) => s.label && s.value > 0)
          .map((s) => `${count(s.value)} ${s.label}`)
          .join(", ");
        return (
          <li key={it.key} className="min-w-0">
            <div className="flex min-w-0 justify-between gap-3 text-sm">
              <span className="min-w-0 truncate">{it.label}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {count(total)}
                <span className="sr-only">{detail ? ` (${detail})` : ""}</span>
              </span>
            </div>
            <div
              className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-surface-muted"
              aria-hidden
            >
              {it.segments.map((s, j) =>
                s.value > 0 ? (
                  <div
                    key={j}
                    className={cn("h-full", s.bar)}
                    style={{ width: `${(s.value / max) * 100}%` }}
                  />
                ) : null,
              )}
            </div>
            {detail && it.segments.length > 1 ? (
              <p className="mt-1 text-[11px] text-muted-foreground" aria-hidden>
                {detail}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
