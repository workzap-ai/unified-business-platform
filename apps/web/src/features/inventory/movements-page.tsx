"use client";

import { useMemo } from "react";
import Link from "next/link";
import { History, Lock } from "lucide-react";
import { formatDateTime, formatNumber, humanize, relativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/display";
import { PageHeader, PageShell, ModuleNav, RequirePermission } from "@/components/app/page";
import { DataTable, Pagination, useColumnVisibility, ColumnsMenu, type Column } from "@/components/app/data-table";
import { FilterBar, FilterSelect } from "@/components/app/filters";
import { EmptyState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import type { Movement } from "@/features/business/types";
import { inventoryService } from "./service";
import { useLocations, useVariantIndex } from "./hooks";
import { MOVEMENT_KINDS, movementReferenceHref, shortId } from "./lib";
import { Quantity } from "./stock-display";

const PAGE_SIZE = 25;

export function MovementsPage() {
  return (
    <RequirePermission permission="inventory.read" area="inventory">
      <MovementsPageInner />
    </RequirePermission>
  );
}

function MovementsPageInner() {
  const [state, setState, reset] = useUrlState({ variant: "", page: "1" });
  const page = Math.max(1, Number(state.page) || 1);
  const params = { page, pageSize: PAGE_SIZE, variantId: state.variant || undefined };
  const movements = useScopedQuery(["inventory", "movements", params], () => inventoryService.movements(params), {
    placeholderData: (prev) => prev,
  });
  const variants = useVariantIndex();
  const locations = useLocations();

  const variantOptions = useMemo(() => {
    const options = [...(variants.map?.values() ?? [])]
      .sort((a, b) => a.product_name.localeCompare(b.product_name) || a.sku.localeCompare(b.sku))
      .map((v) => ({ value: v.variant_id, label: `${v.product_name} · ${v.sku}` }));
    // Keep an unknown variant from the URL selectable so the chip still shows it's filtered.
    if (state.variant && !options.some((o) => o.value === state.variant))
      options.unshift({ value: state.variant, label: `Variant ${shortId(state.variant)}` });
    return options;
  }, [variants.map, state.variant]);

  const columns: Column<Movement>[] = [
    {
      key: "date",
      header: "Date",
      cell: (m) => (
        <time dateTime={m.created_at} title={formatDateTime(m.created_at)} className="whitespace-nowrap">
          <span className="hidden md:inline">{formatDateTime(m.created_at)}</span>
          <span className="md:hidden">{relativeTime(m.created_at)}</span>
        </time>
      ),
    },
    {
      key: "product",
      header: "Product / SKU",
      cell: (m) => {
        const info = variants.map?.get(m.variant_id);
        if (!info)
          return variants.isPending ? (
            <span className="text-muted-foreground">…</span>
          ) : (
            <span className="font-mono text-xs text-muted-foreground" title={m.variant_id}>
              {shortId(m.variant_id)}
            </span>
          );
        return (
          <div className="min-w-0">
            <Link href={`/catalog/products/${info.product_id}`} className="block max-w-56 truncate font-medium hover:underline">
              {info.product_name}
            </Link>
            <p className="truncate font-mono text-xs text-muted-foreground">{info.sku}</p>
          </div>
        );
      },
    },
    {
      key: "location",
      header: "Location",
      hideBelow: "lg",
      optional: true,
      cell: (m) => locations.data?.find((l) => l.id === m.location_id)?.name ?? <span className="text-muted-foreground">—</span>,
    },
    {
      key: "kind",
      header: "Type",
      hideBelow: "sm",
      cell: (m) => <Badge tone={MOVEMENT_KINDS[m.kind].tone}>{MOVEMENT_KINDS[m.kind].label}</Badge>,
    },
    { key: "quantity", header: "Qty", align: "right", cell: (m) => <Quantity value={m.quantity} /> },
    {
      key: "balance",
      header: "Balance after",
      align: "right",
      hideBelow: "md",
      cell: (m) => <span className="tabular text-muted-foreground">{formatNumber(m.balance_after)}</span>,
    },
    {
      key: "reason",
      header: "Reason",
      hideBelow: "lg",
      optional: true,
      cell: (m) => (
        <span className="block max-w-64 truncate" title={m.reason}>
          {m.reason || <span className="text-muted-foreground">—</span>}
        </span>
      ),
    },
    { key: "actor", header: "By", hideBelow: "xl", optional: true, cell: (m) => m.actor_label },
    {
      key: "reference",
      header: "Reference",
      hideBelow: "xl",
      optional: true,
      cell: (m) => {
        const href = movementReferenceHref(m);
        if (!m.ref_type || m.ref_type === "manual") return <span className="text-muted-foreground">Manual</span>;
        const label = `${humanize(m.ref_type)}${m.ref_id ? ` ${shortId(m.ref_id)}` : ""}`;
        return href ? (
          <Link href={href} className="text-primary hover:underline">
            {label}
          </Link>
        ) : (
          label
        );
      },
    },
  ];
  const { hidden, toggle } = useColumnVisibility("inventory-movements", columns);
  const selected = variants.map?.get(state.variant);

  return (
    <PageShell>
      <PageHeader
        title="Stock movements"
        description="Every receipt, sale, return and adjustment, newest first."
      />
      <ModuleNav moduleKey="inventory" />
      <Notice tone="neutral" icon={Lock} className="mb-4">
        The ledger is append-only: entries are never edited or deleted. To correct a mistake, record an
        opposite adjustment from{" "}
        <Link href="/inventory/stock" className="font-medium text-primary hover:underline">
          Stock levels
        </Link>
        .
      </Notice>
      <FilterBar
        activeCount={state.variant ? 1 : 0}
        onClear={reset}
        actions={<ColumnsMenu columns={columns} hidden={hidden} onToggle={toggle} />}
      >
        <FilterSelect label="Product" value={state.variant} options={variantOptions} onChange={(variant) => setState({ variant })} />
        {selected && (
          <Link href={`/catalog/products/${selected.product_id}`} className="shrink-0 text-xs font-medium text-primary hover:underline">
            Open product
          </Link>
        )}
      </FilterBar>
      <DataTable
        caption="Stock movement ledger"
        columns={columns}
        hiddenColumns={hidden}
        rows={movements.data?.items}
        getRowId={(m) => m.id}
        loading={movements.isPending}
        error={movements.error}
        onRetry={() => void movements.refetch()}
        empty={
          state.variant ? (
            <EmptyState
              compact
              icon={History}
              title="No movements for this product yet"
              description="Receipts, sales and adjustments for this SKU will be listed here."
              action={
                <Button variant="secondary" size="sm" onClick={reset}>
                  Show all movements
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={History}
              title="No stock movements yet"
              description="Movements are recorded when you receive stock, confirm orders or make adjustments."
              action={
                <Button size="sm" asChild>
                  <Link href="/inventory/stock">Go to stock levels</Link>
                </Button>
              }
            />
          )
        }
      />
      {movements.data && (
        <Pagination page={page} pageSize={PAGE_SIZE} total={movements.data.total} onPage={(p) => setState({ page: String(p) }, { resetPage: false })} />
      )}
    </PageShell>
  );
}
