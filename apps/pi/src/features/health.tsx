"use client";

/**
 * pi Health, as in Owner OS: pi checks its own set-up and work, fixes the safe things
 * by itself, runs self-tests in a sandbox and tells you what needs you. Live while
 * open. GET /pi/health, POST /pi/health/heal, /pi/health/fix/{key},
 * /pi/health/self-test.
 */

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FlaskConical,
  HeartPulse,
  Sparkles,
  Wrench,
  XCircle,
} from "lucide-react";
import Link from "next/link";

import {
  Badge,
  Button,
  Card,
  CardSection,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  cn,
} from "@/components/ui";
import { errorText, get, post } from "@/lib/api";
import { piLink } from "@/lib/links";
import { timeAgo } from "@/lib/format";
import { useAction, useBusinessKey, useCan } from "@/lib/session";

type Status = "ok" | "warning" | "problem" | "fixed";

type Check = {
  key: string;
  area: string;
  status: Status;
  title: string;
  detail: string;
  count: number;
  fix: "auto" | "button" | "settings" | null;
  href: string | null;
  action: string | null;
  last_fixed_at: string | null;
};

type Scenario = {
  key: string;
  title: string;
  message: string;
  passed: boolean | null;
  reason: string;
  reply: string;
  retried: boolean;
  hint: string;
  href: string | null;
  at: string;
};

type Health = {
  score: number;
  verdict: string;
  counts: Record<string, number>;
  checks: Check[];
  areas: string[];
  fixed_recently: {
    total: number;
    items: {
      check: string | null;
      what: string | null;
      count: number;
      at: string;
    }[];
  };
  trends: {
    day: string;
    replies: number;
    held: number;
    failed_sends: number;
    fixes: number;
  }[];
  gaps: {
    question: string;
    asked: number;
    last_asked_at: string;
    href: string;
  }[];
  learning: {
    answers_learned_30d: number;
    open_questions: number;
    drafts_waiting: number;
  };
  self_tests: {
    last_run_at: string | null;
    pass_rate: number | null;
    passed: number;
    total: number;
    scenarios: Scenario[];
    daily: {
      day: string;
      passed: number;
      total: number;
      rate: number | null;
    }[];
  };
  checked_at: string;
};

const LIVE_EVERY_MS = 30_000;
const KEY = ["pi-health"];

const DOT: Record<Status, string> = {
  problem: "bg-danger",
  warning: "bg-warning",
  fixed: "bg-success",
  ok: "bg-success/60",
};
const STATUS_LABEL: Record<Status, string> = {
  problem: "Needs you",
  warning: "Worth a look",
  fixed: "Fixed by pi",
  ok: "OK",
};

/** A page link from the API, as a pi app page (Owner OS paths are mapped). */
const page = (href: string | null | undefined) => piLink(href) ?? "/home";

export function HealthPage() {
  const can = useCan();
  const key = useBusinessKey();
  const manage = can("pi.settings.manage");
  const query = useQuery({
    queryKey: key(KEY),
    queryFn: () => get<Health>("/pi/health"),
    enabled: can("pi.read"),
    // Live: what pi finds or fixes shows up while the page is open.
    refetchInterval: LIVE_EVERY_MS,
  });
  const heal = useAction(() => post<Health>("/pi/health/heal"), {
    invalidate: [KEY],
    success: "pi ran its fixes",
  });
  const selfTest = useAction(() => post<Health>("/pi/health/self-test"), {
    invalidate: [KEY],
    success: "Self-tests finished",
  });
  const data = query.data;
  return (
    <div>
      <PageHeader
        title="pi Health"
        description="pi checks its own set-up and work, fixes the safe things by itself, and tells you what needs you."
        action={
          <>
            <LiveBadge
              fetching={query.isFetching}
              updatedAt={query.dataUpdatedAt}
            />
            {manage ? (
              <Button
                size="sm"
                variant="secondary"
                loading={heal.isPending}
                onClick={() => heal.mutate(undefined)}
              >
                <Wrench className="size-4" aria-hidden /> Fix now
              </Button>
            ) : null}
          </>
        }
      />
      {!can("pi.read") ? (
        <Card>
          <EmptyState
            icon={<HeartPulse className="size-6" aria-hidden />}
            title="No access"
          >
            You don&apos;t have access to pi Health. Ask your business owner.
          </EmptyState>
        </Card>
      ) : query.isError && !data ? (
        <ErrorState
          message={errorText(query.error)}
          onRetry={() => query.refetch()}
        />
      ) : !data ? (
        <LoadingBlock rows={4} label="Loading pi Health" />
      ) : (
        <div className="space-y-6">
          <Summary data={data} />
          <Trends data={data} />
          <SelfTests
            data={data}
            manage={manage}
            running={selfTest.isPending}
            onRun={() => selfTest.mutate(undefined)}
          />
          <Checks data={data} manage={manage} />
          <Learning data={data} />
        </div>
      )}
    </div>
  );
}

