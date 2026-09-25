"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  CircleDollarSign,
  MessagesSquare,
  Shuffle,
  TriangleAlert,
  UserCheck,
} from "lucide-react";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ChartCard } from "@/components/app/charts";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { piService } from "@/features/pi/service";
import { useNavItemAvailable } from "@/features/navigation/hooks";
import { ExportMenu, ReportShell, dayLabel } from "./components";

export function PiReport() {
  return (
    <ReportShell
      title="PI Analytics"
      description="How the AI WhatsApp assistant performed over the last 30 days."
      permission="pi.analytics.read"
      area="PI analytics"
      actions={
        <Button variant="secondary" size="sm" asChild>
          <Link href="/pi/analytics">
            Full PI analytics <ArrowRight />
          </Link>
        </Button>
      }
    >
      <PiContent />
    </ReportShell>
  );
}

function PiContent() {
  const available = useNavItemAvailable("pi");
  const query = useScopedQuery(
    ["pi", "analytics", 30],
    () => piService.analytics(30),
    { enabled: available === true },
  );
  if (available === false)
    return (
      <Notice tone="neutral" icon={Bot} title="PI isn't enabled here">
        PI analytics appear once PI is installed and enabled for this
        environment in Platform Products.
      </Notice>
    );
  const data = query.data;
  const t = data?.totals;
  const loading = query.isPending;

  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );

  return (
    <>
      <div className="mb-4 flex justify-end">
        <ExportMenu
          disabled={!data}
          exports={[
            {
              label: "Conversations per day",
              filename: "pi-conversations-30d",
              headers: ["Day", "Started", "Resolved"],
              rows: () =>
                (data?.conversations ?? []).map((d) => [
                  d.day,
                  d.started,
                  d.resolved,
                ]),
            },
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard
          label="Conversations"
          icon={MessagesSquare}
          loading={loading}
          tone="pi"
          value={formatNumber(t?.conversations)}
          detail="Last 30 days"
        />
        <MetricCard
          label="AI responses"
          icon={Bot}
          loading={loading}
          tone="pi"
          value={formatNumber(t?.ai_responses)}
          detail={
            t ? `${formatNumber(t.messages)} messages in total` : undefined
          }
        />
        <MetricCard
          label="Handoffs"
          icon={UserCheck}
          loading={loading}
          tone={(t?.handoffs ?? 0) > 0 ? "warning" : "default"}
          value={formatNumber(t?.handoffs)}
          detail="Passed to your team"
        />
        <MetricCard
          label="Provider fallbacks"
          icon={Shuffle}
          loading={loading}
          value={formatNumber(t?.fallbacks)}
          detail="Replies served by a backup provider"
        />
        <MetricCard
          label="Failure rate"
          icon={TriangleAlert}
          loading={loading}
          tone={(t?.failure_rate ?? 0) > 0.05 ? "danger" : "default"}
          value={formatPercent(t?.failure_rate, 1)}
          detail={t ? `Across ${formatNumber(t.runs)} agent runs` : undefined}
        />
        {t && t.cost_estimate_usd !== null && (
          <MetricCard
            label="AI cost (estimate)"
            icon={CircleDollarSign}
            value={formatMoney(t.cost_estimate_usd, "USD")}
            detail={data?.currency_note || "Estimate from token usage"}
          />
        )}
      </MetricGrid>

      <ChartCard
        className="mt-4"
        title="Conversations"
        description="Started vs resolved per day"
        data={data?.conversations.map((d) => ({
          day: dayLabel(d.day),
          started: d.started,
          resolved: d.resolved,
        }))}
        loading={loading}
        xKey="day"
        xLabel="Day"
        series={[
          { key: "started", label: "Started" },
          { key: "resolved", label: "Resolved" },
        ]}
        format={(v) => formatNumber(v)}
        kind="line"
        height={240}
      />

      {t && t.cost_estimate_usd !== null && (
        <Notice tone="neutral" className="mt-4">
          Cost figures are estimates calculated from token usage and published
          provider prices. Your provider invoice is the source of truth.
        </Notice>
      )}
    </>
  );
}
