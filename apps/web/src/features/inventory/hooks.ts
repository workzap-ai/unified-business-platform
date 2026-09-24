"use client";

import { useMemo } from "react";
import { useScopedQuery } from "@/hooks/use-scoped";
import { useSession } from "@/features/auth/session-provider";
import { inventoryService } from "./service";
import { fetchAllLevels, sortLocations, stockByProduct, variantIndex } from "./lib";

/** Query-key prefixes owned by the inventory module. */
export const INVENTORY_KEY = ["inventory"] as const;
export const LOCATIONS_KEY = ["inventory", "locations"] as const;
export const ALL_LEVELS_KEY = ["inventory", "levels", "all"] as const;

/** Keys to invalidate after any stock change (levels, ledger, reports, overview badges). */
export const STOCK_CHANGED: unknown[][] = [["inventory"], ["reports"], ["overview"]];

export function useAllLevels(enabled = true) {
  const { can } = useSession();
  return useScopedQuery([...ALL_LEVELS_KEY], fetchAllLevels, {
    enabled: enabled && can("inventory.read"),
    staleTime: 30_000,
  });
}

export function useProductStock(enabled = true) {
  const levels = useAllLevels(enabled);
  const map = useMemo(() => (levels.data ? stockByProduct(levels.data.items) : undefined), [levels.data]);
  return { ...levels, map };
}

export function useVariantIndex(enabled = true) {
  const levels = useAllLevels(enabled);
  const map = useMemo(() => (levels.data ? variantIndex(levels.data.items) : undefined), [levels.data]);
  return { ...levels, map };
}

export function useLocations(enabled = true) {
  const { can } = useSession();
  const query = useScopedQuery([...LOCATIONS_KEY], () => inventoryService.locations(), {
    enabled: enabled && can("inventory.read"),
    staleTime: 60_000,
  });
  const sorted = useMemo(() => (query.data ? sortLocations(query.data) : undefined), [query.data]);
  return { ...query, sorted };
}
