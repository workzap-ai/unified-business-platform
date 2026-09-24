"use client";

import { cn } from "@/lib/utils";
import { formatNumber } from "@/lib/format";
import { Badge } from "@/components/ui/display";
import { Progress } from "@/components/ui/controls";
import { StatusBadge } from "@/components/app/status-badge";
import { STOCK_STATE_LABEL, type StockState } from "./lib";

/** Stock health chip. "untracked" reads as a quiet outline so it never looks like a problem. */
export function StockChip({
  state,
  label,
}: {
  state: StockState | "untracked";
  label?: string;
}) {
  if (state === "untracked")
    return (
      <Badge tone="outline" className="text-muted-foreground">
        {label ?? "Not tracked"}
      </Badge>
    );
  return (
    <StatusBadge status={state} label={label ?? STOCK_STATE_LABEL[state]} />
  );
}

/**
 * Available quantity with a small bar scaled against twice the low-stock threshold, so
 * the threshold sits at the bar's midpoint.
 */
export function AvailableBar({
  available,
  threshold,
  state,
  className,
}: {
  available: number;
  threshold: number | null;
  state: StockState;
  className?: string;
}) {
  const scale = Math.max((threshold ?? 0) * 2, 1);
  const value = Math.max(0, Math.min(100, (available / scale) * 100));
  const tone =
    state === "out" ? "danger" : state === "low" ? "warning" : "success";
  return (
    <div className={cn("flex items-center justify-end gap-2", className)}>
      <Progress
        value={value}
        tone={tone}
        className="hidden w-14 sm:block"
        aria-label={`${formatNumber(available)} available${threshold !== null ? `, threshold ${threshold}` : ""}`}
      />
      <span
        className={cn(
          "tabular min-w-8 text-right font-medium",
          state === "out" && "text-danger",
          state === "low" && "text-warning",
        )}
      >
        {formatNumber(available)}
      </span>
    </div>
  );
}

export function Quantity({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "tabular font-semibold",
        value > 0 ? "text-success" : value < 0 ? "text-danger" : "",
        className,
      )}
    >
      {value > 0 ? "+" : value < 0 ? "−" : ""}
      {formatNumber(Math.abs(value))}
    </span>
  );
}
