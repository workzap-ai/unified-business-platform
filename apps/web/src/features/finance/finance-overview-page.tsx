"use client";

import Link from "next/link";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Info,
  Landmark,
  Plus,
  Receipt,
} from "lucide-react";
import { formatMoney, formatNumber, toCents } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  SegmentedList,
  SegmentedTrigger,
  Skeleton,
  Tabs,
} from "@/components/ui/display";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { ChartCard } from "@/components/app/charts";
import { ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import { formatDay } from "@/features/billing/utils";
import { financeService } from "./service";
import { AGING_LABELS, PERIODS, categoryLabel, periodRange } from "./utils";

export function FinanceOverviewPage() {
  return (
    <RequirePermission permission="finance.read" area="finance">
      <FinanceOverview />
    </RequirePermission>
  );
}

function FinanceOverview() {
  const { can } = useSession();
  const [state, setState] = useUrlState({ period: "30" });
  const days = PERIODS.some((p) => p.value === state.period)
    ? Number(state.period)
    : 30;
  const { start, end } = periodRange(days);
  const query = useScopedQuery(
    ["finance", "summary", start, end],
    () => financeService.summary(start, end),
    {
      placeholderData: (previous) => previous,
    },
  );
  const data = query.data;
  const currency = data?.currency ?? "USD";
  const loading = query.isPending;
  const net = data ? toCents(data.net_cash) : BigInt(0);
  const periodLabel =
    PERIODS.find((p) => Number(p.value) === days)?.label ?? "30 days";

  return (
    <PageShell>
      <PageHeader
        title="Finance"
        description="Cash movement, receivables and spending for the period you choose."
        actions={
          can("finance.write") ? (
            <Button asChild>
              <Link href="/finance/expenses?new=1">
                <Plus /> Record expense
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="finance" />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={String(days)}
          onValueChange={(period) => setState({ period })}
        >
          <SegmentedList aria-label="Reporting period">
            {PERIODS.map((p) => (
              <SegmentedTrigger key={p.value} value={p.value}>
                {p.label}
              </SegmentedTrigger>
            ))}
          </SegmentedList>
        </Tabs>
        <p className="tabular text-xs text-muted-foreground">
          {formatDay(start)} – {formatDay(end)}
        </p>
      </div>

      {query.isError ? (
        <Card>
          <ErrorState
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        </Card>
      ) : (
        <>
          <MetricGrid>
            <MetricCard
              label="Cash in"
              icon={ArrowDownLeft}
              loading={loading}
              tone="success"
              value={data ? formatMoney(data.cash_in, currency) : "—"}
              detail={`Payments received, last ${periodLabel}`}
              href="/billing/payments"
            />
            <MetricCard
              label="Cash out"
              icon={ArrowUpRight}
              loading={loading}
              value={data ? formatMoney(data.cash_out, currency) : "—"}
              detail={`Recorded expenses, last ${periodLabel}`}
              href="/finance/expenses"
            />
            <MetricCard
              label="Net cash"
              icon={Landmark}
              loading={loading}
              tone={
                net > BigInt(0)
                  ? "success"
                  : net < BigInt(0)
                    ? "danger"
                    : "default"
              }
              value={
                data ? (
                  <span
                    className={
                      net < BigInt(0)
                        ? "text-danger"
                        : net > BigInt(0)
                          ? "text-success"
                          : undefined
                    }
                  >
                    {formatMoney(data.net_cash, currency)}
                  </span>
                ) : (
                  "—"
                )
              }
              detail={
                net < BigInt(0)
                  ? "More went out than came in"
                  : "Cash in minus cash out"
              }
            />
            <MetricCard
              label="Receivables"
              icon={Receipt}
              loading={loading}
              value={data ? formatMoney(data.receivables, currency) : "—"}
              detail="Open invoice balances today"
              href="/finance/receivables"
            />
          </MetricGrid>

          <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <ChartCard
              title="Expenses by category"
              description={`Recorded expenses, last ${periodLabel}`}
              data={data?.expenses_by_category.map((e) => ({
                category: categoryLabel(e.category),
                amount: Number(e.amount),
              }))}
              loading={loading}
              xKey="category"
              xLabel="Category"
              series={[{ key: "amount", label: "Amount" }]}
              kind="bar"
              height={240}
              format={(v) => formatMoney(v, currency, { compact: true })}
              emptyMessage="No expenses recorded in this period."
              actions={
                <Link
                  href="/finance/expenses"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Expenses
                </Link>
              }
            />

            <Card>
              <CardHeader
                title="Receivables aging"
                description="Open balances by days past due"
                actions={
                  <Link
                    href="/finance/receivables"
                    className="text-xs font-medium text-primary hover:underline"
                  >
                    Details
                  </Link>
                }
              />
              <div className="px-4 pb-4">
                {loading || !data ? (
                  <div className="space-y-2">
                    {Array.from({ length: 5 }, (_, i) => (
                      <Skeleton key={i} className="h-8" />
                    ))}
                  </div>
                ) : (
                  <table className="w-full text-[13px]">
                    <caption className="sr-only">Receivables aging</caption>
                    <thead>
                      <tr className="border-b border-border text-xs text-muted-foreground">
                        <th scope="col" className="py-2 text-left font-medium">
                          Age
                        </th>
                        <th scope="col" className="py-2 text-right font-medium">
                          Invoices
                        </th>
                        <th scope="col" className="py-2 text-right font-medium">
                          Balance
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.aging.map((a) => (
                        <tr
                          key={a.bucket}
                          className="border-b border-border last:border-0"
                        >
                          <td className="py-2">
                            {AGING_LABELS[a.bucket] ?? a.bucket}
                          </td>
                          <td className="tabular py-2 text-right text-muted-foreground">
                            {formatNumber(a.count)}
                          </td>
                          <td
                            className={
                              a.bucket !== "current" && Number(a.amount) > 0
                                ? "tabular py-2 text-right font-medium text-danger"
                                : "tabular py-2 text-right font-medium"
                            }
                          >
                            {formatMoney(a.amount, currency)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t border-border-strong font-semibold">
                        <td className="py-2">Total</td>
                        <td className="tabular py-2 text-right">
                          {formatNumber(
                            data.aging.reduce((sum, a) => sum + a.count, 0),
                          )}
                        </td>
                        <td className="tabular py-2 text-right">
                          {formatMoney(data.receivables, currency)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            </Card>
          </div>
        </>
      )}

      <Notice
        tone="neutral"
        icon={Info}
        title="Operational finance, not a general ledger"
        className="mt-4"
      >
        These figures come from payments recorded on invoices and expenses
        recorded here. They show day-to-day cash movement; they are not
        double-entry accounts, and don&apos;t replace your accountant&apos;s
        books or tax filings.
      </Notice>
    </PageShell>
  );
}
