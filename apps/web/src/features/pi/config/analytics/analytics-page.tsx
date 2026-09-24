"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Bot,
  Coins,
  MessageSquare,
  MessagesSquare,
  Percent,
  Shuffle,
  UserCheck,
  Hash,
} from "lucide-react";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  SegmentedList,
  SegmentedTrigger,
  Skeleton,
  Tabs,
} from "@/components/ui/display";
import { Progress } from "@/components/ui/controls";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ChartCard, DistributionBar } from "@/components/app/charts";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { piService } from "../../service";
import type { AnalyticsRange, PiAnalytics, ToolDefinition } from "../../types";
import {
  AGENT_LABELS,
  HANDOFF_REASON_LABELS,
  PROVIDER_LABELS,
  SampleDataNote,
  SubNav,
  formatLatency,
  humanizeError,
  piKeys,
} from "../shared";
import { ANALYTICS_SECTIONS, type AnalyticsSection } from "../sections";

const RANGES: AnalyticsRange[] = [7, 30, 90];
const n = (v: number) => formatNumber(v);
const compact = (v: number) => formatNumber(v, true);
const usd = (v: number) => formatMoney(v, "USD");

export function AnalyticsPage({ section }: { section?: AnalyticsSection }) {
  return (
    <RequirePermission permission="pi.analytics.read" area="PI analytics">
      <Analytics section={section} />
    </RequirePermission>
  );
}

function Analytics({ section }: { section?: AnalyticsSection }) {
  const [state, set] = useUrlState({ range: "30" });
  const range: AnalyticsRange = RANGES.includes(
    Number(state.range) as AnalyticsRange,
  )
    ? (Number(state.range) as AnalyticsRange)
    : 30;
  const analytics = useScopedQuery(piKeys.analytics(range), () =>
    piService.analytics(range),
  );
  const tools = useScopedQuery(piKeys.tools, () => piService.tools(), {
    enabled: section === "tool-activity",
  });
  const qs = range === 30 ? "" : `?range=${range}`;
  const title = section
    ? (ANALYTICS_SECTIONS.find((s) => s.slug === section)?.label ?? "Analytics")
    : "Analytics";

  const data = analytics.data;
  const empty =
    data && data.totals.conversations === 0 && data.totals.messages === 0;

  return (
    <PageShell>
      <PageHeader
        title={title === "Analytics" ? "Analytics" : `Analytics · ${title}`}
        description="How PI is performing: volume, quality, AI usage and escalations."
        actions={
          <Tabs value={String(range)} onValueChange={(v) => set({ range: v })}>
            <SegmentedList aria-label="Date range">
              {RANGES.map((r) => (
                <SegmentedTrigger key={r} value={String(r)}>
                  {r} days
                </SegmentedTrigger>
              ))}
            </SegmentedList>
          </Tabs>
        }
      />
      <SubNav
        label="Analytics sections"
        items={[
          { href: `/pi/analytics${qs}`, label: "Overview", exact: true },
          ...ANALYTICS_SECTIONS.map((s) => ({
            href: `/pi/analytics/${s.slug}${qs}`,
            label: s.label,
          })),
        ]}
      />
      <SampleDataNote className="-mt-2 mb-4" />

      {analytics.isError ? (
        <Card>
          <ErrorState
            error={analytics.error}
            onRetry={() => void analytics.refetch()}
          />
        </Card>
      ) : empty ? (
        <Card>
          <EmptyState
            tone="pi"
            icon={BarChart3}
            title="No PI activity in this period"
            description="Analytics appear once customers start messaging your connected WhatsApp number."
            action={
              <Link
                href="/pi/whatsapp"
                className="text-[13px] font-medium text-primary hover:underline"
              >
                Check WhatsApp connection
              </Link>
            }
          />
        </Card>
      ) : !section ? (
        <Overview data={data} qs={qs} />
      ) : section === "conversations" ? (
        <Conversations data={data} />
      ) : section === "agent-runs" ? (
        <AgentRuns data={data} />
      ) : section === "ai-usage" ? (
        <AiUsage data={data} />
      ) : section === "fallbacks" ? (
        <Fallbacks data={data} />
      ) : section === "handoffs" ? (
        <Handoffs data={data} />
      ) : (
        <ToolActivity data={data} tools={tools.data} />
      )}
    </PageShell>
  );
}

