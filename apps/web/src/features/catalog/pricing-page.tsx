"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueries } from "@tanstack/react-query";
import { BadgeDollarSign, Pencil } from "lucide-react";
import { formatMoney } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  PageHeader,
  PageShell,
  ModuleNav,
  RequirePermission,
} from "@/components/app/page";
import {
  DataTable,
  Pagination,
  type Column,
} from "@/components/app/data-table";
import { FilterBar, FilterSelect, SearchInput } from "@/components/app/filters";
import { EmptyState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { Variant } from "@/features/business/types";
import { catalogService } from "./service";
import { EditVariantDialog } from "./variant-dialogs";

const PAGE_SIZE = 25;

type PriceRow = Variant & {
  product_name: string;
  product_status: "active" | "inactive";
};

export function PricingPage() {
  return (
    <RequirePermission permission="catalog.read" area="the catalog">
      <PricingInner />
    </RequirePermission>
  );
}

function PricingInner() {
  const { can, scopeKey, status: sessionStatus } = useSession();
  const canWrite = can("catalog.write");
  const [state, setState, reset] = useUrlState({
    search: "",
    status: "",
    currency: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    page,
    pageSize: PAGE_SIZE,
    search: state.search || undefined,
  };
  const products = useScopedQuery(
    ["catalog", "products", params],
    () => catalogService.products(params),
    {
      placeholderData: (prev) => prev,
    },
  );

  // Variant prices live on product detail; load details for this page in parallel (max 25),
  // sharing cache entries with the product record page.
  const details = useQueries({
    queries: (products.data?.items ?? []).map((p) => ({
      queryKey: [...scopeKey, "catalog", "product", p.id],
      queryFn: () => catalogService.product(p.id),
      enabled: sessionStatus === "ready",
      staleTime: 30_000,
    })),
  });
  const detailsPending = details.some((d) => d.isPending);
  const detailsFailed = details.filter((d) => d.isError).length;

  const allRows: PriceRow[] = details.flatMap((d) =>
    d.data
      ? d.data.variants.map((v) => ({
          ...v,
          product_name: d.data.name,
          product_status: d.data.status,
        }))
      : [],
  );
  const currencies = [...new Set(allRows.map((r) => r.currency))].sort();
  const rows = allRows.filter(
    (r) =>
      (!state.status || r.status === state.status) &&
      (!state.currency || r.currency === state.currency),
  );

  const [editing, setEditing] = useState<PriceRow | null>(null);

  const columns: Column<PriceRow>[] = [
    {
      key: "product",
      header: "Product",
      cell: (r) => (
        <div className="min-w-0">
          <Link
            href={`/catalog/products/${r.product_id}`}
            className="block max-w-64 truncate font-medium hover:underline"
          >
            {r.product_name}
          </Link>
          <p className="truncate text-xs text-muted-foreground">{r.name}</p>
        </div>
      ),
    },
    {
      key: "sku",
      header: "SKU",
      hideBelow: "sm",
      cell: (r) => <span className="font-mono text-xs">{r.sku}</span>,
    },
    {
      key: "currency",
      header: "Currency",
      hideBelow: "md",
      cell: (r) => <span className="text-muted-foreground">{r.currency}</span>,
    },
    {
      key: "status",
      header: "Status",
      hideBelow: "md",
      cell: (r) => (
        <StatusBadge
          status={r.product_status === "inactive" ? "inactive" : r.status}
          label={
            r.product_status === "inactive" ? "Product inactive" : undefined
          }
        />
      ),
    },
    {
      key: "price",
      header: "Price",
      align: "right",
      cell: (r) => (
        <span className="tabular font-medium">
          {formatMoney(r.price, r.currency)}
        </span>
      ),
    },
  ];
  if (canWrite)
    columns.push({
      key: "edit",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      width: "1%",
      cell: (r) => (
        <Button
          variant="ghost"
          size="xs"
          onClick={() => setEditing(r)}
          aria-label={`Change price for ${r.sku}`}
        >
          <Pencil /> <span className="hidden sm:inline">Price</span>
        </Button>
      ),
    });

  const activeCount = [state.search, state.status, state.currency].filter(
    Boolean,
  ).length;

  return (
    <PageShell>
      <PageHeader
        title="Pricing"
        description="Current price of every variant. Price changes are audited and apply to new quotes and orders only."
      />
      <ModuleNav moduleKey="catalog" />
      <FilterBar activeCount={activeCount} onClear={reset}>
        <SearchInput
          value={state.search}
          onChange={(search) => setState({ search })}
          placeholder="Search product or SKU"
          className="w-full min-w-44 md:w-72"
        />
        <FilterSelect
          label="Status"
          value={state.status}
          options={[
            { value: "active", label: "Active" },
            { value: "inactive", label: "Inactive" },
          ]}
          onChange={(status) => setState({ status }, { resetPage: false })}
        />
        {currencies.length > 1 || state.currency ? (
          <FilterSelect
            label="Currency"
            value={state.currency}
            options={currencies.map((c) => ({ value: c, label: c }))}
            onChange={(currency) =>
              setState({ currency }, { resetPage: false })
            }
          />
        ) : null}
      </FilterBar>
      {(state.status || state.currency) && (
        <p className="-mt-1 mb-2 text-xs text-muted-foreground">
          Status and currency filter the variants of the products on this page.
        </p>
      )}
      <DataTable
        caption="Variant prices"
        columns={columns}
        rows={
          products.isPending || (detailsPending && !allRows.length)
            ? undefined
            : rows
        }
        getRowId={(r) => r.id}
        loading={products.isPending || (detailsPending && !allRows.length)}
        error={products.error}
        onRetry={() => void products.refetch()}
        empty={
          activeCount ? (
            <EmptyState
              compact
              icon={BadgeDollarSign}
              title="No prices match these filters"
              action={
                <Button size="sm" variant="secondary" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={BadgeDollarSign}
              title="No prices yet"
              description="Prices come from product variants. Add a product to set its first price."
              action={
                canWrite ? (
                  <Button size="sm" asChild>
                    <Link href="/catalog/products/new">Add product</Link>
                  </Button>
                ) : undefined
              }
            />
          )
        }
      />
      {detailsFailed > 0 && (
        <p className="mt-2 text-xs text-danger" role="alert">
          Prices for {detailsFailed}{" "}
          {detailsFailed === 1 ? "product" : "products"} couldn’t be loaded.
        </p>
      )}
      {products.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={products.data.total}
          onPage={(p) => setState({ page: String(p) }, { resetPage: false })}
        />
      )}
      <EditVariantDialog
        variant={editing}
        productName={editing?.product_name}
        open={Boolean(editing)}
        onOpenChange={(o) => !o && setEditing(null)}
        priceOnly
      />
    </PageShell>
  );
}
