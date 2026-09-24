"use client";

import { useState } from "react";
import Link from "next/link";
import { Boxes, SlidersHorizontal } from "lucide-react";
import { formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Label, Switch } from "@/components/ui/controls";
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
import type { StockLevel } from "@/features/business/types";
import { inventoryService } from "./service";
import { useLocations } from "./hooks";
import { stockState } from "./lib";
import { AvailableBar, StockChip } from "./stock-display";
import { AdjustStockSheet, type AdjustTarget } from "./adjust-stock-sheet";

const PAGE_SIZE = 25;
const VIEWS: SavedView[] = [
  { id: "all", name: "All stock", params: {}, builtIn: true },
  { id: "low", name: "Low stock", params: { low_only: "true" }, builtIn: true },
];

export function StockPage() {
  return (
    <RequirePermission permission="inventory.read" area="inventory">
      <StockPageInner />
    </RequirePermission>
  );
}

function StockPageInner() {
  const { can } = useSession();
  const canAdjust = can("inventory.adjust");
  const [state, setState, reset] = useUrlState({
    search: "",
    location: "",
    low_only: "",
    page: "1",
  });
  const page = Math.max(1, Number(state.page) || 1);
  const params = {
    page,
    pageSize: PAGE_SIZE,
    search: state.search || undefined,
    locationId: state.location || undefined,
    lowOnly: state.low_only === "true",
  };
  const levels = useScopedQuery(
    ["inventory", "levels", params],
    () => inventoryService.levels(params),
    {
      placeholderData: (prev) => prev,
    },
  );
  const locations = useLocations();
  const [target, setTarget] = useState<AdjustTarget | null>(null);
  const [open, setOpen] = useState(false);

  const adjust = (row: StockLevel) => {
    setTarget({
      variant_id: row.variant_id,
      product_name: row.product_name,
      variant_name: row.variant_name,
      sku: row.sku,
      location_id: row.location_id,
    });
    setOpen(true);
  };

  const columns: Column<StockLevel>[] = [
    {
      key: "product",
      header: "Product",
      cell: (r) => (
        <div className="min-w-0">
          <Link
            href={`/catalog/products/${r.product_id}`}
            className="block truncate font-medium hover:underline"
          >
            {r.product_name}
          </Link>
          <p className="truncate text-xs text-muted-foreground">
            {r.variant_name}
            <span className="sm:hidden"> · {r.sku}</span>
          </p>
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
      key: "location",
      header: "Location",
      hideBelow: "md",
      cell: (r) => r.location_name,
    },
    {
      key: "on_hand",
      header: "On hand",
      align: "right",
      hideBelow: "lg",
      cell: (r) => <span className="tabular">{formatNumber(r.on_hand)}</span>,
    },
    {
      key: "reserved",
      header: "Reserved",
      align: "right",
      hideBelow: "lg",
      cell: (r) => (
        <span className="tabular text-muted-foreground">
          {formatNumber(r.reserved)}
        </span>
      ),
    },
    {
      key: "available",
      header: "Available",
      align: "right",
      cell: (r) => (
        <AvailableBar
          available={r.available}
          threshold={r.low_stock_threshold}
          state={stockState(r)}
        />
      ),
    },
    {
      key: "threshold",
      header: "Threshold",
      align: "right",
      hideBelow: "xl",
      cell: (r) => (
        <span className="tabular text-muted-foreground">
          {r.low_stock_threshold ?? "—"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      hideBelow: "sm",
      cell: (r) => <StockChip state={stockState(r)} />,
    },
  ];
  if (canAdjust) {
    columns.push({
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      width: "1%",
      cell: (r) => (
        <Button
          variant="ghost"
          size="xs"
          onClick={() => adjust(r)}
          aria-label={`Adjust stock for ${r.product_name} ${r.sku} at ${r.location_name}`}
        >
          <SlidersHorizontal /> <span className="hidden sm:inline">Adjust</span>
        </Button>
      ),
    });
  }

  const filtered = Boolean(state.search || state.location || state.low_only);
  const activeCount = [state.search, state.location, state.low_only].filter(
    Boolean,
  ).length;

  return (
    <PageShell>
      <PageHeader
        title="Stock levels"
        description="On-hand, reserved and available quantities for every tracked SKU and location."
      />
      <ModuleNav moduleKey="inventory" />
      <SavedViews
        tableId="inventory-stock"
        views={VIEWS}
        current={{
          search: state.search,
          location: state.location,
          low_only: state.low_only,
        }}
        onApply={(p) =>
          setState({
            search: p.search ?? "",
            location: p.location ?? "",
            low_only: p.low_only ?? "",
          })
        }
      />
      <FilterBar activeCount={activeCount} onClear={reset}>
        <SearchInput
          value={state.search}
          onChange={(search) => setState({ search })}
          placeholder="Search product or SKU"
          className="w-full min-w-44 md:w-72"
        />
        <FilterSelect
          label="Location"
          value={state.location}
          options={(locations.sorted ?? []).map((l) => ({
            value: l.id,
            label: l.name,
          }))}
          onChange={(location) => setState({ location })}
        />
        <div className="flex h-8 shrink-0 items-center gap-2 rounded-md border border-border bg-surface px-2.5">
          <Switch
            id="low-only"
            checked={state.low_only === "true"}
            onCheckedChange={(checked) =>
              setState({ low_only: checked ? "true" : "" })
            }
          />
          <Label
            htmlFor="low-only"
            className="cursor-pointer whitespace-nowrap"
          >
            Low stock only
          </Label>
        </div>
      </FilterBar>
      <DataTable
        caption="Stock levels"
        columns={columns}
        rows={levels.data?.items}
        getRowId={(r) => `${r.variant_id}:${r.location_id}`}
        loading={levels.isPending}
        error={levels.error}
        onRetry={() => void levels.refetch()}
        empty={
          filtered ? (
            <EmptyState
              compact
              icon={Boxes}
              title={
                state.low_only === "true" && !state.search && !state.location
                  ? "Nothing is low on stock"
                  : "No stock matches these filters"
              }
              description={
                state.low_only === "true"
                  ? "Every tracked SKU is above its low-stock threshold."
                  : "Try a different search or location."
              }
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Boxes}
              title="No stock recorded yet"
              description="Stock levels appear once a tracked product receives its first receipt or adjustment."
              action={
                <Button size="sm" asChild>
                  <Link href="/catalog/products">Go to products</Link>
                </Button>
              }
              secondary={
                <Button size="sm" variant="secondary" asChild>
                  <Link href="/inventory/locations">Set up locations</Link>
                </Button>
              }
            />
          )
        }
      />
      {levels.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={levels.data.total}
          onPage={(p) => setState({ page: String(p) }, { resetPage: false })}
        />
      )}
      <AdjustStockSheet target={target} open={open} onOpenChange={setOpen} />
    </PageShell>
  );
}
