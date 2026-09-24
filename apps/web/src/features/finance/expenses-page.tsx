"use client";

import { useState } from "react";
import { Ban, Plus, SearchX, Wallet } from "lucide-react";
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
import { FilterBar, FilterSelect, SearchInput } from "@/components/app/filters";
import { ConfirmDialog } from "@/components/app/forms";
import { EmptyState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Expense } from "@/features/business/types";
import { formatDay } from "@/features/billing/utils";
import { financeService } from "./service";
import { ExpenseDialog } from "./expense-dialog";
import { CATEGORY_OPTIONS, categoryLabel } from "./utils";

const PAGE_SIZE = 25;

export function ExpensesPage() {
  return (
    <RequirePermission permission="finance.read" area="expenses">
      <ExpensesList />
    </RequirePermission>
  );
}

function ExpensesList() {
  const { can } = useSession();
  const canWrite = can("finance.write");
  const [state, setState, reset] = useUrlState({
    search: "",
    category: "",
    page: "1",
    new: "",
  });
  const [voiding, setVoiding] = useState<Expense | null>(null);
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    page,
    pageSize: PAGE_SIZE,
    search: state.search || undefined,
    category: state.category || undefined,
  };
  const query = useScopedQuery(
    ["expenses", params],
    () => financeService.expenses(params),
    {
      placeholderData: (previous) => previous,
    },
  );
  const voidExpense = useScopedMutation(
    (id: string) => financeService.voidExpense(id),
    {
      invalidate: [["expenses"], ["finance"]],
      success: (e) => `${e.number} voided`,
      onSuccess: () => setVoiding(null),
    },
  );
  const activeCount = [state.search, state.category].filter(Boolean).length;
  const dialogOpen = canWrite && state.new === "1";
  const setDialog = (open: boolean) =>
    setState({ new: open ? "1" : "" }, { resetPage: false });
  const currency = query.data?.items[0]?.currency;

  const columns: Column<Expense>[] = [
    {
      key: "number",
      header: "Number",
      cell: (e) => (
        <span className="font-medium whitespace-nowrap">{e.number}</span>
      ),
    },
    {
      key: "date",
      header: "Date",
      cell: (e) => (
        <span className="tabular whitespace-nowrap">
          {formatDay(e.incurred_on)}
        </span>
      ),
      hideBelow: "sm",
    },
    {
      key: "category",
      header: "Category",
      cell: (e) => categoryLabel(e.category),
      hideBelow: "md",
    },
    {
      key: "description",
      header: "Description",
      cell: (e) => (
        <span
          className={
            e.status === "void"
              ? "block max-w-72 truncate text-muted-foreground line-through"
              : "block max-w-72 truncate"
          }
        >
          {e.description}
        </span>
      ),
    },
    {
      key: "vendor",
      header: "Vendor",
      cell: (e) => (
        <span className="block max-w-44 truncate">{e.vendor || "—"}</span>
      ),
      hideBelow: "lg",
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      cell: (e) => (
        <span className="tabular font-medium whitespace-nowrap">
          {formatMoney(e.amount, e.currency)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (e) => <StatusBadge status={e.status} />,
      hideBelow: "sm",
    },
    {
      key: "recorded_by",
      header: "Recorded by",
      cell: (e) => (
        <span className="whitespace-nowrap text-muted-foreground">
          {e.recorded_by_label}
        </span>
      ),
      hideBelow: "xl",
    },
    ...(canWrite
      ? [
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            align: "right" as const,
            cell: (e: Expense) =>
              e.status === "recorded" ? (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => setVoiding(e)}
                  aria-label={`Void expense ${e.number}`}
                  title="Void expense"
                >
                  <Ban />
                </Button>
              ) : null,
          },
        ]
      : []),
  ];

  return (
    <PageShell>
      <PageHeader
        title="Expenses"
        description="What the business spends, by category. Void mistakes instead of deleting them."
        actions={
          canWrite ? (
            <Button onClick={() => setDialog(true)}>
              <Plus /> Record expense
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="finance" />

      <FilterBar activeCount={activeCount} onClear={reset}>
        <SearchInput
          value={state.search}
          onChange={(search) => setState({ search })}
          placeholder="Search description or vendor…"
          className="w-full md:w-72"
        />
        <FilterSelect
          label="Category"
          value={state.category}
          options={CATEGORY_OPTIONS}
          onChange={(category) => setState({ category })}
        />
      </FilterBar>

      <DataTable
        columns={columns}
        rows={query.data?.items}
        getRowId={(e) => e.id}
        loading={query.isPending}
        error={query.error}
        onRetry={() => void query.refetch()}
        caption="Expenses"
        empty={
          activeCount > 0 ? (
            <EmptyState
              icon={SearchX}
              title="No expenses match these filters"
              description="Try a different search or category."
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Wallet}
              title="No expenses recorded yet"
              description="Record rent, payroll, software and other spending to see where cash goes."
              action={
                canWrite ? (
                  <Button size="sm" onClick={() => setDialog(true)}>
                    <Plus /> Record expense
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

      {canWrite && (
        <ExpenseDialog
          open={dialogOpen}
          onOpenChange={setDialog}
          currency={currency}
        />
      )}
      <ConfirmDialog
        open={voiding !== null}
        onOpenChange={(open) => !open && setVoiding(null)}
        title={voiding ? `Void ${voiding.number}?` : "Void expense?"}
        description="Voiding cannot be undone."
        consequences={[
          voiding
            ? `${formatMoney(voiding.amount, voiding.currency)} is removed from cash out and category totals.`
            : "The amount is removed from cash out and category totals.",
          "The expense stays in the list, marked void, for your records.",
          "If it was recorded with the wrong details, record a new expense afterwards.",
        ]}
        confirmLabel="Void expense"
        destructive
        loading={voidExpense.isPending}
        onConfirm={() => voiding && voidExpense.mutate(voiding.id)}
      />
    </PageShell>
  );
}
