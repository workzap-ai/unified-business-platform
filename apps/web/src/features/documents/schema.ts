import { z } from "zod";
import { toCents } from "@/lib/format";
import type { OrderLineInput, QuoteLineInput } from "@/features/business/types";
import { INTEGER_PATTERN, lineGrossCents, MONEY_PATTERN, newKey, QUANTITY_PATTERN } from "./lib";

export type LinesMode = "quote" | "order";

/** A line being edited. Catalog lines carry a variant and a locked catalog price. */
export type DraftLine = {
  key: string;
  variant_id: string | null;
  sku: string | null;
  description: string;
  unit_price: string;
  quantity: string;
  discount: string;
  /** null = unknown (e.g. loaded from an existing document). */
  track_inventory: boolean | null;
};

export function draftLineSchema(mode: LinesMode) {
  return z
    .object({
      key: z.string(),
      variant_id: z.string().nullable(),
      sku: z.string().nullable(),
      description: z.string(),
      unit_price: z.string(),
      quantity: z.string(),
      discount: z.string(),
      track_inventory: z.boolean().nullable(),
    })
    .superRefine((line, ctx) => {
      const custom = line.variant_id === null;
      if (custom && mode === "order") {
        ctx.addIssue({ code: "custom", path: ["description"], message: "Orders only accept catalog items" });
      }
      if (custom && !line.description.trim()) {
        ctx.addIssue({ code: "custom", path: ["description"], message: "Describe the service" });
      } else if (line.description.trim().length > 300) {
        ctx.addIssue({ code: "custom", path: ["description"], message: "Keep it under 300 characters" });
      }
      if (custom && !MONEY_PATTERN.test(line.unit_price.trim())) {
        ctx.addIssue({ code: "custom", path: ["unit_price"], message: "Enter a price like 1500.00" });
      }
      const qty = line.quantity.trim();
      if (mode === "order") {
        if (!INTEGER_PATTERN.test(qty) || Number(qty) < 1 || Number(qty) > 100_000) {
          ctx.addIssue({ code: "custom", path: ["quantity"], message: "Whole units, 1–100,000" });
        }
      } else if (!QUANTITY_PATTERN.test(qty) || Number(qty) <= 0) {
        ctx.addIssue({ code: "custom", path: ["quantity"], message: "More than 0, up to 3 decimals" });
      }
      const discount = line.discount.trim() || "0";
      if (!MONEY_PATTERN.test(discount)) {
        ctx.addIssue({ code: "custom", path: ["discount"], message: "Enter an amount like 250.00" });
      } else if (MONEY_PATTERN.test(line.unit_price.trim()) && toCents(discount) > lineGrossCents(line.unit_price, qty || "0")) {
        ctx.addIssue({ code: "custom", path: ["discount"], message: "Discount exceeds the line amount" });
      }
    });
}

export function linesSchema(mode: LinesMode) {
  return z
    .array(draftLineSchema(mode))
    .min(1, "Add at least one item")
    .max(100, "A document can have up to 100 lines");
}

export function toQuoteLineInputs(lines: DraftLine[]): QuoteLineInput[] {
  return lines.map((line) =>
    line.variant_id
      ? { variant_id: line.variant_id, quantity: line.quantity.trim(), discount: line.discount.trim() || "0" }
      : {
          variant_id: null,
          description: line.description.trim(),
          unit_price: line.unit_price.trim(),
          quantity: line.quantity.trim(),
          discount: line.discount.trim() || "0",
        },
  );
}

export function toOrderLineInputs(lines: DraftLine[]): OrderLineInput[] {
  return lines
    .filter((line): line is DraftLine & { variant_id: string } => line.variant_id !== null)
    .map((line) => ({ variant_id: line.variant_id, quantity: Number(line.quantity.trim()), discount: line.discount.trim() || "0" }));
}

type ExistingLine = {
  variant_id: string | null;
  description: string;
  unit_price: string;
  quantity: string | number;
  discount: string;
  sku?: string | null;
};

export function fromDocumentLines(lines: ExistingLine[]): DraftLine[] {
  return lines.map((line) => ({
    key: newKey(),
    variant_id: line.variant_id,
    sku: line.sku ?? null,
    description: line.description,
    unit_price: line.unit_price,
    quantity: normalizeQuantity(String(line.quantity)),
    discount: line.discount,
    track_inventory: null,
  }));
}

/** "2.000" → "2", "1.500" → "1.5". */
function normalizeQuantity(value: string) {
  if (!value.includes(".")) return value;
  return value.replace(/0+$/, "").replace(/\.$/, "");
}
