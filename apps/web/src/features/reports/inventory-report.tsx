"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Boxes, PackageCheck } from "lucide-react";
import { formatMoney, formatNumber } from "@/lib/format";
import { DataTable, type Column } from "@/components/app/data-table";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { EmptyState, ErrorState } from "@/components/app/states";
import { SectionHeader } from "@/components/app/page";
import { StatusBadge } from "@/components/app/status-badge";
import { useScopedQuery } from "@/hooks/use-scoped";
import { inventoryService } from "@/features/inventory/service";
import type { StockLevel } from "@/features/business/types";
import { reportsService } from "./service";
import { ExportMenu, ReportShell } from "./components";

const LOW_HREF = "/inventory/stock?low_only=true";

export function InventoryReport() {
  return (
    <ReportShell
      title="Inventory"
      description="Stock value on hand and items that need replenishing."
      permission="inventory.read"
      area="inventory reports"
    >
      <InventoryContent />
    </ReportShell>
  );
}

function InventoryContent() {
  const summary = useScopedQuery(["reports", "inventory"], () => reportsService.inventory());
  const levels = useScopedQuery(["inventory", "levels", { lowOnly: true, pageSize: 25 }], () =>
    inventoryService.levels({ lowOnly: true, pageSize: 25 }),
  );
  const data = summary.data;
  const currency = data?.currency ?? "USD";
  const rows = levels.data?.items;

  const columns: Column<StockLevel>[] = [
    {
      key: "item",
      header: "Item",
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{r.product_name}</p>
          <p className="truncate text-xs text-muted-foreground">{r.variant_name}</p>
        </div>
      ),
    },
    { key: "sku", header: "SKU", hideBelow: "sm", cell: (r) => <span className="font-mono text-xs">{r.sku}</span> },
    { key: "location", header: "Location", hideBelow: "md", cell: (r) => r.location_name },
    { key: "on_hand", header: "On hand", align: "right", hideBelow: "lg", cell: (r) => <span className="tabular">{formatNumber(r.on_hand)}</span> },
    { key: "reserved", header: "Reserved", align: "right", hideBelow: "lg", cell: (r) => <span className="tabular">{formatNumber(r.reserved)}</span> },
    { key: "available", header: "Available", align: "right", cell: (r) => <span className="tabular font-semibold">{formatNumber(r.available)}</span> },
    { key: "threshold", header: "Threshold", align: "right", hideBelow: "md", cell: (r) => <span className="tabular text-muted-foreground">{formatNumber(r.low_stock_threshold)}</span> },
    { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.available <= 0 ? "out" : "low"} /> },
  ];

  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />;

  return (
    <>
      <MetricGrid className="xl:grid-cols-3">
        <MetricCard label="Stock value" icon={Boxes} loading={summary.isPending} value={formatMoney(data?.stock_value, currency)} detail="On-hand quantity × current price" />
        <MetricCard
          label="Items low on stock"
          icon={AlertTriangle}
          loading={summary.isPending}
          tone={(data?.low_stock_count ?? 0) > 0 ? "warning" : "default"}
          value={formatNumber(data?.low_stock_count)}
          detail="At or below their threshold"
          href={LOW_HREF}
        />
        <MetricCard
          label="Out of stock"
          icon={PackageCheck}
          loading={levels.isPending}
          tone={(rows?.filter((r) => r.available <= 0).length ?? 0) > 0 ? "danger" : "default"}
          value={levels.isError ? "—" : formatNumber(rows?.filter((r) => r.available <= 0).length ?? 0)}
          detail="Stock rows listed below with nothing available"
        />
      </MetricGrid>

      <SectionHeader
        className="mt-6"
        title="Low-stock items"
        description={levels.data && levels.data.total > 25 ? `Showing 25 of ${formatNumber(levels.data.total)} stock rows.` : "Stock rows at or below their threshold, per location."}
        actions={
          <>
            <ExportMenu
              disabled={!rows?.length}
              exports={[
                {
                  label: "Low-stock items",
                  filename: "low-stock-items",
                  headers: ["Product", "Variant", "SKU", "Location", "On hand", "Reserved", "Available", "Threshold"],
                  rows: () => (rows ?? []).map((r) => [r.product_name, r.variant_name, r.sku, r.location_name, r.on_hand, r.reserved, r.available, r.low_stock_threshold]),
                },
              ]}
            />
            <Link href={LOW_HREF} className="hidden items-center gap-1 text-[13px] font-medium text-primary hover:underline sm:inline-flex">
              Open in stock <ArrowRight className="size-3.5" />
            </Link>
          </>
        }
      />
      <DataTable
        caption="Low-stock items"
        columns={columns}
        rows={rows}
        getRowId={(r) => `${r.variant_id}:${r.location_id}`}
        rowHref={() => LOW_HREF}
        loading={levels.isPending}
        error={levels.error}
        onRetry={() => void levels.refetch()}
        loadingRows={6}
        empty={<EmptyState compact icon={PackageCheck} title="Everything is stocked" description="No item is at or below its low-stock threshold." />}
      />
      <Link href={LOW_HREF} className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-primary hover:underline sm:hidden">
        Open in stock <ArrowRight className="size-3.5" />
      </Link>
    </>
  );
}
