"use client";

import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { adminService } from "@/features/admin/service";
import { catalogService } from "./service";
import { fetchAllProducts } from "./lib";

export const CATEGORIES_KEY = ["catalog", "categories"] as const;
/** Anything that changes products also changes stock names and PI's catalog view. */
export const CATALOG_CHANGED: unknown[][] = [["catalog"], ["inventory"]];

export function useCategories(enabled = true) {
  const { can } = useSession();
  return useScopedQuery([...CATEGORIES_KEY], () => catalogService.categories(), {
    enabled: enabled && can("catalog.read"),
    staleTime: 60_000,
  });
}

export function useAllProducts(enabled = true) {
  return useScopedQuery(["catalog", "products", "all"], fetchAllProducts, { enabled, staleTime: 30_000 });
}

export function useProduct(id: string) {
  return useScopedQuery(["catalog", "product", id], () => catalogService.product(id));
}

/** Workspace default currency for new prices; falls back to USD if settings can't be read. */
export function useDefaultCurrency() {
  const settings = useScopedQuery(["settings", "business"], () => adminService.businessSettings(), {
    retry: false,
    staleTime: 5 * 60_000,
  });
  const currency = settings.data?.default_currency ?? (settings.isError ? "USD" : undefined);
  return { currency, settled: !settings.isPending, lowStockThreshold: settings.data?.low_stock_threshold };
}
