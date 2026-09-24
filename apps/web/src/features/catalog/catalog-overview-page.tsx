"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  EyeOff,
  FolderTree,
  Layers,
  Package,
  Plus,
} from "lucide-react";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  ModuleNav,
  RequirePermission,
} from "@/components/app/page";
import { MetricCard, MetricGrid } from "@/components/app/metric-card";
import { DistributionBar } from "@/components/app/charts";
import { EmptyState, ErrorState } from "@/components/app/states";
import { StatusBadge } from "@/components/app/status-badge";
import { useSession } from "@/features/auth/session-provider";
import type { ProductListItem } from "@/features/business/types";
import { useAllLevels } from "@/features/inventory/hooks";
import { distinctVariants } from "@/features/inventory/lib";
import { useAllProducts, useCategories } from "./hooks";
import { priceRange } from "./lib";

export function CatalogOverviewPage() {
  return (
    <RequirePermission permission="catalog.read" area="the catalog">
      <CatalogOverviewInner />
    </RequirePermission>
  );
}

function CatalogOverviewInner() {
  const { can } = useSession();
  const canWrite = can("catalog.write");
  const canStock = can("inventory.read");
  const products = useAllProducts();
  const categories = useCategories();
  const levels = useAllLevels(canStock);

  const items = useMemo(() => products.data?.items ?? [], [products.data]);
  const active = items.filter((p) => p.status === "active");
  const variants = items.reduce((sum, p) => sum + p.variant_count, 0);
  const visible = active.filter((p) => p.pi_visible).length;
  const hidden = items.filter((p) => !p.pi_visible);
  const recent = useMemo(
    () =>
      [...items]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .slice(0, 6),
    [items],
  );
  const lowCount = levels.data
    ? distinctVariants(levels.data.items, (l) => l.is_low || l.available <= 0)
    : undefined;

  const segments = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of items) {
      const key = p.category_name ?? "Uncategorized";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const top = sorted
      .slice(0, 4)
      .map(([label, value]) => ({ key: label, label, value }));
    const rest = sorted.slice(4).reduce((s, [, v]) => s + v, 0);
    if (rest)
      top.push({
        key: "__other",
        label: `Other (${sorted.length - 4})`,
        value: rest,
      });
    return top;
  }, [items]);

  const header = (
    <>
      <PageHeader
        title="Catalog"
        description="Products, variants and prices used by quotes, orders, inventory and PI."
        actions={
          canWrite ? (
            <Button asChild>
              <Link href="/catalog/products/new">
                <Plus /> Add product
              </Link>
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="catalog" />
    </>
  );

  if (products.isError) {
    return (
      <PageShell>
        {header}
        <ErrorState
          error={products.error}
          onRetry={() => void products.refetch()}
        />
      </PageShell>
    );
  }

  const loading = products.isPending;
  if (!loading && items.length === 0) {
    return (
      <PageShell>
        {header}
        <Card>
          <EmptyState
            icon={Package}
            title="Your catalog is empty"
            description="Add the products you sell with their prices. Quotes, orders, stock and PI's answers all start here."
            action={
              canWrite ? (
                <Button size="sm" asChild>
                  <Link href="/catalog/products/new">
                    <Plus /> Add your first product
                  </Link>
                </Button>
              ) : undefined
            }
            secondary={
              <Button size="sm" variant="secondary" asChild>
                <Link href="/catalog/categories">Set up categories</Link>
              </Button>
            }
          />
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell>
      {header}
      <MetricGrid className={canStock ? "xl:grid-cols-5" : "xl:grid-cols-4"}>
        <MetricCard
          label="Active products"
          icon={Package}
          loading={loading}
          value={formatNumber(active.length)}
          href="/catalog/products?status=active"
          detail={
            items.length > active.length
              ? `${formatNumber(items.length - active.length)} inactive`
              : "All products active"
          }
        />
        <MetricCard
          label="Variants"
          icon={Layers}
          loading={loading}
          value={formatNumber(variants)}
          href="/catalog/pricing"
          detail="Sellable SKUs"
        />
        <MetricCard
          label="Categories"
          icon={FolderTree}
          loading={categories.isPending}
          value={formatNumber(categories.data?.length ?? 0)}
          href="/catalog/categories"
        />
        <MetricCard
          label="Visible to PI"
          icon={Bot}
          tone="pi"
          loading={loading}
          value={active.length ? formatPercent(visible / active.length) : "—"}
          detail={`${formatNumber(visible)} of ${formatNumber(active.length)} active`}
          href="/catalog/products?pi=hidden"
        />
        {canStock && (
          <MetricCard
            label="Low or out of stock"
            icon={AlertTriangle}
            loading={levels.isPending}
            value={levels.isError ? "—" : formatNumber(lowCount ?? 0)}
            tone={lowCount ? "warning" : "default"}
            href="/inventory/stock?low_only=true"
            detail={
              levels.isError
                ? "Unavailable right now"
                : "Variants needing restock"
            }
          />
        )}
      </MetricGrid>
      {products.data?.truncated && (
        <p className="mt-2 text-xs text-muted-foreground">
          Figures cover the first {formatNumber(items.length)} of{" "}
          {formatNumber(products.data.total)} products.
        </p>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Products by category"
            description="Share of all products"
            actions={
              <Link
                href="/catalog/categories"
                className="text-xs font-medium text-primary hover:underline"
              >
                Categories
              </Link>
            }
          />
          <div className="px-4 pb-4">
            {loading ? (
              <Skeleton className="h-16" />
            ) : (
              <DistributionBar
                segments={segments}
                format={(v) => formatNumber(v)}
              />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Hidden from PI"
            icon={<EyeOff />}
            description="PI only sees approved, active products that are visible to PI."
            actions={
              hidden.length ? (
                <Link
                  href="/catalog/products?pi=hidden"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  View
                </Link>
              ) : undefined
            }
          />
          <div className="px-2 pb-2">
            {loading ? (
              <div className="space-y-2 px-2 pb-2">
                {Array.from({ length: 3 }, (_, i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : hidden.length === 0 ? (
              <p className="px-2 pb-3 text-[13px] text-muted-foreground">
                Every product is visible to PI.
              </p>
            ) : (
              <ProductRows products={hidden.slice(0, 5)} />
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Recently added"
          actions={
            <Link
              href="/catalog/products"
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              All products <ArrowRight className="size-3" />
            </Link>
          }
        />
        <div className="px-2 pb-2">
          {loading ? (
            <div className="space-y-2 px-2 pb-2">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-10" />
              ))}
            </div>
          ) : (
            <ProductRows products={recent} showDate />
          )}
        </div>
      </Card>
    </PageShell>
  );
}

function ProductRows({
  products,
  showDate = false,
}: {
  products: ProductListItem[];
  showDate?: boolean;
}) {
  return (
    <ul>
      {products.map((p) => (
        <li key={p.id}>
          <Link
            href={`/catalog/products/${p.id}`}
            className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-muted"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-muted text-muted-foreground">
              <Package className="size-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium">
                {p.name}
              </span>
              <span className="block truncate text-xs text-muted-foreground">
                {p.category_name ?? "Uncategorized"} · {p.variant_count}{" "}
                {p.variant_count === 1 ? "variant" : "variants"}
                {showDate ? ` · Added ${formatDate(p.created_at)}` : ""}
              </span>
            </span>
            <span className="tabular hidden shrink-0 text-[13px] sm:inline">
              {priceRange(p.min_price, p.max_price, p.currency)}
            </span>
            {p.status !== "active" && <StatusBadge status={p.status} />}
          </Link>
        </li>
      ))}
    </ul>
  );
}
