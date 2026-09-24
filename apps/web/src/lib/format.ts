import { differenceInCalendarDays, format, formatDistanceToNowStrict, isValid } from "date-fns";

/**
 * Money arrives from the API as decimal strings (PostgreSQL NUMERIC / Python Decimal).
 * Display formatting converts to Number only for rendering. Arithmetic in the UI
 * (previews) goes through integer cents so totals never drift.
 */
export function toCents(value: string | number | null | undefined): bigint {
  if (value === null || value === undefined || value === "") return BigInt(0);
  const text = typeof value === "number" ? value.toFixed(2) : value.trim();
  const negative = text.startsWith("-");
  const [whole = "0", fraction = ""] = text.replace("-", "").split(".");
  const cents = BigInt(whole || "0") * BigInt(100) + BigInt((fraction + "00").slice(0, 2));
  return negative ? -cents : cents;
}

export function centsToString(cents: bigint): string {
  const negative = cents < BigInt(0);
  const abs = negative ? -cents : cents;
  const whole = abs / BigInt(100);
  const fraction = (abs % BigInt(100)).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${whole}.${fraction}`;
}

const moneyFormatters = new Map<string, Intl.NumberFormat>();

export function formatMoney(
  value: string | number | null | undefined,
  currency = "USD",
  options: { compact?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return "—";
  const key = `${currency}:${options.compact ? "c" : "f"}`;
  let formatter = moneyFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      notation: options.compact ? "compact" : "standard",
      maximumFractionDigits: options.compact ? 1 : 2,
      minimumFractionDigits: options.compact ? 0 : 2,
    });
    moneyFormatters.set(key, formatter);
  }
  return formatter.format(Number(value));
}

export function formatNumber(value: number | string | null | undefined, compact = false) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("en-US", {
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 2,
  }).format(Number(value));
}

export function formatPercent(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function parse(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return isValid(date) ? date : null;
}

export function formatDate(value: string | Date | null | undefined, pattern = "d MMM yyyy") {
  const date = parse(value);
  return date ? format(date, pattern) : "—";
}

export function formatDateTime(value: string | Date | null | undefined) {
  return formatDate(value, "d MMM yyyy, HH:mm");
}

export function formatTime(value: string | Date | null | undefined) {
  return formatDate(value, "HH:mm");
}

export function relativeTime(value: string | Date | null | undefined) {
  const date = parse(value);
  if (!date) return "—";
  const seconds = (Date.now() - date.getTime()) / 1000;
  if (seconds < 45) return "just now";
  return `${formatDistanceToNowStrict(date)} ago`;
}

export function daysUntil(value: string | Date | null | undefined): number | null {
  const date = parse(value);
  return date ? differenceInCalendarDays(date, new Date()) : null;
}

export function humanize(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}
