"use client";

import { cn } from "@/lib/utils";
import { formatMoney, toCents } from "@/lib/format";
import { Skeleton } from "@/components/ui/display";
import { computeTotals, formatRate, type PricedLine } from "./lib";

type Totals = {
  subtotal: string;
  discount_total: string;
  tax_total: string;
  total: string;
};

/**
 * Subtotal → discounts → tax → total. Pass `lines` for a live preview computed in integer
 * cents, or `totals` to show the amounts the server stored on a document.
 */
export function TotalsPanel({
  lines,
  totals,
  taxRate,
  currency,
  loading = false,
  preview = false,
  className,
}: {
  lines?: PricedLine[];
  totals?: Totals;
  taxRate: string | null | undefined;
  currency: string;
  loading?: boolean;
  preview?: boolean;
  className?: string;
}) {
  if (loading) {
    return (
      <div className={cn("space-y-2", className)}>
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-4" />
        ))}
      </div>
    );
  }
  const values: Totals = totals ?? computeTotals(lines ?? [], taxRate);
  const hasDiscount = toCents(values.discount_total) > BigInt(0);
  return (
    <div className={className}>
      <dl className="space-y-1.5 text-[13px]">
        <Row label="Subtotal" value={formatMoney(values.subtotal, currency)} />
        {hasDiscount && (
          <Row
            label="Discounts"
            value={`−${formatMoney(values.discount_total, currency)}`}
          />
        )}
        <Row
          label={taxRate ? `Tax (${formatRate(taxRate)})` : "Tax"}
          value={
            taxRate
              ? formatMoney(values.tax_total, currency)
              : "Calculated on save"
          }
          muted={!taxRate}
        />
        <div className="mt-2 flex items-baseline justify-between gap-4 border-t border-border pt-2.5">
          <dt className="text-sm font-semibold">
            {taxRate || totals ? "Total" : "Total before tax"}
          </dt>
          <dd className="tabular text-lg font-semibold tracking-tight">
            {formatMoney(values.total, currency)}
          </dd>
        </div>
      </dl>
      {preview && (
        <p className="mt-2 text-2xs text-muted-foreground">
          Preview. Final amounts are priced by the server when you save.
        </p>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  muted = false,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "tabular font-medium",
          muted && "text-xs font-normal text-muted-foreground",
        )}
      >
        {value}
      </dd>
    </div>
  );
}
