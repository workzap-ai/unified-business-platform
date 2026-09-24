"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  Blocks,
  Check,
  Minus,
  PanelLeft,
  SearchX,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate, humanize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  Skeleton,
} from "@/components/ui/display";
import { PageShell, RequirePermission } from "@/components/app/page";
import { PageSkeleton } from "@/components/app/page-skeleton";
import { PropertyList, RecordHeader } from "@/components/app/record";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useBreadcrumbs } from "@/components/shell/breadcrumbs";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import {
  productsService,
  type ProductState,
} from "@/features/products/service";
import { adminService } from "./service";
import {
  EnvironmentSwitch,
  InstallButton,
  InstallStatus,
} from "./product-shared";

export function ProductDetailPage({ productKey }: { productKey: string }) {
  return (
    <RequirePermission
      permission="admin.products.manage"
      area="platform products"
    >
      <ProductDetailContent productKey={productKey} />
    </RequirePermission>
  );
}

function ProductDetailContent({ productKey }: { productKey: string }) {
  const products = useScopedQuery(["products"], () => productsService.list());
  const product = products.data?.find((p) => p.key === productKey);
  if (products.isPending) return <PageSkeleton variant="detail" />;
  if (products.isError) {
    return (
      <PageShell width="default">
        <ErrorState
          error={products.error}
          onRetry={() => void products.refetch()}
        />
      </PageShell>
    );
  }
  if (!product) {
    return (
      <PageShell width="default">
        <EmptyState
          icon={SearchX}
          title="Product not found"
          description="No product with this key is registered on the platform."
          action={
            <Button variant="secondary" asChild>
              <Link href="/settings/products">Back to products</Link>
            </Button>
          }
        />
      </PageShell>
    );
  }
  return <ProductDetail product={product} />;
}

function ProductDetail({ product: p }: { product: ProductState }) {
  const { can, session } = useSession();
  useBreadcrumbs([{ label: p.name }], {
    href: `/settings/products/${p.key}`,
    kind: "Product",
  });
  const permissions = useScopedQuery(["admin", "permissions"], () =>
    adminService.permissions(),
  );
  const productPermissions = permissions.data?.filter(
    (perm) =>
      perm.group.toLowerCase() === p.key.toLowerCase() || perm.group === p.name,
  );
  const installed = p.tenant_status === "installed";
  const readPermission = `${p.key}.read`;
  const inNav = installed && p.environment_enabled && can(readPermission);
  const navChecks = [
    { label: "Installed in this workspace", ok: installed },
    {
      label: `Enabled in ${session?.environment?.name ?? "this environment"}`,
      ok: p.environment_enabled,
    },
    { label: `Your role includes ${readPermission}`, ok: can(readPermission) },
  ];

  return (
    <PageShell width="default">
      <RecordHeader
        icon={Blocks}
        title={p.name}
        subtitle={p.description}
        status={<InstallStatus product={p} />}
        identifier={p.key}
        actions={
          <>
            <InstallButton product={p} />
            {installed && (
              <>
                <Button variant="secondary" size="sm" asChild>
                  <Link href={`/${p.key}`}>
                    Open workspace <ArrowUpRight />
                  </Link>
                </Button>
                <Button variant="secondary" size="sm" asChild>
                  <Link href={`/${p.key}/settings`}>
                    <Settings2 /> Settings
                  </Link>
                </Button>
              </>
            )}
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Features"
              description="Capabilities this product provides. Highlighted features are active in this environment."
            />
            <CardBody>
              <ul className="grid gap-2 sm:grid-cols-2">
                {p.features.map((f) => {
                  const on = p.enabled_features.includes(f);
                  return (
                    <li
                      key={f}
                      className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-[13px]"
                    >
                      {on ? (
                        <Check
                          className="size-4 text-success"
                          aria-hidden="true"
                        />
                      ) : (
                        <Minus
                          className="size-4 text-muted-foreground"
                          aria-hidden="true"
                        />
                      )}
                      <span
                        className={cn(
                          "flex-1 font-medium",
                          !on && "text-muted-foreground",
                        )}
                      >
                        {humanize(f)}
                      </span>
                      <span className="sr-only">
                        {on ? "Active" : "Inactive"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Permissions"
              description={`Grant these to roles in Roles & permissions to give members access to ${p.name}.`}
              actions={
                <Link
                  href="/settings/roles?tab=matrix"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Permission matrix
                </Link>
              }
            />
            <CardBody>
              {permissions.isPending ? (
                <Skeleton className="h-32" />
              ) : permissions.isError ? (
                <ErrorState
                  compact
                  error={permissions.error}
                  onRetry={() => void permissions.refetch()}
                />
              ) : !productPermissions?.length ? (
                <p className="text-[13px] text-muted-foreground">
                  This product doesn&apos;t register its own permissions.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {productPermissions.map((perm) => (
                    <li
                      key={perm.key}
                      className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <span className="text-[13px] font-medium">
                        {perm.label}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">
                        {perm.key}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Installation" />
            <CardBody>
              <PropertyList
                items={[
                  { label: "Status", value: <InstallStatus product={p} /> },
                  {
                    label: "Category",
                    value: p.category === "ai" ? "AI" : humanize(p.category),
                  },
                  {
                    label: "Installed",
                    value: p.installed_at ? formatDate(p.installed_at) : null,
                  },
                  { label: "Workspace", value: session?.tenant?.name ?? null },
                ]}
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Environment" />
            <CardBody>
              <EnvironmentSwitch
                product={p}
                id={`product-detail-enabled-${p.key}`}
              />
            </CardBody>
          </Card>
          <Card>
            <CardHeader
              title="Navigation"
              icon={<PanelLeft />}
              actions={
                <Badge tone={inNav ? "success" : "neutral"} dot>
                  {inNav ? "In your sidebar" : "Not in your sidebar"}
                </Badge>
              }
            />
            <CardBody>
              <p className="mb-2 text-xs text-muted-foreground">
                {p.name} appears in the sidebar when all of these are true:
              </p>
              <ul className="space-y-1.5 text-[13px]">
                {navChecks.map((c) => (
                  <li key={c.label} className="flex items-center gap-2">
                    {c.ok ? (
                      <Check
                        className="size-4 text-success"
                        aria-hidden="true"
                      />
                    ) : (
                      <Minus
                        className="size-4 text-muted-foreground"
                        aria-hidden="true"
                      />
                    )}
                    <span className={cn(!c.ok && "text-muted-foreground")}>
                      {c.label}
                    </span>
                    <span className="sr-only">{c.ok ? "(yes)" : "(no)"}</span>
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}
