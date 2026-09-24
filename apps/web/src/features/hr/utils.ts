import type { Employee } from "@/features/business/types";

export const EMPLOYMENT_TYPES: {
  value: Employee["employment_type"];
  label: string;
}[] = [
  { value: "full_time", label: "Full-time" },
  { value: "part_time", label: "Part-time" },
  { value: "contract", label: "Contract" },
  { value: "intern", label: "Intern" },
];

export function employmentLabel(type: string) {
  return EMPLOYMENT_TYPES.find((t) => t.value === type)?.label ?? type;
}

export const EMPLOYEE_STATUSES: { value: Employee["status"]; label: string }[] =
  [
    { value: "active", label: "Active" },
    { value: "on_leave", label: "On leave" },
    { value: "terminated", label: "Terminated" },
  ];

/** Page size used when the UI needs the whole roster (manager names, headcounts). */
export const ROSTER_PAGE_SIZE = 100;

export const CURRENCIES = [
  "USD",
  "EUR",
  "GBP",
  "PKR",
  "AED",
  "SAR",
  "INR",
  "CAD",
  "AUD",
];
