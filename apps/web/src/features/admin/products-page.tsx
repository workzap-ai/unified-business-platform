"use client";

import Link from "next/link";
import { ArrowUpRight, Blocks, Info, Settings2 } from "lucide-react";
import { formatDate, humanize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState, Notice } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import {
  productsService,
  type ProductState,
} from "@/features/products/service";
import {
  EnvironmentSwitch,
  InstallButton,
  InstallStatus,
} from "./product-shared";

export function ProductsPage() {
  return (
    <RequirePermission
      permission="admin.products.manage"
      area="platform products"
    >
      <ProductsContent />
    </RequirePermission>
  );
}

function ProductsContent() {
  const products = useScopedQuery(["products"], () => productsService.list());
  return (
    <PageShell width="default">
      <PageHeader
        title="Platform products"
        description="Add-on products that extend this workspace."
      />
      <Notice tone="info" icon={Info} className="mb-5">
        Products registered by the platform appear here; each is installed per
        workspace and enabled per environment.
      </Notice>
      {products.isPending ? (
        <div className="grid gap-3">
          <Skeleton className="h-52 rounded-xl" />
        </div>
      ) : products.isError ? (
        <ErrorState
          error={products.error}
          onRetry={() => void products.refetch()}
        />
      ) : products.data.length === 0 ? (
        <EmptyState
          icon={Blocks}
          title="No products registered"
          description="When the platform registers a product, it appears here ready to install."
        />
      ) : (
        <ul className="grid gap-3">
          {products.data.map((p) => (
            <li key={p.key}>
              <ProductCard product={p} />
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}

function ProductCard({ product: p }: { product: ProductState }) {
  const installed = p.tenant_status === "installed";
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-pi-soft text-pi">
            <Blocks className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-semibold">
                <Link
                  href={`/settings/products/${p.key}`}
                  className="hover:underline"
                >
                  {p.name}
                </Link>
              </h2>
              <Badge tone="outline">
                {p.category === "ai" ? "AI" : humanize(p.category)}
              </Badge>
              <InstallStatus product={p} />
            </div>
            <p className="mt-1 max-w-2xl text-[13px] text-muted-foreground">
              {p.description}
            </p>
            {p.installed_at && (
              <p className="mt-1 text-xs text-muted-foreground">
                Installed {formatDate(p.installed_at)}
              </p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <InstallButton product={p} />
          <Button variant="secondary" size="sm" asChild>
            <Link href={`/settings/products/${p.key}`}>Details</Link>
          </Button>
        </div>
      </div>

      {p.features.length > 0 && (
        <ul
          className="mt-4 flex flex-wrap gap-1.5"
          aria-label={`${p.name} features`}
        >
          {p.features.map((f) => (
            <li key={f}>
              <Badge
                tone={p.enabled_features.includes(f) ? "primary" : "neutral"}
              >
                {humanize(f)}
              </Badge>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 grid gap-3 border-t border-border pt-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <EnvironmentSwitch product={p} id={`product-enabled-${p.key}`} />
        {installed && (
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/${p.key}`}>
                Open workspace <ArrowUpRight />
              </Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/${p.key}/settings`}>
                <Settings2 /> Product settings
              </Link>
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
