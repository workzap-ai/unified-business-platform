"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Boxes,
  EyeOff,
  FileText,
  History,
  Package,
  Pencil,
  Plus,
  Power,
  ShoppingCart,
  SlidersHorizontal,
} from "lucide-react";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/input";
import {
  Card,
  CardBody,
  CardHeader,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/display";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { DataTable, type Column } from "@/components/app/data-table";
import { ConfirmDialog } from "@/components/app/forms";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedMutation, useScopedQuery } from "@/hooks/use-scoped";
import { useUrlState } from "@/hooks/use-url-state";
import { useSession } from "@/features/auth/session-provider";
import type {
  ProductDetail,
  StockLevel,
  Variant,
} from "@/features/business/types";
import { inventoryService } from "@/features/inventory/service";
import { useLocations } from "@/features/inventory/hooks";
import { stockState, variantIndex } from "@/features/inventory/lib";
import { AvailableBar, StockChip } from "@/features/inventory/stock-display";
import { MovementList } from "@/features/inventory/movement-list";
import {
  AdjustStockSheet,
  type AdjustTarget,
} from "@/features/inventory/adjust-stock-sheet";
import { catalogService } from "./service";
import { CATALOG_CHANGED, useProduct } from "./hooks";
import { attributeEntries, formatAttribute, priceRange } from "./lib";
import { PiVisibility } from "./products-list-page";
import { ProductEditDialog } from "./product-edit-dialog";
import { AddVariantDialog, EditVariantDialog } from "./variant-dialogs";

export function ProductDetailPage({ id }: { id: string }) {
  return (
    <RequirePermission permission="catalog.read" area="the catalog">
      <ProductDetailInner id={id} />
    </RequirePermission>
  );
}

