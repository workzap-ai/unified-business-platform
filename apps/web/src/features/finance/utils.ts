import { format, subDays } from "date-fns";
import { EXPENSE_CATEGORIES, type Expense } from "@/features/business/types";

export const AGING_BUCKETS = [
  "current",
  "1-30",
  "31-60",
  "61-90",
  "90+",
] as const;

export const AGING_LABELS: Record<string, string> = {
  current: "Not yet due",
  "1-30": "1–30 days",
  "31-60": "31–60 days",
  "61-90": "61–90 days",
  "90+": "90+ days",
};

export const CATEGORY_LABELS: Record<Expense["category"], string> = {
  rent: "Rent",
  payroll: "Payroll",
  utilities: "Utilities",
  inventory: "Inventory",
  marketing: "Marketing",
  software: "Software",
  travel: "Travel",
  taxes: "Taxes",
  professional_services: "Professional services",
  other: "Other",
};

export const CATEGORY_OPTIONS = EXPENSE_CATEGORIES.map((value) => ({
  value,
  label: CATEGORY_LABELS[value],
}));

export function categoryLabel(category: string) {
  return CATEGORY_LABELS[category as Expense["category"]] ?? category;
}

export const PERIODS = [
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "365", label: "12 months" },
] as const;

/** Inclusive period ending today, as YYYY-MM-DD strings. */
export function periodRange(days: number) {
  const now = new Date();
  return {
    start: format(subDays(now, days - 1), "yyyy-MM-dd"),
    end: format(now, "yyyy-MM-dd"),
  };
}
