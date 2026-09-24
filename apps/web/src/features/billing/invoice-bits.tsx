import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/app/status-badge";
import type { Invoice } from "@/features/business/types";
import { dueHint, formatDay } from "./utils";

/** Lifecycle status plus a danger "Overdue" chip when an open invoice is past due. */
export function InvoiceStatus({
  invoice,
  className,
}: {
  invoice: Pick<Invoice, "status" | "is_overdue">;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      <StatusBadge status={invoice.status} />
      {invoice.is_overdue && <StatusBadge status="overdue" />}
    </span>
  );
}

export function DueDate({ invoice }: { invoice: Pick<Invoice, "status" | "due_date"> }) {
  const hint = dueHint(invoice);
  return (
    <div className="leading-tight">
      <span className="tabular">{formatDay(invoice.due_date)}</span>
      {hint && (
        <span
          className={cn(
            "block text-xs",
            hint.tone === "danger"
              ? "font-medium text-danger"
              : hint.tone === "warning"
                ? "text-warning"
                : "text-muted-foreground",
          )}
        >
          {hint.text}
        </span>
      )}
    </div>
  );
}
