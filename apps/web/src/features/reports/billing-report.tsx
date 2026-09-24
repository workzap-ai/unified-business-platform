"use client";

import Link from "next/link";
import { AlertTriangle, FilePen, HandCoins, Receipt } from "lucide-react";
import { formatMoney, formatNumber } from "@/lib/format";
import { Card, CardBody, CardHeader, Skeleton } from "@/components/ui/display";
import { ChartCard, DistributionBar } from "@/components/app/charts";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { billingService } from "@/features/billing/service";
import { financeService } from "@/features/finance/service";
import { reportsService } from "./service";
import { ExportMenu, ReportShell, monthLabel } from "./components";

function localDate(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const BUCKET_LABELS: Record<string, string> = {
  current: "Not yet due",
  "1-30": "1–30 days overdue",
  "31-60": "31–60 days overdue",
  "61-90": "61–90 days overdue",
  "90+": "90+ days overdue",
};

export function BillingReport() {
  return (
    <ReportShell
      title="Billing"
      description="Receivables, overdue balances and monthly collections."
      permission="billing.read"
      area="billing reports"
    >
      <BillingContent />
    </ReportShell>
  );
}

function BillingContent() {
  const { can } = useSession();
  const canFinance = can("finance.read");
  const start = localDate(-30);
  const end = localDate(0);
  const summary = useScopedQuery(["billing", "summary"], () => billingService.summary());
  const finance = useScopedQuery(["finance", "summary", start, end], () => financeService.summary(start, end), { enabled: canFinance });
  const revenue = useScopedQuery(["reports", "revenue", 12], () => reportsService.revenue(12));
  const s = summary.data;
  const currency = s?.currency ?? revenue.data?.currency ?? "USD";
  const loading = summary.isPending;

  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />;

  const aging = finance.data?.aging ?? [];
  const agingTotal = aging.reduce((sum, a) => sum + Number(a.amount), 0);

  return (
    <>
      <div className="mb-4 flex justify-end">
        <ExportMenu
          disabled={!revenue.data}
          exports={[
            {
              label: "Collections per month",
              filename: "collections-per-month",
              headers: ["Month", "Collected", "Currency"],
              rows: () => (revenue.data?.months ?? []).map((m) => [m.month, m.collected, revenue.data?.currency]),
            },
            ...(finance.data
              ? [
                  {
                    label: "Receivables aging",
                    filename: "receivables-aging",
                    headers: ["Bucket", "Invoices", "Amount", "Currency"],
                    rows: () => aging.map((a) => [BUCKET_LABELS[a.bucket] ?? a.bucket, a.count, a.amount, finance.data?.currency]),
                  },
                ]
              : []),
          ]}
        />
      </div>

      <MetricGrid>
        <MetricCard label="Outstanding" icon={Receipt} loading={loading} value={formatMoney(s?.outstanding, currency)} detail="Issued, not yet paid" href="/billing/invoices?status=issued" />
        <MetricCard
          label="Overdue"
          icon={AlertTriangle}
          loading={loading}
          tone={s && s.overdue_count > 0 ? "danger" : "default"}
          value={formatMoney(s?.overdue, currency)}
          detail={s ? `${formatNumber(s.overdue_count)} overdue invoice${s.overdue_count === 1 ? "" : "s"}` : undefined}
          href="/billing/invoices?overdue=true"
        />
        <MetricCard label="Collected this month" icon={HandCoins} loading={loading} tone="success" value={formatMoney(s?.collected_this_month, currency)} />
        <MetricCard label="Draft invoices" icon={FilePen} loading={loading} value={formatNumber(s?.draft_count)} detail="Not issued yet" href="/billing/invoices?status=draft" />
      </MetricGrid>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Card>
          <CardHeader
            title="Receivables aging"
            description={canFinance ? "Open balances by days past due" : undefined}
            actions={
              canFinance ? (
                <Link href="/finance" className="text-xs font-medium text-primary hover:underline">
                  Finance
                </Link>
              ) : undefined
            }
          />
          <CardBody>
            {!canFinance ? (
              <p className="py-4 text-[13px] text-muted-foreground">Receivables aging is visible to members with finance access.</p>
            ) : finance.isPending ? (
              <Skeleton className="h-20" />
            ) : finance.isError ? (
              <ErrorState compact error={finance.error} onRetry={() => void finance.refetch()} />
            ) : agingTotal === 0 ? (
              <p className="py-4 text-[13px] text-muted-foreground">No open receivables.</p>
            ) : (
              <>
                <p className="tabular mb-3 text-[22px] leading-tight font-semibold tracking-tight">
                  {formatMoney(finance.data.receivables, finance.data.currency)}
                </p>
                <DistributionBar
                  segments={aging.map((a) => ({ key: a.bucket, label: BUCKET_LABELS[a.bucket] ?? a.bucket, value: Number(a.amount) }))}
                  format={(v) => formatMoney(v, finance.data.currency, { compact: true })}
                />
              </>
            )}
          </CardBody>
        </Card>

        {revenue.isError ? (
          <Card>
            <ErrorState compact error={revenue.error} onRetry={() => void revenue.refetch()} />
          </Card>
        ) : (
          <ChartCard
            title="Collections per month"
            description="Payments received, last 12 months"
            data={revenue.data?.months.map((m) => ({ month: monthLabel(m.month, true), collected: Number(m.collected) }))}
            loading={revenue.isPending}
            xKey="month"
            xLabel="Month"
            series={[{ key: "collected", label: "Collected" }]}
            format={(v) => formatMoney(v, currency, { compact: true })}
            kind="bar"
            height={240}
            headline={
              revenue.data && (
                <p className="text-[13px] text-muted-foreground">
                  Total collected <span className="tabular font-semibold text-foreground">{formatMoney(revenue.data.total_collected, revenue.data.currency)}</span>
                </p>
              )
            }
          />
        )}
      </div>
    </>
  );
}
