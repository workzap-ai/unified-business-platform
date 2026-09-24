"use client";

import Link from "next/link";
import { subDays, format } from "date-fns";
import { AlertTriangle, CheckCircle2, FilePen, FilePlus2, Receipt, Wallet } from "lucide-react";
import { formatMoney, formatNumber, pluralize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import { ModuleNav, PageHeader, PageShell, RequirePermission } from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { DistributionBar } from "@/components/app/charts";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { financeService } from "@/features/finance/service";
import type { Invoice } from "@/features/business/types";
import { billingService } from "./service";
import { DueDate } from "./invoice-bits";
import { formatDay, methodLabel } from "./utils";

const AGING_LABELS: Record<string, string> = {
  current: "Not yet due",
  "1-30": "1–30 days",
  "31-60": "31–60 days",
  "61-90": "61–90 days",
  "90+": "90+ days",
};

export function BillingOverviewPage() {
  return (
    <RequirePermission permission="billing.read" area="billing">
      <BillingOverview />
    </RequirePermission>
  );
}

function BillingOverview() {
  const { can } = useSession();
  const end = format(new Date(), "yyyy-MM-dd");
  const start = format(subDays(new Date(), 29), "yyyy-MM-dd");

  const summary = useScopedQuery(["billing", "summary"], () => billingService.summary());
  const overdue = useScopedQuery(["invoices", { overdue: true, pageSize: 8 }], () =>
    billingService.invoices({ overdue: true, pageSize: 8 }),
  );
  const payments = useScopedQuery(["payments", { page: 1, pageSize: 6 }], () =>
    billingService.payments({ page: 1, pageSize: 6 }),
  );
  const finance = useScopedQuery(["finance", "summary", start, end], () => financeService.summary(start, end), {
    enabled: can("finance.read"),
  });

  const data = summary.data;
  const currency = data?.currency ?? "USD";
  const loading = summary.isPending;

  const columns: Column<Invoice>[] = [
    {
      key: "number",
      header: "Invoice",
      cell: (i) => (
        <Link href={`/billing/invoices/${i.id}`} className="font-medium hover:underline">
          {i.number}
        </Link>
      ),
    },
    {
      key: "customer",
      header: "Customer",
      cell: (i) => <span className="block max-w-48 truncate">{i.customer_name ?? "—"}</span>,
      hideBelow: "sm",
    },
    { key: "due", header: "Due", cell: (i) => <DueDate invoice={i} /> },
    {
      key: "balance",
      header: "Balance due",
      align: "right",
      cell: (i) => <span className="tabular font-medium">{formatMoney(i.balance_due, i.currency)}</span>,
    },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Billing"
        description="Invoices, collections and what customers still owe you."
        actions={
          can("billing.write") ? (
            <Button asChild>
              <Link href="/billing/invoices/new">
                <FilePlus2 /> New invoice
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="billing" />

      {summary.isError ? (
        <Card className="mb-4">
          <ErrorState error={summary.error} onRetry={() => void summary.refetch()} compact />
        </Card>
      ) : (
        <MetricGrid>
          <MetricCard
            label="Outstanding"
            icon={Receipt}
            loading={loading}
            href="/billing/invoices?status=issued"
            value={data ? formatMoney(data.outstanding, currency) : "—"}
            detail="Issued and partially paid"
          />
          <MetricCard
            label="Overdue"
            icon={AlertTriangle}
            loading={loading}
            href="/billing/invoices?overdue=true"
            tone={data && data.overdue_count > 0 ? "danger" : "default"}
            value={data ? formatMoney(data.overdue, currency) : "—"}
            detail={data ? pluralize(data.overdue_count, "invoice") + " past due" : undefined}
          />
          <MetricCard
            label="Collected this month"
            icon={Wallet}
            loading={loading}
            href="/billing/payments"
            tone="success"
            value={data ? formatMoney(data.collected_this_month, currency) : "—"}
            detail="Payments received"
          />
          <MetricCard
            label="Drafts"
            icon={FilePen}
            loading={loading}
            href="/billing/invoices?status=draft"
            value={data ? formatNumber(data.draft_count) : "—"}
            detail={data && data.draft_count > 0 ? "Waiting to be issued" : "Nothing waiting"}
          />
        </MetricGrid>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section aria-labelledby="overdue-heading" className="min-w-0">
          <div className="mb-2 flex items-end justify-between gap-3">
            <div>
              <h2 id="overdue-heading" className="text-[15px] font-semibold tracking-tight">
                Overdue invoices
              </h2>
              <p className="mt-0.5 text-[13px] text-muted-foreground">Oldest balances to chase first.</p>
            </div>
            <Link href="/billing/invoices?overdue=true" className="text-xs font-medium text-primary hover:underline">
              View all
            </Link>
          </div>
          <DataTable
            columns={columns}
            rows={overdue.data?.items}
            getRowId={(i) => i.id}
            loading={overdue.isPending}
            error={overdue.error}
            onRetry={() => void overdue.refetch()}
            rowHref={(i) => `/billing/invoices/${i.id}`}
            caption="Overdue invoices"
            loadingRows={5}
            empty={
              <EmptyState
                compact
                icon={CheckCircle2}
                title="Nothing overdue"
                description="Every issued invoice is still within its payment terms."
              />
            }
          />
        </section>

        <div className="flex min-w-0 flex-col gap-4">
          {can("finance.read") && (
            <Card>
              <CardHeader
                title="Receivables aging"
                description="Open balances by days past due"
                actions={
                  <Link href="/finance/receivables" className="text-xs font-medium text-primary hover:underline">
                    Details
                  </Link>
                }
              />
              <div className="px-4 pb-4">
                {finance.isPending ? (
                  <div className="space-y-3">
                    <Skeleton className="h-2.5 w-full rounded-full" />
                    <Skeleton className="h-16" />
                  </div>
                ) : finance.isError ? (
                  <ErrorState error={finance.error} onRetry={() => void finance.refetch()} compact />
                ) : finance.data.aging.every((a) => Number(a.amount) === 0) ? (
                  <p className="py-3 text-[13px] text-muted-foreground">No open balances right now.</p>
                ) : (
                  <DistributionBar
                    segments={finance.data.aging.map((a) => ({
                      key: a.bucket,
                      label: AGING_LABELS[a.bucket] ?? a.bucket,
                      value: Number(a.amount),
                    }))}
                    format={(v) => formatMoney(v, finance.data.currency, { compact: true })}
                  />
                )}
              </div>
            </Card>
          )}

          <Card>
            <CardHeader
              title="Recent payments"
              actions={
                <Link href="/billing/payments" className="text-xs font-medium text-primary hover:underline">
                  View all
                </Link>
              }
            />
            <div className="px-2 pb-2">
              {payments.isPending ? (
                <div className="space-y-2 px-2 pb-2">
                  {Array.from({ length: 4 }, (_, i) => (
                    <Skeleton key={i} className="h-10" />
                  ))}
                </div>
              ) : payments.isError ? (
                <ErrorState error={payments.error} onRetry={() => void payments.refetch()} compact />
              ) : payments.data.items.length === 0 ? (
                <p className="px-2 pt-1 pb-3 text-[13px] text-muted-foreground">
                  No payments recorded yet. Payments appear here when you record them on an issued invoice.
                </p>
              ) : (
                <ul>
                  {payments.data.items.map((p) => (
                    <li key={p.id}>
                      <Link
                        href={`/billing/invoices/${p.invoice_id}`}
                        className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted"
                      >
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-success-soft text-success">
                          <Wallet className="size-4" aria-hidden="true" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-medium">
                            {p.customer_name ?? p.invoice_number ?? p.number}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {[p.invoice_number, methodLabel(p.method), formatDay(p.received_on)]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </span>
                        <span className="tabular shrink-0 text-[13px] font-semibold">
                          {formatMoney(p.amount, p.currency)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
