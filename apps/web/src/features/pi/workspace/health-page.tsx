"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FlaskConical,
  Sparkles,
  Wrench,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardBody, CardHeader } from "@/components/ui/display";
import { ChartCard, Sparkline } from "@/components/app/charts";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { ErrorState } from "@/components/app/states";
import { PageSkeleton } from "@/components/app/page-skeleton";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { formatTime, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  piHealthService,
  type HealthCheck,
  type HealthStatus,
  type PiHealth,
  type SelfTestScenario,
} from "../health-service";

const LIVE_EVERY_MS = 30_000;
const KEY = ["pi", "health"];

const DOT: Record<HealthStatus, string> = {
  problem: "bg-danger",
  warning: "bg-warning",
  fixed: "bg-success",
  ok: "bg-success/60",
};
const STATUS_LABEL: Record<HealthStatus, string> = {
  problem: "Needs you",
  warning: "Worth a look",
  fixed: "Fixed by pi",
  ok: "OK",
};

export function HealthPage() {
  return (
    <RequirePermission permission="pi.read" area="pi">
      <HealthView />
    </RequirePermission>
  );
}

function HealthView() {
  const { can } = useSession();
  const manage = can("pi.settings.manage");
  const query = useScopedQuery(KEY, piHealthService.get, {
    // Live: what pi finds or fixes shows up while the page is open.
    refetchInterval: LIVE_EVERY_MS,
  });
  const heal = useScopedMutation(piHealthService.heal, {
    invalidate: [KEY],
    success: "pi ran its fixes",
  });
  const selfTest = useScopedMutation(piHealthService.selfTest, {
    invalidate: [KEY],
    success: "Self-tests finished",
  });
  const data = query.data;
  return (
    <PageShell>
      <PageHeader
        title="pi Health"
        description="pi checks its own set-up and work, fixes the safe things by itself, and tells you what needs you."
        actions={
          <>
            <LiveBadge
              fetching={query.isFetching}
              updatedAt={query.dataUpdatedAt}
            />
            {manage && (
              <Button
                size="sm"
                variant="secondary"
                loading={heal.isPending}
                onClick={() => heal.mutate(undefined)}
              >
                <Wrench aria-hidden="true" /> Fix now
              </Button>
            )}
          </>
        }
      />
      {query.isError && !data ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !data ? (
        <PageSkeleton variant="dashboard" />
      ) : (
        <div className="space-y-4">
          <Summary data={data} />
          <ChartCard
            title="Last 7 days"
            description="Replies pi sent, replies held back or failed, messages that failed to send, and fixes pi made itself."
            data={data.trends.map((d) => ({ ...d, day: dayLabel(d.day) }))}
            xKey="day"
            xLabel="Day"
            kind="bar"
            height={200}
            series={[
              { key: "replies", label: "Replies sent" },
              { key: "held", label: "Held back / failed" },
              { key: "failed_sends", label: "Failed sends" },
              { key: "fixes", label: "Fixed by pi" },
            ]}
            emptyMessage="No activity in the last 7 days."
          />
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
    </PageShell>
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
      className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground"
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
      {fetching || !updatedAt ? "updating…" : formatTime(new Date(updatedAt))}
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

function Summary({ data }: { data: PiHealth }) {
  const counts = data.counts;
  return (
    <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
      <Card>
        <CardBody className="flex items-center gap-4 pt-4">
          <ScoreRing score={data.score} />
          <div className="min-w-0">
            <p className="text-base font-semibold text-foreground">
              {data.verdict}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(counts.problem ?? 0) > 0 && (
                <Badge tone="danger">{counts.problem} need you</Badge>
              )}
              {(counts.warning ?? 0) > 0 && (
                <Badge tone="warning">{counts.warning} worth a look</Badge>
              )}
              {(counts.fixed ?? 0) > 0 && (
                <Badge tone="success">{counts.fixed} fixed just now</Badge>
              )}
              <Badge tone="neutral">{counts.ok ?? 0} OK</Badge>
            </div>
          </div>
        </CardBody>
      </Card>
      <Card>
        <CardBody className="pt-4">
          <p className="text-xs font-medium text-muted-foreground">
            Fixed by pi · last 7 days
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
            {data.fixed_recently.total}
          </p>
          {data.fixed_recently.items[0] ? (
            <p className="mt-1 truncate text-xs text-muted-foreground">
              Latest: {data.fixed_recently.items[0].what} ·{" "}
              {relativeTime(data.fixed_recently.items[0].at)}
            </p>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">
              Nothing needed fixing.
            </p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function Checks({ data, manage }: { data: PiHealth; manage: boolean }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {data.areas.map((area) => {
        const rows = data.checks.filter((c) => c.area === area);
        if (!rows.length) return null;
        return (
          <Card key={area}>
            <CardHeader title={area} />
            <CardBody className="space-y-0 divide-y divide-border p-0 pb-1">
              {rows.map((check) => (
                <CheckRow key={check.key} check={check} manage={manage} />
              ))}
              {area === "API" && (
                <p className="px-4 py-2.5 text-xs text-muted-foreground">
                  The server&apos;s own errors (HTTP 5xx) and slow pages are
                  only written to its logs, so they aren&apos;t counted here.
                </p>
              )}
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}

function CheckRow({ check, manage }: { check: HealthCheck; manage: boolean }) {
  const fix = useScopedMutation(() => piHealthService.fix(check.key), {
    invalidate: [KEY],
    success: "Done. pi is on it.",
  });
  return (
    <div className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 gap-2.5">
        <span
          className={cn(
            "mt-1.5 size-2 shrink-0 rounded-full",
            DOT[check.status],
          )}
          title={STATUS_LABEL[check.status]}
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-[13.5px] font-medium text-foreground">
            <span className="sr-only">{STATUS_LABEL[check.status]}: </span>
            {check.title}
          </p>
          {check.detail && (
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
              {check.detail}
            </p>
          )}
        </div>
      </div>
      <div className="shrink-0 pl-4.5 sm:pl-0">
        {check.fix === "auto" && check.last_fixed_at ? (
          <Badge tone="success">
            Auto-fixed {formatTime(check.last_fixed_at)}
          </Badge>
        ) : check.fix === "auto" && check.status !== "ok" ? (
          <Badge tone="info">pi fixes this</Badge>
        ) : check.fix === "button" && manage ? (
          <Button
            size="xs"
            variant="secondary"
            loading={fix.isPending}
            onClick={() => fix.mutate(undefined)}
          >
            {check.action ?? "Fix now"}
          </Button>
        ) : check.fix === "settings" && check.href ? (
          <Button size="xs" variant="ghost" asChild>
            <Link href={check.href}>
              Open <ArrowRight aria-hidden="true" />
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
  data: PiHealth;
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
      <CardHeader
        icon={<FlaskConical />}
        title="Self-tests"
        description="pi sends itself a few typical customer messages in a sandbox (nothing reaches a customer) and checks each reply by fixed rules."
        actions={
          manage && (
            <Button
              size="sm"
              variant="secondary"
              loading={running}
              onClick={onRun}
            >
              Run tests now
            </Button>
          )
        }
      />
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span>
            <span className="text-2xl font-semibold tabular-nums text-foreground">
              {tests.pass_rate === null ? "–" : `${tests.pass_rate}%`}
            </span>{" "}
            <span className="text-muted-foreground">
              passed ({tests.passed}/{tests.total})
            </span>
          </span>
          <span className="text-xs text-muted-foreground">
            {tests.last_run_at
              ? `Last run ${relativeTime(tests.last_run_at)}`
              : "Not run yet. pi runs them once a day."}
          </span>
          {rates.length > 1 && (
            <span className="w-32" title="Pass rate, last 7 days">
              <Sparkline values={rates} color="var(--success)" />
            </span>
          )}
        </div>
        {tests.scenarios.length > 0 && (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {tests.scenarios.map((s) => (
              <ScenarioRow key={s.key} scenario={s} />
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function ScenarioRow({ scenario: s }: { scenario: SelfTestScenario }) {
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
          className="mt-1.5 size-2 shrink-0 rounded-full bg-border"
          aria-label="Not tested"
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium text-foreground">
          {s.title}{" "}
          <span className="font-normal text-muted-foreground">
            · “{s.message}”
          </span>
        </p>
        {s.passed !== true && (
          <p className="text-xs text-muted-foreground">
            {s.reason}
            {s.retried && " (pi fixed what it could and tested again)"}
          </p>
        )}
        {s.reply && (
          <p className="mt-1 line-clamp-2 border-l-2 border-border pl-2 text-xs text-foreground-secondary">
            {s.reply}
          </p>
        )}
        {s.passed === false && s.hint && (
          <p className="mt-1 text-xs">
            {s.hint}{" "}
            {s.href && (
              <Link
                href={s.href}
                className="font-medium text-primary hover:underline"
              >
                Open
              </Link>
            )}
          </p>
        )}
      </div>
    </li>
  );
}

function Learning({ data }: { data: PiHealth }) {
  const l = data.learning;
  return (
    <Card>
      <CardHeader
        icon={<Sparkles />}
        title="Questions pi couldn't answer"
        description="pi learns from your answers and its own tests: teach it once and it uses the answer in every chat. (No AI model is retrained.)"
      />
      <CardBody className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="success">
            {l.answers_learned_30d} team answers became knowledge (30 days)
          </Badge>
          {l.drafts_waiting > 0 && (
            <Badge tone="pi">
              {l.drafts_waiting} drafts waiting for your approval in the pi app
            </Badge>
          )}
          {l.open_questions > 0 && (
            <Link href="/pi/requests">
              <Badge tone="warning">
                {l.open_questions} questions waiting in Requests
              </Badge>
            </Link>
          )}
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
                  <p className="text-[13.5px] text-foreground">
                    {gap.question}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Asked in {gap.asked} chat{gap.asked === 1 ? "" : "s"} ·{" "}
                    {relativeTime(gap.last_asked_at)}
                  </p>
                </div>
                <Button size="xs" variant="soft" asChild>
                  <Link href={gap.href}>
                    <BookOpen aria-hidden="true" /> Teach pi
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function dayLabel(day: string) {
  const date = new Date(`${day}T00:00:00`);
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
  });
}
