import type { Location, Movement, StockLevel } from "@/features/business/types";
import { inventoryService } from "./service";

/** Stock health for one level row (variant x location). */
export type StockState = "healthy" | "low" | "out";

export function stockState(
  level: Pick<StockLevel, "available" | "is_low">,
): StockState {
  if (level.available <= 0) return "out";
  if (level.is_low) return "low";
  return "healthy";
}

export const STOCK_STATE_LABEL: Record<StockState, string> = {
  healthy: "Healthy",
  low: "Low stock",
  out: "Out of stock",
};

const PAGE = 100;
const MAX_PAGES = 10;

export type AllLevels = {
  items: StockLevel[];
  total: number;
  truncated: boolean;
};

/**
 * Every stock level row, fetched in pages of 100 (the API maximum). Used to derive
 * per-product stock, variant names for the movement ledger and inventory metrics.
 * Capped so a very large catalog degrades to a partial (flagged) picture.
 */
export async function fetchAllLevels(): Promise<AllLevels> {
  const first = await inventoryService.levels({ page: 1, pageSize: PAGE });
  const items = [...first.items];
  const pages = Math.min(Math.ceil(first.total / PAGE), MAX_PAGES);
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, i) =>
        inventoryService.levels({ page: i + 2, pageSize: PAGE }),
      ),
    );
    for (const page of rest) items.push(...page.items);
  }
  return { items, total: first.total, truncated: first.total > items.length };
}

export type VariantInfo = {
  variant_id: string;
  product_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
};

export function variantIndex(levels: StockLevel[]): Map<string, VariantInfo> {
  const map = new Map<string, VariantInfo>();
  for (const l of levels) {
    if (!map.has(l.variant_id)) {
      map.set(l.variant_id, {
        variant_id: l.variant_id,
        product_id: l.product_id,
        product_name: l.product_name,
        variant_name: l.variant_name,
        sku: l.sku,
      });
    }
  }
  return map;
}

export type ProductStock = {
  available: number;
  onHand: number;
  state: StockState;
  lines: number;
};

/** Sum available stock per product across variants and locations. */
export function stockByProduct(
  levels: StockLevel[],
): Map<string, ProductStock> {
  const map = new Map<string, ProductStock>();
  for (const l of levels) {
    const current = map.get(l.product_id) ?? {
      available: 0,
      onHand: 0,
      state: "healthy" as StockState,
      lines: 0,
    };
    current.available += l.available;
    current.onHand += l.on_hand;
    current.lines += 1;
    if (l.is_low && current.state === "healthy") current.state = "low";
    map.set(l.product_id, current);
  }
  for (const value of map.values())
    if (value.available <= 0) value.state = "out";
  return map;
}

/** Distinct variants matching a predicate (levels are per variant x location). */
export function distinctVariants(
  levels: StockLevel[],
  predicate: (l: StockLevel) => boolean = () => true,
) {
  return new Set(levels.filter(predicate).map((l) => l.variant_id)).size;
}

export type BadgeTone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "pi"
  | "outline";

export const MOVEMENT_KINDS: Record<
  Movement["kind"],
  { label: string; tone: BadgeTone }
> = {
  receipt: { label: "Receipt", tone: "success" },
  return: { label: "Return", tone: "info" },
  sale: { label: "Sale", tone: "primary" },
  adjustment: { label: "Adjustment", tone: "warning" },
  transfer_in: { label: "Transfer in", tone: "neutral" },
  transfer_out: { label: "Transfer out", tone: "neutral" },
};

export function sortLocations(list: Location[]): Location[] {
  return [...list].sort(
    (a, b) =>
      Number(b.is_default) - Number(a.is_default) ||
      a.name.localeCompare(b.name),
  );
}

export function signed(quantity: number) {
  return quantity > 0
    ? `+${quantity.toLocaleString("en-US")}`
    : quantity.toLocaleString("en-US");
}

export function shortId(id: string) {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

/** Link for a movement's source document when it points at something we can open. */
export function movementReferenceHref(
  m: Pick<Movement, "ref_type" | "ref_id">,
): string | null {
  if (!m.ref_id || !m.ref_type) return null;
  if (m.ref_type === "order") return `/orders/${m.ref_id}`;
  if (m.ref_type === "invoice") return `/billing/invoices/${m.ref_id}`;
  return null;
}
