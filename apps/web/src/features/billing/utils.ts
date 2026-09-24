import { differenceInCalendarDays, format, isValid, parseISO } from "date-fns";
import { formatDate } from "@/lib/format";
import type { Invoice, Payment } from "@/features/business/types";

/** Local calendar date as YYYY-MM-DD (the API's date-only format). */
export function todayISO() {
  return format(new Date(), "yyyy-MM-dd");
}

/** Parses date-only strings as local dates so they never shift a day across time zones. */
export function parseDay(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = parseISO(value);
  return isValid(date) ? date : null;
}

export function formatDay(value: string | null | undefined, pattern?: string) {
  return formatDate(parseDay(value), pattern);
}

/** Calendar days from today to the date: negative when the date is in the past. */
export function daysFromToday(value: string | null | undefined): number | null {
  const date = parseDay(value);
  return date ? differenceInCalendarDays(date, new Date()) : null;
}

export function dayCount(days: number) {
  return `${days} ${days === 1 ? "day" : "days"}`;
}

export const OPEN_STATUSES: Invoice["status"][] = ["issued", "partially_paid"];

/** Due-date hint for open invoices: "3 days overdue", "Due today", "Due in 5 days". */
export function dueHint(
  invoice: Pick<Invoice, "status" | "due_date">,
): { text: string; tone: "danger" | "warning" | "muted" } | null {
  if (!OPEN_STATUSES.includes(invoice.status)) return null;
  const days = daysFromToday(invoice.due_date);
  if (days === null) return null;
  if (days < 0) return { text: `${dayCount(-days)} overdue`, tone: "danger" };
  if (days === 0) return { text: "Due today", tone: "warning" };
  return { text: `Due in ${dayCount(days)}`, tone: days <= 3 ? "warning" : "muted" };
}

export const PAYMENT_METHODS: { value: Payment["method"]; label: string }[] = [
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "mobile_wallet", label: "Mobile wallet" },
  { value: "other", label: "Other" },
];

export function methodLabel(method: string) {
  return PAYMENT_METHODS.find((m) => m.value === method)?.label ?? method;
}

/* Decimal math -------------------------------------------------------------------------- */

/** Up to 2 decimals, no sign. */
export const MONEY_PATTERN = /^\d{1,12}(\.\d{1,2})?$/;
/** Up to 3 decimals, no sign. */
export const QUANTITY_PATTERN = /^\d{1,9}(\.\d{1,3})?$/;

/** Parses a non-negative decimal string into an integer scaled by 10^digits (no floats). */
export function scaled(value: string | null | undefined, digits: number): bigint {
  const text = (value ?? "").trim();
  if (!/^-?\d*(\.\d*)?$/.test(text) || text === "" || text === "." || text === "-") return BigInt(0);
  const negative = text.startsWith("-");
  const [whole = "0", fraction = ""] = text.replace("-", "").split(".");
  const factor = BigInt(10) ** BigInt(digits);
  const result =
    BigInt(whole || "0") * factor + BigInt((fraction + "0".repeat(digits)).slice(0, digits) || "0");
  return negative ? -result : result;
}

/** unit price (cents) × quantity (3 decimals), rounded half up to cents. */
export function lineGrossCents(unitPrice: string, quantity: string): bigint {
  const cents = scaled(unitPrice, 2);
  const qty = scaled(quantity, 3);
  return (cents * qty + BigInt(500)) / BigInt(1000);
}

/** amount (cents) × rate (e.g. "0.1600"), rounded half up to cents. */
export function taxCents(amountCents: bigint, rate: string): bigint {
  const bp = scaled(rate, 4);
  if (amountCents <= BigInt(0) || bp <= BigInt(0)) return BigInt(0);
  return (amountCents * bp + BigInt(5000)) / BigInt(10000);
}

/** "0.1600" → "16%" for display. */
export function formatRate(rate: string) {
  const bp = scaled(rate, 4);
  const whole = bp / BigInt(100);
  const rest = bp % BigInt(100);
  return rest === BigInt(0) ? `${whole}%` : `${whole}.${rest.toString().padStart(2, "0").replace(/0$/, "")}%`;
}
