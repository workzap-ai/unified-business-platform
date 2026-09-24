"use client";

import Link from "next/link";
import { CheckCircle2, SearchX } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney, formatNumber, pluralize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/display";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Invoice } from "@/features/business/types";
import { billingService } from "@/features/billing/service";
import { DueDate, InvoiceStatus } from "@/features/billing/invoice-bits";
import { dayCount, daysFromToday } from "@/features/billing/utils";
import { financeService } from "./service";
import { AGING_BUCKETS, AGING_LABELS, periodRange } from "./utils";

const OPEN_PAGE_SIZE = 100;

function bucketOf(invoice: Pick<Invoice, "due_date">): string {
  const days = daysFromToday(invoice.due_date);
  if (days === null || days >= 0) return "current";
  const late = -days;
  return late <= 30
    ? "1-30"
    : late <= 60
      ? "31-60"
      : late <= 90
        ? "61-90"
        : "90+";
}

const COLUMNS: Column<Invoice>[] = [
  {
    key: "number",
    header: "Invoice",
    cell: (i) => (
      <Link
        href={`/billing/invoices/${i.id}`}
        className="font-medium whitespace-nowrap hover:underline"
      >
        {i.number}
      </Link>
    ),
  },
  {
    key: "customer",
    header: "Customer",
    cell: (i) => (
      <span className="block max-w-56 truncate">{i.customer_name ?? "—"}</span>
    ),
    hideBelow: "sm",
  },
  {
    key: "status",
    header: "Status",
    cell: (i) => <InvoiceStatus invoice={i} />,
    hideBelow: "md",
  },
  {
    key: "due",
    header: "Due",
    cell: (i) => <DueDate invoice={i} />,
    hideBelow: "lg",
  },
  {
    key: "days",
    header: "Days overdue",
    align: "right",
    cell: (i) => {
      const days = daysFromToday(i.due_date);
      if (days === null || days >= 0)
        return <span className="text-muted-foreground">—</span>;
      return (
        <span className="tabular font-medium text-danger">
          {dayCount(-days)}
        </span>
      );
    },
  },
  {
    key: "balance",
    header: "Balance due",
    align: "right",
    cell: (i) => (
      <span className="tabular font-medium whitespace-nowrap">
        {formatMoney(i.balance_due, i.currency)}
      </span>
    ),
  },
];

export function ReceivablesPage() {
  return (
    <RequirePermission permission="finance.read" area="receivables">
      <Receivables />
    </RequirePermission>
  );
}

