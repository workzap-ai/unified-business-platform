"use client";

import { useScopedQuery } from "@/hooks/use-scoped";
import { adminService } from "@/features/admin/service";
import { documentsService } from "./service";

/** Business settings drive tax previews, validity defaults and approval rules. */
export function useBusinessSettings() {
  return useScopedQuery(
    ["settings", "business"],
    () => adminService.businessSettings(),
    {
      staleTime: 60_000,
    },
  );
}

export function useQuote(id: string) {
  return useScopedQuery(["quotes", "detail", id], () =>
    documentsService.quote(id),
  );
}

export function useOrder(id: string) {
  return useScopedQuery(["orders", "detail", id], () =>
    documentsService.order(id),
  );
}
