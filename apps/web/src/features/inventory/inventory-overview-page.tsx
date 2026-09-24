"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CircleSlash,
  MapPin,
  PackageCheck,
  SlidersHorizontal,
  Wallet,
} from "lucide-react";
import { formatMoney, formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  ModuleNav,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { DataTable, type Column } from "@/components/app/data-table";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { reportsService } from "@/features/reports/service";
import type { StockLevel } from "@/features/business/types";
import { inventoryService } from "./service";
import { useAllLevels, useLocations } from "./hooks";
import { distinctVariants, stockState, variantIndex } from "./lib";
import { AvailableBar, StockChip } from "./stock-display";
import { MovementList } from "./movement-list";
import { AdjustStockSheet, type AdjustTarget } from "./adjust-stock-sheet";

export function InventoryOverviewPage() {
  return (
    <RequirePermission permission="inventory.read" area="inventory">
      <InventoryOverviewInner />
    </RequirePermission>
  );
}

function InventoryOverviewInner() {
  const { can } = useSession();
  const canReports = can("reports.read");
  const canAdjust = can("inventory.adjust");
  const levels = useAllLevels();
  const locations = useLocations();
  const report = useScopedQuery(
    ["reports", "inventory"],
    () => reportsService.inventory(),
    { enabled: canReports },
  );
  const movements = useScopedQuery(
    ["inventory", "movements", { page: 1, pageSize: 8 }],
    () => inventoryService.movements({ page: 1, pageSize: 8 }),
  );
  const [target, setTarget] = useState<AdjustTarget | null>(null);
  const [open, setOpen] = useState(false);

  const items = useMemo(() => levels.data?.items ?? [], [levels.data]);
  const variants = useMemo(() => variantIndex(items), [items]);
  const tracked = distinctVariants(items);
  const low = distinctVariants(items, (l) => l.is_low && l.available > 0);
  const out = distinctVariants(items, (l) => l.available <= 0);
  const lowRows = useMemo(
    () =>
      items
        .filter((l) => l.is_low || l.available <= 0)
        .sort(
          (a, b) =>
            a.available - b.available ||
            a.product_name.localeCompare(b.product_name),
        )
        .slice(0, 10),
    [items],
  );
  const loading = levels.isPending;

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
            <span className="font-mono">{r.sku}</span> · {r.location_name}
          </p>
        </div>
      ),
    },
    {
      key: "threshold",
      header: "Threshold",
      align: "right",
      hideBelow: "md",
      cell: (r) => (
        <span className="tabular text-muted-foreground">
          {r.low_stock_threshold ?? "—"}
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
      key: "status",
      header: "Status",
      hideBelow: "sm",
      cell: (r) => <StockChip state={stockState(r)} />,
    },
  ];
  if (canAdjust)
    columns.push({
      key: "adjust",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      width: "1%",
      cell: (r) => (
        <Button
          variant="ghost"
          size="xs"
          aria-label={`Adjust stock for ${r.product_name} ${r.sku}`}
          onClick={() => {
            setTarget({
              variant_id: r.variant_id,
              product_name: r.product_name,
              variant_name: r.variant_name,
              sku: r.sku,
              location_id: r.location_id,
            });
            setOpen(true);
          }}
        >
          <SlidersHorizontal /> <span className="hidden sm:inline">Adjust</span>
        </Button>
      ),
    });

  if (levels.isError) {
    return (
      <PageShell>
        <PageHeader
          title="Inventory"
          description="Stock health across products and locations."
        />
        <ModuleNav moduleKey="inventory" />
        <ErrorState
          error={levels.error}
          onRetry={() => void levels.refetch()}
        />
      </PageShell>
    );
  }

  const noLocations = locations.isSuccess && locations.data.length === 0;

  return (
    <PageShell>
      <PageHeader
        title="Inventory"
        description="Stock health across products and locations."
        actions={
          <>
            <Button variant="secondary" asChild>
              <Link href="/inventory/movements">Ledger</Link>
            </Button>
            <Button asChild>
              <Link href="/inventory/stock">
                <Boxes /> Stock levels
              </Link>
            </Button>
          </>
        }
      />
      <ModuleNav moduleKey="inventory" />

      {noLocations && (
        <Notice
          tone="warning"
          icon={MapPin}
          title="Create your first stock location"
          className="mb-4"
          action={
            <Button size="sm" variant="secondary" asChild>
              <Link href="/inventory/locations">Add location</Link>
            </Button>
          }
        >
          Stock is counted per location. Add one before recording receipts.
        </Notice>
      )}

      <MetricGrid className={canReports ? "xl:grid-cols-5" : "xl:grid-cols-4"}>
        <MetricCard
          label="Tracked SKUs"
          icon={PackageCheck}
          loading={loading}
          value={formatNumber(tracked)}
          href="/inventory/stock"
          detail={
            levels.data?.truncated
              ? "First 1,000 stock lines"
              : `${formatNumber(items.length)} stock lines`
          }
        />
        <MetricCard
          label="Low stock"
          icon={AlertTriangle}
          loading={loading}
          value={formatNumber(low)}
          tone={low > 0 ? "warning" : "default"}
          href="/inventory/stock?low_only=true"
          detail="At or below threshold"
        />
        <MetricCard
          label="Out of stock"
          icon={CircleSlash}
          loading={loading}
          value={formatNumber(out)}
          tone={out > 0 ? "danger" : "default"}
          href="/inventory/stock?low_only=true"
          detail="Nothing available to sell"
        />
        {canReports && (
          <MetricCard
            label="Stock value"
            icon={Wallet}
            loading={report.isPending}
            value={
              report.data
                ? formatMoney(report.data.stock_value, report.data.currency, {
                    compact: true,
                  })
                : "—"
            }
            detail={
              report.isError
                ? "Unavailable right now"
                : "On hand at current prices"
            }
          />
        )}
        <MetricCard
          label="Locations"
          icon={MapPin}
          loading={locations.isPending}
          href="/inventory/locations"
          value={formatNumber(
            locations.data?.filter((l) => l.status === "active").length ?? 0,
          )}
          detail={
            locations.data?.find((l) => l.is_default)?.name
              ? `Default: ${locations.data.find((l) => l.is_default)!.name}`
              : undefined
          }
        />
      </MetricGrid>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="low-stock-heading">
          <div className="mb-2 flex items-end justify-between gap-3">
            <div>
              <h2
                id="low-stock-heading"
                className="text-[15px] font-semibold tracking-tight"
              >
                Needs restocking
              </h2>
              <p className="text-[13px] text-muted-foreground">
                Lowest available first
              </p>
            </div>
            <Link
              href="/inventory/stock?low_only=true"
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              All low stock <ArrowRight className="size-3" />
            </Link>
          </div>
          <DataTable
            caption="Items that need restocking"
            columns={columns}
            rows={levels.data ? lowRows : undefined}
            getRowId={(r) => `${r.variant_id}:${r.location_id}`}
            loading={loading}
            loadingRows={5}
            empty={
              <EmptyState
                compact
                icon={PackageCheck}
                title={
                  tracked
                    ? "Everything is well stocked"
                    : "No stock tracked yet"
                }
                description={
                  tracked
                    ? "No SKU is at or below its low-stock threshold."
                    : "Stock appears here after the first receipt for a tracked product."
                }
                action={
                  !tracked ? (
                    <Button size="sm" variant="secondary" asChild>
                      <Link href="/catalog/products">View products</Link>
                    </Button>
                  ) : undefined
                }
              />
            }
          />
        </section>

        <Card>
          <CardHeader
            title="Recent movements"
            description="Latest changes to stock"
            actions={
              <Link
                href="/inventory/movements"
                className="text-xs font-medium text-primary hover:underline"
              >
                Full ledger
              </Link>
            }
          />
          <div className="px-4 pb-3">
            {movements.isError ? (
              <ErrorState
                compact
                error={movements.error}
                onRetry={() => void movements.refetch()}
              />
            ) : (
              <MovementList
                movements={movements.data?.items}
                loading={movements.isPending}
                variants={variants}
                locations={locations.data}
              />
            )}
          </div>
        </Card>
      </div>
      <AdjustStockSheet target={target} open={open} onOpenChange={setOpen} />
    </PageShell>
  );
}
