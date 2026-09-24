"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, FolderTree, Plus } from "lucide-react";
import { pluralize } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/display";
import {
  PageHeader,
  PageShell,
  ModuleNav,
  RequirePermission,
} from "@/components/app/page";
import { EmptyState, ErrorState } from "@/components/app/states";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import type { Category } from "@/features/business/types";
import { catalogService } from "./service";
import { useCategories } from "./hooks";
import { CategoryDialog } from "./category-dialog";

export function CategoriesPage() {
  return (
    <RequirePermission permission="catalog.read" area="the catalog">
      <CategoriesInner />
    </RequirePermission>
  );
}

function CategoriesInner() {
  const { can } = useSession();
  const canWrite = can("catalog.write");
  const categories = useCategories();
  const [open, setOpen] = useState(false);
  const list = [...(categories.data ?? [])].sort((a, b) =>
    a.name.localeCompare(b.name),
  );

  return (
    <PageShell>
      <PageHeader
        title="Categories"
        description="Group products for browsing, reporting and PI's product answers."
        actions={
          canWrite ? (
            <Button onClick={() => setOpen(true)}>
              <Plus /> New category
            </Button>
          ) : undefined
        }
      />
      <ModuleNav moduleKey="catalog" />
      {categories.isError ? (
        <div className="rounded-xl border border-border bg-surface">
          <ErrorState
            error={categories.error}
            onRetry={() => void categories.refetch()}
          />
        </div>
      ) : categories.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-[108px] rounded-xl" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <div className="rounded-xl border border-border bg-surface shadow-sm">
          <EmptyState
            icon={FolderTree}
            title="No categories yet"
            description="Categories like “Chairs” or “Accessories” keep a growing catalog easy to browse."
            action={
              canWrite ? (
                <Button size="sm" onClick={() => setOpen(true)}>
                  <Plus /> New category
                </Button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((c) => (
            <li key={c.id}>
              <CategoryCard category={c} />
            </li>
          ))}
        </ul>
      )}
      <CategoryDialog open={open} onOpenChange={setOpen} />
    </PageShell>
  );
}

function CategoryCard({ category }: { category: Category }) {
  const count = useScopedQuery(
    ["catalog", "products", { categoryId: category.id, pageSize: 1 }],
    () => catalogService.products({ categoryId: category.id, pageSize: 1 }),
  );
  return (
    <Link
      href={`/catalog/products?category=${category.id}`}
      className="group flex h-full flex-col rounded-xl border border-border bg-surface p-4 shadow-sm transition-colors hover:border-border-strong focus-visible:outline-2 focus-visible:outline-ring"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-muted-foreground">
          <FolderTree className="size-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-semibold">{category.name}</p>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {category.slug}
          </p>
        </div>
        <ArrowRight
          className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
          aria-hidden="true"
        />
      </div>
      <p className="mt-2 line-clamp-2 min-h-[2lh] text-[13px] text-muted-foreground">
        {category.description || "No description."}
      </p>
      <div className="mt-2 text-xs font-medium">
        {count.isPending ? (
          <Skeleton className="h-4 w-20" />
        ) : count.isError ? (
          <span className="text-muted-foreground">Count unavailable</span>
        ) : (
          <span className="tabular">
            {pluralize(count.data.total, "product")}
          </span>
        )}
      </div>
    </Link>
  );
}
