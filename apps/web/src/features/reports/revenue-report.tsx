"use client";

import { CircleDollarSign, HandCoins, Percent, Receipt } from "lucide-react";
import {
  centsToString,
  formatMoney,
  formatPercent,
  toCents,
} from "@/lib/format";
import { ChartCard } from "@/components/app/charts";
import { DataTable, type Column } from "@/components/app/data-table";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ErrorState } from "@/components/app/states";
import { SectionHeader } from "@/components/app/page";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { reportsService } from "./service";
import {
  ExportMenu,
  RangeTabs,
  ReportShell,
  monthLabel,
  ratio,
} from "./components";

type Row = { month: string; invoiced: string; collected: string };

export function RevenueReport() {
  return (
    <ReportShell
      title="Revenue"
      description="Invoiced and collected revenue by month."
      permission="billing.read"
      area="revenue reports"
    >
      <RevenueContent />
    </ReportShell>
  );
}

function RevenueContent() {
  const [state, setState] = useUrlState({ months: "12" });
  const months = state.months === "24" ? 24 : 12;
  const query = useScopedQuery(["reports", "revenue", months], () =>
    reportsService.revenue(months),
  );
  const data = query.data;
  const currency = data?.currency ?? "USD";
  const loading = query.isPending;
  const uncollected = data
    ? centsToString(
        toCents(data.total_invoiced) - toCents(data.total_collected),
      )
    : null;
  const averageCollected =
    data && data.months.length
      ? centsToString(
          toCents(data.total_collected) / BigInt(data.months.length),
        )
      : null;

  const columns: Column<Row>[] = [
    {
      key: "month",
      header: "Month",
      cell: (r) => <span className="font-medium">{monthLabel(r.month)}</span>,
    },
    {
      key: "invoiced",
      header: "Invoiced",
      align: "right",
      cell: (r) => (
        <span className="tabular">{formatMoney(r.invoiced, currency)}</span>
      ),
    },
    {
      key: "collected",
      header: "Collected",
      align: "right",
      cell: (r) => (
        <span className="tabular">{formatMoney(r.collected, currency)}</span>
      ),
    },
    {
      key: "rate",
      header: "Collection rate",
      align: "right",
      hideBelow: "sm",
      cell: (r) => (
        <span className="tabular text-muted-foreground">
          {formatPercent(ratio(r.collected, r.invoiced))}
        </span>
      ),
    },
  ];

  if (query.isError) {
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <RangeTabs
          label="Report period"
          value={String(months)}
          onChange={(v) => setState({ months: v })}
          options={[
            { value: "12", label: "12 months" },
            { value: "24", label: "24 months" },
          ]}
        />
        <ExportMenu
          disabled={!data}
          exports={[
            {
              label: "Monthly revenue",
              filename: `revenue-${months}-months`,
              headers: ["Month", "Invoiced", "Collected", "Currency"],
              rows: () =>
                (data?.months ?? []).map((m) => [
                  m.month,
                  m.invoiced,
                  m.collected,
                  currency,
                ]),
            },
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard
          label="Invoiced"
          icon={Receipt}
          loading={loading}
          value={formatMoney(data?.total_invoiced, currency)}
          detail={`Last ${months} months`}
        />
        <MetricCard
          label="Collected"
          icon={HandCoins}
          loading={loading}
          value={formatMoney(data?.total_collected, currency)}
          detail={
            averageCollected
              ? `${formatMoney(averageCollected, currency, { compact: true })} per month on average`
              : undefined
          }
        />
        <MetricCard
          label="Collection rate"
          icon={Percent}
          loading={loading}
          value={formatPercent(
            data ? ratio(data.total_collected, data.total_invoiced) : null,
          )}
          detail="Collected ÷ invoiced"
        />
        <MetricCard
          label="Not yet collected"
          icon={CircleDollarSign}
          loading={loading}
          tone={
            uncollected && toCents(uncollected) > BigInt(0)
              ? "warning"
              : "default"
          }
          value={formatMoney(uncollected, currency)}
          detail="Invoiced minus collected"
        />
      </MetricGrid>

      <ChartCard
        className="mt-4"
        title="Invoiced vs collected"
        description={`Monthly totals, last ${months} months`}
        data={data?.months.map((m) => ({
          month: monthLabel(m.month, months === 12),
          invoiced: Number(m.invoiced),
          collected: Number(m.collected),
        }))}
        loading={loading}
        xKey="month"
        xLabel="Month"
        series={[
          { key: "invoiced", label: "Invoiced" },
          { key: "collected", label: "Collected" },
        ]}
        format={(v) => formatMoney(v, currency, { compact: true })}
        kind="area"
        height={280}
      />

      <SectionHeader
        className="mt-6"
        title="Monthly breakdown"
        description="Most recent month first."
      />
      <DataTable
        caption="Revenue by month"
        columns={columns}
        rows={data ? [...data.months].reverse() : undefined}
        getRowId={(r) => r.month}
        loading={loading}
        loadingRows={6}
        empty={
          <p className="px-4 py-8 text-center text-[13px] text-muted-foreground">
            No invoices or payments in this period.
          </p>
        }
      />
    </>
  );
}