function DetailsLink({ href }: { href: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline"
    >
      Details <ArrowRight className="size-3" aria-hidden="true" />
    </Link>
  );
}

function Overview({ data, qs }: { data?: PiAnalytics; qs: string }) {
  const loading = !data;
  const t = data?.totals;
  return (
    <div className="space-y-4">
      <MetricGrid>
        <MetricCard
          label="Conversations"
          icon={MessagesSquare}
          loading={loading}
          value={n(t?.conversations ?? 0)}
          href={`/pi/analytics/conversations${qs}`}
        />
        <MetricCard
          label="Messages"
          icon={MessageSquare}
          loading={loading}
          value={n(t?.messages ?? 0)}
          href={`/pi/analytics/conversations${qs}`}
        />
        <MetricCard
          label="AI responses"
          icon={Bot}
          tone="pi"
          loading={loading}
          value={n(t?.ai_responses ?? 0)}
          href={`/pi/analytics/agent-runs${qs}`}
        />
        <MetricCard
          label="Handoffs"
          icon={UserCheck}
          loading={loading}
          value={n(t?.handoffs ?? 0)}
          href={`/pi/analytics/handoffs${qs}`}
        />
        <MetricCard
          label="Fallbacks"
          icon={Shuffle}
          loading={loading}
          value={n(t?.fallbacks ?? 0)}
          href={`/pi/analytics/fallbacks${qs}`}
        />
        <MetricCard
          label="Failure rate"
          icon={Percent}
          loading={loading}
          tone={t && t.failure_rate > 0.05 ? "danger" : "default"}
          value={formatPercent(t?.failure_rate ?? 0, 1)}
          detail="of agent runs"
        />
        <MetricCard
          label="Tokens"
          icon={Hash}
          loading={loading}
          value={compact((t?.input_tokens ?? 0) + (t?.output_tokens ?? 0))}
          detail={
            t
              ? `${compact(t.input_tokens)} in · ${compact(t.output_tokens)} out`
              : undefined
          }
          href={`/pi/analytics/ai-usage${qs}`}
        />
        {t?.cost_estimate_usd != null && (
          <MetricCard
            label="Estimated AI cost"
            icon={Coins}
            value={usd(t.cost_estimate_usd)}
            detail={<Badge tone="outline">Estimate</Badge>}
            href={`/pi/analytics/ai-usage${qs}`}
          />
        )}
      </MetricGrid>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Conversations"
          description="Started vs resolved per day"
          data={data?.conversations}
          loading={loading}
          xKey="day"
          xLabel="Day"
          kind="line"
          height={180}
          series={[
            { key: "started", label: "Started" },
            { key: "resolved", label: "Resolved" },
          ]}
          actions={<DetailsLink href={`/pi/analytics/conversations${qs}`} />}
        />
        <ChartCard
          title="Messages"
          description="Inbound, AI and human replies"
          data={data?.messages}
          loading={loading}
          xKey="day"
          xLabel="Day"
          kind="bar"
          stacked
          height={180}
          series={[
            { key: "inbound", label: "Inbound" },
            { key: "outbound_ai", label: "AI replies" },
            { key: "outbound_human", label: "Human replies" },
          ]}
          actions={<DetailsLink href={`/pi/analytics/conversations${qs}`} />}
        />
        <ChartCard
          title="Fallbacks"
          description="Replies served by a fallback provider"
          data={data?.fallbacks}
          loading={loading}
          xKey="day"
          xLabel="Day"
          kind="bar"
          height={160}
          series={[{ key: "count", label: "Fallbacks" }]}
          actions={<DetailsLink href={`/pi/analytics/fallbacks${qs}`} />}
        />
        <ChartCard
          title="Handoffs"
          description="Opened vs resolved per day"
          data={data?.handoffs_by_day}
          loading={loading}
          xKey="day"
          xLabel="Day"
          kind="line"
          height={160}
          series={[
            { key: "opened", label: "Opened" },
            { key: "resolved", label: "Resolved" },
          ]}
          actions={<DetailsLink href={`/pi/analytics/handoffs${qs}`} />}
        />
      </div>
    </div>
  );
}