function ProductDetailInner({ id }: { id: string }) {
  const { can } = useSession();
  const canWrite = can("catalog.write");
  const product = useProduct(id);
  const [state, setState] = useUrlState({ tab: "overview" });
  const [editOpen, setEditOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const p = product.data;

  useBreadcrumbs(
    p ? [{ label: p.name }] : [],
    p ? { href: `/catalog/products/${p.id}`, kind: "Product" } : undefined,
  );

  const update = useScopedMutation(
    (input: { status?: ProductDetail["status"]; pi_visible?: boolean }) =>
      catalogService.updateProduct(id, input),
    {
      invalidate: CATALOG_CHANGED,
      success: (r) =>
        r.status !== p?.status
          ? r.status === "active"
            ? "Product activated"
            : "Product deactivated"
          : r.pi_visible
            ? "Now visible to PI"
            : "Hidden from PI",
      error: "Couldn't update this product.",
      onSuccess: () => setStatusOpen(false),
    },
  );

  if (product.isPending) {
    return (
      <PageShell>
        <RecordHeader title="" loading />
        <Skeleton className="h-9 w-80 max-w-full" />
        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-72 rounded-xl" />
          <Skeleton className="h-56 rounded-xl" />
        </div>
      </PageShell>
    );
  }

  if (product.isError || !p) {
    return (
      <PageShell>
        <div className="rounded-xl border border-border bg-surface">
          <ErrorState
            error={product.error}
            onRetry={() => void product.refetch()}
          />
          <div className="-mt-8 pb-8 text-center">
            <Link
              href="/catalog/products"
              className="text-sm font-medium text-primary hover:underline"
            >
              Back to products
            </Link>
          </div>
        </div>
      </PageShell>
    );
  }

  const active = p.status === "active";
  const currency = p.variants[0]?.currency ?? "USD";
  const prices = p.variants.map((v) => v.price);
  const sorted = [...prices].sort((a, b) => Number(a) - Number(b));

  return (
    <PageShell>
      <RecordHeader
        icon={Package}
        title={p.name}
        status={<StatusBadge status={p.status} />}
        subtitle={`${p.offering_type.toUpperCase()} · ${p.category_name ?? "Uncategorized"}`}
        meta={
          <>
            <span className="tabular">
              {priceRange(
                sorted[0] ?? null,
                sorted[sorted.length - 1] ?? null,
                currency,
              )}
            </span>
            <span>
              {formatNumber(p.variants.length)}{" "}
              {p.variants.length === 1 ? "variant" : "variants"}
            </span>
            <PiVisibility visible={p.pi_visible} />
            <span>Added {formatDate(p.created_at)}</span>
          </>
        }
        actions={
          canWrite ? (
            <>
              <Button
                variant="secondary"
                onClick={() => update.mutate({ pi_visible: !p.pi_visible })}
                loading={
                  update.isPending && update.variables?.pi_visible !== undefined
                }
                disabled={update.isPending}
              >
                {p.pi_visible ? <EyeOff /> : <Bot />}{" "}
                {p.pi_visible ? "Hide from PI" : "Show to PI"}
              </Button>
              <Button
                variant={active ? "danger-outline" : "secondary"}
                onClick={() => setStatusOpen(true)}
              >
                <Power /> {active ? "Deactivate" : "Activate"}
              </Button>
              <Button onClick={() => setEditOpen(true)}>
                <Pencil /> Edit
              </Button>
            </>
          ) : undefined
        }
      />

      {!active && (
        <Notice
          tone="neutral"
          icon={Power}
          className="mb-4"
          title="This product is inactive"
        >
          It can’t be added to new quotes or orders, and PI won’t offer it.
        </Notice>
      )}
      {active && !p.pi_visible && (
        <Notice tone="pi" icon={EyeOff} className="mb-4">
          Hidden from PI: customers chatting with PI won’t be offered this
          product. Your team can still sell it.
        </Notice>
      )}

      <Tabs value={state.tab} onValueChange={(tab) => setState({ tab })}>
        <TabsList aria-label="Product sections">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="variants">
            Variants ({p.variants.length})
          </TabsTrigger>
          {can("inventory.read") && (
            <TabsTrigger value="inventory">Inventory</TabsTrigger>
          )}
          <TabsTrigger value="related">Related</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <OverviewTab product={p} />
        </TabsContent>
        <TabsContent value="variants">
          <VariantsTab product={p} canWrite={canWrite} />
        </TabsContent>
        {can("inventory.read") && (
          <TabsContent value="inventory">
            <InventoryTab product={p} />
          </TabsContent>
        )}
        <TabsContent value="related">
          <RelatedTab product={p} />
        </TabsContent>
      </Tabs>

      <ProductEditDialog
        product={p}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
      <ConfirmDialog
        open={statusOpen}
        onOpenChange={setStatusOpen}
        title={active ? `Deactivate ${p.name}?` : `Activate ${p.name}?`}
        description={
          active
            ? "You can reactivate it at any time."
            : "The product becomes available for sale again."
        }
        consequences={
          active
            ? [
                "PI stops offering this product to customers.",
                "It can't be added to new quotes or orders.",
                "Existing quotes, orders and invoices are not changed.",
              ]
            : [
                "It can be added to new quotes and orders.",
                p.pi_visible
                  ? "PI can offer it to customers again."
                  : "It stays hidden from PI until you show it.",
              ]
        }
        confirmLabel={active ? "Deactivate" : "Activate"}
        destructive={active}
        loading={update.isPending}
        onConfirm={() =>
          update.mutate({ status: active ? "inactive" : "active" })
        }
      />
    </PageShell>
  );
}

function OverviewTab({ product }: { product: ProductDetail }) {
  const attributes = attributeEntries(product.attributes);
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-4">
        <Card>
          <CardHeader title="Description" />
          <CardBody>
            {product.description ? (
              <p className="text-[13.5px] leading-relaxed whitespace-pre-line text-foreground-secondary">
                {product.description}
              </p>
            ) : (
              <p className="text-[13px] text-muted-foreground">
                No description yet. A short description helps PI answer customer
                questions accurately.
              </p>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Pricing" description="Current price per variant" />
          <div className="px-4 pb-3">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Variant prices</caption>
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th scope="col" className="py-2 text-left font-medium">
                    Variant
                  </th>
                  <th
                    scope="col"
                    className="hidden py-2 text-left font-medium sm:table-cell"
                  >
                    SKU
                  </th>
                  <th scope="col" className="py-2 text-right font-medium">
                    Price
                  </th>
                </tr>
              </thead>
              <tbody>
                {product.variants.map((v) => (
                  <tr
                    key={v.id}
                    className="border-b border-border last:border-0"
                  >
                    <td className="py-2">
                      {v.name}
                      {v.status === "inactive" && (
                        <StatusBadge status="inactive" className="ml-2" />
                      )}
                    </td>
                    <td className="hidden py-2 font-mono text-xs text-muted-foreground sm:table-cell">
                      {v.sku}
                    </td>
                    <td className="tabular py-2 text-right font-medium">
                      {formatMoney(v.price, v.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
      <div className="space-y-4">
        <Card>
          <CardHeader title="Details" />
          <CardBody className="pb-2">
            <PropertyList
              items={[
                {
                  label: "Status",
                  value: <StatusBadge status={product.status} />,
                },
                { label: "Category", value: product.category_name },
                {
                  label: "PI visibility",
                  value: <PiVisibility visible={product.pi_visible} />,
                  hint: "PI only sees active products that are visible to PI.",
                },
                {
                  label: "Variants",
                  value: (
                    <span className="tabular">{product.variants.length}</span>
                  ),
                },
                {
                  label: "Tracked",
                  value: `${product.variants.filter((v) => v.track_inventory).length} of ${product.variants.length}`,
                },
                { label: "Added", value: formatDate(product.created_at) },
              ]}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Attributes" />
          <CardBody className="pb-2">
            {attributes.length ? (
              <PropertyList
                items={attributes.map(([k, v]) => ({
                  label: k,
                  value: formatAttribute(v),
                }))}
              />
            ) : (
              <p className="pb-2 text-[13px] text-muted-foreground">
                No attributes recorded.
              </p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function VariantsTab({
  product,
  canWrite,
}: {
  product: ProductDetail;
  canWrite: boolean;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<Variant | null>(null);
  const [toggling, setToggling] = useState<Variant | null>(null);
  const currency = product.variants[0]?.currency ?? "USD";

  const toggle = useScopedMutation(
    (v: Variant) =>
      catalogService.updateVariant(v.id, {
        status: v.status === "active" ? "inactive" : "active",
      }),
    {
      invalidate: CATALOG_CHANGED,
      success: (v) =>
        v.status === "active" ? `${v.sku} activated` : `${v.sku} deactivated`,
      error: "Couldn't update this variant.",
      onSuccess: () => setToggling(null),
    },
  );

  const columns: Column<Variant>[] = [
    {
      key: "sku",
      header: "SKU",
      cell: (v) => <span className="font-mono text-xs">{v.sku}</span>,
    },
    {
      key: "name",
      header: "Name",
      cell: (v) => <span className="font-medium">{v.name}</span>,
    },
    {
      key: "price",
      header: "Price",
      align: "right",
      cell: (v) => (
        <span className="tabular">{formatMoney(v.price, v.currency)}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      hideBelow: "sm",
      cell: (v) => <StatusBadge status={v.status} />,
    },
    {
      key: "tracked",
      header: "Inventory",
      hideBelow: "md",
      cell: (v) =>
        v.track_inventory ? (
          "Tracked"
        ) : (
          <span className="text-muted-foreground">Not tracked</span>
        ),
    },
    {
      key: "threshold",
      header: "Low-stock at",
      align: "right",
      hideBelow: "lg",
      cell: (v) => (
        <span className="tabular text-muted-foreground">
          {v.track_inventory ? (v.low_stock_threshold ?? "Default") : "—"}
        </span>
      ),
    },
  ];
  if (canWrite)
    columns.push({
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      width: "1%",
      cell: (v) => (
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={`Edit ${v.sku}`}
            onClick={() => setEditing(v)}
          >
            <Pencil />
          </Button>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={
              v.status === "active"
                ? `Deactivate ${v.sku}`
                : `Activate ${v.sku}`
            }
            onClick={() => setToggling(v)}
          >
            <Power />
          </Button>
        </div>
      ),
    });

  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-3">
        <p className="text-[13px] text-muted-foreground">
          Each variant is sold, priced and stocked separately.
        </p>
        {canWrite && (
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <Plus /> Add variant
          </Button>
        )}
      </div>
      <DataTable
        caption="Variants"
        columns={columns}
        rows={product.variants}
        getRowId={(v) => v.id}
        empty={
          <EmptyState
            compact
            icon={Package}
            title="No variants"
            description="Add a variant so this product can be sold."
          />
        }
      />
      <AddVariantDialog
        productId={product.id}
        existingSkus={product.variants.map((v) => v.sku)}
        currency={currency}
        open={addOpen}
        onOpenChange={setAddOpen}
      />
      <EditVariantDialog
        variant={editing}
        open={Boolean(editing)}
        onOpenChange={(o) => !o && setEditing(null)}
        productName={product.name}
      />
      <ConfirmDialog
        open={Boolean(toggling)}
        onOpenChange={(o) => !o && setToggling(null)}
        title={
          toggling?.status === "active"
            ? `Deactivate ${toggling?.sku}?`
            : `Activate ${toggling?.sku}?`
        }
        consequences={
          toggling?.status === "active"
            ? [
                "PI stops offering this variant.",
                "It can't be added to new quotes or orders.",
                "Stock history and existing documents are kept.",
              ]
            : ["The variant can be sold and quoted again."]
        }
        confirmLabel={toggling?.status === "active" ? "Deactivate" : "Activate"}
        destructive={toggling?.status === "active"}
        loading={toggle.isPending}
        onConfirm={() => toggling && toggle.mutate(toggling)}
      />
    </div>
  );
}

function InventoryTab({ product }: { product: ProductDetail }) {
  const { can } = useSession();
  const canAdjust = can("inventory.adjust");
  const levels = useScopedQuery(
    ["inventory", "levels", "product", product.id, product.name],
    () => inventoryService.levels({ search: product.name, pageSize: 100 }),
  );
  const rows = useMemo(
    () => levels.data?.items.filter((l) => l.product_id === product.id) ?? [],
    [levels.data, product.id],
  );
  const tracked = product.variants.filter((v) => v.track_inventory);
  const [variantId, setVariantId] = useState<string>(
    tracked[0]?.id ?? product.variants[0]?.id ?? "",
  );
  const movements = useScopedQuery(
    ["inventory", "movements", { page: 1, pageSize: 10, variantId }],
    () => inventoryService.movements({ page: 1, pageSize: 10, variantId }),
    { enabled: Boolean(variantId) },
  );
  const locations = useLocations();
  const [target, setTarget] = useState<AdjustTarget | null>(null);
  const [open, setOpen] = useState(false);
  const index = useMemo(() => variantIndex(rows), [rows]);

  const adjust = (v: Variant, locationId?: string) => {
    setTarget({
      variant_id: v.id,
      product_name: product.name,
      variant_name: v.name,
      sku: v.sku,
      location_id: locationId ?? null,
    });
    setOpen(true);
  };

  const columns: Column<StockLevel>[] = [
    {
      key: "variant",
      header: "Variant",
      cell: (r) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{r.variant_name}</p>
          <p className="font-mono text-xs text-muted-foreground">{r.sku}</p>
        </div>
      ),
    },
    {
      key: "location",
      header: "Location",
      hideBelow: "sm",
      cell: (r) => r.location_name,
    },
    {
      key: "on_hand",
      header: "On hand",
      align: "right",
      hideBelow: "md",
      cell: (r) => <span className="tabular">{formatNumber(r.on_hand)}</span>,
    },
    {
      key: "reserved",
      header: "Reserved",
      align: "right",
      hideBelow: "md",
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
      key: "status",
      header: "Status",
      hideBelow: "lg",
      cell: (r) => <StockChip state={stockState(r)} />,
    },
  ];
  if (canAdjust)
    columns.push({
      key: "adjust",
      header: <span className="sr-only">Actions</span>,
      align: "right",
      width: "1%",
      cell: (r) => {
        const v = product.variants.find((x) => x.id === r.variant_id);
        return v ? (
          <Button
            variant="ghost"
            size="xs"
            aria-label={`Adjust stock for ${r.sku} at ${r.location_name}`}
            onClick={() => adjust(v, r.location_id)}
          >
            <SlidersHorizontal />{" "}
            <span className="hidden sm:inline">Adjust</span>
          </Button>
        ) : null;
      },
    });

  const untracked = product.variants.length > 0 && tracked.length === 0;
  const selected = product.variants.find((v) => v.id === variantId);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section aria-labelledby="stock-heading" className="min-w-0">
        <div className="mb-2 flex items-end justify-between gap-3">
          <h2
            id="stock-heading"
            className="text-[15px] font-semibold tracking-tight"
          >
            Stock by location
          </h2>
          {canAdjust && tracked[0] && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                adjust(selected?.track_inventory ? selected : tracked[0]!)
              }
            >
              <SlidersHorizontal /> Record stock
            </Button>
          )}
        </div>
        {untracked ? (
          <Card>
            <EmptyState
              compact
              icon={Boxes}
              title="Inventory isn't tracked for this product"
              description="Turn on tracking for a variant (Variants tab) to count stock and get low-stock alerts."
            />
          </Card>
        ) : (
          <DataTable
            caption="Stock levels for this product"
            columns={columns}
            rows={levels.data ? rows : undefined}
            getRowId={(r) => `${r.variant_id}:${r.location_id}`}
            loading={levels.isPending}
            error={levels.error}
            onRetry={() => void levels.refetch()}
            loadingRows={3}
            empty={
              <EmptyState
                compact
                icon={Boxes}
                title="No stock recorded yet"
                description="Record a receipt to set the starting quantity."
                action={
                  canAdjust && tracked[0] ? (
                    <Button size="sm" onClick={() => adjust(tracked[0]!)}>
                      Record receipt
                    </Button>
                  ) : undefined
                }
              />
            }
          />
        )}
      </section>
      <Card>
        <CardHeader
          title="Recent movements"
          icon={<History />}
          actions={
            variantId ? (
              <Link
                href={`/inventory/movements?variant=${variantId}`}
                className="text-xs font-medium text-primary hover:underline"
              >
                Full ledger
              </Link>
            ) : undefined
          }
        />
        <div className="px-4 pb-3">
          {product.variants.length > 1 && (
            <div className="mb-2">
              <label htmlFor="movement-variant" className="sr-only">
                Variant
              </label>
              <NativeSelect
                id="movement-variant"
                value={variantId}
                onChange={(e) => setVariantId(e.target.value)}
                className="h-8 text-[13px]"
              >
                {product.variants.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} ({v.sku})
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}
          {movements.isError ? (
            <ErrorState
              compact
              error={movements.error}
              onRetry={() => void movements.refetch()}
            />
          ) : (
            <MovementList
              movements={movements.data?.items}
              loading={movements.isPending && Boolean(variantId)}
              variants={index}
              locations={locations.data}
              showProduct={false}
              empty="No movements for this variant yet."
            />
          )}
        </div>
      </Card>
      <AdjustStockSheet target={target} open={open} onOpenChange={setOpen} />
    </div>
  );
}

function RelatedTab({ product }: { product: ProductDetail }) {
  const { can } = useSession();
  const q = encodeURIComponent(product.name);
  const links = [
    {
      show: can("orders.read"),
      href: `/orders?search=${q}`,
      icon: ShoppingCart,
      label: "Orders",
      description: "Orders that mention this product",
    },
    {
      show: can("quotes.read"),
      href: `/quotes?search=${q}`,
      icon: FileText,
      label: "Quotes",
      description: "Quotes that mention this product",
    },
    {
      show: can("inventory.read"),
      href: `/inventory/stock?search=${q}`,
      icon: Boxes,
      label: "Stock levels",
      description: "All locations for this product",
    },
    {
      show: can("inventory.read") && Boolean(product.variants[0]),
      href: `/inventory/movements?variant=${product.variants[0]?.id ?? ""}`,
      icon: History,
      label: "Stock ledger",
      description: "Movements for the first variant",
    },
  ].filter((l) => l.show);
  if (!links.length)
    return (
      <EmptyState
        compact
        icon={Package}
        title="Nothing related you can view"
        description="Related orders and quotes need additional permissions."
      />
    );
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {links.map((l) => (
        <li key={l.label}>
          <Link
            href={l.href}
            className="flex items-center gap-3 rounded-xl border border-border bg-surface p-3.5 shadow-sm transition-colors hover:border-border-strong"
          >
            <span className="flex size-9 items-center justify-center rounded-lg bg-surface-muted text-muted-foreground">
              <l.icon className="size-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13px] font-semibold">{l.label}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {l.description}
              </span>
            </span>
            <ArrowRight
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}
