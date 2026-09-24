/**
 * Document math and rules shared by the quote and order screens. All money arithmetic runs
 * on integer cents (bigint) so previews match the server to the cent; numbers are only used
 * for display-only ratios.
 */
import { addDays, format } from "date-fns";
import { centsToString, daysUntil, formatMoney, toCents } from "@/lib/format";
import type { BusinessSettings, Quote } from "@/features/business/types";

const ZERO = BigInt(0);

/** Parse a non-negative decimal string into an integer scaled by 10^scale (extra digits truncated). */
export function toScaled(
  value: string | number | null | undefined,
  scale: number,
): bigint {
  if (value === null || value === undefined || value === "") return ZERO;
  const text = String(value).trim();
  if (!/^-?\d*(\.\d*)?$/.test(text)) return ZERO;
  const negative = text.startsWith("-");
  const [whole = "0", fraction = ""] = text.replace("-", "").split(".");
  const factor = BigInt(10) ** BigInt(scale);
  const scaled =
    BigInt(whole || "0") * factor +
    BigInt((fraction + "0".repeat(scale)).slice(0, scale) || "0");
  return negative ? -scaled : scaled;
}

/** Gross line amount in cents: unit price × quantity (quantity up to 3 decimals, half-up to cents). */
export function lineGrossCents(
  unitPrice: string,
  quantity: string | number,
): bigint {
  const product = toCents(unitPrice) * toScaled(quantity, 3);
  return (product + BigInt(500)) / BigInt(1000);
}

/** Tax in cents on a taxable amount for a rate expressed as a fraction ("0.1600"). */
export function taxCents(taxable: bigint, rate: string): bigint {
  if (taxable <= ZERO) return ZERO;
  return (taxable * toScaled(rate, 4) + BigInt(5000)) / BigInt(10000);
}

export type PricedLine = {
  unit_price: string;
  quantity: string | number;
  discount: string;
};

export type DocumentTotals = {
  subtotal: string;
  discount_total: string;
  taxable: string;
  tax_total: string;
  total: string;
};

export function computeTotals(
  lines: PricedLine[],
  taxRate: string | null | undefined,
): DocumentTotals {
  let subtotal = ZERO;
  let discount = ZERO;
  for (const line of lines) {
    subtotal += lineGrossCents(line.unit_price || "0", line.quantity || "0");
    discount += toCents(line.discount || "0");
  }
  const taxable = subtotal - discount;
  const tax = taxRate ? taxCents(taxable, taxRate) : ZERO;
  return {
    subtotal: centsToString(subtotal),
    discount_total: centsToString(discount),
    taxable: centsToString(taxable),
    tax_total: centsToString(tax),
    total: centsToString(taxable + tax),
  };
}

export function lineTotal(line: PricedLine): string {
  return centsToString(
    lineGrossCents(line.unit_price || "0", line.quantity || "0") -
      toCents(line.discount || "0"),
  );
}

/** "0.1600" → "16%" (display only). */
export function formatRate(rate: string | null | undefined): string {
  if (rate === null || rate === undefined || rate === "") return "—";
  const basis = toScaled(rate, 4); // ten-thousandths
  const whole = basis / BigInt(100);
  const fraction = basis % BigInt(100);
  return fraction === ZERO
    ? `${whole}%`
    : `${whole}.${fraction.toString().padStart(2, "0").replace(/0$/, "")}%`;
}

/**
 * Why a quote needs approval, mirroring the server rules: PI-drafted quotes always need a
 * reviewer; manual quotes need one when the discount rate or total exceed business limits.
 */
export function approvalReasons(
  doc: {
    subtotal: string;
    discount_total: string;
    total: string;
    source: Quote["source"] | "manual";
  },
  settings: BusinessSettings | undefined,
  currency: string,
): string[] {
  const reasons: string[] = [];
  if (doc.source === "pi")
    reasons.push("Drafted by PI — always needs approval");
  if (!settings) return reasons;
  const subtotal = toCents(doc.subtotal);
  const discount = toCents(doc.discount_total);
  if (
    subtotal > ZERO &&
    discount * BigInt(10000) >
      toScaled(settings.max_discount_rate, 4) * subtotal
  ) {
    const pct = ((Number(discount) / Number(subtotal)) * 100)
      .toFixed(1)
      .replace(/\.0$/, "");
    reasons.push(
      `Discount of ${pct}% exceeds the ${formatRate(settings.max_discount_rate)} limit`,
    );
  }
  const threshold = settings.quote_approval_threshold;
  if (threshold !== null && toCents(doc.total) > toCents(threshold)) {
    reasons.push(
      `Total is above the ${formatMoney(threshold, currency)} approval threshold`,
    );
  }
  return reasons;
}

export function dateFromToday(days: number): string {
  return format(addDays(new Date(), days), "yyyy-MM-dd");
}

export const OPEN_QUOTE_STATUSES: Quote["status"][] = [
  "draft",
  "pending_approval",
  "approved",
  "sent",
];

/** Validity warning for open quotes: "expired" once passed, "soon" within 3 days. */
export function validityState(
  quote: Pick<Quote, "valid_until" | "status">,
): "expired" | "soon" | null {
  if (!OPEN_QUOTE_STATUSES.includes(quote.status)) return null;
  const days = daysUntil(quote.valid_until);
  if (days === null) return null;
  if (days < 0) return "expired";
  if (days <= 3) return "soon";
  return null;
}

export const MONEY_PATTERN = /^\d{1,12}(\.\d{1,2})?$/;
export const QUANTITY_PATTERN = /^\d{1,11}(\.\d{1,3})?$/;
export const INTEGER_PATTERN = /^\d{1,6}$/;

export function newKey() {
  return `l-${Math.random().toString(36).slice(2, 10)}`;
}