function Receivables() {
  const { can } = useSession();
  const canBilling = can("billing.read");
  const [state, setState] = useUrlState({ bucket: "" });
  const { start, end } = periodRange(30);
  const summary = useScopedQuery(["finance", "summary", start, end], () =>
    financeService.summary(start, end),
  );
  const issued = useScopedQuery(
    ["invoices", { status: "issued", pageSize: OPEN_PAGE_SIZE }],
    () =>
      billingService.invoices({ status: "issued", pageSize: OPEN_PAGE_SIZE }),
    { enabled: canBilling },
  );
  const partial = useScopedQuery(
    ["invoices", { status: "partially_paid", pageSize: OPEN_PAGE_SIZE }],
    () =>
      billingService.invoices({
        status: "partially_paid",
        pageSize: OPEN_PAGE_SIZE,
      }),
    { enabled: canBilling },
  );

  const open =
    issued.data && partial.data
      ? [...issued.data.items, ...partial.data.items].sort((a, b) => {
          if (a.due_date === b.due_date)
            return a.number.localeCompare(b.number);
          if (!a.due_date) return 1;
          if (!b.due_date) return -1;
          return a.due_date.localeCompare(b.due_date);
        })
      : undefined;
  const truncated =
    (issued.data?.total ?? 0) > OPEN_PAGE_SIZE ||
    (partial.data?.total ?? 0) > OPEN_PAGE_SIZE;
  const bucket = AGING_BUCKETS.includes(
    state.bucket as (typeof AGING_BUCKETS)[number],
  )
    ? state.bucket
    : "";
  const rows =
    open && bucket ? open.filter((i) => bucketOf(i) === bucket) : open;
  const currency = summary.data?.currency ?? "USD";
  const tableError = issued.error ?? partial.error;

  return (
    <PageShell>
      <PageHeader
        title="Receivables"
        description="Money customers owe you, grouped by how late it is."
      />
      <ModuleNav moduleKey="finance" />

      {summary.isError ? (
        <Card className="mb-4">
          <ErrorState
            error={summary.error}
            onRetry={() => void summary.refetch()}
            compact
          />
        </Card>
      ) : (
        <div
          className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
          role="group"
          aria-label="Aging buckets"
        >
          {summary.isPending
            ? AGING_BUCKETS.map((b) => (
                <Skeleton key={b} className="h-[92px] rounded-xl" />
              ))
            : AGING_BUCKETS.map((b) => {
                const row = summary.data.aging.find((a) => a.bucket === b);
                const selected = bucket === b;
                const late = b !== "current" && Number(row?.amount ?? 0) > 0;
                return (
                  <button
                    key={b}
                    type="button"
                    aria-pressed={selected}
                    disabled={!canBilling}
                    onClick={() => setState({ bucket: selected ? "" : b })}
                    className={cn(
                      "rounded-xl border bg-surface p-3.5 text-left shadow-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default",
                      selected
                        ? "border-primary ring-2 ring-primary/15"
                        : "border-border hover:border-border-strong",
                    )}
                  >
                    <p className="text-[12.5px] font-medium text-muted-foreground">
                      {AGING_LABELS[b]}
                    </p>
                    <p
                      className={cn(
                        "tabular mt-1 truncate text-xl font-semibold tracking-tight",
                        late && "text-danger",
                      )}
                    >
                      {formatMoney(row?.amount ?? "0", currency)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {pluralize(row?.count ?? 0, "invoice")}
                    </p>
                  </button>
                );
              })}
        </div>
      )}

      {!canBilling ? (
        <Notice tone="neutral" title="Invoice details need billing access">
          You can see aging totals, but listing individual invoices requires the
          billing read permission.
        </Notice>
      ) : (
        <>
          <div className="mb-2 flex items-end justify-between gap-3">
            <div>
              <h2 className="text-[15px] font-semibold tracking-tight">
                Open invoices{bucket ? ` · ${AGING_LABELS[bucket]}` : ""}
              </h2>
              <p className="mt-0.5 text-[13px] text-muted-foreground">
                Issued and partially paid, earliest due first.
                {rows ? ` ${formatNumber(rows.length)} shown.` : ""}
              </p>
            </div>
            {bucket && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setState({ bucket: "" })}
              >
                Show all
              </Button>
            )}
          </div>
          {truncated && (
            <Notice tone="info" className="mb-3">
              Showing the first {OPEN_PAGE_SIZE} invoices of each status. Use
              the{" "}
              <Link
                href="/billing/invoices?status=issued"
                className="font-medium text-primary hover:underline"
              >
                invoice list
              </Link>{" "}
              to see the rest.
            </Notice>
          )}
          <DataTable
            columns={COLUMNS}
            rows={tableError ? undefined : rows}
            getRowId={(i) => i.id}
            loading={issued.isPending || partial.isPending}
            error={tableError}
            onRetry={() => {
              void issued.refetch();
              void partial.refetch();
            }}
            rowHref={(i) => `/billing/invoices/${i.id}`}
            caption="Open invoices"
            empty={
              bucket ? (
                <EmptyState
                  compact
                  icon={SearchX}
                  title={`Nothing in ${AGING_LABELS[bucket]}`}
                  description="No open invoices fall into this aging bucket."
                  action={
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setState({ bucket: "" })}
                    >
                      Show all open invoices
                    </Button>
                  }
                />
              ) : (
                <EmptyState
                  icon={CheckCircle2}
                  title="No open receivables"
                  description="Every issued invoice has been paid. New balances appear here as invoices are issued."
                />
              )
            }
          />
        </>
      )}
    </PageShell>
  );
}
