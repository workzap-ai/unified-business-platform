"use client";

import Link from "next/link";
import { FilePlus2, Receipt, SearchX } from "lucide-react";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  ModuleNav,
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import {
  ColumnsMenu,
  DataTable,
  Pagination,
  useColumnVisibility,
  type Column,
} from "@/components/app/data-table";
import {
  FilterBar,
  FilterSelect,
  SavedViews,
  SearchInput,
  type SavedView,
} from "@/components/app/filters";
import { EmptyState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Invoice } from "@/features/business/types";
import { billingService } from "./service";
import { DueDate, InvoiceStatus } from "./invoice-bits";
import { formatDay } from "./utils";

const PAGE_SIZE = 25;

const VIEWS: SavedView[] = [
  { id: "all", name: "All", params: {}, builtIn: true },
  { id: "draft", name: "Draft", params: { status: "draft" }, builtIn: true },
  { id: "issued", name: "Issued", params: { status: "issued" }, builtIn: true },
  {
    id: "partially_paid",
    name: "Partially paid",
    params: { status: "partially_paid" },
    builtIn: true,
  },
  { id: "paid", name: "Paid", params: { status: "paid" }, builtIn: true },
  {
    id: "overdue",
    name: "Overdue",
    params: { overdue: "true" },
    builtIn: true,
  },
  { id: "void", name: "Void", params: { status: "void" }, builtIn: true },
];

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "issued", label: "Issued" },
  { value: "partially_paid", label: "Partially paid" },
  { value: "paid", label: "Paid" },
  { value: "void", label: "Void" },
];

const COLUMNS: Column<Invoice>[] = [
  {
    key: "number",
    header: "Number",
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
  },
  {
    key: "issue_date",
    header: "Issued",
    cell: (i) =>
      i.issue_date ? (
        <span className="tabular whitespace-nowrap">
          {formatDay(i.issue_date)}
        </span>
      ) : (
        <span className="text-muted-foreground">Not issued</span>
      ),
    hideBelow: "lg",
    optional: true,
  },
  {
    key: "due_date",
    header: "Due",
    cell: (i) => <DueDate invoice={i} />,
    hideBelow: "md",
    optional: true,
  },
  {
    key: "total",
    header: "Total",
    align: "right",
    cell: (i) => (
      <span className="tabular whitespace-nowrap">
        {formatMoney(i.total, i.currency)}
      </span>
    ),
    hideBelow: "lg",
    optional: true,
  },
  {
    key: "balance",
    header: "Balance due",
    align: "right",
    cell: (i) =>
      i.status === "void" ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        <span className="tabular font-medium whitespace-nowrap">
          {formatMoney(i.balance_due, i.currency)}
        </span>
      ),
  },
];

export function InvoicesPage() {
  return (
    <RequirePermission permission="billing.read" area="invoices">
      <InvoicesList />
    </RequirePermission>
  );
}

function InvoicesList() {
  const { can } = useSession();
  const [state, setState, reset] = useUrlState({
    search: "",
    status: "",
    overdue: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    page,
    pageSize: PAGE_SIZE,
    search: state.search || undefined,
    status: state.status || undefined,
    overdue: state.overdue === "true" || undefined,
  };
  const query = useScopedQuery(
    ["invoices", params],
    () => billingService.invoices(params),
    {
      placeholderData: (previous) => previous,
    },
  );
  const { hidden, toggle } = useColumnVisibility("billing-invoices", COLUMNS);
  const activeCount = [state.search, state.status, state.overdue].filter(
    Boolean,
  ).length;
  const canWrite = can("billing.write");

  return (
    <PageShell>
      <PageHeader
        title="Invoices"
        description="Bill customers, track what's due and record payments."
        actions={
          canWrite ? (
            <Button asChild>
              <Link href="/billing/invoices/new">
                <FilePlus2 /> New invoice
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="billing" />

      <SavedViews
        tableId="billing-invoices"
        views={VIEWS}
        current={{
          search: state.search,
          status: state.status,
          overdue: state.overdue,
        }}
        onApply={(p) => setState({ search: "", status: "", overdue: "", ...p })}
      />
      <FilterBar
        activeCount={activeCount}
        onClear={reset}
        actions={
          <ColumnsMenu columns={COLUMNS} hidden={hidden} onToggle={toggle} />
        }
      >
        <SearchInput
          value={state.search}
          onChange={(search) => setState({ search })}
          placeholder="Search number or customer…"
          className="w-full md:w-72"
        />
        <FilterSelect
          label="Status"
          value={state.status}
          options={STATUS_OPTIONS}
          onChange={(status) => setState({ status })}
        />
        <FilterSelect
          label="Due"
          value={state.overdue}
          options={[{ value: "true", label: "Overdue only" }]}
          onChange={(overdue) => setState({ overdue })}
        />
      </FilterBar>

      <DataTable
        columns={COLUMNS}
        hiddenColumns={hidden}
        rows={query.data?.items}
        getRowId={(i) => i.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        rowHref={(i) => `/billing/invoices/${i.id}`}
        caption="Invoices"
        empty={
          activeCount > 0 ? (
            <EmptyState
              icon={SearchX}
              title="No invoices match these filters"
              description="Try a different search or clear the filters to see every invoice."
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Receipt}
              title="No invoices yet"
              description="Create an invoice for a customer, or invoices will appear here when confirmed orders are billed."
              action={
                canWrite ? (
                  <Button size="sm" asChild>
                    <Link href="/billing/invoices/new">
                      <FilePlus2 /> New invoice
                    </Link>
                  </Button>
                ) : undefined
              }
            />
          )
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
