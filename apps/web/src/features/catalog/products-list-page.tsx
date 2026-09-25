"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Bot, EyeOff, Package, Plus } from "lucide-react";
import { formatDate, formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  ModuleNav,
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
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type { ProductListItem } from "@/features/business/types";
import { useProductStock } from "@/features/inventory/hooks";
import { StockChip } from "@/features/inventory/stock-display";
import { catalogService } from "./service";
import { useCategories } from "./hooks";
import { priceRange } from "./lib";

const PAGE_SIZE = 25;
const VIEWS: SavedView[] = [
  { id: "all", name: "All", params: {}, builtIn: true },
  { id: "active", name: "Active", params: { status: "active" }, builtIn: true },
  {
    id: "inactive",
    name: "Inactive",
    params: { status: "inactive" },
    builtIn: true,
  },
  {
    id: "hidden",
    name: "Hidden from PI",
    params: { pi: "hidden" },
    builtIn: true,
  },
];

export function ProductsListPage() {
  return (
    <RequirePermission permission="catalog.read" area="the catalog">
      <ProductsListInner />
    </RequirePermission>
  );
}

export function PiVisibility({ visible }: { visible: boolean }) {
  return visible ? (
    <Badge tone="pi">
      <Bot aria-hidden="true" /> Visible to PI
    </Badge>
  ) : (
    <Badge tone="outline" className="text-muted-foreground">
      <EyeOff aria-hidden="true" /> Hidden from PI
    </Badge>
  );
}

function ProductsListInner() {
  const { can } = useSession();
  const canWrite = can("catalog.write");
  const canStock = can("inventory.read");
  const [state, setState, reset] = useUrlState({
    search: "",
    status: "",
    category: "",
    pi: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    page,
    pageSize: PAGE_SIZE,
    search: state.search || undefined,
    status: state.status || undefined,
    categoryId: state.category || undefined,
  };
  const products = useScopedQuery(
    ["catalog", "products", params],
    () => catalogService.products(params),
    {
      placeholderData: (prev) => prev,
    },
  );
  const categories = useCategories();
  const stock = useProductStock(canStock);

  const hiddenOnly = state.pi === "hidden";
  const rows = useMemo(
    () =>
      hiddenOnly
        ? products.data?.items.filter((p) => !p.pi_visible)
        : products.data?.items,
    [products.data, hiddenOnly],
  );

  const columns: Column<ProductListItem>[] = [
    {
      key: "product",
      header: "Offering",
      cell: (p) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="hidden size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-muted text-muted-foreground sm:flex">
            <Package className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <Link
              href={`/catalog/products/${p.id}`}
              className="block max-w-72 truncate font-medium hover:underline"
            >
              {p.name}
            </Link>
            <p className="truncate text-xs text-muted-foreground">
              {p.offering_type.toUpperCase()} ·{" "}
              {p.category_name ?? "Uncategorized"}
            </p>
          </div>
        </div>
      ),
    },
    {
      key: "variants",
      header: "Variants",
      align: "right",
      hideBelow: "md",
      cell: (p) => (
        <span className="tabular">{formatNumber(p.variant_count)}</span>
      ),
    },
    {
      key: "price",
      header: "Price",
      align: "right",
      cell: (p) => (
        <span className="tabular whitespace-nowrap">
          {priceRange(p.min_price, p.max_price, p.currency)}
        </span>
      ),
    },
  ];
  if (canStock)
    columns.push({
      key: "stock",
      header: "Stock",
      hideBelow: "sm",
      optional: true,
      cell: (p) => {
        if (stock.isPending)
          return <span className="text-xs text-muted-foreground">…</span>;
        const s = stock.map?.get(p.id);
        if (!s) return <StockChip state="untracked" />;
        return (
          <span className="inline-flex items-center gap-2">
            <StockChip
              state={s.state}
              label={
                s.state === "healthy"
                  ? "In stock"
                  : s.state === "low"
                    ? "Low"
                    : "Out"
              }
            />
            <span className="tabular hidden text-xs text-muted-foreground xl:inline">
              {formatNumber(s.available)} avail.
            </span>
          </span>
        );
      },
    });
  columns.push(
    {
      key: "pi",
      header: "PI",
      hideBelow: "lg",
      optional: true,
      cell: (p) => <PiVisibility visible={p.pi_visible} />,
    },
    {
      key: "status",
      header: "Status",
      hideBelow: "sm",
      cell: (p) => <StatusBadge status={p.status} />,
    },
    {
      key: "created",
      header: "Added",
      hideBelow: "xl",
      optional: true,
      defaultHidden: true,
      cell: (p) => (
        <span className="whitespace-nowrap text-muted-foreground">
          {formatDate(p.created_at)}
        </span>
      ),
    },
  );
  const { hidden, toggle } = useColumnVisibility("catalog-products", columns);

  const activeCount = [
    state.search,
    state.status,
    state.category,
    state.pi,
  ].filter(Boolean).length;
  const filtered = activeCount > 0;

  return (
    <PageShell>
      <PageHeader
        title="Services & offerings"
        description="Everything you sell, with variants, prices and what PI can offer customers."
        actions={
          canWrite ? (
            <Button asChild>
              <Link href="/catalog/products/new">
                <Plus /> Add offering
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="catalog" />
      <SavedViews
        tableId="catalog-products"
        views={VIEWS}
        current={{
          search: state.search,
          status: state.status,
          category: state.category,
          pi: state.pi,
        }}
        onApply={(p) =>
          setState({
            search: p.search ?? "",
            status: p.status ?? "",
            category: p.category ?? "",
            pi: p.pi ?? "",
          })
        }
      />
      <FilterBar
        activeCount={activeCount}
        onClear={reset}
        actions={
          <ColumnsMenu columns={columns} hidden={hidden} onToggle={toggle} />
        }
      >
        <SearchInput
          value={state.search}
          onChange={(search) => setState({ search })}
          placeholder="Search name or SKU"
          className="w-full min-w-44 md:w-72"
        />
        <FilterSelect
          label="Status"
          value={state.status}
          options={[
            { value: "active", label: "Active" },
            { value: "inactive", label: "Inactive" },
          ]}
          onChange={(status) => setState({ status })}
        />
        <FilterSelect
          label="Category"
          value={state.category}
          options={(categories.data ?? []).map((c) => ({
            value: c.id,
            label: c.name,
          }))}
          onChange={(category) => setState({ category })}
        />
        {hiddenOnly && (
          <FilterSelect
            label="PI"
            value="hidden"
            options={[{ value: "hidden", label: "Hidden" }]}
            onChange={(pi) => setState({ pi }, { resetPage: false })}
          />
        )}
      </FilterBar>
      {hiddenOnly && (
        <p className="-mt-1 mb-2 text-xs text-muted-foreground">
          Showing hidden products from this page of results
          {products.data && products.data.total > PAGE_SIZE
            ? " — move between pages to see more"
            : ""}
          .
        </p>
      )}
      <DataTable
        caption="Products"
        columns={columns}
        hiddenColumns={hidden}
        rows={rows}
        getRowId={(p) => p.id}
        rowHref={(p) => `/catalog/products/${p.id}`}
        loading={products.isPending}
        error={products.error}
        onRetry={() => void products.refetch()}
        empty={
          filtered ? (
            <EmptyState
              compact
              icon={Package}
              title={
                hiddenOnly && !state.search
                  ? "Nothing hidden from PI here"
                  : "No products match these filters"
              }
              description={
                hiddenOnly
                  ? "Every product on this page is visible to PI."
                  : "Try a different search, status or category."
              }
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Package}
              title="No products yet"
              description="Add the products and services you sell. Prices and stock here power quotes, orders and PI's answers."
              action={
                canWrite ? (
                  <Button size="sm" asChild>
                    <Link href="/catalog/products/new">
                      <Plus /> Add offering
                    </Link>
                  </Button>
                ) : undefined
              }
            />
          )
        }
      />
      {products.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={products.data.total}
          onPage={(p) => setState({ page: String(p) }, { resetPage: false })}
        />
      )}
    </PageShell>
  );
}
