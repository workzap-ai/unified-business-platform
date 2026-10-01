"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronRight,
  Lightbulb,
  Loader2,
  Printer,
  RefreshCw,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { ChartCard } from "@/components/app/charts";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { useScopedQuery } from "@/hooks/use-scoped";
import { errorMessage } from "@/services/api-client";
import {
  agentService,
  type AnalyticsBlock,
  type ChartSpec,
  type Kpi,
  type TeamBrief,
} from "./service";

// Pages a brief or table may link to; anything else renders as plain text.
const pages = new Set([
  "/customers",
  "/sales",
  "/quotes",
  "/orders",
  "/billing",
  "/finance",
  "/inventory",
  "/hr",
  "/workspace-agent",
  "/pi/inbox",
  "/pi/handoffs",
  "/settings/integrations",
]);

function formatter(unit: Kpi["unit"], currency: string | null) {
  return (value: number) => {
    if (unit === "percent") return `${value.toFixed(1)}%`;
    if (unit === "days") return `${value.toFixed(0)} days`;
    const big = Math.abs(value) >= 10_000;
    if (unit === "currency" && currency)
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
        notation: big ? "compact" : "standard",
        maximumFractionDigits: big ? 1 : 0,
      }).format(value);
    return new Intl.NumberFormat(undefined, {
      notation: big ? "compact" : "standard",
      maximumFractionDigits: 1,
    }).format(value);
  };
}

export function KpiGrid({ kpis }: { kpis: Kpi[] }) {
  if (!kpis.length) return null;
  return (
    <MetricGrid className="md:grid-cols-2 xl:grid-cols-4">
      {kpis.map((k) => (
        <MetricCard
          key={k.key}
          label={k.label}
          value={formatter(k.unit, k.currency)(k.value)}
          change={
            k.change_pct === null
              ? undefined
              : {
                  value: k.change_pct / 100,
                  label: k.compare ?? "vs last month",
                  goodWhen: k.good,
                }
          }
          detail={k.detail || undefined}
        />
      ))}
    </MetricGrid>
  );
}

function Chart({ chart }: { chart: ChartSpec }) {
  return (
    <ChartCard
      title={chart.title}
      description={chart.description || undefined}
      data={chart.data}
      xKey={chart.x_key}
      xLabel={chart.x_label}
      series={chart.series}
      kind={chart.kind}
      stacked={chart.stacked}
      format={formatter(chart.unit, chart.currency)}
      height={200}
    />
  );
}

const cellText = (value: unknown) =>
  value === null || value === undefined
    ? "—"
    : typeof value === "number"
      ? value.toLocaleString(undefined, { maximumFractionDigits: 1 })
      : String(value);

