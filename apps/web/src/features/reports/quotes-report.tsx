"use client";

import { CheckCircle2, FileText, Percent, Wallet } from "lucide-react";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { DistributionBar } from "@/components/app/charts";
import { DataTable, type Column } from "@/components/app/data-table";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ErrorState } from "@/components/app/states";
import { StatusBadge, statusLabel } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import type { QuotesReport as QuotesReportData } from "@/features/business/types";
import { reportsService } from "./service";
import { ExportMenu, ReportShell, ratio } from "./components";

type StatusRow = QuotesReportData["by_status"][number];
const STATUS_ORDER = ["draft", "pending_approval", "approved", "sent", "accepted", "rejected", "expired", "cancelled"];

export function QuotesReport() {
  return (
    <ReportShell
      title="Quotes"
      description="Quote pipeline by status and how often quotes convert."
      permission="quotes.read"
      area="quote reports"
    >
      <QuotesContent />
    </ReportShell>
  );
}

function QuotesContent() {
  const query = useScopedQuery(["reports", "quotes"], () => reportsService.quotes());
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
  const total = byStatus?.reduce((s, r) => s + r.count, 0) ?? 0;
  const accepted = byStatus?.find((r) => r.status === "accepted");
  const conversion = data?.conversion_rate === null || data?.conversion_rate === undefined ? null : Number(data.conversion_rate);

  const columns: Column<StatusRow>[] = [
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
    { key: "count", header: "Quotes", align: "right", cell: (r) => <span className="tabular">{formatNumber(r.count)}</span> },
    { key: "share", header: "Share", align: "right", hideBelow: "sm", cell: (r) => <span className="tabular text-muted-foreground">{formatPercent(ratio(r.count, total))}</span> },
    { key: "value", header: "Value", align: "right", cell: (r) => <span className="tabular">{formatMoney(r.value, currency)}</span> },
  ];

  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;

  return (
    <>
      <div className="mb-4 flex justify-end">
        <ExportMenu
          disabled={!data}
          exports={[
            {
              label: "Quotes by status",
              filename: "quotes-by-status",
              headers: ["Status", "Quotes", "Value", "Currency"],
              rows: () => (byStatus ?? []).map((r) => [statusLabel(r.status), r.count, r.value, currency]),
            },
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard label="Quotes" icon={FileText} loading={loading} value={formatNumber(total)} detail="All quotes in this environment" href="/quotes" />
        <MetricCard label="Open value" icon={Wallet} loading={loading} value={formatMoney(data?.open_value, currency)} detail="Draft, awaiting approval, approved or sent" />
        <MetricCard
          label="Conversion rate"
          icon={Percent}
          loading={loading}
          value={formatPercent(conversion, 1)}
          detail={conversion === null ? "No decided quotes yet" : "Accepted ÷ accepted, rejected and expired"}
        />
        <MetricCard label="Accepted" icon={CheckCircle2} loading={loading} tone="success" value={formatNumber(accepted?.count ?? 0)} detail={accepted ? formatMoney(accepted.value, currency) : undefined} />
      </MetricGrid>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader title="By status" description="Share of quotes in each state" />
          <CardBody>
            {loading ? (
              <Skeleton className="h-16" />
            ) : total === 0 ? (
              <p className="py-4 text-[13px] text-muted-foreground">No quotes yet.</p>
            ) : (
              <DistributionBar
                segments={(byStatus ?? []).map((r) => ({ key: r.status, label: statusLabel(r.status), value: r.count }))}
                format={(v) => formatNumber(v)}
              />
            )}
          </CardBody>
        </Card>
        <DataTable
          caption="Quotes by status"
          columns={columns}
          rows={byStatus}
          getRowId={(r) => r.status}
          rowHref={(r) => `/quotes?status=${r.status}`}
          loading={loading}
          loadingRows={6}
          empty={<p className="px-4 py-8 text-center text-[13px] text-muted-foreground">No quotes yet.</p>}
        />
      </div>
    </>
  );
}
