import type { Customer, CustomerActivity } from "@/features/business/types";
import type { TimelineEvent } from "@/components/app/record";

export const CUSTOMER_SOURCE_LABELS: Record<Customer["source"], string> = {
  manual: "Manual",
  whatsapp: "WhatsApp",
  import: "Import",
};

export const CUSTOMER_STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
];

/** Maps backend activity kinds (e.g. "order.created", "note") to timeline icon kinds. */
export function timelineKind(kind: string): string {
  const k = kind.toLowerCase();
  const known = [
    "note",
    "order",
    "quote",
    "invoice",
    "payment",
    "conversation",
    "handoff",
    "lead",
    "status",
    "created",
    "updated",
  ];
  const direct = known.find(
    (name) =>
      k === name || k.startsWith(`${name}.`) || k.startsWith(`${name}_`),
  );
  if (direct) return direct;
  if (k.includes("message") || k.includes("whatsapp")) return "conversation";
  if (k.includes("archiv") || k.includes("restor")) return "status";
  return known.find((name) => k.includes(name)) ?? "system";
}

export function refHref(
  refType: string | null,
  refId: string | null,
): string | undefined {
  if (!refType || !refId) return undefined;
  switch (refType) {
    case "order":
      return `/orders/${refId}`;
    case "quote":
      return `/quotes/${refId}`;
    case "invoice":
      return `/billing/invoices/${refId}`;
    case "lead":
      return `/sales/leads/${refId}`;
    case "conversation":
      return `/pi/inbox?conversation=${encodeURIComponent(refId)}`;
    default:
      return undefined;
  }
}

export function activityToEvent(activity: CustomerActivity): TimelineEvent {
  return {
    id: activity.id,
    kind: timelineKind(activity.kind),
    title: activity.summary,
    actor: activity.actor_label,
    at: activity.created_at,
    href: refHref(activity.ref_type, activity.ref_id),
  };
}

function csvCell(value: string | null | undefined): string {
  const text = value ?? "";
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Client-side CSV of the given rows (current page selection). */
export function downloadCustomersCsv(
  rows: Customer[],
  filename = "customers.csv",
) {
  const header = [
    "Name",
    "Email",
    "Phone",
    "Company",
    "Status",
    "Source",
    "Tags",
    "Last contacted",
    "Created",
  ];
  const lines = rows.map((c) =>
    [
      c.name,
      c.email,
      c.phone,
      c.company,
      c.status,
      c.source,
      c.tags.join("; "),
      c.last_contacted_at,
      c.created_at,
    ]
      .map(csvCell)
      .join(","),
  );
  const blob = new Blob([[header.join(","), ...lines].join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Normalizes a phone entry to compact international form (+923001234567). */
export function normalizePhone(value: string): string {
  return value.replace(/[\s().-]/g, "");
}