function LiveBadge({
  fetching,
  updatedAt,
}: {
  fetching: boolean;
  updatedAt: number;
}) {
  return (
    <span
      className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-border px-3 text-xs font-medium text-muted-foreground"
      title={`Refreshes every ${LIVE_EVERY_MS / 1000} seconds while open`}
    >
      <span className="relative flex size-2">
        <span
          className={cn(
            "absolute inline-flex size-full rounded-full bg-success opacity-60",
            fetching ? "animate-ping" : "motion-safe:animate-pulse",
          )}
        />
        <span className="relative inline-flex size-2 rounded-full bg-success" />
      </span>
      Live ·{" "}
      {fetching || !updatedAt
        ? "updating…"
        : new Date(updatedAt).toLocaleTimeString("en", {
            hour: "numeric",
            minute: "2-digit",
          })}
    </span>
  );
}

function scoreTone(score: number) {
  return score >= 90
    ? "var(--success)"
    : score >= 70
      ? "var(--warning)"
      : "var(--danger)";
}

function ScoreRing({ score }: { score: number }) {
  const r = 30;
  const length = 2 * Math.PI * r;
  return (
    <svg
      viewBox="0 0 72 72"
      className="size-20 shrink-0"
      role="img"
      aria-label={`Health score ${score} out of 100`}
    >
      <circle
        cx="36"
        cy="36"
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth="7"
      />
      <circle
        cx="36"
        cy="36"
        r={r}
        fill="none"
        stroke={scoreTone(score)}
        strokeWidth="7"
        strokeLinecap="round"
        strokeDasharray={`${(score / 100) * length} ${length}`}
        transform="rotate(-90 36 36)"
        className="transition-[stroke-dasharray] duration-700"
      />
      <text
        x="36"
        y="41"
        textAnchor="middle"
        className="fill-foreground text-[17px] font-semibold tabular-nums"
      >
        {score}
      </text>
    </svg>
  );
}

function Summary({ data }: { data: Health }) {
  const counts = data.counts;
  const latest = data.fixed_recently.items[0];
  return (
    <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
      <Card>
        <CardSection className="flex items-center gap-4">
          <ScoreRing score={data.score} />
          <div className="min-w-0">
            <p className="text-base font-semibold">{data.verdict}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(counts.problem ?? 0) > 0 ? (
                <Badge tone="danger">{counts.problem} need you</Badge>
              ) : null}
              {(counts.warning ?? 0) > 0 ? (
                <Badge tone="warning">{counts.warning} worth a look</Badge>
              ) : null}
              {(counts.fixed ?? 0) > 0 ? (
                <Badge tone="success">{counts.fixed} fixed just now</Badge>
              ) : null}
              <Badge>{counts.ok ?? 0} OK</Badge>
            </div>
          </div>
        </CardSection>
      </Card>
      <Card>
        <CardSection>
          <p className="text-xs font-medium text-muted-foreground">
            Fixed by pi · last 7 days
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            {data.fixed_recently.total}
          </p>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {latest
              ? `Latest: ${latest.what ?? latest.check ?? "a fix"} · ${timeAgo(latest.at)}`
              : "Nothing needed fixing."}
          </p>
        </CardSection>
      </Card>
    </div>
  );
}

const SERIES = [
  { key: "replies", label: "Replies sent", color: "var(--accent)" },
  { key: "held", label: "Held back / failed", color: "var(--warning)" },
  { key: "failed_sends", label: "Failed sends", color: "var(--danger)" },
  { key: "fixes", label: "Fixed by pi", color: "var(--success)" },
] as const;

