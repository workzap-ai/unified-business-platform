"use client";

import { Ban, Calculator, ShoppingCart, Wallet } from "lucide-react";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { ChartCard, DistributionBar } from "@/components/app/charts";
import { DataTable, type Column } from "@/components/app/data-table";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ErrorState } from "@/components/app/states";
import { StatusBadge, statusLabel } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import type { OrdersReport as OrdersReportData } from "@/features/business/types";
import { reportsService } from "./service";
import {
  ExportMenu,
  RangeTabs,
  ReportShell,
  dayLabel,
  ratio,
  sumMoney,
} from "./components";

type StatusRow = OrdersReportData["by_status"][number];
const RANGES = ["30", "90", "365"] as const;
const STATUS_ORDER = [
  "draft",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "cancelled",
];

export function OrdersReport() {
  return (
    <ReportShell
      title="Orders"
      description="Order volume, value and where orders are in fulfilment."
      permission="orders.read"
      area="order reports"
    >
      <OrdersContent />
    </ReportShell>
  );
}

function OrdersContent() {
  const [state, setState] = useUrlState({ days: "30" });
  const days = Number(
    (RANGES as readonly string[]).includes(state.days) ? state.days : "30",
  );
  const query = useScopedQuery(["reports", "orders", days], () =>
    reportsService.orders(days),
  );
  const data = query.data;
  const currency = data?.currency ?? "USD";
  const loading = query.isPending;

  const byStatus = data
    ? [...data.by_status].sort((a, b) => {
        const ia = STATUS_ORDER.indexOf(a.status);
        const ib = STATUS_ORDER.indexOf(b.status);
        return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      })
    : undefined;
  const totalCount = byStatus?.reduce((s, r) => s + r.count, 0) ?? 0;
  const counted =
    byStatus?.filter((r) => !["draft", "cancelled"].includes(r.status)) ?? [];
  const bookedValue = sumMoney(counted.map((r) => r.value));
  const cancelled = byStatus?.find((r) => r.status === "cancelled")?.count ?? 0;

  const columns: Column<StatusRow>[] = [
    {
      key: "status",
      header: "Status",
      cell: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: "count",
      header: "Orders",
      align: "right",
      cell: (r) => <span className="tabular">{formatNumber(r.count)}</span>,
    },
    {
      key: "share",
      header: "Share",
      align: "right",
      hideBelow: "sm",
      cell: (r) => (
        <span className="tabular text-muted-foreground">
          {formatPercent(ratio(r.count, totalCount))}
        </span>
      ),
    },
    {
      key: "value",
      header: "Value",
      align: "right",
      cell: (r) => (
        <span className="tabular">{formatMoney(r.value, currency)}</span>
      ),
    },
  ];

  if (query.isError)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <RangeTabs
          label="Report period"
          value={String(days)}
          onChange={(v) => setState({ days: v })}
          options={[
            { value: "30", label: "30 days" },
            { value: "90", label: "90 days" },
            { value: "365", label: "365 days" },
          ]}
        />
        <ExportMenu
          disabled={!data}
          exports={[
            {
              label: "Orders per day",
              filename: `orders-per-day-${days}d`,
              headers: ["Day", "Orders", "Value", "Currency"],
              rows: () =>
                (data?.by_day ?? []).map((d) => [
                  d.day,
                  d.count,
                  d.value,
                  currency,
                ]),
            },
            {
              label: "Orders by status",
              filename: `orders-by-status-${days}d`,
              headers: ["Status", "Orders", "Value", "Currency"],
              rows: () =>
                (byStatus ?? []).map((r) => [
                  statusLabel(r.status),
                  r.count,
                  r.value,
                  currency,
                ]),
            },
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard
          label="Orders"
          icon={ShoppingCart}
          loading={loading}
          value={formatNumber(totalCount)}
          detail={`Created in the last ${days} days`}
          href="/orders"
        />
        <MetricCard
          label="Booked value"
          icon={Wallet}
          loading={loading}
          value={formatMoney(bookedValue, currency)}
          detail="Excludes drafts and cancelled"
        />
        <MetricCard
          label="Average order value"
          icon={Calculator}
          loading={loading}
          value={formatMoney(data?.average_order_value, currency)}
          detail="Excludes drafts and cancelled"
        />
        <MetricCard
          label="Cancelled"
          icon={Ban}
          loading={loading}
          tone={cancelled > 0 ? "warning" : "default"}
          value={formatNumber(cancelled)}
          detail={
            totalCount
              ? `${formatPercent(ratio(cancelled, totalCount))} of orders`
              : undefined
          }
        />
      </MetricGrid>

      <ChartCard
        className="mt-4"
        title="Orders per day"
        description="Excludes cancelled orders; days without orders are omitted"
        data={data?.by_day.map((d) => ({
          day: dayLabel(d.day),
          orders: d.count,
        }))}
        loading={loading}
        xKey="day"
        xLabel="Day"
        series={[{ key: "orders", label: "Orders" }]}
        format={(v) => formatNumber(v)}
        kind="bar"
        height={240}
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader
            title="By status"
            description="Share of orders in each state"
          />
          <CardBody>
            {loading ? (
              <Skeleton className="h-16" />
            ) : totalCount === 0 ? (
              <p className="py-4 text-[13px] text-muted-foreground">
                No orders in this period.
              </p>
            ) : (
              <DistributionBar
                segments={(byStatus ?? []).map((r) => ({
                  key: r.status,
                  label: statusLabel(r.status),
                  value: r.count,
                }))}
                format={(v) => formatNumber(v)}
              />
            )}
          </CardBody>
        </Card>
        <DataTable
          caption="Orders by status"
          columns={columns}
          rows={byStatus}
          getRowId={(r) => r.status}
          rowHref={(r) => `/orders?status=${r.status}`}
          loading={loading}
          loadingRows={5}
          empty={
            <p className="px-4 py-8 text-center text-[13px] text-muted-foreground">
              No orders in this period.
            </p>
          }
        />
      </div>
    </>
  );
}