export function AnalyticsView({
  block,
  showKpis = true,
}: {
  block: AnalyticsBlock;
  showKpis?: boolean;
}) {
  if (!block.checked_areas.length)
    return (
      <p className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
        Your role doesn&apos;t include the areas needed for this analysis.
      </p>
    );
  return (
    <section className="space-y-4" aria-label={`${block.topic} analytics`}>
      {showKpis && <KpiGrid kpis={block.kpis} />}
      {block.notes.map((note) => (
        <p key={note} className="text-xs text-muted-foreground">
          {note}
        </p>
      ))}
      <div className="grid gap-4 xl:grid-cols-2">
        {block.charts.map((chart) => (
          <Chart key={chart.id} chart={chart} />
        ))}
      </div>
      {block.tables.map((table) => (
        <div
          key={table.title}
          className="rounded-xl border border-border bg-surface p-4"
        >
          <h3 className="text-sm font-semibold">{table.title}</h3>
          {table.note && (
            <p className="mt-0.5 text-xs text-muted-foreground">{table.note}</p>
          )}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  {table.columns.map((c) => (
                    <th
                      key={c}
                      scope="col"
                      className="px-2 py-1.5 text-left font-medium capitalize text-muted-foreground"
                    >
                      {c.replaceAll("_", " ")}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {table.columns.map((c) => (
                      <td key={c} className="tabular px-2 py-1.5">
                        {cellText(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}

const levelTone = {
  high: "success",
  medium: "warning",
  low: "neutral",
} as const;

function PageLink({ page }: { page: string | null }) {
  if (!page || !pages.has(page)) return null;
  return (
    <Link className="text-xs text-primary underline" href={page}>
      Open
    </Link>
  );
}

export function BriefCard({ team }: { team: TeamBrief }) {
  const { brief } = team;
  return (
    <article
      className="space-y-4 rounded-2xl border border-primary/25 bg-surface p-4 shadow-sm"
      aria-label="Decision brief"
    >
      <header className="flex flex-wrap items-center gap-2">
        <Brain className="size-4 text-primary" aria-hidden="true" />
        <h3 className="text-sm font-semibold">Decision brief</h3>
        <Badge tone={team.mode === "ai" ? "primary" : "neutral"}>
          {team.mode === "ai" ? "AI team" : "Rule-based"}
        </Badge>
        <Badge tone={levelTone[brief.confidence]}>
          {brief.confidence} confidence
        </Badge>
      </header>
      <div className="rounded-xl bg-primary/5 p-3">
        <p className="text-xs font-medium tracking-wide text-primary uppercase">
          Recommendation
        </p>
        <p className="mt-1 text-sm font-semibold" dir="auto">
          {brief.recommendation}
        </p>
      </div>
      <p className="text-sm leading-6 whitespace-pre-wrap" dir="auto">
        {brief.answer}
      </p>
      {!!brief.options.length && (
        <div className="grid gap-3 md:grid-cols-3">
          {brief.options.map((o) => (
            <div key={o.name} className="rounded-xl border border-border p-3">
              <p className="text-sm font-semibold" dir="auto">
                {o.name}
              </p>
              <p className="mt-1 text-xs text-muted-foreground" dir="auto">
                {o.expected_impact}
              </p>
              <ul className="mt-2 space-y-1 text-xs">
                {o.pros.map((p) => (
                  <li key={p} className="flex gap-1.5" dir="auto">
                    <span className="text-success" aria-label="Pro">
                      +
                    </span>
                    {p}
                  </li>
                ))}
                {o.cons.map((c) => (
                  <li key={c} className="flex gap-1.5" dir="auto">
                    <span className="text-danger" aria-label="Con">
                      −
                    </span>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {!!brief.next_steps.length && (
        <div>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold">
            <CheckCircle2
              className="size-3.5 text-success"
              aria-hidden="true"
            />
            Next steps
          </h4>
          <ol className="space-y-2">
            {brief.next_steps.map((s, i) => (
              <li
                key={`${s.action}-${i}`}
                className="flex items-start justify-between gap-3 rounded-lg border border-border p-2.5 text-sm"
              >
                <div className="min-w-0" dir="auto">
                  <p className="font-medium">
                    {i + 1}. {s.action}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {s.why}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="text-[11px] text-muted-foreground">
                    {s.impact} impact · {s.effort} effort
                  </span>
                  <PageLink page={s.page} />
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
      {!!brief.risks.length && (
        <div>
          <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold">
            <AlertTriangle
              className="size-3.5 text-warning"
              aria-hidden="true"
            />
            Risks
          </h4>
          <ul className="list-disc space-y-1 pl-5 text-sm" dir="auto">
            {brief.risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {!!team.specialists.length && (
        <details className="rounded-xl border border-border p-3">
          <summary className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold">
            <Users className="size-3.5" aria-hidden="true" />
            What each specialist found ({team.specialists.length})
          </summary>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {team.specialists.map((s) => (
              <div key={s.role} className="rounded-lg bg-surface-muted p-3">
                <p className="text-xs font-semibold">{s.title}</p>
                <p className="mt-1 text-sm" dir="auto">
                  {s.headline}
                </p>
                <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                  {[...s.findings, ...s.opportunities].map((f) => (
                    <li key={f} dir="auto">
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      )}
      {!!brief.assumptions.length && (
        <p className="text-[11px] text-muted-foreground" dir="auto">
          Based on: {brief.assumptions.join(" · ")}
        </p>
      )}
    </article>
  );
}

const PERIODS = [6, 12, 24] as const;
const QUESTIONS = [
  "What should I focus on this month?",
  "Can I afford to hire one more person?",
  "Where am I losing money?",
];

export function InsightsBoard({
  onAsk,
  busy,
}: {
  onAsk: (question: string) => void;
  busy: boolean;
}) {
  const [months, setMonths] = useState<(typeof PERIODS)[number]>(12);
  const [question, setQuestion] = useState("");
  const [team, setTeam] = useState<TeamBrief | null>(null);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState("");
  const report = useScopedQuery(
    ["workspace-agent", "analytics", "report", months],
    () => agentService.analytics("report", months),
    { retry: false },
  );
  const ask = async (q: string) => {
    if (!q.trim() || thinking) return;
    setThinking(true);
    setError("");
    try {
      setTeam(await agentService.team(q.trim()));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setThinking(false);
    }
  };
  return (
    <div className="insights-print space-y-5">
      <style>{`@media print {
  body * { visibility: hidden; }
  .insights-print, .insights-print * { visibility: visible; }
  .insights-print { position: absolute; inset: 0 auto auto 0; width: 100%; }
  .insights-noprint { display: none !important; }
}`}</style>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Business insights</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Exact figures from the areas your role can see
            {report.data
              ? ` · ${report.data.currency} · checked ${report.data.checked_areas.join(", ") || "nothing"}`
              : ""}
            . Forecasts are estimates with a likely range.
          </p>
        </div>
        <div className="insights-noprint flex items-center gap-2">
          <div
            className="flex rounded-lg border border-border p-0.5"
            role="group"
            aria-label="Period"
          >
            {PERIODS.map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={months === p}
                onClick={() => setMonths(p)}
                className={`rounded-md px-2.5 py-1 text-xs ${months === p ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground"}`}
              >
                {p}m
              </button>
            ))}
          </div>
          <Button
            variant="secondary"
            size="sm"
            aria-label="Refresh insights"
            disabled={report.isFetching}
            onClick={() => void report.refetch()}
          >
            <RefreshCw
              className={`size-3.5 ${report.isFetching ? "animate-spin" : ""}`}
            />
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => window.print()}
            disabled={!report.data}
          >
            <Printer className="mr-1 size-3.5" />
            Save as PDF
          </Button>
        </div>
      </div>

      <form
        className="insights-noprint rounded-2xl border border-border bg-surface p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
      >
        <label
          htmlFor="team-question"
          className="flex items-center gap-1.5 text-sm font-semibold"
        >
          <Lightbulb className="size-4 text-primary" aria-hidden="true" />
          Ask your advisory team
        </label>
        <p className="mt-1 text-xs text-muted-foreground">
          Sales, finance, operations, support, people and an analyst review your
          data in parallel; a strategist turns it into one recommendation.
        </p>
        <div className="mt-3 flex gap-2">
          <input
            id="team-question"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            maxLength={1000}
            placeholder="e.g. Should I run a discount campaign next month?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            dir="auto"
          />
          <Button type="submit" disabled={thinking || !question.trim()}>
            {thinking ? <Loader2 className="size-4 animate-spin" /> : "Ask"}
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              disabled={thinking}
              onClick={() => {
                setQuestion(q);
                void ask(q);
              }}
              className="inline-flex items-center rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-surface-muted disabled:opacity-50"
            >
              {q}
              <ChevronRight className="ml-0.5 size-3" />
            </button>
          ))}
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onAsk(
                "Give me a full business report with forecasts and what to do next.",
              )
            }
            className="inline-flex items-center rounded-full border border-primary/30 px-2.5 py-1 text-xs text-primary hover:bg-primary/5 disabled:opacity-50"
          >
            Discuss in chat
            <ChevronRight className="ml-0.5 size-3" />
          </button>
        </div>
        {thinking && (
          <p role="status" className="mt-3 text-xs text-muted-foreground">
            The team is reviewing your numbers…
          </p>
        )}
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
      </form>
      {team && <BriefCard team={team} />}

      {report.isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Crunching your numbers…
        </p>
      ) : report.error ? (
        <p role="alert" className="text-sm text-danger">
          {errorMessage(report.error)}
        </p>
      ) : (
        <AnalyticsView block={report.data} />
      )}
    </div>
  );
}