/** The last 7 days as grouped bars: one group per day, one bar per series. */
function Trends({ data }: { data: Health }) {
  const days = data.trends;
  const max = Math.max(1, ...days.flatMap((d) => SERIES.map((s) => d[s.key])));
  const empty = days.every((d) => SERIES.every((s) => !d[s.key]));
  return (
    <Card>
      <CardSection className="space-y-3">
        <div>
          <h2 className="font-semibold">Last 7 days</h2>
          <p className="text-xs text-muted-foreground">
            Replies pi sent, replies held back or failed, messages that failed
            to send, and fixes pi made itself.
          </p>
        </div>
        {empty ? (
          <p className="text-sm text-muted-foreground">
            No activity in the last 7 days.
          </p>
        ) : (
          <>
            <div
              className="grid h-40 items-end gap-2"
              style={{
                gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`,
              }}
              role="img"
              aria-label={days
                .map(
                  (d) =>
                    `${dayLabel(d.day)}: ${SERIES.map((s) => `${d[s.key]} ${s.label.toLowerCase()}`).join(", ")}`,
                )
                .join("; ")}
            >
              {days.map((d) => (
                <div key={d.day} className="flex h-full flex-col">
                  <div className="flex flex-1 items-end justify-center gap-0.5">
                    {SERIES.map((s) => (
                      <span
                        key={s.key}
                        className="w-full max-w-3 rounded-t-sm"
                        style={{
                          height: `${(d[s.key] / max) * 100}%`,
                          minHeight: d[s.key] ? 2 : 0,
                          background: s.color,
                        }}
                        title={`${s.label}: ${d[s.key]}`}
                      />
                    ))}
                  </div>
                  <span className="mt-1 truncate text-center text-[11px] text-muted-foreground">
                    {dayLabel(d.day)}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {SERIES.map((s) => (
                <span key={s.key} className="inline-flex items-center gap-1.5">
                  <span
                    className="inline-block size-2.5 rounded-sm"
                    style={{ background: s.color }}
                  />
                  {s.label} ·{" "}
                  {days.reduce((n, d) => n + d[s.key], 0).toLocaleString("en")}
                </span>
              ))}
            </div>
          </>
        )}
      </CardSection>
    </Card>
  );
}

function Checks({ data, manage }: { data: Health; manage: boolean }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {data.areas.map((area) => {
        const rows = data.checks.filter((c) => c.area === area);
        if (!rows.length) return null;
        return (
          <Card key={area}>
            <div className="px-5 pt-5 sm:px-6">
              <h2 className="font-semibold">{area}</h2>
            </div>
            <div className="divide-y divide-border pb-1">
              {rows.map((check) => (
                <CheckRow key={check.key} check={check} manage={manage} />
              ))}
              {area === "API" ? (
                <p className="px-5 py-2.5 text-xs text-muted-foreground sm:px-6">
                  The server&apos;s own errors and slow pages are only written
                  to its logs, so they aren&apos;t counted here.
                </p>
              ) : null}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function CheckRow({ check, manage }: { check: Check; manage: boolean }) {
  const fix = useAction(
    () => post<Health>(`/pi/health/fix/${encodeURIComponent(check.key)}`),
    { invalidate: [KEY], success: "Done. pi is on it." },
  );
  return (
    <div className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-start sm:justify-between sm:px-6">
      <div className="flex min-w-0 gap-2.5">
        <span
          className={cn(
            "mt-1.5 size-2 shrink-0 rounded-full",
            DOT[check.status] ?? "bg-warning",
          )}
          title={STATUS_LABEL[check.status]}
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-sm font-medium">
            <span className="sr-only">{STATUS_LABEL[check.status]}: </span>
            {check.title}
          </p>
          {check.detail ? (
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
              {check.detail}
            </p>
          ) : null}
        </div>
      </div>
      <div className="shrink-0 ps-4 sm:ps-0">
        {check.fix === "auto" && check.last_fixed_at ? (
          <Badge tone="success">
            Auto-fixed {timeAgo(check.last_fixed_at)}
          </Badge>
        ) : check.fix === "auto" && check.status !== "ok" ? (
          <Badge tone="info">pi fixes this</Badge>
        ) : check.fix === "button" && manage ? (
          <Button
            size="sm"
            variant="secondary"
            loading={fix.isPending}
            onClick={() => fix.mutate(undefined)}
          >
            {check.action ?? "Fix now"}
          </Button>
        ) : check.fix === "settings" && check.href ? (
          <Button size="sm" variant="ghost" asChild>
            <Link href={page(check.href)}>
              Open <ArrowRight className="size-4 rtl:rotate-180" aria-hidden />
            </Link>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function SelfTests({
  data,
  manage,
  running,
  onRun,
}: {
  data: Health;
  manage: boolean;
  running: boolean;
  onRun: () => void;
}) {
  const tests = data.self_tests;
  const rates = tests.daily
    .filter((d) => d.rate !== null)
    .map((d) => d.rate as number);
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 gap-2">
            <FlaskConical
              className="mt-0.5 size-5 shrink-0 text-accent"
              aria-hidden
            />
            <div className="min-w-0">
              <h2 className="font-semibold">Self-tests</h2>
              <p className="text-xs text-muted-foreground">
                pi sends itself a few typical customer messages in a sandbox
                (nothing reaches a customer) and checks each reply by fixed
                rules.
              </p>
            </div>
          </div>
          {manage ? (
            <Button
              size="sm"
              variant="secondary"
              loading={running}
              onClick={onRun}
              className="shrink-0"
            >
              Run tests now
            </Button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span>
            <span className="text-2xl font-semibold tabular-nums">
              {tests.pass_rate === null ? "–" : `${tests.pass_rate}%`}
            </span>{" "}
            <span className="text-muted-foreground">
              passed ({tests.passed}/{tests.total})
            </span>
          </span>
          <span className="text-xs text-muted-foreground">
            {tests.last_run_at
              ? `Last run ${timeAgo(tests.last_run_at)}`
              : "Not run yet. pi runs them once a day."}
          </span>
          {rates.length > 1 ? <Sparkline values={rates} /> : null}
        </div>
        {tests.scenarios.length > 0 ? (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {tests.scenarios.map((s) => (
              <ScenarioRow key={s.key} scenario={s} />
            ))}
          </ul>
        ) : null}
      </CardSection>
    </Card>
  );
}

/** Pass rate over the last days (0-100), as a small line. */
function Sparkline({ values }: { values: number[] }) {
  const W = 120;
  const H = 28;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - (Math.max(0, Math.min(100, v)) / 100) * (H - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-7 w-32"
      role="img"
      aria-label={`Pass rate, last days: ${values.join("%, ")}%`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--success)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ScenarioRow({ scenario: s }: { scenario: Scenario }) {
  return (
    <li className="flex gap-2.5 px-3 py-2.5">
      {s.passed === true ? (
        <CheckCircle2
          className="mt-0.5 size-4 shrink-0 text-success"
          aria-label="Passed"
        />
      ) : s.passed === false ? (
        <XCircle
          className="mt-0.5 size-4 shrink-0 text-danger"
          aria-label="Failed"
        />
      ) : (
        <span
          className="mt-1.5 size-2 shrink-0 rounded-full bg-border-strong"
          aria-label="Not tested"
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {s.title}{" "}
          <span className="font-normal text-muted-foreground" data-user-text>
            · “{s.message}”
          </span>
        </p>
        {s.passed !== true ? (
          <p className="text-xs text-muted-foreground">
            {s.reason}
            {s.retried ? " (pi fixed what it could and tested again)" : ""}
          </p>
        ) : null}
        {s.reply ? (
          <p
            className="mt-1 line-clamp-2 border-s-2 border-border ps-2 text-xs text-foreground-secondary"
            data-user-text
          >
            {s.reply}
          </p>
        ) : null}
        {s.passed === false && s.hint ? (
          <p className="mt-1 text-xs">
            {s.hint}{" "}
            {s.href ? (
              <Link
                href={page(s.href)}
                className="font-medium text-accent hover:underline"
              >
                Open
              </Link>
            ) : null}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function Learning({ data }: { data: Health }) {
  const l = data.learning;
  return (
    <Card>
      <CardSection className="space-y-3">
        <div className="flex gap-2">
          <Sparkles
            className="mt-0.5 size-5 shrink-0 text-accent"
            aria-hidden
          />
          <div className="min-w-0">
            <h2 className="font-semibold">Questions pi couldn&apos;t answer</h2>
            <p className="text-xs text-muted-foreground">
              pi learns from your answers and its own tests: teach it once and
              it uses the answer in every chat. (No AI model is retrained.)
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="success">
            {l.answers_learned_30d} team answers became knowledge (30 days)
          </Badge>
          {l.drafts_waiting > 0 ? (
            <Link href="/my-pi/knowledge">
              <Badge tone="accent">
                {l.drafts_waiting} drafts waiting for your approval
              </Badge>
            </Link>
          ) : null}
          {l.open_questions > 0 ? (
            <Link href="/requests">
              <Badge tone="warning">
                {l.open_questions} questions waiting in Requests
              </Badge>
            </Link>
          ) : null}
        </div>
        {data.gaps.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No unanswered questions in the last 30 days.
          </p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {data.gaps.map((gap) => (
              <li
                key={gap.question}
                className="flex flex-col gap-1.5 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="text-sm" data-user-text>
                    {gap.question}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Asked in {gap.asked} chat{gap.asked === 1 ? "" : "s"} ·{" "}
                    {timeAgo(gap.last_asked_at)}
                  </p>
                </div>
                <Button size="sm" variant="secondary" asChild>
                  <Link href={page(gap.href)}>
                    <BookOpen className="size-4" aria-hidden /> Teach pi
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardSection>
    </Card>
  );
}

function dayLabel(day: string) {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en", {
    weekday: "short",
    day: "numeric",
  });
}
