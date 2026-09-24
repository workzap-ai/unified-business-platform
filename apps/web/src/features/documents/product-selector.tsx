"use client";

import { useState } from "react";
import { Command } from "cmdk";
import { ArrowLeft, Boxes, ChevronRight, PackagePlus, Plus, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatMoney, formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton, Spinner } from "@/components/ui/display";
import { Dialog, DialogBody, DialogContent, DialogHeader } from "@/components/ui/overlays";
import { ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { catalogService } from "@/features/catalog/service";
import { inventoryService } from "@/features/inventory/service";
import type { ProductDetail, ProductListItem, Variant } from "@/features/business/types";
import { commandItemClass, useDebouncedValue } from "./customer-selector";

export type PickedVariant = { product: Pick<ProductDetail, "id" | "name">; variant: Variant };

/**
 * Available stock for a variant across locations. Returns null when stock isn't tracked,
 * isn't visible to this member, or hasn't loaded.
 */
export function useVariantStock(sku: string | null, variantId: string | null, enabled = true) {
  const { can } = useSession();
  const allowed = can("inventory.read") && Boolean(sku) && Boolean(variantId) && enabled;
  const query = useScopedQuery(
    ["inventory", "levels", "sku", sku],
    () => inventoryService.levels({ search: sku ?? undefined, pageSize: 50 }),
    { enabled: allowed, staleTime: 30_000 },
  );
  if (!allowed || !query.data) return { available: null as number | null, loading: allowed && query.isPending };
  const rows = query.data.items.filter((row) => row.variant_id === variantId);
  if (!rows.length) return { available: null as number | null, loading: false };
  return { available: rows.reduce((sum, row) => sum + row.available, 0), loading: false };
}

export function StockHint({
  sku,
  variantId,
  trackInventory,
  quantity,
  className,
}: {
  sku: string | null;
  variantId: string | null;
  trackInventory: boolean | null;
  quantity?: number;
  className?: string;
}) {
  const { available, loading } = useVariantStock(sku, variantId, trackInventory !== false);
  if (trackInventory === false) return <span className={cn("text-xs text-muted-foreground", className)}>Not stock-tracked</span>;
  if (loading) return <Skeleton className={cn("h-3.5 w-20", className)} />;
  if (available === null) return null;
  const short = quantity !== undefined && quantity > available;
  return (
    <span
      className={cn(
        "tabular text-xs font-medium",
        available <= 0 || short ? "text-danger" : available <= 5 ? "text-warning" : "text-muted-foreground",
        className,
      )}
    >
      {formatNumber(available)} available
      {short && <span className="font-normal"> · short by {formatNumber(quantity - available)}</span>}
    </span>
  );
}

/** Two-step catalog picker: find a product, then choose one of its active variants. */
export function ProductSelector({
  onPick,
  showStock = false,
  excludeVariantIds = [],
  triggerLabel = "Add catalog item",
}: {
  onPick: (pick: PickedVariant) => void;
  showStock?: boolean;
  excludeVariantIds?: string[];
  triggerLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [product, setProduct] = useState<ProductListItem | null>(null);

  function close(next: boolean) {
    setOpen(next);
    if (!next) setProduct(null);
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(true)}>
        <PackagePlus /> {triggerLabel}
      </Button>
      <DialogContent size="md" className="h-[min(560px,calc(100dvh-2rem))]">
        <DialogHeader
          title={product ? product.name : "Add a catalog item"}
          description={product ? "Choose a variant. Catalog prices can't be changed here." : "Search your active products."}
        />
        {product ? (
          <VariantList
            productId={product.id}
            showStock={showStock}
            excludeVariantIds={excludeVariantIds}
            onBack={() => setProduct(null)}
            onPick={(variant) => {
              onPick({ product: { id: product.id, name: product.name }, variant });
              close(false);
            }}
          />
        ) : (
          <ProductSearch onSelect={setProduct} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProductSearch({ onSelect }: { onSelect: (product: ProductListItem) => void }) {
  const [query, setQuery] = useState("");
  const term = useDebouncedValue(query.trim());
  const results = useScopedQuery(
    ["catalog", "products", "selector", term],
    () => catalogService.products({ search: term || undefined, status: "active", pageSize: 12 }),
    { staleTime: 30_000 },
  );
  return (
    <Command label="Find a product" shouldFilter={false} loop className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4">
        <Search className="size-4 text-muted-foreground" aria-hidden="true" />
        <Command.Input
          value={query}
          onValueChange={setQuery}
          placeholder="Search products or SKUs…"
          className="h-11 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-muted-foreground"
          autoFocus
        />
        {results.isFetching && <Spinner />}
      </div>
      <Command.List className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-1.5">
        {results.isError ? (
          <ErrorState error={results.error} onRetry={() => void results.refetch()} compact />
        ) : !results.data ? (
          <div className="space-y-1.5 p-1">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-11" />
            ))}
          </div>
        ) : results.data.items.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <Boxes className="mx-auto size-5 text-muted-foreground" aria-hidden="true" />
            <p className="mt-2 text-[13px] font-medium">{term ? `No products match “${term}”` : "No active products yet"}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Only active catalog products can be added.</p>
          </div>
        ) : (
          results.data.items.map((p) => (
            <Command.Item key={p.id} value={p.id} onSelect={() => onSelect(p)} className={commandItemClass}>
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-surface-muted text-muted-foreground">
                <Boxes className="size-4" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{p.name}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {[p.category_name, `${p.variant_count} ${p.variant_count === 1 ? "variant" : "variants"}`].filter(Boolean).join(" · ")}
                </span>
              </span>
              <span className="tabular shrink-0 text-xs text-muted-foreground">
                {p.min_price === null
                  ? "—"
                  : p.min_price === p.max_price
                    ? formatMoney(p.min_price, p.currency ?? "USD")
                    : `from ${formatMoney(p.min_price, p.currency ?? "USD")}`}
              </span>
              <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            </Command.Item>
          ))
        )}
      </Command.List>
    </Command>
  );
}

function VariantList({
  productId,
  showStock,
  excludeVariantIds,
  onBack,
  onPick,
}: {
  productId: string;
  showStock: boolean;
  excludeVariantIds: string[];
  onBack: () => void;
  onPick: (variant: Variant) => void;
}) {
  const detail = useScopedQuery(["catalog", "product", productId], () => catalogService.product(productId));
  const variants = detail.data?.variants.filter((v) => v.status === "active") ?? [];
  return (
    <DialogBody className="px-3 py-3">
      <Button type="button" variant="ghost" size="xs" onClick={onBack} className="mb-2">
        <ArrowLeft /> All products
      </Button>
      {detail.isError ? (
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} compact />
      ) : detail.isPending ? (
        <div className="space-y-1.5">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : variants.length === 0 ? (
        <p className="px-3 py-8 text-center text-[13px] text-muted-foreground">This product has no active variants to sell.</p>
      ) : (
        <ul className="space-y-1.5">
          {variants.map((variant) => {
            const added = excludeVariantIds.includes(variant.id);
            return (
              <li key={variant.id}>
                <button
                  type="button"
                  disabled={added}
                  onClick={() => onPick(variant)}
                  className="flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left transition-colors hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-medium">{variant.name}</span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="font-mono text-xs text-muted-foreground">{variant.sku}</span>
                      {showStock && (
                        <StockHint sku={variant.sku} variantId={variant.id} trackInventory={variant.track_inventory} />
                      )}
                    </span>
                  </span>
                  <span className="tabular shrink-0 text-[13px] font-semibold">{formatMoney(variant.price, variant.currency)}</span>
                  {added ? (
                    <Badge tone="neutral">Added</Badge>
                  ) : (
                    <Plus className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </DialogBody>
  );
}
