"use client";

import Link from "next/link";
import { Wallet } from "lucide-react";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { EmptyState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import type { Payment } from "@/features/business/types";
import { billingService } from "./service";
import { formatDay, methodLabel } from "./utils";

const PAGE_SIZE = 25;

type PaymentRow = Payment & {
  invoice_number?: string;
  customer_name?: string | null;
};

const COLUMNS: Column<PaymentRow>[] = [
  {
    key: "number",
    header: "Payment",
    cell: (p) => (
      <span className="font-medium whitespace-nowrap">{p.number}</span>
    ),
  },
  {
    key: "invoice",
    header: "Invoice",
    cell: (p) => (
      <Link
        href={`/billing/invoices/${p.invoice_id}`}
        className="whitespace-nowrap text-primary hover:underline"
      >
        {p.invoice_number ?? "View invoice"}
      </Link>
    ),
  },
  {
    key: "customer",
    header: "Customer",
    cell: (p) => (
      <span className="block max-w-48 truncate">{p.customer_name ?? "—"}</span>
    ),
    hideBelow: "md",
  },
  {
    key: "method",
    header: "Method",
    cell: (p) => methodLabel(p.method),
    hideBelow: "sm",
  },
  {
    key: "received_on",
    header: "Received on",
    cell: (p) => (
      <span className="tabular whitespace-nowrap">
        {formatDay(p.received_on)}
      </span>
    ),
    hideBelow: "sm",
  },
  {
    key: "amount",
    header: "Amount",
    align: "right",
    cell: (p) => (
      <span className="tabular font-medium whitespace-nowrap">
        {formatMoney(p.amount, p.currency)}
      </span>
    ),
  },
  {
    key: "reference",
    header: "Reference",
    cell: (p) =>
      p.reference ? (
        <span className="block max-w-40 truncate font-mono text-xs">
          {p.reference}
        </span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
    hideBelow: "lg",
  },
  {
    key: "recorded_by",
    header: "Recorded by",
    cell: (p) => (
      <span className="whitespace-nowrap text-muted-foreground">
        {p.recorded_by_label}
      </span>
    ),
    hideBelow: "xl",
  },
];

export function PaymentsPage() {
  return (
    <RequirePermission permission="billing.read" area="payments">
      <PaymentsList />
    </RequirePermission>
  );
}

function PaymentsList() {
  const [state, setState] = useUrlState({ page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const query = useScopedQuery(
    ["payments", { page, pageSize: PAGE_SIZE }],
    () => billingService.payments({ page, pageSize: PAGE_SIZE }),
    { placeholderData: (previous) => previous },
  );

  return (
    <PageShell>
      <PageHeader
        title="Payments"
        description="Every payment recorded against your invoices, newest first."
      />
      <ModuleNav moduleKey="billing" />
      <DataTable
        columns={COLUMNS}
        rows={query.data?.items}
        getRowId={(p) => p.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(p) => `/billing/invoices/${p.invoice_id}`}
        caption="Payments"
        empty={
          <EmptyState
            icon={Wallet}
            title="No payments recorded yet"
            description="Open an issued invoice and choose Record payment when money arrives."
            action={
              <Button variant="secondary" size="sm" asChild>
                <Link href="/billing/invoices?status=issued">
                  View issued invoices
                </Link>
              </Button>
            }
          />
        }
      />
      {query.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data.total}
          onPage={(next) =>
            setState({ page: String(next) }, { resetPage: false })
          }
        />
      )}
    </PageShell>
  );
}
