"use client";

import Link from "next/link";
import { Crown, UserPlus, Users } from "lucide-react";
import { formatMoney, formatNumber } from "@/lib/format";
import { ChartCard } from "@/components/app/charts";
import { DataTable, type Column } from "@/components/app/data-table";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { EmptyState, ErrorState } from "@/components/app/states";
import { SectionHeader } from "@/components/app/page";
import { useScopedQuery } from "@/hooks/use-scoped";
import type { CustomersReport as CustomersReportData } from "@/features/business/types";
import { reportsService } from "./service";
import { ExportMenu, ReportShell, monthLabel } from "./components";

type TopRow = CustomersReportData["top"][number];

export function CustomersReport() {
  return (
    <ReportShell
      title="Customers"
      description="Customer growth and who you invoice the most."
      permission="customers.read"
      area="customer reports"
    >
      <CustomersContent />
    </ReportShell>
  );
}

function CustomersContent() {
  const query = useScopedQuery(["reports", "customers"], () =>
    reportsService.customers(),
  );
  const data = query.data;
  const currency = data?.currency ?? "USD";
  const loading = query.isPending;
  const newTotal =
    data?.new_by_month.reduce((sum, [, count]) => sum + count, 0) ?? 0;
  const thisMonth = data?.new_by_month[data.new_by_month.length - 1]?.[1] ?? 0;
  const top = data?.top[0];

  const columns: Column<TopRow>[] = [
    {
      key: "rank",
      header: "#",
      width: "44px",
      cell: (r) => (
        <span className="tabular text-muted-foreground">
          {(data?.top.indexOf(r) ?? 0) + 1}
        </span>
      ),
    },
    {
      key: "name",
      header: "Customer",
      cell: (r) => (
        <Link
          href={`/customers/${r.customer_id}`}
          className="font-medium hover:text-primary hover:underline"
        >
          {r.name}
        </Link>
      ),
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
      key: "orders",
      header: "Orders",
      align: "right",
      hideBelow: "sm",
      cell: (r) => <span className="tabular">{formatNumber(r.orders)}</span>,
    },
  ];

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
              label: "New customers by month",
              filename: "new-customers-by-month",
              headers: ["Month", "New customers"],
              rows: () =>
                (data?.new_by_month ?? []).map(([month, count]) => [
                  month,
                  count,
                ]),
            },
            {
              label: "Top customers",
              filename: "top-customers",
              headers: [
                "Customer",
                "Customer ID",
                "Invoiced",
                "Orders",
                "Currency",
              ],
              rows: () =>
                (data?.top ?? []).map((r) => [
                  r.name,
                  r.customer_id,
                  r.invoiced,
                  r.orders,
                  currency,
                ]),
            },
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard
          label="Total customers"
          icon={Users}
          loading={loading}
          value={formatNumber(data?.total)}
          href="/customers"
        />
        <MetricCard
          label="New, last 12 months"
          icon={UserPlus}
          loading={loading}
          value={formatNumber(newTotal)}
          detail={`${formatNumber(thisMonth)} this month`}
        />
        <MetricCard
          label="Top customer"
          icon={Crown}
          loading={loading}
          value={
            top ? formatMoney(top.invoiced, currency, { compact: true }) : "—"
          }
          detail={top?.name ?? "No invoiced customers yet"}
        />
      </MetricGrid>

      <ChartCard
        className="mt-4"
        title="New customers"
        description="Customers added per month"
        data={data?.new_by_month.map(([month, count]) => ({
          month: monthLabel(month, true),
          customers: count,
        }))}
        loading={loading}
        xKey="month"
        xLabel="Month"
        series={[{ key: "customers", label: "New customers" }]}
        format={(v) => formatNumber(v)}
        kind="bar"
        height={240}
      />

      <SectionHeader
        className="mt-6"
        title="Top customers"
        description="Ranked by invoiced amount (issued and paid invoices)."
      />
      <DataTable
        caption="Top customers by invoiced amount"
        columns={columns}
        rows={data?.top}
        getRowId={(r) => r.customer_id}
        rowHref={(r) => `/customers/${r.customer_id}`}
        loading={loading}
        loadingRows={6}
        empty={
          <EmptyState
            compact
            icon={Users}
            title="No invoiced customers yet"
            description="Customers appear here once invoices are issued to them."
          />
        }
      />
    </>
  );
}
