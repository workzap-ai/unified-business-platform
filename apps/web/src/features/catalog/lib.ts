import { formatMoney } from "@/lib/format";
import type { ProductListItem } from "@/features/business/types";
import { catalogService } from "./service";

/** Query-key prefix owned by the catalog module (never "products": that's installed products). */
export const CATALOG_KEY = ["catalog"] as const;

/** Mirrors the API: lowercase words separated by single hyphens. */
export const SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
/** Mirrors the API SKU rule. */
export const SKU_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
/** Non-negative decimal with up to two fraction digits. */
export const PRICE_PATTERN = /^\d{1,12}(\.\d{1,2})?$/;
export const CURRENCY_PATTERN = /^[A-Z]{3}$/;

export function slugify(value: string, max = 80) {
  return value
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, max)
    .replace(/-+$/g, "");
}

export function priceRange(
  min: string | null,
  max: string | null,
  currency: string | null | undefined,
) {
  if (min === null && max === null) return "—";
  const cur = currency ?? "USD";
  if (min === null || max === null || min === max)
    return formatMoney(min ?? max, cur);
  return `${formatMoney(min, cur)} – ${formatMoney(max, cur)}`;
}

export type AllProducts = {
  items: ProductListItem[];
  total: number;
  truncated: boolean;
};

const PAGE = 100;
const MAX_PAGES = 10;

/** Every product (list shape), fetched in pages of 100 for overview-level aggregates. */
export async function fetchAllProducts(): Promise<AllProducts> {
  const first = await catalogService.products({ page: 1, pageSize: PAGE });
  const items = [...first.items];
  const pages = Math.min(Math.ceil(first.total / PAGE), MAX_PAGES);
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, i) =>
        catalogService.products({ page: i + 2, pageSize: PAGE }),
      ),
    );
    for (const page of rest) items.push(...page.items);
  }
  return { items, total: first.total, truncated: first.total > items.length };
}

export function attributeEntries(attributes: Record<string, unknown>) {
  return Object.entries(attributes).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );
}

export function formatAttribute(value: unknown) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