function TableCard({
  title,
  description,
  loading,
  children,
}: {
  title: string;
  description?: string;
  loading: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardBody>{loading ? <Skeleton className="h-48" /> : children}</CardBody>
    </Card>
  );
}

function SimpleTable({
  caption,
  headers,
  rows,
  empty = "No data for this period.",
}: {
  caption: string;
  headers: { label: string; align?: "right" }[];
  rows: { key: string; cells: React.ReactNode[] }[];
  empty?: string;
}) {
  if (!rows.length)
    return (
      <p className="py-6 text-center text-[13px] text-muted-foreground">
        {empty}
      </p>
    );
  return (
    <div className="scrollbar-thin overflow-x-auto">
      <table className="w-full text-[13px]">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border">
            {headers.map((h) => (
              <th
                key={h.label}
                scope="col"
                className={`px-2 py-1.5 text-xs font-medium whitespace-nowrap text-muted-foreground ${h.align === "right" ? "text-right" : "text-left"}`}
              >
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-b border-border last:border-0">
              {r.cells.map((c, i) => (
                <td
                  key={i}
                  className={`px-2 py-2 ${headers[i]?.align === "right" ? "tabular text-right" : ""}`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Conversations({ data }: { data?: PiAnalytics }) {
  const intents = [...(data?.intents ?? [])].sort((a, b) => b.count - a.count);
  const max = Math.max(1, ...intents.map((i) => i.count));
  const total = intents.reduce((s, i) => s + i.count, 0);
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Conversations"
          description="Started vs resolved per day"
          data={data?.conversations}
          loading={!data}
          xKey="day"
          xLabel="Day"
          kind="line"
          series={[
            { key: "started", label: "Started" },
            { key: "resolved", label: "Resolved" },
          ]}
        />
        <ChartCard
          title="Messages"
          description="Inbound and replies by sender"
          data={data?.messages}
          loading={!data}
          xKey="day"
          xLabel="Day"
          kind="bar"
          stacked
          series={[
            { key: "inbound", label: "Inbound" },
            { key: "outbound_ai", label: "AI replies" },
            { key: "outbound_human", label: "Human replies" },
          ]}
        />
      </div>
      <TableCard
        title="Intents"
        description="What customers asked about"
        loading={!data}
      >
        <SimpleTable
          caption="Intents"
          headers={[
            { label: "Intent" },
            { label: "Share" },
            { label: "Conversations", align: "right" },
          ]}
          rows={intents.map((i) => ({
            key: i.intent,
            cells: [
              <span key="i" className="whitespace-nowrap">
                {i.intent.replace(/_/g, " ")}
              </span>,
              <div key="b" className="flex min-w-32 items-center gap-2">
                <Progress
                  value={(i.count / max) * 100}
                  tone="pi"
                  className="flex-1"
                  aria-label={`${i.intent} share`}
                />
                <span className="tabular w-10 text-right text-xs text-muted-foreground">
                  {total ? formatPercent(i.count / total) : "—"}
                </span>
              </div>,
              n(i.count),
            ],
          }))}
        />
      </TableCard>
    </div>
  );
}

function AgentRuns({ data }: { data?: PiAnalytics }) {
  const rows = (data?.runs_by_agent ?? []).map((r) => ({
    agent: AGENT_LABELS[r.agent],
    runs: r.runs,
    failures: r.failures,
  }));
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Runs by agent"
          description="Runs and failures in the period"
          data={rows}
          loading={!data}
          xKey="agent"
          xLabel="Agent"
          kind="bar"
          series={[
            { key: "runs", label: "Runs" },
            { key: "failures", label: "Failures" },
          ]}
        />
        <ChartCard
          title="Response latency"
          description="Median (p50) and 95th percentile per day"
          data={data?.latency}
          loading={!data}
          xKey="day"
          xLabel="Day"
          kind="line"
          format={formatLatency}
          series={[
            { key: "p50", label: "p50" },
            { key: "p95", label: "p95" },
          ]}
        />
      </div>
      <TableCard title="Agent reliability" loading={!data}>
        <SimpleTable
          caption="Agent reliability"
          headers={[
            { label: "Agent" },
            { label: "Runs", align: "right" },
            { label: "Failures", align: "right" },
            { label: "Failure rate", align: "right" },
          ]}
          rows={rows.map((r) => ({
            key: r.agent,
            cells: [
              r.agent,
              n(r.runs),
              n(r.failures),
              r.runs ? formatPercent(r.failures / r.runs, 1) : "—",
            ],
          }))}
        />
      </TableCard>
    </div>
  );
}

function AiUsage({ data }: { data?: PiAnalytics }) {
  return (
    <div className="space-y-4">
      <ChartCard
        title="Provider usage"
        description="AI requests per provider per day"
        data={data?.provider_usage}
        loading={!data}
        xKey="day"
        xLabel="Day"
        kind="bar"
        stacked
        series={(["openai", "gemini", "groq"] as const).map((p) => ({
          key: p,
          label: PROVIDER_LABELS[p],
        }))}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Input tokens"
          description="Prompt and context tokens per day"
          data={data?.tokens}
          loading={!data}
          xKey="day"
          xLabel="Day"
          kind="area"
          height={200}
          format={compact}
          series={[{ key: "input", label: "Input tokens" }]}
        />
        <ChartCard
          title="Output tokens"
          description="Generated reply tokens per day"
          data={data?.tokens}
          loading={!data}
          xKey="day"
          xLabel="Day"
          kind="area"
          height={200}
          format={compact}
          series={[{ key: "output", label: "Output tokens" }]}
        />
      </div>
      {data && data.cost_estimate === null ? (
        <Notice tone="neutral" title="Cost estimate unavailable">
          Per-token rates aren&apos;t configured for this environment, so no
          estimate is shown.
        </Notice>
      ) : (
        <ChartCard
          title="Estimated AI cost"
          description="Estimate · USD per day"
          data={data?.cost_estimate ?? undefined}
          loading={!data}
          xKey="day"
          xLabel="Day"
          kind="area"
          height={200}
          format={usd}
          series={[{ key: "amount", label: "Estimated cost" }]}
          headline={
            data && (
              <p className="text-xs text-muted-foreground">
                {data.currency_note}
                {data.totals.cost_estimate_usd != null && (
                  <>
                    {" "}
                    Period total{" "}
                    <span className="tabular font-semibold text-foreground">
                      {usd(data.totals.cost_estimate_usd)}
                    </span>{" "}
                    (estimate).
                  </>
                )}
              </p>
            )
          }
        />
      )}
    </div>
  );
}

function Fallbacks({ data }: { data?: PiAnalytics }) {
  return (
    <div className="space-y-4">
      <Notice tone="info" title="How the fallback chain works">
        PI tries the primary provider first. If it fails with a transient error
        it moves to the fallback, then the secondary fallback. If every provider
        fails, the conversation is handed to your team — customers never receive
        an invented answer.
      </Notice>
      <ChartCard
        title="Fallbacks per day"
        description="Replies that needed a fallback provider or handoff"
        data={data?.fallbacks}
        loading={!data}
        xKey="day"
        xLabel="Day"
        kind="bar"
        series={[{ key: "count", label: "Fallbacks" }]}
      />
      <TableCard
        title="Fallback paths"
        description="Where requests went when a provider failed"
        loading={!data}
      >
        <SimpleTable
          caption="Fallback paths"
          headers={[
            { label: "From" },
            { label: "To" },
            { label: "Count", align: "right" },
            { label: "Top reason" },
          ]}
          rows={(data?.fallback_pairs ?? []).map((p, i) => ({
            key: `${p.from}-${p.to}-${i}`,
            cells: [
              PROVIDER_LABELS[p.from],
              p.to === "handoff" ? (
                <Badge key="h" tone="warning">
                  Human handoff
                </Badge>
              ) : (
                PROVIDER_LABELS[p.to]
              ),
              n(p.count),
              humanizeError(p.top_reason),
            ],
          }))}
          empty="No fallbacks in this period."
        />
      </TableCard>
    </div>
  );
}

function Handoffs({ data }: { data?: PiAnalytics }) {
  const reasons = [...(data?.handoffs_by_reason ?? [])].sort(
    (a, b) => b.count - a.count,
  );
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader
          title="Handoffs by reason"
          description="Why PI passed conversations to your team"
        />
        <CardBody>
          {!data ? (
            <Skeleton className="h-24" />
          ) : reasons.every((r) => r.count === 0) ? (
            <p className="py-6 text-center text-[13px] text-muted-foreground">
              No handoffs in this period.
            </p>
          ) : (
            <DistributionBar
              segments={reasons.map((r) => ({
                key: r.reason,
                label: HANDOFF_REASON_LABELS[r.reason],
                value: r.count,
              }))}
            />
          )}
        </CardBody>
      </Card>
      <ChartCard
        title="Opened vs resolved"
        description="Handoffs per day"
        data={data?.handoffs_by_day}
        loading={!data}
        xKey="day"
        xLabel="Day"
        kind="line"
        series={[
          { key: "opened", label: "Opened" },
          { key: "resolved", label: "Resolved" },
        ]}
      />
    </div>
  );
}

function ToolActivity({
  data,
  tools,
}: {
  data?: PiAnalytics;
  tools?: ToolDefinition[];
}) {
  const catalog = new Map((tools ?? []).map((t) => [t.key, t]));
  const rows = [...(data?.tools ?? [])].sort(
    (a, b) =>
      b.success + b.failed + b.denied - (a.success + a.failed + a.denied),
  );
  return (
    <TableCard
      title="Tool activity"
      description="Calls per tool with outcome"
      loading={!data}
    >
      <SimpleTable
        caption="Tool activity"
        headers={[
          { label: "Tool" },
          { label: "Success", align: "right" },
          { label: "Failed", align: "right" },
          { label: "Denied", align: "right" },
          { label: "Failure rate", align: "right" },
        ]}
        rows={rows.map((r) => {
          const total = r.success + r.failed + r.denied;
          const tool = catalog.get(r.tool);
          const rate = total ? r.failed / total : 0;
          return {
            key: r.tool,
            cells: [
              <span key="t" className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{tool?.name ?? r.tool}</span>
                {tool?.capability === "mutation" && (
                  <Badge tone="warning">Changes data</Badge>
                )}
              </span>,
              n(r.success),
              n(r.failed),
              n(r.denied),
              <span
                key="r"
                className={rate > 0.05 ? "font-medium text-danger" : undefined}
              >
                {total ? formatPercent(rate, 1) : "—"}
              </span>,
            ],
          };
        })}
        empty="No tool calls in this period."
      />
      <p className="mt-3 text-xs text-muted-foreground">
        Denied calls were blocked by a permission or business rule check — that
        is PI&apos;s safety layer working, not an error.
      </p>
    </TableCard>
  );
}
